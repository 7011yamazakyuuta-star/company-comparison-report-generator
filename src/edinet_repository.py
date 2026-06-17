from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

from .data_loader import DEFAULT_DB_PATH


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
