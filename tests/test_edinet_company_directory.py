import pandas as pd

from src.data_loader import load_sample_dataset
from src.edinet_company_directory import (
    build_company_directory_from_filings,
    merge_company_master_with_edinet_filings,
    overlay_dataset_company_master,
    ticker_from_sec_code,
)


def test_ticker_from_sec_code_normalizes_edinet_security_code():
    assert ticker_from_sec_code("70110") == "7011"
    assert ticker_from_sec_code(" 72030 ") == "7203"
    assert ticker_from_sec_code("ABC") == ""


def test_build_company_directory_from_filings_keeps_latest_submitter_row():
    filings = pd.DataFrame(
        [
            {
                "doc_id": "OLD",
                "edinet_code": "EOLD",
                "sec_code": "99990",
                "filer_name": "Old Company",
                "submit_datetime": "2025-06-01 10:00",
            },
            {
                "doc_id": "NEW",
                "edinet_code": "ENEW",
                "sec_code": "99990",
                "filer_name": "New Company",
                "submit_datetime": "2026-06-01 10:00",
            },
            {
                "doc_id": "NOSEC",
                "edinet_code": "ENONE",
                "sec_code": "",
                "filer_name": "No Sec Code",
                "submit_datetime": "2026-06-02 10:00",
            },
        ]
    )

    directory = build_company_directory_from_filings(filings)

    assert directory["ticker"].tolist() == ["9999"]
    assert directory.loc[0, "company_name"] == "New Company"
    assert directory.loc[0, "edinet_code"] == "ENEW"
    assert directory.loc[0, "source_note"] == "EDINET documents API cache"


def test_merge_company_master_with_edinet_filings_preserves_sample_master():
    dataset = load_sample_dataset()
    filings = pd.DataFrame(
        [
            {
                "doc_id": "SAMPLE",
                "edinet_code": "E99999",
                "sec_code": "99990",
                "filer_name": "Added Company",
                "submit_datetime": "2026-06-01 10:00",
            },
            {
                "doc_id": "EXISTING",
                "edinet_code": "E99998",
                "sec_code": "70110",
                "filer_name": "Should Not Override",
                "submit_datetime": "2026-06-01 10:00",
            },
        ]
    )

    merged = merge_company_master_with_edinet_filings(dataset.company_master, filings)

    assert "9999" in set(merged["ticker"])
    assert "7011" in set(merged["ticker"])
    assert merged[merged["ticker"] == "9999"].iloc[0]["company_name"] == "Added Company"
    assert merged[merged["ticker"] == "7011"].iloc[0]["company_name"] != "Should Not Override"


def test_overlay_dataset_company_master_keeps_financial_frames_unchanged():
    dataset = load_sample_dataset()
    filings = pd.DataFrame(
        [
            {
                "doc_id": "SAMPLE",
                "edinet_code": "E99999",
                "sec_code": "99990",
                "filer_name": "Added Company",
                "submit_datetime": "2026-06-01 10:00",
            }
        ]
    )

    overlaid = overlay_dataset_company_master(dataset, filings)

    assert "9999" in set(overlaid.company_master["ticker"])
    assert overlaid.financials.equals(dataset.financials)
    assert overlaid.market_data.equals(dataset.market_data)
    assert overlaid.manual_kpis.equals(dataset.manual_kpis)
