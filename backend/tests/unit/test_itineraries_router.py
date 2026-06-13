"""Unit tests for the itineraries API router."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from app.main import app

client = TestClient(app)


@pytest.mark.asyncio
async def test_get_itinerary_success():
    mock_trip = {
        "id": "33d058d9-ce53-477d-9c57-09f034205e6f",
        "user_id": "test-user-id",
        "title": "Paris Trip",
        "constraints": {
            "start_date": "2026-07-01",
            "end_date": "2026-07-05",
            "destinations": ["Paris"]
        },
        "status": "completed",
        "created_at": None
    }
    mock_itinerary = {
        "id": "itinerary-uuid",
        "trip_id": "33d058d9-ce53-477d-9c57-09f034205e6f",
        "content": {
            "destination": "Paris",
            "days": [
                {
                    "day": 1,
                    "date": "2026-07-01",
                    "location": "Paris",
                    "activities": [
                        {
                            "name": "Eiffel Tower Tour",
                            "type": "attraction",
                            "start_time": "10:00",
                            "cost_usd": 25.0,
                            "description": "Visit the Eiffel Tower"
                        }
                    ]
                }
            ]
        },
        "budget_breakdown": {
            "total_estimated_cost": 25.0,
            "currency": "USD",
            "categories": [
                {"category": "attractions", "amount": 25.0}
            ]
        },
        "validation_status": "approved"
    }

    with patch("app.services.database.get_trip", new_callable=AsyncMock) as mock_get_trip, \
         patch("app.services.database.get_itinerary", new_callable=AsyncMock) as mock_get_itin:
        mock_get_trip.return_value = mock_trip
        mock_get_itin.return_value = mock_itinerary

        response = client.get("/api/itineraries/33d058d9-ce53-477d-9c57-09f034205e6f")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "33d058d9-ce53-477d-9c57-09f034205e6f"
        assert data["destination"] == "Paris"
        assert data["startDate"] == "2026-07-01"
        assert data["endDate"] == "2026-07-05"
        assert len(data["days"]) == 1
        assert data["days"][0]["day"] == 1
        assert data["days"][0]["activities"][0]["title"] == "Eiffel Tower Tour"
        assert data["days"][0]["activities"][0]["category"] == "attraction"
        assert data["budget"]["total"] == 25.0
        assert data["budget"]["breakdown"][0]["name"] == "attractions"
        assert data["budget"]["breakdown"][0]["amount"] == 25.0


@pytest.mark.asyncio
async def test_get_itinerary_not_found():
    with patch("app.services.database.get_trip", new_callable=AsyncMock) as mock_get_trip:
        mock_get_trip.return_value = None

        response = client.get("/api/itineraries/non-existent-id")
        
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"]
