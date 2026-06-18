from __future__ import annotations

import pandas as pd

from ..company_master import normalize_ticker_column


METRIC_LABELS = {
    "revenue_growth_rate": "売上高成長率",
    "operating_margin": "営業利益率",
    "roa": "ROA",
    "roe": "ROE",
    "asset_turnover": "総資産回転率",
    "net_margin": "当期利益率",
    "financial_leverage": "財務レバレッジ",
    "current_ratio": "流動比率",
    "equity_ratio": "自己資本比率",
    "debt_ratio": "負債比率",
    "fixed_ratio": "固定比率",
    "fixed_long_term_adequacy_ratio": "固定長期適合率",
    "fcf": "FCF",
    "break_even_sales": "損益分岐点売上高",
    "safety_margin": "安全余裕率",
    "operating_leverage": "営業レバレッジ",
    "fcf_margin": "FCFマージン",
    "per": "PER",
    "pbr": "PBR",
}

KEY_METRICS = list(METRIC_LABELS.keys())


def _numeric(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    converted = df.copy()
    for column in columns:
        if column in converted.columns:
            converted[column] = pd.to_numeric(converted[column], errors="coerce")
    return converted


def _safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    denom = pd.to_numeric(denominator, errors="coerce").replace(0, pd.NA)
    numer = pd.to_numeric(numerator, errors="coerce")
    return numer.divide(denom)


def compute_financial_metrics(
    financials: pd.DataFrame,
    market_data: pd.DataFrame,
    manual_kpis: pd.DataFrame,
) -> pd.DataFrame:
    financials = normalize_ticker_column(financials)
    market_data = normalize_ticker_column(market_data)
    manual_kpis = normalize_ticker_column(manual_kpis)

    numeric_financials = [
        "fiscal_year",
        "revenue",
        "operating_income",
        "net_income",
        "total_assets",
        "equity",
        "current_assets",
        "current_liabilities",
        "fixed_assets",
        "long_term_liabilities",
        "cash_flow_operating",
        "capex",
        "shares_outstanding",
    ]
    financials = _numeric(financials, numeric_financials)
    market_data = _numeric(market_data, ["fiscal_year", "share_price", "market_cap", "eps", "bps", "per", "pbr"])
    manual_kpis = _numeric(manual_kpis, ["fiscal_year", "variable_cost_ratio", "fixed_cost_estimate"])

    df = financials.merge(market_data, on=["ticker", "fiscal_year"], how="left")
    df = df.merge(manual_kpis, on=["ticker", "fiscal_year"], how="left")
    df = df.sort_values(["ticker", "fiscal_year"]).reset_index(drop=True)

    grouped = df.groupby("ticker", group_keys=False)
    previous_revenue = grouped["revenue"].shift(1)
    previous_assets = grouped["total_assets"].shift(1)
    previous_equity = grouped["equity"].shift(1)
    average_assets = (df["total_assets"] + previous_assets.fillna(df["total_assets"])) / 2
    average_equity = (df["equity"] + previous_equity.fillna(df["equity"])) / 2

    df["revenue_growth_rate"] = _safe_divide(df["revenue"] - previous_revenue, previous_revenue)
    df["operating_margin"] = _safe_divide(df["operating_income"], df["revenue"])
    df["net_margin"] = _safe_divide(df["net_income"], df["revenue"])
    df["roa"] = _safe_divide(df["net_income"], average_assets)
    df["roe"] = _safe_divide(df["net_income"], average_equity)
    df["asset_turnover"] = _safe_divide(df["revenue"], average_assets)
    df["financial_leverage"] = _safe_divide(average_assets, average_equity)
    df["roa_decomposed"] = df["net_margin"] * df["asset_turnover"]
    df["roe_decomposed"] = df["net_margin"] * df["asset_turnover"] * df["financial_leverage"]
    df["current_ratio"] = _safe_divide(df["current_assets"], df["current_liabilities"])
    df["equity_ratio"] = _safe_divide(df["equity"], df["total_assets"])
    df["debt_ratio"] = _safe_divide(df["total_assets"] - df["equity"], df["equity"])
    df["fixed_ratio"] = _safe_divide(df["fixed_assets"], df["equity"])
    df["fixed_long_term_adequacy_ratio"] = _safe_divide(
        df["fixed_assets"], df["equity"] + df["long_term_liabilities"]
    )
    df["fcf"] = df["cash_flow_operating"] - df["capex"]
    df["fcf_margin"] = _safe_divide(df["fcf"], df["revenue"])
    contribution_margin_ratio = 1 - df["variable_cost_ratio"]
    df["contribution_margin"] = df["revenue"] * contribution_margin_ratio
    df["break_even_sales"] = _safe_divide(df["fixed_cost_estimate"], contribution_margin_ratio)
    df["safety_margin"] = _safe_divide(df["revenue"] - df["break_even_sales"], df["revenue"])
    df["operating_leverage"] = _safe_divide(df["contribution_margin"], df["operating_income"])
    return df


def latest_metrics(metrics: pd.DataFrame) -> pd.DataFrame:
    if metrics.empty:
        return metrics.copy()
    idx = metrics.sort_values(["ticker", "fiscal_year"]).groupby("ticker")["fiscal_year"].idxmax()
    return metrics.loc[idx].sort_values("ticker").reset_index(drop=True)
