from __future__ import annotations

from typing import Any

import pandas as pd


def build_assignment_response_table(rubric: dict[str, Any]) -> pd.DataFrame:
    assignment = rubric["assignment"]
    rows = [
        {
            "項目": "上場日条件",
            "対応": f"{assignment['listing_on_or_after']}以降、上場後{assignment['min_years_since_listing']}年以上を自動判定",
        },
        {
            "項目": "比較企業数",
            "対応": f"{assignment['min_companies']}社以上を自動判定",
        },
        {
            "項目": "業種条件",
            "対応": "JPX業種一致、事業テーマ、広義セクターの3モードで判定",
        },
        {
            "項目": "除外業種",
            "対応": "課題モードでYAML定義の金融・医療系除外を適用",
        },
        {
            "項目": "不足データ",
            "対応": f"算定できない指標は「{assignment['missing_value_label']}」として注記",
        },
        {
            "項目": "助言表現",
            "対応": "株式取引の推奨ではなく、比較分析として記述",
        },
    ]
    return pd.DataFrame(rows)


def required_sections_table(rubric: dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"章": section, "出力": "対象"} for section in rubric["assignment"]["report_sections"]]
    )


def find_banned_terms(text: str, rubric: dict[str, Any]) -> list[str]:
    terms = rubric["assignment"].get("banned_investment_advice_terms", [])
    return [term for term in terms if term in text]


def sanitize_advice_terms(text: str, rubric: dict[str, Any]) -> str:
    sanitized = text
    for term in rubric["assignment"].get("banned_investment_advice_terms", []):
        sanitized = sanitized.replace(term, "推奨表現")
    return sanitized

