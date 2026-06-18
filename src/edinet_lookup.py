from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from .edinet_client import EdinetClient, extract_document_rows


def sec_code_candidates(ticker: str) -> set[str]:
    digits = "".join(char for char in str(ticker) if char.isdigit())
    if len(digits) < 4:
        return set()
    ticker4 = digits[:4]
    return {ticker4, f"{ticker4}0"}


def row_matches_tickers(row: dict[str, Any], tickers: list[str]) -> bool:
    sec_code = "".join(char for char in str(row.get("sec_code", "")) if char.isdigit())
    candidates: set[str] = set()
    for ticker in tickers:
        candidates.update(sec_code_candidates(ticker))
    return bool(sec_code and sec_code in candidates)


def filter_rows_for_tickers(
    rows: list[dict[str, Any]],
    tickers: list[str],
    *,
    annual_only: bool = True,
    csv_only: bool = False,
) -> list[dict[str, Any]]:
    filtered = [row for row in rows if row_matches_tickers(row, tickers)]
    if annual_only:
        filtered = [
            row for row in filtered if "有価証券報告書" in str(row.get("doc_description", ""))
        ]
    if csv_only:
        filtered = [row for row in filtered if str(row.get("csv_flag", "")) == "1"]
    return filtered


def filter_document_rows(
    rows: list[dict[str, Any]],
    *,
    annual_only: bool = False,
    csv_only: bool = False,
) -> list[dict[str, Any]]:
    filtered = list(rows)
    if annual_only:
        filtered = [
            row for row in filtered if "有価証券報告書" in str(row.get("doc_description", ""))
        ]
    if csv_only:
        filtered = [row for row in filtered if str(row.get("csv_flag", "")) == "1"]
    return filtered


def fetch_document_rows_in_period(
    client: EdinetClient,
    *,
    end_date: date,
    lookback_days: int = 30,
    doc_type: int = 2,
    annual_only: bool = False,
    csv_only: bool = False,
) -> list[dict[str, Any]]:
    days = max(1, int(lookback_days))
    matched: list[dict[str, Any]] = []
    seen_doc_ids: set[str] = set()
    for offset in range(days):
        target_date = end_date - timedelta(days=offset)
        payload = client.fetch_documents(target_date=target_date, doc_type=doc_type)
        rows = filter_document_rows(extract_document_rows(payload), annual_only=annual_only, csv_only=csv_only)
        for row in rows:
            doc_id = str(row.get("doc_id", ""))
            if doc_id in seen_doc_ids:
                continue
            row = {**row, "fetched_date": target_date.isoformat()}
            matched.append(row)
            seen_doc_ids.add(doc_id)
    return matched


def fetch_document_rows_for_tickers(
    client: EdinetClient,
    tickers: list[str],
    *,
    end_date: date,
    lookback_days: int = 30,
    doc_type: int = 2,
    annual_only: bool = True,
    csv_only: bool = False,
) -> list[dict[str, Any]]:
    days = max(1, int(lookback_days))
    matched: list[dict[str, Any]] = []
    seen_doc_ids: set[str] = set()
    for offset in range(days):
        target_date = end_date - timedelta(days=offset)
        payload = client.fetch_documents(target_date=target_date, doc_type=doc_type)
        rows = extract_document_rows(payload)
        for row in filter_rows_for_tickers(rows, tickers, annual_only=annual_only, csv_only=csv_only):
            doc_id = str(row.get("doc_id", ""))
            if doc_id in seen_doc_ids:
                continue
            row = {**row, "fetched_date": target_date.isoformat()}
            matched.append(row)
            seen_doc_ids.add(doc_id)
    return matched
