"""Input validator tests (≥10 cases)."""

from datetime import date
from decimal import Decimal

import pytest

from app.utils.errors import ValidationError
from app.utils.validators import (
    parse_date,
    validate_budget,
    validate_date_range,
    validate_destination,
)


def test_parse_date_from_iso_string():
    assert parse_date("2026-07-01") == date(2026, 7, 1)


def test_parse_date_from_date_instance():
    d = date(2026, 8, 15)
    assert parse_date(d) == d


def test_parse_date_rejects_invalid_format():
    with pytest.raises(ValidationError):
        parse_date("07/01/2026")


def test_validate_date_range_accepts_valid_range():
    start, end = validate_date_range("2026-07-01", "2026-07-10")
    assert start < end


def test_validate_date_range_rejects_end_before_start():
    with pytest.raises(ValidationError):
        validate_date_range("2026-07-10", "2026-07-01")


def test_validate_budget_accepts_positive_amount():
    assert validate_budget("1500.50") == Decimal("1500.50")


def test_validate_budget_rejects_zero():
    with pytest.raises(ValidationError):
        validate_budget(0)


def test_validate_budget_rejects_over_max():
    with pytest.raises(ValidationError):
        validate_budget(2_000_000)


def test_validate_budget_rejects_invalid_currency_code():
    with pytest.raises(ValidationError):
        validate_budget(100, currency="US")


def test_validate_destination_accepts_city_name():
    assert validate_destination("Paris, France") == "Paris, France"


def test_validate_destination_rejects_too_short():
    with pytest.raises(ValidationError):
        validate_destination("A")


def test_validate_destination_rejects_invalid_characters():
    with pytest.raises(ValidationError):
        validate_destination("Tokyo<script>")
