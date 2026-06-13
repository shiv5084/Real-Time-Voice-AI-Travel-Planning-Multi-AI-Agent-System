"""Input validation helpers for trip planning constraints."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.utils.errors import ValidationError

_DESTINATION_PATTERN = re.compile(r"^[A-Za-z][A-Za-z\s\-',.]{1,98}$")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_date(value: str | date | datetime, *, field: str = "date") -> date:
    """Parse and validate a calendar date (YYYY-MM-DD or date instance)."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not _ISO_DATE.match(value.strip()):
        raise ValidationError(
            f"{field} must be ISO format YYYY-MM-DD",
            field=field,
        )
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValidationError(f"{field} is not a valid date", field=field) from exc


def validate_date_range(
    start: str | date,
    end: str | date,
    *,
    start_field: str = "start_date",
    end_field: str = "end_date",
) -> tuple[date, date]:
    """Ensure end date is on or after start date."""
    start_d = parse_date(start, field=start_field)
    end_d = parse_date(end, field=end_field)
    if end_d < start_d:
        raise ValidationError(
            f"{end_field} must be on or after {start_field}",
            field=end_field,
        )
    return start_d, end_d


def validate_budget(
    amount: str | int | float | Decimal,
    *,
    field: str = "budget",
    min_amount: Decimal = Decimal("0"),
    max_amount: Decimal = Decimal("1000000"),
    currency: str | None = None,
) -> Decimal:
    """Validate trip budget is a positive number within bounds."""
    try:
        value = Decimal(str(amount))
    except (InvalidOperation, ValueError) as exc:
        raise ValidationError(f"{field} must be a numeric amount", field=field) from exc
    if value <= min_amount:
        raise ValidationError(f"{field} must be greater than {min_amount}", field=field)
    if value > max_amount:
        raise ValidationError(f"{field} exceeds maximum allowed budget", field=field)
    if currency and len(currency) != 3:
        raise ValidationError("currency must be a 3-letter ISO code", field="currency")
    return value


def validate_destination(destination: str, *, field: str = "destination") -> str:
    """Validate a human-readable destination name."""
    cleaned = (destination or "").strip()
    if len(cleaned) < 2:
        raise ValidationError(f"{field} is too short", field=field)
    if len(cleaned) > 100:
        raise ValidationError(f"{field} is too long", field=field)
    if not _DESTINATION_PATTERN.match(cleaned):
        raise ValidationError(
            f"{field} contains invalid characters",
            field=field,
        )
    return cleaned
