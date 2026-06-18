from __future__ import annotations

import pandas as pd

from src.analysis_dataset import (
    DATA_SOURCE_EDINET_OVERLAY,
    DATA_SOURCE_SAMPLE,
    build_data_source_audit,
    prepare_analysis_dataset,
)
from src.data_loader import Dataset


def _dataset() -> Dataset:
    return Dataset(
        company_master=pd.DataFrame(
            [
                {"ticker": "3543", "company_name": "コメダHD"},
                {"ticker": "3087", "company_name": "ドトール・日レスHD"},
            ]
        ),
        financials=pd.DataFrame(
            [
                {
                    "ticker": "3543",
                    "fiscal_year": 2024,
                    "revenue": 100,
                    "operating_income": 10,
                    "net_income": 6,
                    "total_assets": 200,
                    "equity": 120,
                    "current_assets": 80,
                    "current_liabilities": 40,
                    "fixed_assets": 100,
                    "long_term_liabilities": 30,
                    "cash_flow_operating": 20,
                    "capex": 5,
                    "shares_outstanding": 10,
                },
                {
                    "ticker": "3087",
                    "fiscal_year": 2024,
                    "revenue": 300,
                    "operating_income": 20,
                    "net_income": 12,
                    "total_assets": 400,
                    "equity": 250,
                    "current_assets": 160,
                    "current_liabilities": 80,
                    "fixed_assets": 200,
                    "long_term_liabilities": 60,
                    "cash_flow_operating": 30,
                    "capex": 8,
                    "shares_outstanding": 20,
                },
            ]
        ),
        market_data=pd.DataFrame(columns=["ticker", "fiscal_year"]),
        manual_kpis=pd.DataFrame(columns=["ticker", "fiscal_year"]),
    )


def test_prepare_analysis_dataset_keeps_sample_by_default() -> None:
    prepared = prepare_analysis_dataset(_dataset(), ["3543"], source_mode=DATA_SOURCE_SAMPLE)

    row = prepared.dataset.financials[prepared.dataset.financials["ticker"] == "3543"].iloc[0]

    assert row["revenue"] == 100
    assert prepared.edinet_rows.empty
    assert prepared.source_summary["data_source"].tolist() == ["sample_csv"]


def test_prepare_analysis_dataset_overlays_matching_edinet_candidate() -> None:
    edinet_rows = pd.DataFrame(
        [
            {
                "doc_id": "S100TEST",
                "ticker": "3543",
                "fiscal_year": 2024,
                "revenue": 43291,
                "operating_income": 8932,
                "net_income": 6015,
                "total_assets": 153600,
                "equity": 66980,
                "current_assets": 26700,
                "current_liabilities": 17850,
                "fixed_assets": 113200,
                "long_term_liabilities": 48500,
                "cash_flow_operating": 9200,
                "capex": 3100,
            }
        ]
    )

    prepared = prepare_analysis_dataset(
        _dataset(),
        ["3543", "3087"],
        source_mode=DATA_SOURCE_EDINET_OVERLAY,
        edinet_rows=edinet_rows,
    )
    rows = prepared.dataset.financials.sort_values("ticker").reset_index(drop=True)
    komeda = rows[rows["ticker"] == "3543"].iloc[0]
    doutor = rows[rows["ticker"] == "3087"].iloc[0]

    assert komeda["revenue"] == 43291
    assert komeda["operating_income"] == 8932
    assert doutor["revenue"] == 300
    assert set(prepared.source_summary["data_source"]) == {"sample_csv", "edinet_candidate"}


def test_build_data_source_audit_marks_partial_edinet_rows() -> None:
    summary = pd.DataFrame(
        [
            {
                "ticker": "3543",
                "fiscal_year": 2024,
                "data_source": "edinet_candidate",
                "doc_id": "S100TEST",
                "available_metrics": 3,
                "missing_metrics": 10,
            },
            {
                "ticker": "3087",
                "fiscal_year": 2024,
                "data_source": "sample_csv",
                "doc_id": "",
                "available_metrics": 13,
                "missing_metrics": 0,
            },
        ]
    )

    audit = build_data_source_audit(summary)

    assert audit.loc[0, "status"] == "partial"
    assert audit.loc[0, "coverage_rate"] == 3 / 13
    assert audit.loc[1, "status"] == "sample"
