"""Unit tests for nutrilog.client."""

from datetime import datetime, timezone
from unittest.mock import MagicMock
from google.oauth2.credentials import Credentials
import httpx
import pytest
import respx

from nutrilog.client import (
    API_BASE_URL,
    APIPermissionError,
    AuthenticationError,
    GoogleHealthClient,
    GoogleHealthError,
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
            NutrientEntry(nutrient="PROTEIN", quantity=GramsQuantity(grams=35.0)),
        ],
    )

    response_payload = {
        "id": "dp-abc-123",
        "nutritionLog": meal.to_api_payload()["nutritionLog"],
    }

    respx.post(f"{API_BASE_URL}/users/me/dataTypes/nutrition-log/dataPoints").respond(
        200, json=response_payload
    )

    result = client.log_meal(meal)
    assert result.id == "dp-abc-123"
    assert result.foodDisplayName == "Protein Bowl"
    assert result.calories_kcal == 500.0
    assert result.protein_g == 35.0


def test_log_meal_not_authenticated():
    unauth_client = GoogleHealthClient(credentials=None)
    with pytest.raises(AuthenticationError, match="Not authenticated"):
        unauth_client.log_meal(
            MealLog(
                foodDisplayName="Meal",
                interval=TimeInterval(startTime="2026-08-17T12:00:00Z", endTime="2026-08-17T12:00:00Z"),
            )
        )


@respx.mock
def test_log_meal_401_error(client):
    respx.post(f"{API_BASE_URL}/users/me/dataTypes/nutrition-log/dataPoints").respond(
        401, json={"error": {"message": "Invalid credentials"}}
    )
    with pytest.raises(AuthenticationError, match="OAuth token is invalid or expired"):
        client.log_meal(
            MealLog(
                foodDisplayName="Meal",
                interval=TimeInterval(startTime="2026-08-17T12:00:00Z", endTime="2026-08-17T12:00:00Z"),
            )
        )


@respx.mock
def test_log_meal_403_error(client):
    respx.post(f"{API_BASE_URL}/users/me/dataTypes/nutrition-log/dataPoints").respond(
        403, json={"error": {"message": "Google Health API has not been enabled"}}
    )
    with pytest.raises(APIPermissionError, match="permission denied"):
        client.log_meal(
            MealLog(
                foodDisplayName="Meal",
                interval=TimeInterval(startTime="2026-08-17T12:00:00Z", endTime="2026-08-17T12:00:00Z"),
            )
        )


@respx.mock
def test_list_meals(client):
    sample_points = [
        {
            "id": "point-1",
            "nutritionLog": {
                "foodDisplayName": "Breakfast Oats",
                "mealType": "BREAKFAST",
                "interval": {"startTime": "2026-08-17T08:00:00Z", "endTime": "2026-08-17T08:00:00Z"},
                "energy": {"kcal": 350},
                "totalCarbohydrate": {"grams": 50},
                "totalFat": {"grams": 8},
                "nutrients": [{"nutrient": "PROTEIN", "quantity": {"grams": 20}}],
            },
        },
        {
            "id": "point-2",
            "nutritionLog": {
                "foodDisplayName": "Chicken Rice",
                "mealType": "LUNCH",
                "interval": {"startTime": "2026-08-17T12:30:00Z", "endTime": "2026-08-17T12:30:00Z"},
                "energy": {"kcal": 650},
                "totalCarbohydrate": {"grams": 70},
                "totalFat": {"grams": 15},
                "nutrients": [{"nutrient": "PROTEIN", "quantity": {"grams": 45}}],
            },
        },
    ]

    respx.get(f"{API_BASE_URL}/users/me/dataTypes/nutrition-log/dataPoints").respond(
        200, json={"dataPoints": sample_points}
    )

    meals = client.list_meals()
    assert len(meals) == 2
    assert meals[0].foodDisplayName == "Breakfast Oats"
    assert meals[0].protein_g == 20.0
    assert meals[1].foodDisplayName == "Chicken Rice"
    assert meals[1].protein_g == 45.0


@respx.mock
def test_delete_meal(client):
    respx.delete(f"{API_BASE_URL}/users/me/dataTypes/nutrition-log/dataPoints/point-123").respond(204)
    assert client.delete_meal("point-123") is True
