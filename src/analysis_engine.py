from __future__ import annotations

from typing import Any

import pandas as pd

from .config_loader import load_analysis_policy
from .metrics.financial import latest_metrics
from .metrics.scoring import build_company_scores


def _num(value: object) -> float | None:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return None
    return float(numeric)


def _fmt_percent(value: object, missing_label: str) -> str:
    numeric = _num(value)
    return missing_label if numeric is None else f"{numeric * 100:.1f}%"


def _fmt_number(value: object, missing_label: str) -> str:
    numeric = _num(value)
    if numeric is None:
        return missing_label
    if abs(numeric) >= 100:
        return f"{numeric:,.0f}"
    return f"{numeric:,.2f}"


def _safe_ratio(numerator: object, denominator: object) -> float | None:
    numer = _num(numerator)
    denom = _num(denominator)
    if numer is None or denom is None or denom == 0:
        return None
    return numer / denom


def _policy_value(policy: dict[str, Any], *path: str, default: float | None = None) -> float | None:
    current: Any = policy
    for key in path:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return _num(current) if current is not None else default


def _latest_ordered(metrics: pd.DataFrame) -> pd.DataFrame:
    latest = latest_metrics(metrics)
    if "_selection_order" in latest.columns:
        return latest.sort_values(["_selection_order", "ticker"]).reset_index(drop=True)
    return latest.sort_values("ticker").reset_index(drop=True)


def _industry_text(companies: pd.DataFrame) -> str:
    columns = ["jpx_industry", "broad_sector", "business_theme", "business_summary"]
    values: list[str] = []
    for column in columns:
        if column in companies.columns:
            values.extend(companies[column].dropna().astype(str).tolist())
    return " ".join(values)


def _matched_lenses(companies: pd.DataFrame, policy: dict[str, Any]) -> list[dict[str, Any]]:
    text = _industry_text(companies)
    lenses = []
    for name, config in policy.get("industry_lenses", {}).items():
        keywords = [str(keyword) for keyword in config.get("keywords", [])]
        if any(keyword and keyword in text for keyword in keywords):
            lenses.append({"name": name, **config})
    return lenses


def _joined(items: list[str], missing_label: str) -> str:
    cleaned = [item for item in dict.fromkeys(items) if item]
    return "、".join(cleaned) if cleaned else missing_label


def _relative_position(value: object, median: object, missing_label: str) -> str:
    value_num = _num(value)
    median_num = _num(median)
    if value_num is None or median_num is None:
        return missing_label
    if median_num == 0:
        if value_num > 0:
            return "中央値を上回る"
        if value_num < 0:
            return "中央値を下回る"
        return "中央値並み"
    ratio = value_num / median_num
    if ratio >= 1.08:
        return "中央値を上回る"
    if ratio <= 0.92:
        return "中央値を下回る"
    return "中央値並み"


def _median_or_na(frame: pd.DataFrame, column: str) -> object:
    if column not in frame.columns:
        return pd.NA
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    if values.empty:
        return pd.NA
    return values.median()


def build_dupont_driver_table(metrics: pd.DataFrame, missing_label: str = "推定不可") -> pd.DataFrame:
    latest = _latest_ordered(metrics)
    if latest.empty:
        return pd.DataFrame()

    medians = {
        "net_margin": _median_or_na(latest, "net_margin"),
        "asset_turnover": _median_or_na(latest, "asset_turnover"),
        "financial_leverage": _median_or_na(latest, "financial_leverage"),
    }

    rows: list[dict[str, str]] = []
    for _, row in latest.iterrows():
        component_scores: dict[str, float] = {}
        for label, column in {
            "利益率": "net_margin",
            "資産回転": "asset_turnover",
            "財務レバレッジ": "financial_leverage",
        }.items():
            value = _num(row.get(column))
            median = _num(medians.get(column))
            if value is None or median is None or median == 0:
                continue
            component_scores[label] = value / median
        main_driver = max(component_scores, key=component_scores.get) if component_scores else missing_label
        rows.append(
            {
                "企業名": str(row.get("company_name", row.get("ticker"))),
                "ROE": _fmt_percent(row.get("roe"), missing_label),
                "当期利益率": _fmt_percent(row.get("net_margin"), missing_label),
                "利益率位置": _relative_position(row.get("net_margin"), medians.get("net_margin"), missing_label),
                "総資産回転率": _fmt_number(row.get("asset_turnover"), missing_label),
                "回転率位置": _relative_position(row.get("asset_turnover"), medians.get("asset_turnover"), missing_label),
                "財務レバレッジ": _fmt_number(row.get("financial_leverage"), missing_label),
                "レバレッジ位置": _relative_position(
                    row.get("financial_leverage"), medians.get("financial_leverage"), missing_label
                ),
                "主なROE要因": main_driver,
            }
        )
    return pd.DataFrame(rows)


def build_profit_bridge_table(metrics: pd.DataFrame, missing_label: str = "推定不可") -> pd.DataFrame:
    if metrics.empty:
        return pd.DataFrame()

    rows: list[dict[str, str]] = []
    for ticker, history in metrics.sort_values(["ticker", "fiscal_year"]).groupby("ticker", sort=False):
        if len(history) < 2:
            latest = history.iloc[-1]
            rows.append(
                {
                    "企業名": str(latest.get("company_name", ticker)),
                    "対象年度": str(latest.get("fiscal_year", "")),
                    "営業利益前年差": missing_label,
                    "売上要因": missing_label,
                    "利益率要因": missing_label,
                    "残差": missing_label,
                    "読み取り": "前年差分析には2期以上のデータが必要。",
                }
            )
            continue

        previous = history.iloc[-2]
        current = history.iloc[-1]
        prev_revenue = _num(previous.get("revenue"))
        cur_revenue = _num(current.get("revenue"))
        prev_margin = _num(previous.get("operating_margin"))
        cur_margin = _num(current.get("operating_margin"))
        prev_op = _num(previous.get("operating_income"))
        cur_op = _num(current.get("operating_income"))

        revenue_effect = None
        margin_effect = None
        op_change = None
        residual = None
        reading = missing_label
        if None not in (prev_revenue, cur_revenue, prev_margin, cur_margin, prev_op, cur_op):
            op_change = cur_op - prev_op
            revenue_effect = (cur_revenue - prev_revenue) * prev_margin
            margin_effect = cur_revenue * (cur_margin - prev_margin)
            residual = op_change - revenue_effect - margin_effect
            if abs(revenue_effect) >= abs(margin_effect):
                reading = "営業利益の前年差は売上規模の変化による影響が相対的に大きい。"
            else:
                reading = "営業利益の前年差は利益率の変化による影響が相対的に大きい。"

        rows.append(
            {
                "企業名": str(current.get("company_name", ticker)),
                "対象年度": str(current.get("fiscal_year", "")),
                "営業利益前年差": _fmt_number(op_change, missing_label),
                "売上要因": _fmt_number(revenue_effect, missing_label),
                "利益率要因": _fmt_number(margin_effect, missing_label),
                "残差": _fmt_number(residual, missing_label),
                "読み取り": reading,
            }
        )
    return pd.DataFrame(rows)


def _risk_flags(row: pd.Series, policy: dict[str, Any], missing_label: str) -> str:
    flags: list[str] = []
    growth = _num(row.get("revenue_growth_rate"))
    margin = _num(row.get("operating_margin"))
    safety = _num(row.get("safety_margin"))
    operating_leverage = _num(row.get("operating_leverage"))
    equity_ratio = _num(row.get("equity_ratio"))
    fcf = _num(row.get("fcf"))
    fcf_margin = _safe_ratio(row.get("fcf"), row.get("revenue"))

    if growth is not None and growth < 0:
        flags.append("売上減少")
    if margin is not None and margin < 0:
        flags.append("営業赤字")
    safety_watch = _policy_value(policy, "diagnostics", "safety_margin", "watch_max", default=0.05)
    if safety is not None and safety_watch is not None and safety <= safety_watch:
        flags.append("安全余裕率が薄い")
    leverage_high = _policy_value(policy, "advanced_algorithms", "operating_leverage", "high_min", default=3.0)
    if operating_leverage is not None and leverage_high is not None and operating_leverage >= leverage_high:
        flags.append("利益感応度が高い")
    equity_watch = _policy_value(policy, "diagnostics", "equity_ratio", "watch_max", default=0.25)
    if equity_ratio is not None and equity_watch is not None and equity_ratio <= equity_watch:
        flags.append("自己資本比率に注意")
    if fcf is not None and fcf < 0:
        flags.append("FCFマイナス")
    fcf_watch = _policy_value(policy, "diagnostics", "fcf_margin", "watch_max", default=0.0)
    if fcf_margin is not None and fcf_watch is not None and fcf_margin <= fcf_watch:
        flags.append("FCF余力に注意")
    return "、".join(flags) if flags else "大きな注意フラグなし"


def build_sensitivity_risk_table(
    metrics: pd.DataFrame,
    *,
    analysis_policy: dict[str, Any] | None = None,
    missing_label: str = "推定不可",
) -> pd.DataFrame:
    policy = analysis_policy or load_analysis_policy()
    latest = _latest_ordered(metrics)
    if latest.empty:
        return pd.DataFrame()

    rows: list[dict[str, str]] = []
    for _, row in latest.iterrows():
        operating_leverage = _num(row.get("operating_leverage"))
        op_income = _num(row.get("operating_income"))
        sales_1pct_op_income_effect = None
        op_income_change_rate = None
        if operating_leverage is not None:
            op_income_change_rate = operating_leverage * 0.01
        if op_income is not None and op_income_change_rate is not None:
            sales_1pct_op_income_effect = op_income * op_income_change_rate
        rows.append(
            {
                "企業名": str(row.get("company_name", row.get("ticker"))),
                "売上1%増減時の営業利益変化率目安": _fmt_percent(op_income_change_rate, missing_label),
                "売上1%増減時の営業利益額目安": _fmt_number(sales_1pct_op_income_effect, missing_label),
                "安全余裕率": _fmt_percent(row.get("safety_margin"), missing_label),
                "FCFマージン": _fmt_percent(_safe_ratio(row.get("fcf"), row.get("revenue")), missing_label),
                "自己資本比率": _fmt_percent(row.get("equity_ratio"), missing_label),
                "リスクフラグ": _risk_flags(row, policy, missing_label),
            }
        )
    return pd.DataFrame(rows)


def build_management_issue_table(
    metrics: pd.DataFrame,
    companies: pd.DataFrame,
    *,
    app_mode: str,
    industry_mode: str,
    analysis_policy: dict[str, Any] | None = None,
    missing_label: str = "推定不可",
) -> pd.DataFrame:
    policy = analysis_policy or load_analysis_policy()
    latest = _latest_ordered(metrics)
    if latest.empty:
        return pd.DataFrame()

    scores = build_company_scores(metrics)
    score_columns = [
        "ticker",
        "data_completeness",
        "growth_score",
        "profitability_score",
        "stability_score",
        "cashflow_score",
        "efficiency_score",
        "trend_resilience_score",
        "valuation_reference_score",
    ]
    latest = latest.merge(scores[[column for column in score_columns if column in scores.columns]], on="ticker", how="left")

    dupont = build_dupont_driver_table(metrics, missing_label).set_index("企業名", drop=False)
    bridge = build_profit_bridge_table(metrics, missing_label).set_index("企業名", drop=False)
    risk = build_sensitivity_risk_table(metrics, analysis_policy=policy, missing_label=missing_label).set_index("企業名", drop=False)

    strength_min = _policy_value(
        policy, "advanced_algorithms", "management_issue", "strength_score_min", default=70
    )
    weakness_max = _policy_value(
        policy, "advanced_algorithms", "management_issue", "weakness_score_max", default=35
    )
    low_data_max = _policy_value(
        policy, "advanced_algorithms", "management_issue", "low_data_confidence_max", default=70
    )
    score_labels = {
        "growth_score": "成長性",
        "profitability_score": "収益性",
        "stability_score": "財務安定性",
        "cashflow_score": "CF創出力",
        "efficiency_score": "資産効率",
        "trend_resilience_score": "変動耐性",
        "valuation_reference_score": "倍率面の割安感ではなく参考水準",
    }

    rows: list[dict[str, str]] = []
    for _, row in latest.iterrows():
        ticker = str(row.get("ticker"))
        company_name = str(row.get("company_name", ticker))
        company_scope = companies[companies["ticker"].astype(str) == ticker]
        if company_scope.empty:
            company_scope = companies

        strengths: list[str] = []
        cautions: list[str] = []
        for column, label in score_labels.items():
            score = _num(row.get(column))
            if score is None:
                continue
            if strength_min is not None and score >= strength_min:
                strengths.append(label)
            if weakness_max is not None and score <= weakness_max:
                cautions.append(label)

        data_completeness = _num(row.get("data_completeness"))
        if data_completeness is not None and low_data_max is not None and data_completeness <= low_data_max:
            cautions.append("データ補強")

        risk_flags = ""
        if company_name in risk.index:
            risk_flags = str(risk.loc[company_name, "リスクフラグ"])
            if risk_flags and risk_flags != "大きな注意フラグなし":
                cautions.append(risk_flags)

        reason_candidates: list[str] = []
        if company_name in dupont.index:
            reason_candidates.append(f"ROE差は{dupont.loc[company_name, '主なROE要因']}を確認する。")
        if company_name in bridge.index:
            reason_candidates.append(str(bridge.loc[company_name, "読み取り"]))
        if pd.notna(row.get("four_p")) or pd.notna(row.get("four_c")):
            reason_candidates.append("4P/4C、顧客関係、バリューチェーンから事業面の理由を補う。")

        lens_drivers: list[str] = []
        lens_notes: list[str] = []
        for lens in _matched_lenses(company_scope, policy):
            lens_drivers.extend(str(driver) for driver in lens.get("drivers", []))
            if lens.get("note"):
                lens_notes.append(str(lens.get("note")))
        if app_mode == "assignment" and industry_mode != "strict_jpx_industry":
            cautions.append("課題では業種一致警告の説明が必要")

        writing_policy = (
            "条件適合、財務指標、＋α考察を分けて書く。"
            if app_mode == "assignment"
            else "業種差と事業モデル差を前提に、汎用比較として書く。"
        )

        rows.append(
            {
                "企業名": company_name,
                "強み候補": _joined(strengths, missing_label),
                "注意点": _joined(cautions, missing_label),
                "差が出た理由候補": _joined(reason_candidates, missing_label),
                "今後確認する外部環境": _joined(lens_drivers, missing_label),
                "業種別メモ": _joined(lens_notes, missing_label),
                "レポートでの書き方": writing_policy,
            }
        )
    return pd.DataFrame(rows)
