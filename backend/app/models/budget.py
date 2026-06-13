"""Budget-related Pydantic models."""

from enum import Enum
from typing import Optional, Literal

from pydantic import BaseModel, Field


class CostCategory(BaseModel):
    """Single cost category breakdown."""

    category: str  # flights, hotels, attractions, food, transport, other
    amount: float = Field(..., ge=0)
    currency: str = "USD"
    items: Optional[list[dict]] = None  # Detailed breakdown per item


class BudgetCompliance(str, Enum):
    """Budget compliance status."""

    WITHIN_BUDGET = "within_budget"
    WARNING = "warning"
    OVER_BUDGET = "over_budget"


class BudgetBreakdown(BaseModel):
    """Complete budget breakdown for a trip."""

    total_budget: float = Field(..., ge=0)
    total_estimated_cost: float = Field(..., ge=0)
    currency: str = "USD"
    compliance: BudgetCompliance
    categories: list[CostCategory] = Field(default_factory=list)
    variance_percentage: Optional[float] = None  # How much over/under budget
    recommendations: Optional[list[str]] = None  # Suggestions to stay within budget


class BudgetOptimization(BaseModel):
    """Budget optimization suggestions."""

    original_cost: float
    optimized_cost: float
    savings: float
    savings_percentage: float
    changes: list[dict]  # List of changes made to optimize
