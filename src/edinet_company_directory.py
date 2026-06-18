from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Iterable

import pandas as pd

from .company_master import normalize_ticker_column
from .config_loader import PROJECT_ROOT
from .data_loader import Dataset


DEFAULT_EDINET_DIRECTORY_PATH = PROJECT_ROOT / "data" / "company_master" / "edinet_company_directory.csv"

COMPANY_MASTER_COLUMNS = [
    "ticker",
    "company_name",
    "edinet_code",
    "jpx_industry",
    "broad_sector",
    "business_theme",
    "listing_date",
    "listing_note",
    "business_summary",
    "source_note",
]


def ticker_from_sec_code(sec_code: object) -> str:
    digits = "".join(char for char in str(sec_code or "") if char.isdigit())
    return digits[:4] if len(digits) >= 4 else ""


def _first_non_empty(values: Iterable[object]) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def build_company_directory_from_filings(filings: pd.DataFrame) -> pd.DataFrame:
    if filings.empty:
        return pd.DataFrame(columns=COMPANY_MASTER_COLUMNS)

    rows = filings.copy()
    for column in ["sec_code", "filer_name", "edinet_code", "submit_datetime", "doc_id"]:
        if column not in rows.columns:
            rows[column] = ""
    rows["ticker"] = rows["sec_code"].map(ticker_from_sec_code)
    rows = rows[rows["ticker"].astype(str).str.len() == 4].copy()
    rows = rows[rows["filer_name"].fillna("").astype(str).str.strip() != ""].copy()
    if rows.empty:
        return pd.DataFrame(columns=COMPANY_MASTER_COLUMNS)

    rows["_submit_sort"] = pd.to_datetime(rows["submit_datetime"], errors="coerce")
    rows = rows.sort_values(["ticker", "_submit_sort", "doc_id"], ascending=[True, False, False])
    latest = rows.groupby("ticker", as_index=False).first()

    directory_rows = []
    for row in latest.itertuples(index=False):
        row_series = pd.Series(row, index=latest.columns)
        ticker = str(row_series.get("ticker", "")).strip()
        filer_name = str(row_series.get("filer_name", "")).strip()
        if not ticker or not filer_name:
            continue
        edinet_code = _first_non_empty([row_series.get("edinet_code")])
        directory_rows.append(
            {
                "ticker": ticker,
                "company_name": filer_name,
                "edinet_code": edinet_code,
                "jpx_industry": "未分類",
                "broad_sector": "EDINET提出企業",
                "business_theme": "EDINET提出企業",
                "listing_date": "",
                "listing_note": "EDINET書類一覧から追加。上場日やJPX業種は別途確認してください。",
                "business_summary": f"{filer_name}のEDINET提出書類から追加した企業候補です。",
                "source_note": "EDINET documents API cache",
            }
        )

    if not directory_rows:
        return pd.DataFrame(columns=COMPANY_MASTER_COLUMNS)
    return normalize_ticker_column(pd.DataFrame(directory_rows, columns=COMPANY_MASTER_COLUMNS))


def load_static_edinet_company_directory(path: Path = DEFAULT_EDINET_DIRECTORY_PATH) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=COMPANY_MASTER_COLUMNS)
    directory = pd.read_csv(path, dtype={"ticker": str})
    for column in COMPANY_MASTER_COLUMNS:
        if column not in directory.columns:
            directory[column] = ""
    return normalize_ticker_column(directory[COMPANY_MASTER_COLUMNS])


def merge_company_master_with_edinet_directory(master: pd.DataFrame, directory: pd.DataFrame) -> pd.DataFrame:
    base = normalize_ticker_column(master.copy())
    if directory.empty:
        return base

    for column in COMPANY_MASTER_COLUMNS:
        if column not in base.columns:
            base[column] = ""
        if column not in directory.columns:
            directory[column] = ""

    existing_tickers = set(base["ticker"].astype(str))
    additions = directory[~directory["ticker"].astype(str).isin(existing_tickers)].copy()
    if additions.empty:
        return base
    merged = pd.concat([base, additions[base.columns]], ignore_index=True)
    return normalize_ticker_column(merged)


def merge_company_master_with_edinet_filings(master: pd.DataFrame, filings: pd.DataFrame) -> pd.DataFrame:
    directory = build_company_directory_from_filings(filings)
    return merge_company_master_with_edinet_directory(master, directory)


def overlay_dataset_company_master(dataset: Dataset, filings: pd.DataFrame) -> Dataset:
    merged = merge_company_master_with_edinet_directory(
        dataset.company_master,
        load_static_edinet_company_directory(),
    )
    merged = merge_company_master_with_edinet_filings(merged, filings)
    return replace(dataset, company_master=merged)
