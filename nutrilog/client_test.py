"""Unit tests for nutrilog.client."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx
from google.oauth2.credentials import Credentials

from nutrilog.client import (
    API_BASE_URL,
    MAX_PAGE_SIZE,
    APIPermissionError,
    AuthenticationError,
    GoogleHealthClient,
    ResourceNotFoundError,
)
from nutrilog.models import (
    Energy,
    GramsQuantity,
    MealLog,
    MealType,
    NutrientEntry,
    TimeInterval,
)


@pytest.fixture
def mock_creds():
    creds = MagicMock(spec=Credentials)
    creds.token = "mock-bearer-token"
    creds.valid = True
    creds.expired = False
    return creds


@pytest.fixture
def client(mock_creds):
    return GoogleHealthClient(credentials=mock_creds)


@respx.mock
def test_log_meal_success(client):
    meal = MealLog(
        foodDisplayName="Protein Bowl",
        mealType=MealType.LUNCH,
        interval=TimeInterval(
            startTime="2026-08-17T12:30:00Z",
            endTime="2026-08-17T12:30:00Z",
        ),
        energy=Energy(kcal=500.0),
        totalCarbohydrate=GramsQuantity(grams=40.0),
        totalFat=GramsQuantity(grams=15.0),
        nutrients=[
            NutrientEntry(
                nutrient="PROTEIN", quantity=GramsQuantity(grams=35.0)
            ),
        ],
    )

    response_payload = {
        "id": "dp-abc-123",
        "nutritionLog": meal.to_api_payload()["nutritionLog"],
    }

    respx.post(
        f"{API_BASE_URL}/users/me/dataTypes/nutrition-log/dataPoints"
    ).respond(200, json=response_payload)

    result = client.log_meal(meal)
    assert result.id == "dp-abc-123"
    assert result.foodDisplayName == "Protein Bowl"
    assert result.calories_kcal == 500.0
    assert result.protein_g == 35.0


def test_log_meal_not_authenticated():
    with patch("nutrilog.client.get_credentials", return_value=None):
        unauth_client = GoogleHealthClient(credentials=None)
        with pytest.raises(AuthenticationError, match="Not authenticated"):
            unauth_client.log_meal(
                MealLog(
                    foodDisplayName="Meal",
                    interval=TimeInterval(
                        startTime="2026-08-17T12:00:00Z",
                        endTime="2026-08-17T12:01:00Z",
                    ),
                )
            )


@respx.mock
def test_log_meal_401_error(client):
    respx.post(
        f"{API_BASE_URL}/users/me/dataTypes/nutrition-log/dataPoints"
    ).respond(401, json={"error": {"message": "Invalid credentials"}})
    with pytest.raises(
        AuthenticationError, match="OAuth token is invalid or expired"
    ):
        client.log_meal(
            MealLog(
                foodDisplayName="Meal",
                interval=TimeInterval(
                    startTime="2026-08-17T12:00:00Z",
                    endTime="2026-08-17T12:00:00Z",
                ),
            )
        )


@respx.mock
def test_log_meal_403_error(client):
    respx.post(
        f"{API_BASE_URL}/users/me/dataTypes/nutrition-log/dataPoints"
    ).respond(
        403,
        json={"error": {"message": "Google Health API has not been enabled"}},
    )
    with pytest.raises(APIPermissionError, match="permission denied"):
        client.log_meal(
            MealLog(
                foodDisplayName="Meal",
                interval=TimeInterval(
                    startTime="2026-08-17T12:00:00Z",
                    endTime="2026-08-17T12:00:00Z",
                ),
            )
        )


@respx.mock
def test_get_meal_by_point_id(client):
    payload = {
        "name": ("users/123/dataTypes/nutrition-log/dataPoints/point-123"),
        "nutritionLog": {
            "foodDisplayName": "Pasta",
            "mealType": "DINNER",
            "interval": {
                "startTime": "2026-08-18T19:00:00+10:00",
                "endTime": "2026-08-18T19:01:00+10:00",
            },
            "energy": {"kcal": 700},
            "nutrients": [
                {
                    "nutrient": "SODIUM",
                    "quantity": {
                        "grams": 0.4,
                        "userProvidedUnit": "MILLIGRAM",
                    },
                }
            ],
            "serving": {"amount": 1, "unit": "meal"},
        },
    }
    respx.get(
        f"{API_BASE_URL}/users/me/dataTypes/nutrition-log/dataPoints/point-123"
    ).respond(200, json=payload)

    meal = client.get_meal("point-123")

    assert meal.id == "point-123"
    assert meal.foodDisplayName == "Pasta"
    assert meal.nutrients[0].quantity.userProvidedUnit.value == "MILLIGRAM"
    assert meal.serving is not None
    assert meal.serving.unit == "meal"


@respx.mock
def test_get_meal_not_found(client):
    respx.get(
        f"{API_BASE_URL}/users/me/dataTypes/nutrition-log/dataPoints/missing"
    ).respond(404, json={"error": {"message": "Not found"}})

    with pytest.raises(ResourceNotFoundError, match="not found"):
        client.get_meal("missing")


@respx.mock
def test_list_meals(client):
    sample_points = [
        {
            "id": "point-1",
            "nutritionLog": {
                "foodDisplayName": "Breakfast Oats",
                "mealType": "BREAKFAST",
                "interval": {
                    "startTime": "2026-08-17T08:00:00Z",
                    "endTime": "2026-08-17T08:00:00Z",
                },
                "energy": {"kcal": 350},
                "totalCarbohydrate": {"grams": 50},
                "totalFat": {"grams": 8},
                "nutrients": [
                    {"nutrient": "PROTEIN", "quantity": {"grams": 20}}
                ],
            },
        },
        {
            "id": "point-2",
            "nutritionLog": {
                "foodDisplayName": "Chicken Rice",
                "mealType": "LUNCH",
                "interval": {
                    "startTime": "2026-08-17T12:30:00Z",
                    "endTime": "2026-08-17T12:30:00Z",
                },
                "energy": {"kcal": 650},
                "totalCarbohydrate": {"grams": 70},
                "totalFat": {"grams": 15},
                "nutrients": [
                    {"nutrient": "PROTEIN", "quantity": {"grams": 45}}
                ],
            },
        },
    ]

    respx.get(
        f"{API_BASE_URL}/users/me/dataTypes/nutrition-log/dataPoints"
    ).respond(200, json={"dataPoints": sample_points})

    meals = client.list_meals()
    assert len(meals) == 2
    assert meals[0].foodDisplayName == "Breakfast Oats"
    assert meals[0].protein_g == 20.0
    assert meals[1].foodDisplayName == "Chicken Rice"
    assert meals[1].protein_g == 45.0


@respx.mock
def test_delete_meal(client):
    respx.post(
        f"{API_BASE_URL}/users/me/dataTypes/nutrition-log/dataPoints:batchDelete"
    ).respond(200)
    assert client.delete_meal("point-123") is True


@respx.mock
def test_delete_meal_403_not_owned_by_client(client):
    """The API forbids deleting another client's points, e.g. Fitbit's."""
    respx.post(
        f"{API_BASE_URL}/users/me/dataTypes/nutrition-log/dataPoints:batchDelete"
    ).respond(
        403,
        json={
            "error": {
                "code": 403,
                "message": "Invalid argument in request: names",
                "status": "PERMISSION_DENIED",
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                        "reason": "DATA_POINT_NOT_OWNED_BY_CLIENT",
                        "domain": "health.googleapis.com",
                        "metadata": {"field": "names"},
                    },
                    {
                        "@type": "type.googleapis.com/google.rpc.BadRequest",
                        "fieldViolations": [
                            {
                                "field": "names",
                                "description": (
                                    "Deleting data points sourced from other "
                                    "API clients is forbidden."
                                ),
                            }
                        ],
                    },
                ],
            }
        },
    )
    with pytest.raises(
        APIPermissionError, match="created by another client"
    ) as exc_info:
        client.delete_meal("point-123")
    # The "enable the API" hint is wrong for this failure and must not be shown.
    assert "Google Cloud Console" not in str(exc_info.value)


@respx.mock
def test_delete_meal_403_api_disabled_keeps_enable_hint(client):
    respx.post(
        f"{API_BASE_URL}/users/me/dataTypes/nutrition-log/dataPoints:batchDelete"
    ).respond(
        403,
        json={
            "error": {
                "message": (
                    "Google Health API has not been used in project 123 before"
                )
            }
        },
    )
    with pytest.raises(APIPermissionError, match="Google Cloud Console"):
        client.delete_meal("point-123")


def _point(name: str, start: str) -> dict:
    return {
        "name": f"users/123/dataTypes/nutrition-log/dataPoints/{name}",
        "nutritionLog": {
            "foodDisplayName": name,
            "mealType": "SNACK",
            "interval": {"startTime": start, "endTime": start},
            "energy": {"kcal": 100},
        },
    }


@respx.mock
def test_list_meals_follows_next_page_token(client):
    """Every matching point must be returned, not just the first page."""
    url = f"{API_BASE_URL}/users/me/dataTypes/nutrition-log/dataPoints"
    respx.get(url).mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "dataPoints": [_point("first", "2026-08-17T01:00:00Z")],
                    "nextPageToken": "tok1",
                },
            ),
            httpx.Response(
                200,
                json={
                    "dataPoints": [_point("second", "2026-08-17T02:00:00Z")],
                    "nextPageToken": "tok2",
                },
            ),
            httpx.Response(
                200,
                json={"dataPoints": [_point("third", "2026-08-17T03:00:00Z")]},
            ),
        ]
    )
    meals = client.list_meals(
        start_time=datetime(2026, 8, 17, tzinfo=timezone.utc),
        end_time=datetime(2026, 8, 18, tzinfo=timezone.utc),
    )
    assert [m.foodDisplayName for m in meals] == ["first", "second", "third"]
    # The token from each response must be sent on the next request.
    assert respx.calls[1].request.url.params.get("pageToken") == "tok1"
    assert respx.calls[2].request.url.params.get("pageToken") == "tok2"


@respx.mock
def test_list_meals_excludes_unparseable_timestamps(client):
    """Unparseable timestamps must not leak into a filtered range."""
    url = f"{API_BASE_URL}/users/me/dataTypes/nutrition-log/dataPoints"
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            json={
                "dataPoints": [
                    _point("good", "2026-08-17T01:00:00Z"),
                    _point("broken", "not-a-date"),
                ]
            },
        )
    )
    meals = client.list_meals(
        start_time=datetime(2026, 8, 17, tzinfo=timezone.utc),
        end_time=datetime(2026, 8, 18, tzinfo=timezone.utc),
    )
    assert [m.foodDisplayName for m in meals] == ["good"]


@respx.mock
def test_list_meals_requests_the_largest_page(client):
    """A small page size would expose the lossy same-timestamp cursor."""
    url = f"{API_BASE_URL}/users/me/dataTypes/nutrition-log/dataPoints"
    respx.get(url).mock(
        return_value=httpx.Response(200, json={"dataPoints": []})
    )
    client.list_meals()
    assert respx.calls[0].request.url.params.get("pageSize") == str(
        MAX_PAGE_SIZE
    )
