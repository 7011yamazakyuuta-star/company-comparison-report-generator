from __future__ import annotations

from collections.abc import Iterable

import pandas as pd


def normalize_ticker(value: object) -> str:
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(4)


def normalize_ticker_column(df: pd.DataFrame) -> pd.DataFrame:
    if "ticker" not in df.columns:
        return df
    normalized = df.copy()
    normalized["ticker"] = normalized["ticker"].map(normalize_ticker)
    return normalized


def select_companies(master: pd.DataFrame, tickers: Iterable[object]) -> pd.DataFrame:
    ordered = [normalize_ticker(ticker) for ticker in tickers]
    companies = normalize_ticker_column(master)
    selected = companies[companies["ticker"].isin(ordered)].copy()
    order_map = {ticker: idx for idx, ticker in enumerate(ordered)}
    selected["_order"] = selected["ticker"].map(order_map)
    selected = selected.sort_values("_order").drop(columns=["_order"])
    missing = [ticker for ticker in ordered if ticker not in set(selected["ticker"])]
    if missing:
        raise ValueError(f"company master missing tickers: {', '.join(missing)}")
    return selected.reset_index(drop=True)


def company_name_map(master: pd.DataFrame) -> dict[str, str]:
    normalized = normalize_ticker_column(master)
    return dict(zip(normalized["ticker"], normalized["company_name"], strict=False))

