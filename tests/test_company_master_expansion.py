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


def test_manual_company_search_handles_heavy_industry_and_literal_symbols():
    from app import _filter_company_master

    master = load_sample_dataset().company_master

    by_name = _filter_company_master(master, "三菱重工業")
    by_theme = _filter_company_master(master, "重工")
    by_symbol = _filter_company_master(master, "?")

    assert by_name["ticker"].tolist() == ["7011"]
    assert {"7011", "7012", "7013"}.issubset(set(by_theme["ticker"]))
    assert by_symbol.empty


def test_sample_directory_has_broader_edinet_enabled_candidates():
    from app import _filter_company_master

    dataset = load_sample_dataset()
    master = dataset.company_master
    broad_tickers = {"7203", "7267", "7201", "2802", "2801", "2002", "6758", "6501", "8058"}

    assert broad_tickers.issubset(set(master["ticker"]))
    assert broad_tickers.issubset(set(dataset.financials["ticker"]))
    assert broad_tickers.issubset(set(dataset.market_data["ticker"]))
    assert broad_tickers.issubset(set(dataset.manual_kpis["ticker"]))
    assert master.loc[master["ticker"].isin(broad_tickers), "edinet_code"].str.startswith("E").all()

    auto_candidates = _filter_company_master(master, "自動車")
    food_candidates = _filter_company_master(master, "食品")
    industry_candidates = _filter_company_master(master, "工業")

    assert {"7203", "7267", "7201"}.issubset(set(auto_candidates["ticker"]))
    assert {"2802", "2801", "2002"}.issubset(set(food_candidates["ticker"]))
    assert {"7011", "7012"}.issubset(set(industry_candidates["ticker"]))


def test_edinet_lookup_preview_table_normalizes_sec_code():
    from app import _edinet_lookup_preview_table

    table = _edinet_lookup_preview_table(
        [
            {
                "sec_code": "99990",
                "filer_name": "テスト株式会社",
                "edinet_code": "E99999",
                "doc_description": "四半期報告書",
                "submit_datetime": "2026-06-18 10:00",
                "csv_flag": "1",
                "raw_json": {"docID": "S100TEST"},
            }
        ]
    )

    assert table.loc[0, "証券コード"] == "9999"
    assert table.loc[0, "CSV"] == "あり"


def test_latest_csv_filings_by_ticker_picks_one_per_company():
    import pandas as pd

    from app import _infer_fiscal_year_from_filing, _latest_csv_filings_by_ticker

    filings = pd.DataFrame(
        [
            {
                "doc_id": "OLD",
                "sec_code": "35430",
                "submit_datetime": "2025-06-20 10:00",
                "csv_flag": "1",
            },
            {
                "doc_id": "NEW",
                "sec_code": "35430",
                "submit_datetime": "2026-06-20 10:00",
                "csv_flag": "1",
            },
            {
                "doc_id": "OTHER",
                "sec_code": "30870",
                "submit_datetime": "2026-06-21 10:00",
                "csv_flag": "1",
            },
        ]
    )

    latest = _latest_csv_filings_by_ticker(filings, ["3543", "3087"])

    assert latest["doc_id"].tolist() == ["NEW", "OTHER"]
    assert latest["_ticker"].tolist() == ["3543", "3087"]
    assert _infer_fiscal_year_from_filing(latest.iloc[0]) == 2026
