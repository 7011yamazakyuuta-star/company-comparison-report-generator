from __future__ import annotations

from typing import Any

import pandas as pd


def _unique_values(df: pd.DataFrame, column: str) -> list[str]:
    values = []
    for value in df[column].dropna().astype(str):
        if value not in values:
            values.append(value)
    return values


def _contains_any(value: object, patterns: list[str]) -> bool:
    text = "" if value is None or pd.isna(value) else str(value)
    return any(pattern in text for pattern in patterns)


def excluded_companies(companies: pd.DataFrame, policy: dict[str, Any]) -> pd.DataFrame:
    exclusions = policy.get("assignment_exclusions", {})
    jpx = exclusions.get("jpx_industries", [])
    broad = exclusions.get("broad_sectors", [])
    themes = exclusions.get("business_themes", [])
    mask = companies.apply(
        lambda row: (
            _contains_any(row.get("jpx_industry"), jpx)
            or _contains_any(row.get("broad_sector"), broad)
            or _contains_any(row.get("business_theme"), themes)
        ),
        axis=1,
    )
    return companies[mask].copy()


def evaluate_industry_mode(
    companies: pd.DataFrame,
    industry_mode: str,
    policy: dict[str, Any],
    app_mode: str = "assignment",
) -> dict[str, object]:
    mode_config = policy["industry_modes"][industry_mode]
    warning_messages = policy.get("warning_messages", {})
    warnings: list[str] = []
    notes: list[str] = []
    status = "OK"

    jpx_values = _unique_values(companies, "jpx_industry")
    theme_values = _unique_values(companies, "business_theme")
    broad_values = _unique_values(companies, "broad_sector")
    jpx_match = len(jpx_values) == 1

    if industry_mode == "strict_jpx_industry":
        passed = jpx_match
        if not passed:
            status = "NG"
            warnings.append(warning_messages.get("jpx_mismatch", "JPX業種が一致していません。"))
    elif industry_mode == "business_theme":
        passed = len(theme_values) == 1
        if app_mode == "assignment":
            status = "警告"
            warnings.append(warning_messages.get("non_strict_assignment", "課題モードでは警告します。"))
        if not jpx_match:
            warnings.append(warning_messages.get("jpx_mismatch", "JPX業種が一致していません。"))
        if not passed:
            status = "NG"
            warnings.append("事業テーマが一致していません。")
    elif industry_mode == "broad_sector":
        passed = len(broad_values) == 1
        if app_mode == "assignment":
            status = "警告"
            warnings.append(warning_messages.get("non_strict_assignment", "課題モードでは警告します。"))
        if not jpx_match:
            warnings.append(warning_messages.get("jpx_mismatch", "JPX業種が一致していません。"))
        if not passed:
            status = "NG"
            warnings.append("広義セクターが一致していません。")
    else:
        raise ValueError(f"unknown industry mode: {industry_mode}")

    if jpx_values:
        notes.append(f"JPX業種: {', '.join(jpx_values)}")
    if theme_values:
        notes.append(f"事業テーマ: {', '.join(theme_values)}")
    if broad_values:
        notes.append(f"広義セクター: {', '.join(broad_values)}")

    return {
        "mode": industry_mode,
        "mode_label": mode_config.get("label", industry_mode),
        "status": status,
        "passed": passed,
        "jpx_match": jpx_match,
        "jpx_values": jpx_values,
        "business_theme_values": theme_values,
        "broad_sector_values": broad_values,
        "warnings": warnings,
        "notes": notes,
    }

