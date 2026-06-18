from src.analysis_engine import (
    build_dupont_driver_table,
    build_management_issue_table,
    build_profit_bridge_table,
    build_sensitivity_risk_table,
)
from src.company_master import select_companies
from src.course_framework import build_plus_alpha_analysis_table, build_required_plus_alpha_table
from src.data_loader import load_sample_dataset
from src.metrics.financial import compute_financial_metrics


def _sample_metrics(tickers):
    dataset = load_sample_dataset()
    companies = select_companies(dataset.company_master, tickers).copy()
    companies["_selection_order"] = range(len(companies))
    metrics = compute_financial_metrics(
        dataset.financials[dataset.financials["ticker"].isin(tickers)],
        dataset.market_data[dataset.market_data["ticker"].isin(tickers)],
        dataset.manual_kpis[dataset.manual_kpis["ticker"].isin(tickers)],
    )
    metrics = metrics.merge(companies[["ticker", "company_name", "_selection_order"]], on="ticker", how="left")
    return metrics, companies


def test_required_plus_alpha_framework_is_explicit():
    table = build_required_plus_alpha_table()

    assert {"必須", "＋α"} <= set(table["区分"])
    assert "損益分岐点分析" in set(table["項目"])
    assert "ROA / ROE分解" in set(table["項目"])


def test_plus_alpha_analysis_covers_course_items_and_missing_notes():
    metrics, companies = _sample_metrics(["3543", "3087"])

    table = build_plus_alpha_analysis_table(metrics, companies)

    assert len(table) == 2
    assert "ROA/ROE分解" in table.columns
    assert "損益分岐点・安全余裕率" in table.columns
    assert "売上増減分析" in table.columns
    assert "将来シナリオ" in table.columns
    assert table["付加価値分析"].str.contains("推定不可", regex=False).all()


def test_advanced_algorithm_tables_are_generated():
    metrics, _companies = _sample_metrics(["3543", "3087"])

    dupont = build_dupont_driver_table(metrics)
    bridge = build_profit_bridge_table(metrics)
    risk = build_sensitivity_risk_table(metrics)
    issues = build_management_issue_table(
        metrics,
        _companies,
        app_mode="assignment",
        industry_mode="business_theme",
    )

    assert len(dupont) == 2
    assert "主なROE要因" in dupont.columns
    assert len(bridge) == 2
    assert "売上要因" in bridge.columns
    assert len(risk) == 2
    assert "売上1%増減時の営業利益変化率目安" in risk.columns
    assert len(issues) == 2
    assert "強み候補" in issues.columns
    assert issues["注意点"].str.contains("業種一致警告", regex=False).any()
