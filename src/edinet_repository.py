from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

from .data_loader import DEFAULT_DB_PATH
from .edinet_parser import EdinetCsvFact, FINANCIAL_TAG_ALIASES, facts_to_financial_row


FILINGS_COLUMNS = [
    "doc_id",
    "edinet_code",
    "sec_code",
    "filer_name",
    "doc_description",
    "submit_datetime",
    "ordinance_code",
    "form_code",
    "doc_type_code",
    "xbrl_flag",
    "pdf_flag",
    "csv_flag",
    "raw_json",
]

FINANCIAL_METRIC_COLUMNS = list(FINANCIAL_TAG_ALIASES.keys())


def initialize_edinet_tables(db_path: Path = DEFAULT_DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            create table if not exists edinet_filings (
                doc_id text primary key,
                edinet_code text,
                sec_code text,
                filer_name text,
                doc_description text,
                submit_datetime text,
                ordinance_code text,
                form_code text,
                doc_type_code text,
                xbrl_flag text,
                pdf_flag text,
                csv_flag text,
                raw_json text
            )
            """
        )
        conn.execute(
            """
            create table if not exists edinet_facts (
                doc_id text,
                ticker text,
                fiscal_year integer,
                metric text,
                value real,
                label text,
                raw_key text,
                context text,
                source_file text,
                primary key (doc_id, metric, raw_key, context, source_file)
            )
            """
        )
        metric_columns = ",\n                ".join(f"{metric} real" for metric in FINANCIAL_METRIC_COLUMNS)
        conn.execute(
            f"""
            create table if not exists edinet_financial_rows (
                doc_id text,
                ticker text,
                fiscal_year integer,
                {metric_columns},
                primary key (doc_id, ticker, fiscal_year)
            )
            """
        )


def save_filings(rows: list[dict[str, Any]], db_path: Path = DEFAULT_DB_PATH) -> int:
    initialize_edinet_tables(db_path)
    saved = 0
    with sqlite3.connect(db_path) as conn:
        for row in rows:
            doc_id = str(row.get("doc_id") or "").strip()
            if not doc_id:
                continue
            values = {column: row.get(column, "") for column in FILINGS_COLUMNS}
            values["raw_json"] = json.dumps(values["raw_json"], ensure_ascii=False)
            conn.execute(
                """
                insert or replace into edinet_filings (
                    doc_id, edinet_code, sec_code, filer_name, doc_description,
                    submit_datetime, ordinance_code, form_code, doc_type_code,
                    xbrl_flag, pdf_flag, csv_flag, raw_json
                ) values (
                    :doc_id, :edinet_code, :sec_code, :filer_name, :doc_description,
                    :submit_datetime, :ordinance_code, :form_code, :doc_type_code,
                    :xbrl_flag, :pdf_flag, :csv_flag, :raw_json
                )
                """,
                values,
            )
            saved += 1
    return saved


def load_filings(db_path: Path = DEFAULT_DB_PATH, limit: int = 200) -> pd.DataFrame:
    initialize_edinet_tables(db_path)
    with sqlite3.connect(db_path) as conn:
        return pd.read_sql_query(
            """
            select
                doc_id,
                edinet_code,
                sec_code,
                filer_name,
                doc_description,
                submit_datetime,
                ordinance_code,
                form_code,
                doc_type_code,
                xbrl_flag,
                pdf_flag,
                csv_flag
            from edinet_filings
            order by submit_datetime desc, doc_id desc
            limit ?
            """,
            conn,
            params=(limit,),
        )


def filter_filings(
    filings: pd.DataFrame,
    query: str = "",
    annual_only: bool = False,
    csv_only: bool = False,
) -> pd.DataFrame:
    filtered = filings.copy()
    if filtered.empty:
        return filtered

    if annual_only and "doc_description" in filtered.columns:
        filtered = filtered[
            filtered["doc_description"].fillna("").astype(str).str.contains("有価証券報告書", regex=False)
        ]
    if csv_only and "csv_flag" in filtered.columns:
        filtered = filtered[filtered["csv_flag"].fillna("").astype(str) == "1"]
    query = query.strip()
    if query:
        searchable_columns = [
            column
            for column in ["doc_id", "edinet_code", "sec_code", "filer_name", "doc_description"]
            if column in filtered.columns
        ]
        if searchable_columns:
            mask = filtered[searchable_columns].fillna("").astype(str).agg(" ".join, axis=1).str.contains(
                query, case=False, regex=False
            )
            filtered = filtered[mask]
    return filtered.reset_index(drop=True)


def save_extracted_facts(
    *,
    doc_id: str,
    ticker: str,
    fiscal_year: int,
    facts: list[EdinetCsvFact],
    db_path: Path = DEFAULT_DB_PATH,
) -> int:
    initialize_edinet_tables(db_path)
    clean_doc_id = str(doc_id).strip()
    if not clean_doc_id:
        return 0
    clean_ticker = str(ticker).strip()
    year = int(fiscal_year)
    with sqlite3.connect(db_path) as conn:
        conn.execute("delete from edinet_facts where doc_id = ?", (clean_doc_id,))
        for fact in facts:
            conn.execute(
                """
                insert or replace into edinet_facts (
                    doc_id, ticker, fiscal_year, metric, value, label, raw_key, context, source_file
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    clean_doc_id,
                    clean_ticker,
                    year,
                    fact.metric,
                    fact.value,
                    fact.label,
                    fact.raw_key,
                    fact.context,
                    fact.source_file,
                ),
            )

        row = facts_to_financial_row(ticker=clean_ticker, fiscal_year=year, facts=facts)
        row_values = {metric: row.get(metric) for metric in FINANCIAL_METRIC_COLUMNS}
        placeholders = ", ".join("?" for _ in ["doc_id", "ticker", "fiscal_year", *FINANCIAL_METRIC_COLUMNS])
        metric_column_sql = ", ".join(FINANCIAL_METRIC_COLUMNS)
        conn.execute(
            f"""
            insert or replace into edinet_financial_rows (
                doc_id, ticker, fiscal_year, {metric_column_sql}
            ) values ({placeholders})
            """,
            (
                clean_doc_id,
                clean_ticker,
                year,
                *(row_values[metric] for metric in FINANCIAL_METRIC_COLUMNS),
            ),
        )
    return len(facts)


def load_extracted_facts(db_path: Path = DEFAULT_DB_PATH, doc_id: str | None = None) -> pd.DataFrame:
    initialize_edinet_tables(db_path)
    where = ""
    params: tuple[str, ...] = ()
    if doc_id:
        where = "where doc_id = ?"
        params = (str(doc_id),)
    with sqlite3.connect(db_path) as conn:
        return pd.read_sql_query(
            f"""
            select
                doc_id,
                ticker,
                fiscal_year,
                metric,
                value,
                label,
                raw_key,
                context,
                source_file
            from edinet_facts
            {where}
            order by doc_id, metric, source_file
            """,
            conn,
            params=params,
        )


def load_edinet_financial_rows(
    db_path: Path = DEFAULT_DB_PATH,
    tickers: list[str] | None = None,
) -> pd.DataFrame:
    initialize_edinet_tables(db_path)
    params: list[str] = []
    where = ""
    if tickers:
        clean_tickers = [str(ticker).strip() for ticker in tickers if str(ticker).strip()]
        if clean_tickers:
            placeholders = ", ".join("?" for _ in clean_tickers)
            where = f"where ticker in ({placeholders})"
            params = clean_tickers
    with sqlite3.connect(db_path) as conn:
        return pd.read_sql_query(
            f"""
            select *
            from edinet_financial_rows
            {where}
            order by ticker, fiscal_year desc, doc_id desc
            """,
            conn,
            params=params,
        )
