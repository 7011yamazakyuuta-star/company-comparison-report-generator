from __future__ import annotations

import zipfile
from pathlib import Path

import pandas as pd

from src.edinet_parser import (
    EdinetCsvFact,
    extract_financial_facts_from_zip,
    facts_to_financial_row,
    list_csv_members,
    summarize_facts,
)
from src.edinet_repository import load_edinet_financial_rows, load_extracted_facts, save_extracted_facts


def _write_zip(path: Path, content: str, *, member_name: str = "XBRL_TO_CSV/sample.csv", encoding: str = "utf-8-sig") -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(member_name, content.encode(encoding))


def test_edinet_parser_extracts_financial_facts_from_csv_zip(tmp_path: Path) -> None:
    zip_path = tmp_path / "csv.zip"
    _write_zip(
        zip_path,
        "\n".join(
            [
                "要素ID,項目名,コンテキスト,値",
                "jpcrp_cor:NetSales,売上高,CurrentYearDuration,43291",
                "jpcrp_cor:OperatingIncome,営業利益,CurrentYearDuration,\"8,932\"",
                "jpcrp_cor:Assets,資産合計,CurrentYearInstant,153600",
                "jpcrp_cor:CurrentLiabilities,流動負債合計,CurrentYearInstant,17850",
            ]
        ),
    )

    facts = extract_financial_facts_from_zip(zip_path)
    summary = summarize_facts(facts)
    row = facts_to_financial_row(ticker="3543", fiscal_year=2024, facts=facts)

    assert list_csv_members(zip_path) == ["XBRL_TO_CSV/sample.csv"]
    assert set(summary["metric"]) >= {"revenue", "operating_income", "total_assets", "current_liabilities"}
    assert row["ticker"] == "3543"
    assert row["fiscal_year"] == 2024
    assert row["revenue"] == 43291
    assert row["operating_income"] == 8932
    assert row["total_assets"] == 153600
    assert row["current_liabilities"] == 17850


def test_edinet_parser_handles_utf16_tsv_and_empty_matches(tmp_path: Path) -> None:
    zip_path = tmp_path / "csv.zip"
    _write_zip(
        zip_path,
        "\n".join(
            [
                "element\tlabel\tcontextRef\tvalue",
                "jpcrp_cor:CashFlowsFromOperatingActivities\t営業活動によるキャッシュ・フロー\tCurrentYearDuration\t9200",
                "jpcrp_cor:Unknown\tその他\tCurrentYearDuration\tabc",
            ]
        ),
        member_name="PublicDoc/sample.tsv",
        encoding="utf-16",
    )

    facts = extract_financial_facts_from_zip(zip_path)
    summary = summarize_facts(facts)
    row = facts_to_financial_row(ticker="3543", fiscal_year=2024, facts=facts)

    assert isinstance(summary, pd.DataFrame)
    assert summary["metric"].tolist() == ["cash_flow_operating"]
    assert row["cash_flow_operating"] == 9200
    assert row["revenue"] is None


def test_edinet_parser_prefers_specific_tags_and_scales_jpy_units(tmp_path: Path) -> None:
    zip_path = tmp_path / "csv.zip"
    _write_zip(
        zip_path,
        "\n".join(
            [
                "element,label,contextRef,unit,value",
                "jpcrp_cor:Assets,Assets,CurrentYearInstant,JPY,153600000000",
                "jpcrp_cor:CurrentAssets,Current assets,CurrentYearInstant,JPY,26700000000",
                "jpcrp_cor:Assets,Assets,PriorYearInstant,JPY,149200000000",
                "ifrs-full:RevenueFromContractsWithCustomers,Revenue,CurrentYearDuration,JPY,43291000000",
            ]
        ),
    )

    facts = extract_financial_facts_from_zip(zip_path)
    row = facts_to_financial_row(ticker="3543", fiscal_year=2024, facts=facts)

    assert row["total_assets"] == 153600
    assert row["current_assets"] == 26700
    assert row["revenue"] == 43291


def test_save_and_load_extracted_edinet_facts(tmp_path: Path) -> None:
    db_path = tmp_path / "edinet.sqlite"
    facts = [
        EdinetCsvFact(
            source_file="sample.csv",
            metric="revenue",
            raw_key="jpcrp_cor:NetSales",
            label="売上高",
            context="CurrentYearDuration",
            value=43291,
        ),
        EdinetCsvFact(
            source_file="sample.csv",
            metric="operating_income",
            raw_key="jpcrp_cor:OperatingIncome",
            label="営業利益",
            context="CurrentYearDuration",
            value=8932,
        ),
    ]

    saved_count = save_extracted_facts(
        doc_id="S100TEST",
        ticker="3543",
        fiscal_year=2024,
        facts=facts,
        db_path=db_path,
    )
    loaded_facts = load_extracted_facts(db_path=db_path, doc_id="S100TEST")
    loaded_rows = load_edinet_financial_rows(db_path=db_path, tickers=["3543"])

    assert saved_count == 2
    assert loaded_facts["metric"].tolist() == ["operating_income", "revenue"]
    assert loaded_rows.loc[0, "doc_id"] == "S100TEST"
    assert loaded_rows.loc[0, "ticker"] == "3543"
    assert loaded_rows.loc[0, "fiscal_year"] == 2024
    assert loaded_rows.loc[0, "revenue"] == 43291
    assert loaded_rows.loc[0, "operating_income"] == 8932
