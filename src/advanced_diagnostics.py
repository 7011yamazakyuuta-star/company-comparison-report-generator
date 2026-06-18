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


def _safe_ratio(numerator: object, denominator: object) -> float | None:
    numer = _num(numerator)
    denom = _num(denominator)
    if numer is None or denom is None or denom == 0:
        return None
    return numer / denom


def _safe_cagr(first: object, last: object, periods: int) -> float | None:
    first_value = _num(first)
    last_value = _num(last)
    if first_value is None or last_value is None or first_value <= 0 or last_value <= 0 or periods <= 0:
        return None
    return (last_value / first_value) ** (1 / periods) - 1


def _label_by_threshold(value: float | None, strong_min: float | None = None, watch_max: float | None = None) -> str:
    if value is None:
        return "推定不可"
    if strong_min is not None and value >= strong_min:
        return "強み候補"
    if watch_max is not None and value <= watch_max:
        return "要確認"
    return "中立"


def _format_percent(value: float | None) -> str:
    return "推定不可" if value is None else f"{value * 100:.1f}%"


def _format_number(value: float | None) -> str:
    return "推定不可" if value is None else f"{value:,.2f}"


def _policy_threshold(policy: dict[str, Any], section: str, key: str, default: float | None = None) -> float | None:
    return _num(policy.get("diagnostics", {}).get(section, {}).get(key, default))


def _industry_text(companies: pd.DataFrame) -> str:
    columns = ["jpx_industry", "broad_sector", "business_theme", "business_summary"]
    values: list[str] = []
    for column in columns:
        if column in companies.columns:
            values.extend(companies[column].dropna().astype(str).tolist())
    return " ".join(values)


def _industry_lenses(companies: pd.DataFrame, policy: dict[str, Any]) -> list[dict[str, Any]]:
    text = _industry_text(companies)
    matched = []
    for name, config in policy.get("industry_lenses", {}).items():
        keywords = [str(keyword) for keyword in config.get("keywords", [])]
        if any(keyword and keyword in text for keyword in keywords):
            matched.append({"name": name, **config})
    return matched


def _data_confidence(value: float | None, policy: dict[str, Any]) -> str:
    high_min = _policy_threshold(policy, "data_confidence", "high_min", 90)
    medium_min = _policy_threshold(policy, "data_confidence", "medium_min", 70)
    if value is None:
        return "低"
    if high_min is not None and value >= high_min:
        return "高"
    if medium_min is not None and value >= medium_min:
        return "中"
    return "低"


def _leader(latest: pd.DataFrame, column: str) -> str | None:
    if column not in latest.columns or latest[column].dropna().empty:
        return None
    sorted_latest = latest.sort_values(column, ascending=False, na_position="last")
    row = sorted_latest.iloc[0]
    return str(row.get("company_name", row.get("ticker")))


def _build_commentary(
    diagnostic_table: pd.DataFrame,
    latest: pd.DataFrame,
    companies: pd.DataFrame,
    app_mode: str,
    industry_mode: str,
    policy: dict[str, Any],
) -> list[str]:
    if diagnostic_table.empty:
        return ["推定不可"]

    growth_leader = _leader(latest, "growth_score")
    profitability_leader = _leader(latest, "profitability_score")
    stability_leader = _leader(latest, "stability_score")
    cashflow_leader = _leader(latest, "cashflow_score")

    lines = []
    leader_parts = []
    if growth_leader:
        leader_parts.append(f"成長性は{growth_leader}")
    if profitability_leader:
        leader_parts.append(f"収益性は{profitability_leader}")
    if stability_leader:
        leader_parts.append(f"財務安定性は{stability_leader}")
    if cashflow_leader:
        leader_parts.append(f"CF創出力は{cashflow_leader}")
    if leader_parts:
        lines.append("選択企業内の相対比較では、" + "、".join(leader_parts) + "が上位候補として確認される。")

    low_confidence = diagnostic_table[diagnostic_table["データ信頼度"] == "低"]["企業名"].astype(str).tolist()
    if low_confidence:
        lines.append(f"{'、'.join(low_confidence)}はデータ充足率が低く、一次資料確認を優先する。")

    if app_mode == "assignment":
        lines.append(
            "課題モードでは、条件適合の判定と財務上の優劣を混同しない。"
            f"特に業種判定モードが{industry_mode}の場合、比較理由と警告の扱いを本文で明記する。"
        )
    else:
        lines.append(
            "汎用分析では、業種差や事業モデル差を前提に、財務指標だけでなく事業ドライバーも並行して確認する。"
        )

    for lens in _industry_lenses(companies, policy):
        note = lens.get("note")
        if note:
            lines.append(str(note))
    return lines


def build_advanced_diagnostics(
    metrics: pd.DataFrame,
    companies: pd.DataFrame,
    *,
    app_mode: str,
    industry_mode: str,
    analysis_policy: dict[str, Any] | None = None,
) -> dict[str, object]:
    policy = analysis_policy or load_analysis_policy()
    if metrics.empty:
        return {
            "diagnostic_table": pd.DataFrame(),
            "commentary": ["推定不可"],
            "mode_notes": [],
            "industry_lenses": [],
        }

    scores = build_company_scores(metrics)
    latest = latest_metrics(metrics)
    if "_selection_order" in latest.columns:
        latest = latest.sort_values(["_selection_order", "ticker"]).reset_index(drop=True)
    latest = latest.merge(
        scores[
            [
                column
                for column in [
                    "ticker",
                    "data_completeness",
                    "analysis_quality_score",
                    "analysis_band",
                    "growth_score",
                    "profitability_score",
                    "stability_score",
                    "cashflow_score",
                ]
                if column in scores.columns
            ]
        ],
        on="ticker",
        how="left",
    )

    rows: list[dict[str, object]] = []
    for _, row in latest.iterrows():
        ticker = str(row["ticker"])
        history = metrics[metrics["ticker"].astype(str) == ticker].sort_values("fiscal_year")
        first = history.iloc[0]
        last = history.iloc[-1]
        if pd.notna(last.get("fiscal_year")) and pd.notna(first.get("fiscal_year")):
            periods = int(last["fiscal_year"] - first["fiscal_year"])
        else:
            periods = 0
        revenue_cagr = _safe_cagr(first.get("revenue"), last.get("revenue"), periods)
        first_margin = _num(first.get("operating_margin"))
        last_margin = _num(last.get("operating_margin"))
        margin_change = None if first_margin is None or last_margin is None else last_margin - first_margin
        cash_conversion = _safe_ratio(last.get("cash_flow_operating"), last.get("operating_income"))
        fcf_margin = _safe_ratio(last.get("fcf"), last.get("revenue"))
        capex_intensity = _safe_ratio(last.get("capex"), last.get("revenue"))
        equity_ratio = _num(last.get("equity_ratio"))
        safety_margin = _num(last.get("safety_margin"))
        data_completeness = _num(row.get("data_completeness"))

        rows.append(
            {
                "証券コード": ticker,
                "企業名": row.get("company_name", ticker),
                "データ信頼度": _data_confidence(data_completeness, policy),
                "売上CAGR": _format_percent(revenue_cagr),
                "売上トレンド判定": _label_by_threshold(
                    revenue_cagr,
                    _policy_threshold(policy, "cagr", "strong_min", 0.08),
                    _policy_threshold(policy, "cagr", "watch_max", 0),
                ),
                "営業利益率変化": _format_percent(margin_change),
                "利益率判定": _label_by_threshold(
                    margin_change,
                    _policy_threshold(policy, "margin_change", "improving_min", 0.01),
                    _policy_threshold(policy, "margin_change", "weakening_max", -0.01),
                ),
                "CF変換力": _format_number(cash_conversion),
                "CF判定": _label_by_threshold(
                    cash_conversion,
                    _policy_threshold(policy, "cash_conversion", "strong_min", 1.0),
                    _policy_threshold(policy, "cash_conversion", "watch_max", 0.6),
                ),
                "FCFマージン": _format_percent(fcf_margin),
                "投資負担": "重め"
                if capex_intensity is not None
                and capex_intensity >= (_policy_threshold(policy, "capex_intensity", "heavy_min", 0.08) or 0.08)
                else "通常" if capex_intensity is not None else "推定不可",
                "自己資本判定": _label_by_threshold(
                    equity_ratio,
                    _policy_threshold(policy, "equity_ratio", "strong_min", 0.45),
                    _policy_threshold(policy, "equity_ratio", "watch_max", 0.25),
                ),
                "損益分岐点余力": _label_by_threshold(
                    safety_margin,
                    _policy_threshold(policy, "safety_margin", "strong_min", 0.20),
                    _policy_threshold(policy, "safety_margin", "watch_max", 0.05),
                ),
                "総合分析スコア": _format_number(_num(row.get("analysis_quality_score"))),
                "総合判定": row.get("analysis_band", "推定不可"),
            }
        )

    diagnostic_table = pd.DataFrame(rows)
    commentary = _build_commentary(diagnostic_table, latest, companies, app_mode, industry_mode, policy)
    mode_notes = list(policy.get("modes", {}).get(app_mode, {}).get("emphasis", []))
    lenses = _industry_lenses(companies, policy)
    return {
        "diagnostic_table": diagnostic_table,
        "commentary": commentary,
        "mode_notes": mode_notes,
        "industry_lenses": lenses,
    }
