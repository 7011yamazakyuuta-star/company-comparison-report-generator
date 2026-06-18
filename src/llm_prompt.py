from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from .advanced_diagnostics import build_advanced_diagnostics
from .analysis_engine import (
    build_dupont_driver_table,
    build_management_issue_table,
    build_profit_bridge_table,
    build_sensitivity_risk_table,
)
from .assignment_filters import check_assignment_conditions
from .company_master import select_companies
from .config_loader import load_industry_policy, load_rubric
from .course_framework import (
    build_plus_alpha_analysis_table,
    build_plus_alpha_commentary,
    build_plus_alpha_status_table,
    build_required_plus_alpha_table,
)
from .data_loader import Dataset
from .metrics.financial import compute_financial_metrics, latest_metrics
from .metrics.scoring import build_company_scores
from .rubric_checker import sanitize_advice_terms


PROMPT_METRIC_COLUMNS = [
    "ticker",
    "company_name",
    "fiscal_year",
    "revenue_growth_rate",
    "operating_margin",
    "roa",
    "roe",
    "asset_turnover",
    "equity_ratio",
    "debt_ratio",
    "fcf",
    "per",
    "pbr",
]

PROMPT_SCORE_COLUMNS = [
    "ticker",
    "company_name",
    "data_completeness",
    "growth_score",
    "profitability_score",
    "stability_score",
    "cashflow_score",
    "analysis_quality_score",
    "analysis_band",
]

PROMPT_EDINET_COLUMNS = [
    "doc_id",
    "edinet_code",
    "sec_code",
    "filer_name",
    "doc_description",
    "submit_datetime",
    "xbrl_flag",
    "csv_flag",
]


def _safe_value(value: object) -> str:
    if value is None or pd.isna(value):
        return "推定不可"
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)


def _markdown_table(df: pd.DataFrame, columns: list[str] | None = None) -> str:
    if df.empty:
        return "推定不可"
    view = df.copy()
    if columns:
        view = view[[column for column in columns if column in view.columns]]
    if view.empty:
        return "推定不可"
    headers = [str(column) for column in view.columns]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for _, row in view.iterrows():
        lines.append("| " + " | ".join(_safe_value(row[column]) for column in view.columns) + " |")
    return "\n".join(lines)


def _bullet(items: list[object]) -> str:
    if not items:
        return "- なし"
    return "\n".join(f"- {item}" for item in items)


def _compute_metrics(dataset: Dataset, selected_tickers: list[str], selected_companies: pd.DataFrame) -> pd.DataFrame:
    selected_financials = dataset.financials[dataset.financials["ticker"].isin(selected_tickers)].copy()
    selected_market = dataset.market_data[dataset.market_data["ticker"].isin(selected_tickers)].copy()
    selected_manual = dataset.manual_kpis[dataset.manual_kpis["ticker"].isin(selected_tickers)].copy()
    metrics = compute_financial_metrics(selected_financials, selected_market, selected_manual)
    ordered = selected_companies[["ticker", "company_name"]].copy()
    ordered["_selection_order"] = range(len(ordered))
    metrics = metrics.merge(ordered, on="ticker", how="left")
    return metrics.sort_values(["_selection_order", "fiscal_year"]).reset_index(drop=True)


def build_llm_report_prompt(
    *,
    selected_tickers: list[str],
    preset: dict[str, Any],
    app_mode: str,
    industry_mode: str,
    dataset: Dataset,
    as_of: date,
    edinet_filings: pd.DataFrame | None = None,
    data_source_audit: pd.DataFrame | None = None,
) -> str:
    rubric = load_rubric()
    industry_policy = load_industry_policy()
    selected_companies = select_companies(dataset.company_master, selected_tickers).copy()
    assignment_result = check_assignment_conditions(
        selected_companies,
        app_mode=app_mode,
        industry_mode=industry_mode,
        rubric=rubric,
        industry_policy=industry_policy,
        as_of=as_of,
    )
    metrics = _compute_metrics(dataset, selected_tickers, selected_companies)
    latest = latest_metrics(metrics)
    scores = build_company_scores(metrics)
    advanced = build_advanced_diagnostics(
        metrics,
        selected_companies,
        app_mode=app_mode,
        industry_mode=industry_mode,
    )
    required_plus_alpha = build_required_plus_alpha_table()
    plus_alpha_table = build_plus_alpha_analysis_table(
        metrics,
        selected_companies,
        missing_label=rubric["assignment"]["missing_value_label"],
    )
    plus_alpha_status_table = build_plus_alpha_status_table(
        metrics,
        missing_label=rubric["assignment"]["missing_value_label"],
    )
    plus_alpha_comments = build_plus_alpha_commentary(
        plus_alpha_table,
        rubric["assignment"]["missing_value_label"],
    )
    missing_label = rubric["assignment"]["missing_value_label"]
    dupont_table = build_dupont_driver_table(metrics, missing_label)
    profit_bridge_table = build_profit_bridge_table(metrics, missing_label)
    sensitivity_table = build_sensitivity_risk_table(metrics, missing_label=missing_label)
    management_issue_table = build_management_issue_table(
        metrics,
        selected_companies,
        app_mode=app_mode,
        industry_mode=industry_mode,
        missing_label=missing_label,
    )

    required_sections = _bullet(list(rubric["assignment"]["report_sections"]))
    alpha_items = _bullet(list(rubric["assignment"]["alpha_analysis_items"]))
    banned_terms = "、".join(rubric["assignment"].get("banned_investment_advice_terms", []))
    edinet_context = edinet_filings.copy() if edinet_filings is not None else pd.DataFrame()
    data_audit_context = data_source_audit.copy() if data_source_audit is not None else pd.DataFrame()
    edinet_status = (
        "EDINET取得済み書類メタデータあり。docID、提出者、書類種別、CSV/XBRL有無を出典候補として参照してください。"
        if not edinet_context.empty
        else "EDINET取得済み書類メタデータなし。財務数値の断定は避け、不足箇所は推定不可としてください。"
    )

    prompt = f"""# 企業比較レポート作成プロンプト

あなたは日本語の企業分析レポート編集者です。以下のデータだけを根拠に、大学課題または汎用分析向けの比較レポート草稿を作成してください。

## 厳守事項
- 投資助言ではありません。株式取引の推奨に見える表現は使わないでください。
- 使用禁止語: {banned_terms}
- 添付された表、EDINET書類メタデータ、データソース監査表にない数値・事実・出典は作らないでください。
- 数値の根拠がEDINET取得データではなく補助データまたは欠損の場合、その数値を断定せず「推定不可」または「要確認」と書いてください。
- 原因分析や今後の見通しは、表中の数値、提出書類メタデータ、明示された業種・事業テーマから言える範囲に限定してください。
- ニュース、株価材料、未提示の市場情報、会社の最新施策など、ここにない外部情報を知っている前提で書かないでください。
- データ不足の箇所は「推定不可」と明記してください。
- 表、箇条書き、短い考察を組み合わせ、Wordに貼り付けやすいMarkdownで出力してください。
- 根拠がない断定は避け、比較分析として記述してください。

## 出力してほしい章
{required_sections}

## ＋α分析に含める項目
{alpha_items}

## 分析条件
- 作成日: {as_of.isoformat()}
- 比較セット: {preset.get("name", preset.get("preset_id", ""))}
- 説明: {preset.get("description", "")}
- アプリモード: {app_mode}
- 業種判定モード: {industry_mode}
- 比較テーマ: {preset.get("comparison_theme", "")}
- manual_custom（手動比較）の場合、上場日・業種一致・除外業種は参考判定であり、強制条件ではありません。

## データソースとEDINET反映状況
- 財務指標の数値: EDINET取得・解析済みデータとデータソース監査表を優先してください。
- EDINET連携: {edinet_status}
- 注意: EDINET CSV/XBRLから抽出できた財務数値だけを根拠のある数値として扱ってください。欠損または補助データ扱いの項目は、本文で「推定不可」または「要確認」と明記してください。

## EDINET取得済み書類メタデータ
{_markdown_table(edinet_context, PROMPT_EDINET_COLUMNS)}

## 分析データ監査
{_markdown_table(data_audit_context)}

## 比較企業
{_markdown_table(selected_companies)}

## 条件適合表
{_markdown_table(assignment_result["condition_table"])}

## 企業別条件チェック
{_markdown_table(assignment_result["company_check_table"])}

## 警告
{_bullet(list(assignment_result["warnings"]))}

## 注記
{_bullet(list(assignment_result["notes"]))}

## 必須部分と＋αの区分
{_markdown_table(required_plus_alpha)}

## 最新年度の主要財務指標
{_markdown_table(latest, PROMPT_METRIC_COLUMNS)}

## 分析品質スコア
{_markdown_table(scores, PROMPT_SCORE_COLUMNS)}

## 高度判定テーブル
{_markdown_table(advanced["diagnostic_table"])}

## 自動考察メモ
{_bullet(list(advanced["commentary"]))}

## モード別確認観点
{_bullet(list(advanced["mode_notes"]))}

## ＋α分析テーブル
{_markdown_table(plus_alpha_table)}

## ＋α分析の実施状態
{_markdown_table(plus_alpha_status_table)}

## ＋α分析メモ
{_bullet(plus_alpha_comments)}

## 高度アルゴリズム: ROE要因分解
{_markdown_table(dupont_table)}

## 高度アルゴリズム: 営業利益ブリッジ
{_markdown_table(profit_bridge_table)}

## 高度アルゴリズム: 感応度・リスクフラグ
{_markdown_table(sensitivity_table)}

## 高度アルゴリズム: 経営分析論点
{_markdown_table(management_issue_table)}

## 依頼
1. まず比較対象の妥当性を説明してください。
2. 必須部分と＋α分析を分けて、どこが通常比較でどこが追加考察か分かるようにしてください。
3. 収益性、財務安定性、キャッシュフロー、＋α分析を比較してください。
4. 警告や欠損データは本文中にも注記してください。
5. 結論は、比較から読み取れる特徴に限定してください。
6. 参考資料として、サンプルCSV、YAML条件、EDINET取得済み書類メタデータの有無を明記してください。
"""
    return sanitize_advice_terms(prompt, rubric)
