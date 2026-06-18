from __future__ import annotations

from typing import Any

import pandas as pd

from .config_loader import load_analysis_policy
from .metrics.financial import latest_metrics


OUTLIER_LIMITS = {
    "operating_margin": (-1.0, 1.0),
    "net_margin": (-1.0, 1.0),
    "fcf_margin": (-1.5, 1.5),
}

OUTLIER_LABELS = {
    "operating_margin": "営業利益率",
    "net_margin": "当期利益率",
    "fcf_margin": "FCFマージン",
}

PLUS_ALPHA_MISSING_REASONS = {
    "ROA / ROE分解": "当期利益率、総資産回転率、財務レバレッジ、ROA、ROEが必要",
    "損益分岐点分析": "固定費・変動費が必要",
    "売上増減分析": "売上高、前年比、客数・単価・数量・店舗数などの分解データが必要",
    "利益増減分析": "営業利益、営業利益率、原材料費、人件費、為替などの要因データが必要",
    "4P / 4C分析": "商品・価格・流通・販促・顧客便益・顧客負担データが必要",
    "顧客関係分析": "リピート率、会員制度、顧客単価、顧客接点データが必要",
    "バリューチェーン分析": "調達、製造、物流、販売、サービスの工程別データが必要",
    "FCF分析": "営業CF、設備投資、FCFが必要",
    "PER / PBR比較": "株価、EPS、BPS、PER、PBRが必要",
    "将来シナリオ分析": "外部環境、原材料費、人件費、為替、投資計画などの追加情報が必要",
    "付加価値分析": "人件費、減価償却費、支払利息、税金などの詳細データが必要",
    "利益処分状況の分析": "配当、内部留保、自己株式取得などの利益処分データが必要",
}


def _num(value: object) -> float | None:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return None
    return float(numeric)


def _is_outlier(value: object, column: str) -> bool:
    numeric = _num(value)
    limits = OUTLIER_LIMITS.get(column)
    if numeric is None or limits is None:
        return False
    low, high = limits
    return numeric < low or numeric > high


def _fmt_percent(value: object, missing_label: str = "推定不可") -> str:
    numeric = _num(value)
    return missing_label if numeric is None else f"{numeric * 100:.1f}%"


def _fmt_number(value: object, missing_label: str = "推定不可") -> str:
    numeric = _num(value)
    if numeric is None:
        return missing_label
    if abs(numeric) >= 100:
        return f"{numeric:,.0f}"
    return f"{numeric:,.2f}"


def _safe_text(value: object, missing_label: str = "推定不可") -> str:
    if value is None or pd.isna(value):
        return missing_label
    text = str(value).strip()
    return text if text else missing_label


def _change_text(current: object, previous: object, missing_label: str) -> str:
    current_value = _num(current)
    previous_value = _num(previous)
    if current_value is None or previous_value is None:
        return missing_label
    diff = current_value - previous_value
    pct = None if previous_value == 0 else diff / previous_value
    if pct is None:
        return f"{diff:,.0f}百万円変化、前年比は{missing_label}"
    return f"{diff:,.0f}百万円変化、前年比{pct * 100:.1f}%"


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


def _driver_text(companies: pd.DataFrame, policy: dict[str, Any], missing_label: str) -> str:
    lenses = _matched_lenses(companies, policy)
    drivers: list[str] = []
    for lens in lenses:
        drivers.extend(str(driver) for driver in lens.get("drivers", []))
    if not drivers:
        return missing_label
    unique = list(dict.fromkeys(drivers))
    return "、".join(unique)


def _scenario_text(companies: pd.DataFrame, policy: dict[str, Any], missing_label: str) -> str:
    notes = [str(lens.get("note")) for lens in _matched_lenses(companies, policy) if lens.get("note")]
    if not notes:
        return missing_label
    return " ".join(notes)


def _decomposition_type(row: pd.Series, latest: pd.DataFrame, missing_label: str) -> str:
    components = {
        "利益率型": "net_margin",
        "資産回転型": "asset_turnover",
        "財務レバレッジ型": "financial_leverage",
    }
    scores: dict[str, float] = {}
    for label, column in components.items():
        value = _num(row.get(column))
        if value is None or column not in latest.columns:
            continue
        median = _num(latest[column].median())
        if median is None or median == 0:
            continue
        scores[label] = value / median
    if not scores:
        return missing_label
    leader = max(scores, key=scores.get)
    return f"{leader}の特徴が相対的に強い"


def build_required_plus_alpha_table(analysis_policy: dict[str, Any] | None = None) -> pd.DataFrame:
    policy = analysis_policy or load_analysis_policy()
    framework = policy.get("required_alpha_framework", {})
    rows: list[dict[str, str]] = []
    for item in framework.get("required", []):
        rows.append(
            {
                "区分": "必須",
                "項目": str(item.get("name", "")),
                "意味": str(item.get("description", "")),
                "ツールでの扱い": str(item.get("output", "")),
            }
        )
    for item in framework.get("plus_alpha", []):
        columns = item.get("data_columns", [])
        data_note = "、".join(columns) if columns else "業種別観点または追加データ"
        rows.append(
            {
                "区分": "＋α",
                "項目": str(item.get("name", "")),
                "意味": str(item.get("description", "")),
                "ツールでの扱い": data_note,
            }
        )
    return pd.DataFrame(rows)


def build_plus_alpha_analysis_table(
    metrics: pd.DataFrame,
    companies: pd.DataFrame,
    *,
    analysis_policy: dict[str, Any] | None = None,
    missing_label: str = "推定不可",
) -> pd.DataFrame:
    policy = analysis_policy or load_analysis_policy()
    if metrics.empty:
        return pd.DataFrame()

    latest = latest_metrics(metrics)
    if "_selection_order" in latest.columns:
        latest = latest.sort_values(["_selection_order", "ticker"]).reset_index(drop=True)

    rows: list[dict[str, str]] = []
    for _, row in latest.iterrows():
        ticker = str(row.get("ticker"))
        company_scope = companies[companies["ticker"].astype(str) == ticker]
        if company_scope.empty:
            company_scope = companies
        history = metrics[metrics["ticker"].astype(str) == ticker].sort_values("fiscal_year")
        previous = history.iloc[-2] if len(history) >= 2 else pd.Series(dtype=object)
        revenue_change = _change_text(row.get("revenue"), previous.get("revenue"), missing_label)
        profit_change = _change_text(row.get("operating_income"), previous.get("operating_income"), missing_label)
        margin_change = None
        if not previous.empty:
            current_margin = _num(row.get("operating_margin"))
            previous_margin = _num(previous.get("operating_margin"))
            if current_margin is not None and previous_margin is not None:
                margin_change = current_margin - previous_margin
        drivers = _driver_text(company_scope, policy, missing_label)
        scenario = _scenario_text(company_scope, policy, missing_label)

        rows.append(
            {
                "企業名": str(row.get("company_name", ticker)),
                "ROA/ROE分解": (
                    f"{_decomposition_type(row, latest, missing_label)}。"
                    f"当期利益率{_fmt_percent(row.get('net_margin'), missing_label)}、"
                    f"総資産回転率{_fmt_number(row.get('asset_turnover'), missing_label)}、"
                    f"財務レバレッジ{_fmt_number(row.get('financial_leverage'), missing_label)}。"
                ),
                "損益分岐点・安全余裕率": (
                    f"損益分岐点売上高{_fmt_number(row.get('break_even_sales'), missing_label)}、"
                    f"安全余裕率{_fmt_percent(row.get('safety_margin'), missing_label)}、"
                    f"営業レバレッジ{_fmt_number(row.get('operating_leverage'), missing_label)}。"
                ),
                "売上増減分析": (
                    f"{revenue_change}。客数、単価、店舗数、稼働率の内訳は"
                    f"{missing_label}のため、追加KPIで確認する。"
                ),
                "利益増減分析": (
                    f"{profit_change}。営業利益率変化は{_fmt_percent(margin_change, missing_label)}。"
                    f"主な確認要因は{drivers}。"
                ),
                "4P/4C": f"4P: {_safe_text(row.get('four_p'), missing_label)} / 4C: {_safe_text(row.get('four_c'), missing_label)}",
                "顧客関係": _safe_text(row.get("customer_relationship"), missing_label),
                "バリューチェーン": _safe_text(row.get("value_chain_note"), missing_label),
                "FCF分析": (
                    f"営業CF{_fmt_number(row.get('cash_flow_operating'), missing_label)}、"
                    f"投資負担{_fmt_number(row.get('capex'), missing_label)}、"
                    f"FCF{_fmt_number(row.get('fcf'), missing_label)}。"
                ),
                "PER/PBR": (
                    f"PER{_fmt_number(row.get('per'), missing_label)}、"
                    f"PBR{_fmt_number(row.get('pbr'), missing_label)}。市場評価の補助指標として扱う。"
                ),
                "将来シナリオ": scenario,
                "付加価値分析": f"{missing_label}。人件費、減価償却費、支払利息、税金などの詳細データが必要。",
                "利益処分状況": f"{missing_label}。配当、内部留保、自己株式取得などの詳細データが必要。",
            }
        )
    return pd.DataFrame(rows)


def build_plus_alpha_status_table(
    metrics: pd.DataFrame,
    *,
    analysis_policy: dict[str, Any] | None = None,
    missing_label: str = "推定不可",
) -> pd.DataFrame:
    policy = analysis_policy or load_analysis_policy()
    framework = policy.get("required_alpha_framework", {})
    if metrics.empty:
        return pd.DataFrame(
            [
                {
                    "＋α項目": str(item.get("name", "")),
                    "状態": "未実施／推定不可",
                    "判定メモ": f"{missing_label}。{PLUS_ALPHA_MISSING_REASONS.get(str(item.get('name', '')), '追加データが必要')}",
                    "追加で必要なデータ": PLUS_ALPHA_MISSING_REASONS.get(str(item.get("name", "")), "追加データが必要"),
                }
                for item in framework.get("plus_alpha", [])
            ]
        )

    latest = latest_metrics(metrics)
    rows: list[dict[str, str]] = []
    for item in framework.get("plus_alpha", []):
        name = str(item.get("name", ""))
        columns = [str(column) for column in item.get("data_columns", [])]
        existing = [column for column in columns if column in latest.columns]
        total_required = len(columns) * max(len(latest), 1)
        available = int(latest[existing].notna().sum().sum()) if existing else 0
        required_met = total_required > 0 and available == total_required and len(existing) == len(columns)
        partial = available > 0

        if required_met:
            status = "実施済み"
        elif partial:
            status = "一部実施"
        else:
            status = "未実施／推定不可"

        outlier_columns = [
            column
            for column in existing
            if column in OUTLIER_LIMITS and latest[column].apply(lambda value: _is_outlier(value, column)).any()
        ]
        outlier_note = ""
        if outlier_columns:
            status = "一部実施" if status == "実施済み" else status
            outlier_note = "。ただし桁異常あり: " + "、".join(OUTLIER_LABELS[column] for column in outlier_columns)

        missing_columns = [column for column in columns if column not in existing or latest[column].isna().any()]
        missing_text = "、".join(missing_columns) if missing_columns else "なし"
        reason = PLUS_ALPHA_MISSING_REASONS.get(name, "追加データが必要")
        if status == "実施済み":
            memo = f"必要データを確認済み{outlier_note}。"
        elif status == "一部実施":
            memo = f"一部データを確認済み。未充足: {missing_text}{outlier_note}。"
        else:
            memo = f"未実施。{reason}"
        rows.append(
            {
                "＋α項目": name,
                "状態": status,
                "判定メモ": memo,
                "追加で必要なデータ": reason,
            }
        )
    return pd.DataFrame(rows)


def build_plus_alpha_commentary(plus_alpha_table: pd.DataFrame, missing_label: str = "推定不可") -> list[str]:
    if plus_alpha_table.empty:
        return [missing_label]
    comments = [
        "＋α分析では、売上・利益・ROEの表だけで終わらせず、差が出た理由と今後の見方を補う。",
        "損益分岐点、安全余裕率、営業レバレッジは、固定費構造と売上変動への利益感応度を見るための中心項目である。",
    ]
    if plus_alpha_table.astype(str).apply(lambda col: col.str.contains(missing_label, regex=False)).any().any():
        comments.append(f"{missing_label}の項目は、EDINETや企業開示資料、店舗KPIなどで追加確認する。")
    return comments
