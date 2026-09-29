"""Parsing and validation of individual field values."""

from __future__ import annotations

from datetime import date, datetime

MIN_RATING = 1
MAX_RATING = 5

# Unambiguous formats first; day-first is the default for dd/mm vs mm/dd.
DATE_FORMATS_DAY_FIRST = ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d.%m.%Y", "%d-%m-%Y", "%m/%d/%Y")
DATE_FORMATS_MONTH_FIRST = ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%m-%d-%Y", "%d/%m/%Y", "%d.%m.%Y")


def parse_rating(value: str | None) -> int | None:
    """Return a rating 1-5, or None if the value is blank or invalid.

    Accepts '4', ' 4 ', '4.0'. Rejects '', 'N/A', '4.5', '7', '0'.
    """
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if not number.is_integer():
        return None
    rating = int(number)
    return rating if MIN_RATING <= rating <= MAX_RATING else None


def parse_date(value: str | None, month_first: bool = False) -> date | None:
    """Parse common date formats; return None for blank or unrecognised values."""
    if not value or not value.strip():
        return None
    text = value.strip()
    formats = DATE_FORMATS_MONTH_FIRST if month_first else DATE_FORMATS_DAY_FIRST
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def clean_text(value: str | None) -> str:
    """Trim surrounding whitespace and collapse internal runs of whitespace."""
    return " ".join((value or "").split())
