from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from .industry_policy import evaluate_industry_mode, excluded_companies
from .listing_policy import check_listing


def _status(ok: bool) -> str:
    return "OK" if ok else "NG"


def check_assignment_conditions(
    companies: pd.DataFrame,
    app_mode: str,
    industry_mode: str,
    rubric: dict[str, Any],
    industry_policy: dict[str, Any],
    as_of: date | None = None,
) -> dict[str, object]:
    assignment = rubric["assignment"]
    min_companies = int(assignment["min_companies"])
    min_years_label = f"上場後{assignment['min_years_since_listing']}年以上"
    rows: list[dict[str, str]] = []
    company_rows: list[dict[str, str]] = []
    warnings: list[str] = []
    notes: list[str] = []

    count_ok = len(companies) >= min_companies
    rows.append(
        {
            "条件": f"{min_companies}社以上の比較",
            "判定": _status(count_ok),
            "詳細": f"{len(companies)}社を選択",
        }
    )

    listing_results = [check_listing(row, rubric, as_of) for _, row in companies.iterrows()]
    for result in listing_results:
        years = result["years_since_listing"]
        years_text = "推定不可" if years is None else f"{years:.1f}年"
        company_rows.append(
            {
                "証券コード": str(result["ticker"]),
                "企業名": str(result["company_name"]),
                "上場日": str(result["listing_date"]),
                "上場後年数": years_text,
                "2000-04-01以降": _status(bool(result["listed_after_threshold"])),
                min_years_label: _status(bool(result["enough_years"])),
                "注記": str(result["listing_note"]),
            }
        )
        if result["listing_note"]:
            notes.append(f"{result['company_name']}: {result['listing_note']}")

    listing_ok = all(bool(result["listing_ok"]) for result in listing_results)
    rows.append(
        {
            "条件": f"{assignment['listing_on_or_after']}以降に上場、かつ{min_years_label}",
            "判定": _status(listing_ok),
            "詳細": "企業別判定表を参照",
        }
    )
    if not listing_ok:
        warnings.append("上場日または上場後年数の条件を満たさない企業があります。")

    industry_result = evaluate_industry_mode(companies, industry_mode, industry_policy, app_mode)
    rows.append(
        {
            "条件": "同じ業種から2社以上",
            "判定": str(industry_result["status"]),
            "詳細": " / ".join(industry_result["notes"]),
        }
    )
    warnings.extend(str(w) for w in industry_result["warnings"])

    exclusion_ok = True
    if app_mode == "assignment":
        excluded = excluded_companies(companies, industry_policy)
        exclusion_ok = excluded.empty
        rows.append(
            {
                "条件": "課題モードの除外業種ではない",
                "判定": _status(exclusion_ok),
                "詳細": "該当なし" if exclusion_ok else "、".join(excluded["company_name"].astype(str)),
            }
        )
        if not exclusion_ok:
            warnings.append("課題モードの除外業種に該当する企業があります。")
    else:
        rows.append(
            {
                "条件": "金融・医療分野の扱い",
                "判定": "OK",
                "詳細": "汎用モードのため除外しない",
            }
        )

    warning_only = any(row["判定"] == "警告" for row in rows)
    passed = count_ok and listing_ok and exclusion_ok and not any(row["判定"] == "NG" for row in rows)
    if warning_only and passed:
        notes.append("警告付きでレポート生成可能です。課題提出時は担当教員の条件確認を推奨します。")

    return {
        "condition_table": pd.DataFrame(rows),
        "company_check_table": pd.DataFrame(company_rows),
        "industry_result": industry_result,
        "warnings": list(dict.fromkeys(warnings)),
        "notes": list(dict.fromkeys(notes)),
        "passed": passed,
    }
