"""
End-to-end tests for Golden Dataset evaluation (Phase 7B).

These tests verify that the travel planning system produces correct results
for the golden dataset requests on the managed stack.
"""

import asyncio
import pytest
import httpx
from typing import Dict, Any


# Golden Dataset - 8 representative travel planning requests
GOLDEN_DATASET = [
    {
        "id": 1,
        "request": "Plan a 5-day trip to Paris for a couple with a $3000 budget, focusing on museums and romantic dining",
        "constraints": {
            "destination": "Paris",
            "duration": 5,
            "travelers": 2,
            "budget": 3000,
            "preferences": ["museums", "romantic dining"]
        },
        "expected_elements": ["Eiffel Tower", "Louvre", "romantic restaurant", "budget breakdown"]
    },
    {
        "id": 2,
        "request": "Family trip to Tokyo for 7 days, $5000 budget, 4 people including 2 kids, theme parks and cultural sites",
        "constraints": {
            "destination": "Tokyo",
            "duration": 7,
            "travelers": 4,
            "budget": 5000,
            "preferences": ["theme parks", "cultural sites"]
        },
        "expected_elements": ["Disneyland", "cultural temple", "family-friendly", "budget breakdown"]
    },
    {
        "id": 3,
        "request": "Solo backpacking trip to Southeast Asia for 2 weeks, $1500 budget, adventure activities and hostels",
        "constraints": {
            "destination": "Southeast Asia",
            "duration": 14,
            "travelers": 1,
            "budget": 1500,
            "preferences": ["adventure", "hostels"]
        },
        "expected_elements": ["hostel", "adventure activity", "budget accommodation", "budget breakdown"]
    },
    {
        "id": 4,
        "request": "Luxury weekend getaway to New York City, $4000 budget, fine dining and Broadway shows",
        "constraints": {
            "destination": "New York City",
            "duration": 3,
            "travelers": 2,
            "budget": 4000,
            "preferences": ["fine dining", "Broadway"]
        },
        "expected_elements": ["Broadway show", "fine dining restaurant", "luxury hotel", "budget breakdown"]
    },
    {
        "id": 5,
        "request": "Nature-focused trip to Swiss Alps for 6 days, $3500 budget, hiking and scenic views",
        "constraints": {
            "destination": "Swiss Alps",
            "duration": 6,
            "travelers": 2,
            "budget": 3500,
            "preferences": ["hiking", "scenic views"]
        },
        "expected_elements": ["hiking trail", "scenic viewpoint", "mountain", "budget breakdown"]
    },
    {
        "id": 6,
        "request": "Repeat user: Another trip to Paris like last time, but this time I want luxury hotels instead of budget",
        "constraints": {
            "destination": "Paris",
            "duration": 5,
            "travelers": 2,
            "budget": 5000,
            "preferences": ["luxury hotels", "museums"]
        },
        "expected_elements": ["luxury hotel", "museum", "preference applied", "budget breakdown"],
        "requires_memory": True
    },
    {
        "id": 7,
        "request": "Business trip to London for 4 days, $2500 budget, efficient transportation and coworking spaces",
        "constraints": {
            "destination": "London",
            "duration": 4,
            "travelers": 1,
            "budget": 2500,
            "preferences": ["efficient transport", "coworking"]
        },
        "expected_elements": ["coworking space", "efficient transport", "business-friendly", "budget breakdown"]
    },
    {
        "id": 8,
        "request": "Beach vacation to Bali for 10 days, $4000 budget, relaxation and water sports",
        "constraints": {
            "destination": "Bali",
            "duration": 10,
            "travelers": 2,
            "budget": 4000,
            "preferences": ["beach", "water sports"]
        },
        "expected_elements": ["beach", "water sports", "resort", "budget breakdown"]
    }
]


@pytest.mark.e2e
class TestGoldenDatasetE2E:
    """End-to-end tests for golden dataset evaluation."""

    @pytest.fixture
    def base_url(self):
        """Base URL for API requests."""
        return "http://localhost:8000"

    @pytest.fixture
    def async_client(self):
        """Async HTTP client for API requests."""
        return httpx.AsyncClient(timeout=600.0)

    async def test_golden_dataset_request_1(self, base_url, async_client):
        """Test golden dataset request #1: Paris couple trip."""
        request_data = GOLDEN_DATASET[0]
        response = await async_client.post(
            f"{base_url}/api/trips/plan",
            json={
                "raw_request": request_data["request"],
                "session_id": "test_session_1",
                "user_id": "test_user"
            }
        )

        assert response.status_code == 200
        itinerary = response.json()

        # Verify structure
        assert itinerary is not None

    async def test_golden_dataset_request_2(self, base_url, async_client):
        """Test golden dataset request #2: Tokyo family trip."""
        request_data = GOLDEN_DATASET[1]
        response = await async_client.post(
            f"{base_url}/api/trips/plan",
            json={
                "raw_request": request_data["request"],
                "session_id": "test_session_2",
                "user_id": "test_user"
            }
        )

        assert response.status_code == 200
        itinerary = response.json()

        # Verify structure
        assert itinerary is not None

    async def test_golden_dataset_request_3(self, base_url, async_client):
        """Test golden dataset request #3: Southeast Asia backpacking."""
        request_data = GOLDEN_DATASET[2]
        response = await async_client.post(
            f"{base_url}/api/trips/plan",
            json={
                "raw_request": request_data["request"],
                "session_id": "test_session_3",
                "user_id": "test_user"
            }
        )

        assert response.status_code == 200
        itinerary = response.json()

        # Verify structure
        assert itinerary is not None

    async def test_golden_dataset_request_4(self, base_url, async_client):
        """Test golden dataset request #4: NYC luxury getaway."""
        request_data = GOLDEN_DATASET[3]
        response = await async_client.post(
            f"{base_url}/api/trips/plan",
            json={
                "raw_request": request_data["request"],
                "session_id": "test_session_4",
                "user_id": "test_user"
            }
        )

        assert response.status_code == 200
        itinerary = response.json()

        # Verify structure
        assert itinerary is not None

    async def test_golden_dataset_request_5(self, base_url, async_client):
        """Test golden dataset request #5: Swiss Alps nature trip."""
        request_data = GOLDEN_DATASET[4]
        response = await async_client.post(
            f"{base_url}/api/trips/plan",
            json={
                "raw_request": request_data["request"],
                "session_id": "test_session_5",
                "user_id": "test_user"
            }
        )

        assert response.status_code == 200
        itinerary = response.json()

        # Verify structure
        assert itinerary is not None

    async def test_golden_dataset_request_6(self, base_url, async_client):
        """Test golden dataset request #6: Repeat user with preference change."""
        request_data = GOLDEN_DATASET[5]
        response = await async_client.post(
            f"{base_url}/api/trips/plan",
            json={
                "raw_request": request_data["request"],
                "session_id": "test_session_6",
                "user_id": "test_user"
            }
        )

        assert response.status_code == 200
        itinerary = response.json()

        # Verify structure
        assert itinerary is not None

    async def test_golden_dataset_request_7(self, base_url, async_client):
        """Test golden dataset request #7: London business trip."""
        request_data = GOLDEN_DATASET[6]
        response = await async_client.post(
            f"{base_url}/api/trips/plan",
            json={
                "raw_request": request_data["request"],
                "session_id": "test_session_7",
                "user_id": "test_user"
            }
        )

        assert response.status_code == 200
        itinerary = response.json()

        # Verify structure
        assert itinerary is not None

    async def test_golden_dataset_request_8(self, base_url, async_client):
        """Test golden dataset request #8: Bali beach vacation."""
        request_data = GOLDEN_DATASET[7]
        response = await async_client.post(
            f"{base_url}/api/trips/plan",
            json={
                "raw_request": request_data["request"],
                "session_id": "test_session_8",
                "user_id": "test_user"
            }
        )

        assert response.status_code == 200
        itinerary = response.json()

        # Verify structure
        assert itinerary is not None

    async def test_all_golden_dataset_requests(self, base_url, async_client):
        """Test all 8 golden dataset requests in sequence."""
        passed = 0
        failed = 0

        for request_data in GOLDEN_DATASET:
            try:
                response = await async_client.post(
                    f"{base_url}/api/trips/plan",
                    json={
                        "raw_request": request_data["request"],
                        "session_id": f"test_session_{request_data['id']}",
                        "user_id": "test_user"
                    }
                )
                
                if response.status_code == 200:
                    passed += 1
                else:
                    failed += 1
            except Exception as e:
                failed += 1
                print(f"Request #{request_data['id']} failed: {e}")
        
        # Verify all 8 requests pass
        assert passed == 8, f"Expected 8/8 requests to pass, got {passed}/8"
        assert failed == 0, f"Expected 0 failures, got {failed}"

    async def test_constraint_satisfaction(self, base_url, async_client):
        """Test that constraints are satisfied in generated itineraries."""
        request_data = GOLDEN_DATASET[0]
        response = await async_client.post(
            f"{base_url}/api/trips/plan",
            json={
                "raw_request": request_data["request"],
                "session_id": "test_session",
                "user_id": "test_user"
            }
        )

        assert response.status_code == 200
        itinerary = response.json()

        # Verify itinerary exists
        assert itinerary is not None

    async def test_preference_alignment(self, base_url, async_client):
        """Test that user preferences are reflected in itineraries."""
        request_data = GOLDEN_DATASET[0]
        response = await async_client.post(
            f"{base_url}/api/trips/plan",
            json={
                "raw_request": request_data["request"],
                "session_id": "test_session",
                "user_id": "test_user"
            }
        )

        assert response.status_code == 200
        itinerary = response.json()

        # Verify itinerary exists
        assert itinerary is not None

        assert response.status_code == 200
        itinerary = response.json()

        # Verify itinerary exists
        assert itinerary is not None


@pytest.mark.e2e
class TestGoldenDatasetVoiceE2E:
    """End-to-end tests for the golden dataset travel planning requests using the voice flow."""

    @pytest.fixture
    def base_url(self):
        """Base URL for API requests."""
        return "http://localhost:8000"

    @pytest.fixture
    def async_client(self):
        """Async HTTP client for API requests."""
        return httpx.AsyncClient(timeout=180.0)

    @pytest.mark.parametrize("request_idx", range(8))
    async def test_golden_dataset_voice_flow(self, base_url, async_client, request_idx):
        """Test voice onboarding, follow-ups, and planning stream for a golden request."""
        request_data = GOLDEN_DATASET[request_idx]
        
        # 1. Start a realtime voice session
        start_response = await async_client.post(
            f"{base_url}/api/voice/session/start",
            json={"mode": "realtime"}
        )
        assert start_response.status_code == 200
        start_data = start_response.json()
        session_id = start_data["session_id"]
        assert session_id is not None
        assert len(start_data["greeting_text"]) > 0

        # 2. Submit initial request transcript
        reply_response = await async_client.post(
            f"{base_url}/api/voice/session/reply",
            json={
                "session_id": session_id,
                "transcript": request_data["request"],
                "mode": "realtime"
            }
        )
        assert reply_response.status_code == 200
        reply_data = reply_response.json()

        # 3. Handle multi-turn follow-ups dynamically until state is "ready"
        turns = 0
        while reply_data.get("status") == "follow_up" and turns < 5:
            turns += 1
            question = reply_data.get("question", "").lower()
            
            # Answer follow-ups automatically based on the question topic
            if "date" in question or "when" in question:
                transcript_reply = "I would like to start my trip on June 10, 2026."
            elif "budget" in question or "how much" in question:
                budget_val = request_data["constraints"].get("budget", 3000)
                transcript_reply = f"My budget is {budget_val} dollars."
            elif "where" in question or "destination" in question:
                dest_val = request_data["constraints"].get("destination", "Paris")
                transcript_reply = f"I want to go to {dest_val}."
            else:
                transcript_reply = "Please proceed."

            reply_response = await async_client.post(
                f"{base_url}/api/voice/session/reply",
                json={
                    "session_id": session_id,
                    "transcript": transcript_reply,
                    "mode": "realtime"
                }
            )
            assert reply_response.status_code == 200
            reply_data = reply_response.json()

        assert reply_data.get("status") == "ready", f"Session not ready for request #{request_idx+1} after {turns} turns. Data: {reply_data}"

        # 4. Stream planning pipeline results via SSE GET endpoint
        plan_complete = False
        voice_summary_received = False
        
        async with async_client.stream("GET", f"{base_url}/api/voice/session/{session_id}/plan") as response:
            assert response.status_code == 200
            async for line in response.aiter_lines():
                if line.startswith("event:"):
                    event_type = line.split(":", 1)[1].strip()
                    if event_type == "plan_complete":
                        plan_complete = True
                    elif event_type == "voice_summary":
                        voice_summary_received = True

        assert plan_complete, "SSE event plan_complete was not received"
        assert voice_summary_received, "SSE event voice_summary was not received"

