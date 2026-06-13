"""Unit tests for Pydantic data models."""

import pytest
from datetime import datetime
from uuid import uuid4

from app.models.user import User, Profile, RegisterRequest, LoginRequest, AuthResponse
from app.models.trip import Trip, TripConstraints, TripPreferences, TripStatus, TripCreate, TripUpdate
from app.models.itinerary import Itinerary, DayPlan, Activity, ValidationStatus, ItineraryCreate
from app.models.budget import BudgetBreakdown, CostCategory, BudgetCompliance
from app.models.agent import AgentResponse, ToolResult, AgentError


class TestUserModels:
    """Tests for user-related models."""

    def test_user_model(self):
        """Test User model creation."""
        user = User(
            id=uuid4(),
            email="test@example.com",
            display_name="Test User",
        )
        assert user.email == "test@example.com"
        assert user.display_name == "Test User"

    def test_profile_model(self):
        """Test Profile model creation."""
        profile = Profile(
            id=uuid4(),
            email="test@example.com",
            display_name="Test User",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        assert profile.email == "test@example.com"

    def test_register_request_valid(self):
        """Test RegisterRequest with valid password."""
        request = RegisterRequest(
            email="test@example.com",
            password="Password123",
            display_name="Test User",
        )
        assert request.email == "test@example.com"
        assert request.password == "Password123"

    def test_register_request_invalid_password_no_uppercase(self):
        """Test RegisterRequest rejects password without uppercase."""
        with pytest.raises(ValueError, match="uppercase"):
            RegisterRequest(
                email="test@example.com",
                password="password123",
            )

    def test_register_request_invalid_password_no_lowercase(self):
        """Test RegisterRequest rejects password without lowercase."""
        with pytest.raises(ValueError, match="lowercase"):
            RegisterRequest(
                email="test@example.com",
                password="PASSWORD123",
            )

    def test_register_request_invalid_password_no_digit(self):
        """Test RegisterRequest rejects password without digit."""
        with pytest.raises(ValueError, match="digit"):
            RegisterRequest(
                email="test@example.com",
                password="PasswordABC",
            )

    def test_login_request(self):
        """Test LoginRequest model."""
        request = LoginRequest(
            email="test@example.com",
            password="Password123",
        )
        assert request.email == "test@example.com"

    def test_auth_response(self):
        """Test AuthResponse model."""
        response = AuthResponse(
            access_token="test_token",
            user=User(
                id=uuid4(),
                email="test@example.com",
            ),
        )
        assert response.access_token == "test_token"
        assert response.token_type == "bearer"


class TestTripModels:
    """Tests for trip-related models."""

    def test_trip_preferences(self):
        """Test TripPreferences model."""
        prefs = TripPreferences(
            accommodation_type="hotel",
            food_preferences=["vegetarian", "vegan"],
            crowd_tolerance="medium",
        )
        assert prefs.accommodation_type == "hotel"
        assert "vegetarian" in prefs.food_preferences

    def test_trip_constraints(self):
        """Test TripConstraints model."""
        constraints = TripConstraints(
            destinations=["Paris", "London"],
            budget=2000,
            travelers=2,
        )
        assert len(constraints.destinations) == 2
        assert constraints.budget == 2000
        assert constraints.travelers == 2

    def test_trip_constraints_invalid_travelers(self):
        """Test TripConstraints rejects invalid traveler count."""
        with pytest.raises(ValueError):
            TripConstraints(travelers=0)

    def test_trip_model(self):
        """Test Trip model."""
        trip = Trip(
            id=uuid4(),
            user_id=uuid4(),
            title="Paris Trip",
            status=TripStatus.PLANNING,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        assert trip.title == "Paris Trip"
        assert trip.status == TripStatus.PLANNING

    def test_trip_create(self):
        """Test TripCreate model."""
        trip_create = TripCreate(
            title="New Trip",
            constraints=TripConstraints(destinations=["Tokyo"]),
        )
        assert trip_create.title == "New Trip"

    def test_trip_update(self):
        """Test TripUpdate model."""
        trip_update = TripUpdate(
            title="Updated Trip",
            status=TripStatus.COMPLETED,
        )
        assert trip_update.title == "Updated Trip"
        assert trip_update.status == TripStatus.COMPLETED


class TestItineraryModels:
    """Tests for itinerary-related models."""

    def test_activity_model(self):
        """Test Activity model."""
        activity = Activity(
            name="Visit Eiffel Tower",
            type="attraction",
            location="Paris",
            cost=15.0,
        )
        assert activity.name == "Visit Eiffel Tower"
        assert activity.type == "attraction"

    def test_day_plan_model(self):
        """Test DayPlan model."""
        day_plan = DayPlan(
            day=1,
            location="Paris",
            activities=[
                Activity(name="Breakfast", type="food"),
                Activity(name="Sightseeing", type="attraction"),
            ],
        )
        assert day_plan.day == 1
        assert len(day_plan.activities) == 2

    def test_day_plan_invalid_day(self):
        """Test DayPlan rejects invalid day number."""
        with pytest.raises(ValueError):
            DayPlan(day=0)

    def test_itinerary_model(self):
        """Test Itinerary model."""
        itinerary = Itinerary(
            id=uuid4(),
            trip_id=uuid4(),
            content={"days": []},
            validation_status=ValidationStatus.APPROVED,
            created_at=datetime.utcnow(),
        )
        assert itinerary.validation_status == ValidationStatus.APPROVED

    def test_itinerary_create(self):
        """Test ItineraryCreate model."""
        itinerary_create = ItineraryCreate(
            trip_id=uuid4(),
            content={"days": []},
        )
        assert itinerary_create.validation_status == ValidationStatus.APPROVED


class TestBudgetModels:
    """Tests for budget-related models."""

    def test_cost_category(self):
        """Test CostCategory model."""
        category = CostCategory(
            category="flights",
            amount=500.0,
            currency="USD",
        )
        assert category.category == "flights"
        assert category.amount == 500.0

    def test_cost_category_invalid_amount(self):
        """Test CostCategory rejects negative amount."""
        with pytest.raises(ValueError):
            CostCategory(category="food", amount=-10.0)

    def test_budget_breakdown(self):
        """Test BudgetBreakdown model."""
        breakdown = BudgetBreakdown(
            total_budget=2000.0,
            total_estimated_cost=1800.0,
            compliance="within_budget",
            categories=[
                CostCategory(category="flights", amount=500.0),
                CostCategory(category="hotels", amount=800.0),
            ],
        )
        assert breakdown.total_budget == 2000.0
        assert breakdown.compliance == "within_budget"
        assert len(breakdown.categories) == 2


class TestAgentModels:
    """Tests for agent-related models."""

    def test_tool_result(self):
        """Test ToolResult model."""
        result = ToolResult(
            tool_name="search_flights",
            success=True,
            data={"flights": []},
            latency_ms=150,
        )
        assert result.tool_name == "search_flights"
        assert result.success is True
        assert result.cache_hit is False

    def test_agent_error(self):
        """Test AgentError model."""
        error = AgentError(
            agent_name="FlightAgent",
            error_type="APIError",
            message="Failed to fetch flights",
            retryable=True,
        )
        assert error.agent_name == "FlightAgent"
        assert error.retryable is True

    def test_agent_response(self):
        """Test AgentResponse model."""
        response = AgentResponse(
            agent_name="FlightAgent",
            success=True,
            tool_results=[
                ToolResult(tool_name="search_flights", success=True),
            ],
            steps_taken=3,
        )
        assert response.agent_name == "FlightAgent"
        assert response.success is True
        assert response.steps_taken == 3
