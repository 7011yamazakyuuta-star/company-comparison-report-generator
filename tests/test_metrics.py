import pandas as pd

from src.metrics.financial import compute_financial_metrics
from src.metrics.scoring import build_company_scores


def test_metrics_do_not_crash_on_zero_division():
    financials = pd.DataFrame(
        [
            {
                "ticker": "0001",
                "fiscal_year": 2024,
                "revenue": 0,
                "operating_income": 10,
                "net_income": 5,
                "total_assets": 0,
                "equity": 0,
                "current_assets": 0,
                "current_liabilities": 0,
                "fixed_assets": 0,
                "long_term_liabilities": 0,
                "cash_flow_operating": 100,
                "capex": 40,
                "cash_flow_investing": -40,
                "cash_flow_financing": 0,
                "shares_outstanding": 1,
            }
        ]
    )
    market = pd.DataFrame([{"ticker": "0001", "fiscal_year": 2024, "share_price": 1, "market_cap": 1}])
    manual = pd.DataFrame([{"ticker": "0001", "fiscal_year": 2024, "variable_cost_ratio": 1, "fixed_cost_estimate": 10}])

    metrics = compute_financial_metrics(financials, market, manual)

    assert len(metrics) == 1
    assert pd.isna(metrics.loc[0, "operating_margin"])
    assert pd.isna(metrics.loc[0, "break_even_sales"])
    assert metrics.loc[0, "fcf"] == 60


def test_company_scores_are_relative_and_handle_missing_values():
    financials = pd.DataFrame(
        [
            {
                "ticker": "0001",
                "fiscal_year": 2023,
                "revenue": 100,
                "operating_income": 12,
                "net_income": 8,
                "total_assets": 80,
                "equity": 40,
                "current_assets": 30,
                "current_liabilities": 15,
                "fixed_assets": 50,
                "long_term_liabilities": 20,
                "cash_flow_operating": 14,
                "capex": 4,
                "shares_outstanding": 1,
            },
            {
                "ticker": "0001",
                "fiscal_year": 2024,
                "revenue": 125,
                "operating_income": 18,
                "net_income": 12,
                "total_assets": 90,
                "equity": 48,
                "current_assets": 34,
                "current_liabilities": 16,
                "fixed_assets": 56,
                "long_term_liabilities": 22,
                "cash_flow_operating": 20,
                "capex": 6,
                "shares_outstanding": 1,
            },
            {
                "ticker": "0002",
                "fiscal_year": 2023,
                "revenue": 100,
                "operating_income": 8,
                "net_income": 4,
                "total_assets": 100,
                "equity": 20,
                "current_assets": 20,
                "current_liabilities": 18,
                "fixed_assets": 80,
                "long_term_liabilities": 40,
                "cash_flow_operating": 8,
                "capex": 5,
                "shares_outstanding": 1,
            },
            {
                "ticker": "0002",
                "fiscal_year": 2024,
                "revenue": 104,
                "operating_income": 7,
                "net_income": 3,
                "total_assets": 108,
                "equity": 22,
                "current_assets": 22,
                "current_liabilities": 20,
                "fixed_assets": 86,
                "long_term_liabilities": 42,
                "cash_flow_operating": 7,
                "capex": 5,
                "shares_outstanding": 1,
            },
        ]
    )
    market = pd.DataFrame(
        [
            {"ticker": "0001", "fiscal_year": 2024, "share_price": 10, "market_cap": 100, "per": 10, "pbr": 1},
            {"ticker": "0002", "fiscal_year": 2024, "share_price": 10, "market_cap": 100, "per": None, "pbr": None},
        ]
    )
    manual = pd.DataFrame(
        [
            {"ticker": "0001", "fiscal_year": 2024, "variable_cost_ratio": 0.6, "fixed_cost_estimate": 10},
            {"ticker": "0002", "fiscal_year": 2024, "variable_cost_ratio": 0.7, "fixed_cost_estimate": 8},
        ]
    )

    metrics = compute_financial_metrics(financials, market, manual)
    scores = build_company_scores(metrics)

    assert len(scores) == 2
    assert "analysis_quality_score" in scores.columns
    assert scores["analysis_quality_score"].notna().all()
    assert scores.loc[scores["ticker"] == "0002", "data_completeness"].iloc[0] < 100
