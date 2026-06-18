from src.company_master import select_companies
from src.data_loader import load_sample_dataset


def test_heavy_industry_companies_are_available_for_manual_search():
    dataset = load_sample_dataset()
    master = dataset.company_master

    heavy_tickers = {"7011", "7012", "7013"}

    assert heavy_tickers.issubset(set(master["ticker"]))
    assert master["company_name"].astype(str).str.contains("三菱重工業").any()
    assert master["business_theme"].astype(str).str.contains("重工").any()

    selected = select_companies(master, ["7011", "7013"])
    assert selected["company_name"].tolist() == ["三菱重工業", "IHI"]

    for frame in [dataset.financials, dataset.market_data, dataset.manual_kpis]:
        assert heavy_tickers.issubset(set(frame["ticker"]))
