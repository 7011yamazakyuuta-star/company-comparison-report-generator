import pandas as pd

from src.metrics.financial import compute_financial_metrics


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

