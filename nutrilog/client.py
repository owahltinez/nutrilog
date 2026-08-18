"""Google Health API (v4) client for logging and querying nutrition data."""

from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Any, List, Optional
from google.oauth2.credentials import Credentials
import httpx

from nutrilog.auth import get_credentials
from nutrilog.models import MealLog

API_BASE_URL = "https://health.googleapis.com/v4"
NUTRITION_DATA_TYPE = "nutrition-log"


class GoogleHealthError(Exception):
    """Base exception for Google Health API errors."""


class AuthenticationError(GoogleHealthError):
    """Authentication or token expiry errors."""


class APIPermissionError(GoogleHealthError):
    """Permission denied or scope errors."""


class ResourceNotFoundError(GoogleHealthError):
    """Resource not found errors."""


class GoogleHealthClient:
    """Client for Google Health API v4 nutrition endpoints."""

    def __init__(
        self,
        credentials: Optional[Credentials] = None,
        base_url: str = API_BASE_URL,
        timeout: float = 15.0,
    ):
        self.credentials = credentials
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _get_headers(self) -> dict[str, str]:
        """Obtain authorization headers, refreshing credentials if needed."""
        creds = self.credentials or get_credentials()
        if not creds or not creds.token:
            raise AuthenticationError(
                "Not authenticated. Please run 'nutrilog auth login' or configure credentials."
            )
        return {
            "Authorization": f"Bearer {creds.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _handle_response_error(self, response: httpx.Response) -> None:
        """Raise appropriate exceptions based on HTTP status code."""
        if response.status_code == 401:
            raise AuthenticationError(
                "OAuth token is invalid or expired. Please run 'nutrilog auth login'."
            )
        elif response.status_code == 403:
            try:
                error_data = response.json().get("error", {})
                err_msg = error_data.get("message", response.text)
                for d in error_data.get("details", []):
                    if d.get("reason") == "DATA_POINT_NOT_OWNED_BY_CLIENT":
                        raise APIPermissionError(
                            "Cannot delete meal: this data point was created by another client "
                            "(e.g. Fitbit app) and can only be deleted from the originating application."
                        )
            except (KeyError, ValueError, TypeError):
                err_msg = response.text
            raise APIPermissionError(
                f"Google Health API permission denied: {err_msg}. "
                "Ensure the Google Health API is enabled in your Google Cloud Console."
            )
        elif response.status_code == 404:
            raise ResourceNotFoundError(f"Requested resource not found: {response.text}")
        elif response.status_code >= 400:
            try:
                err_msg = response.json().get("error", {}).get("message", response.text)
            except Exception:
                err_msg = response.text
            raise GoogleHealthError(f"Google Health API error ({response.status_code}): {err_msg}")

    def log_meal(self, meal: MealLog) -> MealLog:
        """Create a new nutritionLog dataPoint in Google Health API."""
        url = f"{self.base_url}/users/me/dataTypes/{NUTRITION_DATA_TYPE}/dataPoints"
        payload = meal.to_api_payload()

        try:
            with httpx.Client(timeout=self.timeout) as client:
                headers = self._get_headers()
                response = client.post(url, json=payload, headers=headers)
                if response.is_error:
                    self._handle_response_error(response)
                data = response.json()
                return MealLog.from_api_payload(data)
        except httpx.RequestError as exc:
            raise GoogleHealthError(f"Network error while communicating with Google Health API: {exc}") from exc

    def list_meals(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        page_size: int = 100,
    ) -> List[MealLog]:
        """List nutrition data points within a given time range."""
        from nutrilog.storage import get_user_timezone

        active_tz = get_user_timezone()
        url = f"{self.base_url}/users/me/dataTypes/{NUTRITION_DATA_TYPE}/dataPoints"
        params: dict[str, Any] = {"pageSize": page_size}

        if start_time and start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=active_tz)
        if end_time and end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=active_tz)

        try:
            with httpx.Client(timeout=self.timeout) as client:
                headers = self._get_headers()
                response = client.get(url, params=params, headers=headers)
                if response.is_error:
                    self._handle_response_error(response)

                data = response.json()
                data_points = data.get("dataPoints", [])
                meals = []
                for point in data_points:
                    meal = MealLog.from_api_payload(point)
                    try:
                        meal_start = meal.interval.start_datetime
                        if meal_start.tzinfo is None:
                            meal_start = meal_start.replace(tzinfo=timezone.utc)
                        if start_time and meal_start < start_time:
                            continue
                        if end_time and meal_start > end_time:
                            continue
                    except (ValueError, TypeError):
                        pass
                    meals.append(meal)
                return meals
        except httpx.RequestError as exc:
            raise GoogleHealthError(f"Network error while communicating with Google Health API: {exc}") from exc

    def get_today_meals(self, tz: Optional[Any] = None) -> List[MealLog]:
        """Retrieve all meals logged today in the specified or active user timezone."""
        from nutrilog.storage import get_user_timezone

        active_tz = tz or get_user_timezone()
        now_local = datetime.now(active_tz)
        start_of_day = datetime.combine(now_local.date(), time.min, tzinfo=active_tz)
        end_of_day = datetime.combine(now_local.date(), time.max, tzinfo=active_tz)
        return self.list_meals(start_time=start_of_day, end_time=end_of_day)

    def delete_meal(self, data_point_id: str) -> bool:
        """Delete a nutritionLog data point by ID or full resource name."""
        url = f"{self.base_url}/users/me/dataTypes/{NUTRITION_DATA_TYPE}/dataPoints:batchDelete"
        if "/" in data_point_id:
            name = data_point_id
        else:
            name = f"users/me/dataTypes/{NUTRITION_DATA_TYPE}/dataPoints/{data_point_id}"

        payload = {"names": [name]}
        try:
            with httpx.Client(timeout=self.timeout) as client:
                headers = self._get_headers()
                response = client.post(url, json=payload, headers=headers)
                if response.is_error:
                    self._handle_response_error(response)
                return response.status_code in (200, 204)
        except httpx.RequestError as exc:
            raise GoogleHealthError(f"Network error while communicating with Google Health API: {exc}") from exc
