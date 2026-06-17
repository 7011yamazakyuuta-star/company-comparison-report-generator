from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .company_master import normalize_ticker_column
from .config_loader import PROJECT_ROOT


DEFAULT_MASTER_PATH = PROJECT_ROOT / "data" / "company_master" / "sample_company_master.csv"
DEFAULT_FINANCIALS_PATH = PROJECT_ROOT / "data" / "sample_financials" / "sample_financials.csv"
DEFAULT_MARKET_PATH = PROJECT_ROOT / "data" / "sample_financials" / "sample_market_data.csv"
DEFAULT_MANUAL_KPIS_PATH = PROJECT_ROOT / "data" / "manual_kpis" / "sample_manual_kpis.csv"
DEFAULT_DB_PATH = PROJECT_ROOT / "work" / "app_data.sqlite"


@dataclass(frozen=True)
class Dataset:
    company_master: pd.DataFrame
    financials: pd.DataFrame
    market_data: pd.DataFrame
    manual_kpis: pd.DataFrame


def _read_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"ticker": str})
    return normalize_ticker_column(df)


def load_sample_dataset(
    master_path: Path = DEFAULT_MASTER_PATH,
    financials_path: Path = DEFAULT_FINANCIALS_PATH,
    market_path: Path = DEFAULT_MARKET_PATH,
    manual_kpis_path: Path = DEFAULT_MANUAL_KPIS_PATH,
) -> Dataset:
    return Dataset(
        company_master=_read_csv(master_path),
        financials=_read_csv(financials_path),
        market_data=_read_csv(market_path),
        manual_kpis=_read_csv(manual_kpis_path),
    )


def refresh_sqlite_database(dataset: Dataset, db_path: Path = DEFAULT_DB_PATH) -> Path:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        dataset.company_master.to_sql("company_master", conn, if_exists="replace", index=False)
        dataset.financials.to_sql("financials", conn, if_exists="replace", index=False)
        dataset.market_data.to_sql("market_data", conn, if_exists="replace", index=False)
        dataset.manual_kpis.to_sql("manual_kpis", conn, if_exists="replace", index=False)
    return db_path


def load_dataset_from_sqlite(db_path: Path = DEFAULT_DB_PATH) -> Dataset:
    with sqlite3.connect(db_path) as conn:
        return Dataset(
            company_master=normalize_ticker_column(pd.read_sql_query("select * from company_master", conn)),
            financials=normalize_ticker_column(pd.read_sql_query("select * from financials", conn)),
            market_data=normalize_ticker_column(pd.read_sql_query("select * from market_data", conn)),
            manual_kpis=normalize_ticker_column(pd.read_sql_query("select * from manual_kpis", conn)),
        )


def load_dataset(use_sqlite: bool = True, db_path: Path = DEFAULT_DB_PATH) -> Dataset:
    dataset = load_sample_dataset()
    if not use_sqlite:
        return dataset
    refresh_sqlite_database(dataset, db_path)
    return load_dataset_from_sqlite(db_path)

