from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd


def parse_date(value: object) -> date | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    return datetime.strptime(text, "%Y-%m-%d").date()


def years_since(start: date | None, as_of: date | None = None) -> float | None:
    if start is None:
        return None
    end = as_of or date.today()
    return (end - start).days / 365.2425


def check_listing(company: pd.Series, rubric: dict[str, Any], as_of: date | None = None) -> dict[str, object]:
    assignment = rubric["assignment"]
    threshold = parse_date(assignment["listing_on_or_after"])
    min_years = float(assignment["min_years_since_listing"])
    listing_date = parse_date(company.get("listing_date"))
    elapsed = years_since(listing_date, as_of)
    listed_after_threshold = bool(listing_date and threshold and listing_date >= threshold)
    enough_years = bool(elapsed is not None and elapsed >= min_years)
    return {
        "ticker": company.get("ticker"),
        "company_name": company.get("company_name"),
        "listing_date": listing_date.isoformat() if listing_date else "",
        "years_since_listing": elapsed,
        "listed_after_threshold": listed_after_threshold,
        "enough_years": enough_years,
        "listing_ok": listed_after_threshold and enough_years,
        "listing_note": company.get("listing_note") or "",
    }

