from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .company_master import normalize_ticker_column
from .data_loader import Dataset
from .edinet_parser import FINANCIAL_TAG_ALIASES
from .edinet_repository import load_edinet_financial_rows


FINANCIAL_METRIC_COLUMNS = list(FINANCIAL_TAG_ALIASES.keys())


DATA_SOURCE_SAMPLE = "sample"
DATA_SOURCE_EDINET_OVERLAY = "edinet_overlay"


@dataclass(frozen=True)
class PreparedAnalysisDataset:
    dataset: Dataset
    source_summary: pd.DataFrame
    edinet_rows: pd.DataFrame


def _empty_summary() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "ticker",
            "fiscal_year",
            "data_source",
            "doc_id",
            "available_metrics",
            "missing_metrics",
        ]
    )


def _metric_count(row: pd.Series) -> tuple[int, int]:
    available = 0
    missing = 0
    for metric in FINANCIAL_METRIC_COLUMNS:
        value = pd.to_numeric(pd.Series([row.get(metric)]), errors="coerce").iloc[0]
        if pd.isna(value):
            missing += 1
        else:
            available += 1
    return available, missing


def _summarize_rows(rows: pd.DataFrame, *, source: str) -> pd.DataFrame:
    if rows.empty:
        return _empty_summary()
    summary_rows = []
    for row in rows.itertuples(index=False):
        row_series = pd.Series(row, index=rows.columns)
        available, missing = _metric_count(row_series)
        summary_rows.append(
            {
                "ticker": str(row_series.get("ticker", "")),
                "fiscal_year": row_series.get("fiscal_year"),
                "data_source": source,
                "doc_id": str(row_series.get("doc_id", "")),
                "available_metrics": available,
                "missing_metrics": missing,
            }
        )
    return pd.DataFrame(summary_rows)


def build_data_source_audit(source_summary: pd.DataFrame) -> pd.DataFrame:
    if source_summary.empty:
        return pd.DataFrame(
            columns=[
                "ticker",
                "fiscal_year",
                "data_source",
                "doc_id",
                "coverage_rate",
                "status",
                "note",
            ]
        )
    rows = []
    for row in source_summary.itertuples(index=False):
        row_series = pd.Series(row, index=source_summary.columns)
        available = int(row_series.get("available_metrics", 0) or 0)
        missing = int(row_series.get("missing_metrics", 0) or 0)
        total = available + missing
        coverage = available / total if total else 0
        source = str(row_series.get("data_source", ""))
        if source == "sample_csv":
            status = "sample"
            note = "サンプルCSV由来です。課題MVPの基準データとして使います。"
        elif available == 0:
            status = "not_ready"
            note = "EDINET候補ですが、主要財務項目をまだ抽出できていません。"
        elif missing > 0:
            status = "partial"
            note = "EDINET候補です。一部欠損があるため、レポート反映前に確認が必要です。"
        else:
            status = "ready"
            note = "EDINET候補です。主要財務項目がそろっています。"
        rows.append(
            {
                "ticker": str(row_series.get("ticker", "")),
                "fiscal_year": row_series.get("fiscal_year"),
                "data_source": source,
                "doc_id": str(row_series.get("doc_id", "")),
                "coverage_rate": coverage,
                "status": status,
                "note": note,
            }
        )
    return pd.DataFrame(rows)


def _align_edinet_rows(edinet_rows: pd.DataFrame, base_columns: list[str]) -> pd.DataFrame:
    if edinet_rows.empty:
        return pd.DataFrame(columns=base_columns)
    rows = normalize_ticker_column(edinet_rows.copy())
    rows["fiscal_year"] = pd.to_numeric(rows["fiscal_year"], errors="coerce")
    rows = rows.dropna(subset=["ticker", "fiscal_year"])
    rows["fiscal_year"] = rows["fiscal_year"].astype(int)
    for column in base_columns:
        if column not in rows.columns:
            rows[column] = pd.NA
    return rows[base_columns + [column for column in ["doc_id"] if column in rows.columns]]


def prepare_analysis_dataset(
    dataset: Dataset,
    selected_tickers: list[str],
    *,
    source_mode: str = DATA_SOURCE_SAMPLE,
    edinet_rows: pd.DataFrame | None = None,
    allow_sample_fallback: bool = True,
) -> PreparedAnalysisDataset:
    clean_tickers = [str(ticker).strip() for ticker in selected_tickers if str(ticker).strip()]
    if source_mode != DATA_SOURCE_EDINET_OVERLAY:
        sample_rows = dataset.financials[dataset.financials["ticker"].isin(clean_tickers)].copy()
        return PreparedAnalysisDataset(
            dataset=dataset,
            source_summary=_summarize_rows(sample_rows, source="sample_csv"),
            edinet_rows=pd.DataFrame(),
        )

    base_financials = normalize_ticker_column(dataset.financials.copy())
    base_columns = list(base_financials.columns)

    loaded_edinet_rows = (
        edinet_rows.copy()
        if edinet_rows is not None
        else load_edinet_financial_rows(tickers=clean_tickers)
    )
    if loaded_edinet_rows.empty:
        if not allow_sample_fallback:
            prepared = Dataset(
                company_master=dataset.company_master,
                financials=base_financials.iloc[0:0].copy(),
                market_data=dataset.market_data.iloc[0:0].copy(),
                manual_kpis=dataset.manual_kpis.iloc[0:0].copy(),
            )
            return PreparedAnalysisDataset(
                dataset=prepared,
                source_summary=_empty_summary(),
                edinet_rows=loaded_edinet_rows,
            )
        sample_rows = dataset.financials[dataset.financials["ticker"].isin(clean_tickers)].copy()
        return PreparedAnalysisDataset(
            dataset=dataset,
            source_summary=_summarize_rows(sample_rows, source="sample_csv"),
            edinet_rows=loaded_edinet_rows,
        )

    aligned_edinet = _align_edinet_rows(loaded_edinet_rows, base_columns)
    if aligned_edinet.empty:
        if not allow_sample_fallback:
            prepared = Dataset(
                company_master=dataset.company_master,
                financials=base_financials.iloc[0:0].copy(),
                market_data=dataset.market_data.iloc[0:0].copy(),
                manual_kpis=dataset.manual_kpis.iloc[0:0].copy(),
            )
            return PreparedAnalysisDataset(
                dataset=prepared,
                source_summary=_empty_summary(),
                edinet_rows=loaded_edinet_rows,
            )
        sample_rows = dataset.financials[dataset.financials["ticker"].isin(clean_tickers)].copy()
        return PreparedAnalysisDataset(
            dataset=dataset,
            source_summary=_summarize_rows(sample_rows, source="sample_csv"),
            edinet_rows=loaded_edinet_rows,
        )

    if not allow_sample_fallback:
        prepared = Dataset(
            company_master=dataset.company_master,
            financials=aligned_edinet[base_columns].sort_values(["ticker", "fiscal_year"]).reset_index(drop=True),
            market_data=dataset.market_data.iloc[0:0].copy(),
            manual_kpis=dataset.manual_kpis.iloc[0:0].copy(),
        )
        return PreparedAnalysisDataset(
            dataset=prepared,
            source_summary=_summarize_rows(aligned_edinet, source="edinet_candidate"),
            edinet_rows=loaded_edinet_rows,
        )

    replacement_keys = set(zip(aligned_edinet["ticker"].astype(str), aligned_edinet["fiscal_year"].astype(int)))
    base_keys = list(zip(base_financials["ticker"].astype(str), pd.to_numeric(base_financials["fiscal_year"], errors="coerce")))
    keep_mask = [
        (ticker, int(year)) not in replacement_keys if pd.notna(year) else True
        for ticker, year in base_keys
    ]
    combined_financials = pd.concat(
        [base_financials.loc[keep_mask, base_columns], aligned_edinet[base_columns]],
        ignore_index=True,
    ).sort_values(["ticker", "fiscal_year"])

    prepared = Dataset(
        company_master=dataset.company_master,
        financials=combined_financials,
        market_data=dataset.market_data,
        manual_kpis=dataset.manual_kpis,
    )
    summary = pd.concat(
        [
            _summarize_rows(
                base_financials[
                    base_financials["ticker"].isin(clean_tickers)
                    & ~base_financials[["ticker", "fiscal_year"]].apply(
                        lambda row: (
                            (str(row["ticker"]), int(row["fiscal_year"])) in replacement_keys
                            if pd.notna(row["fiscal_year"])
                            else False
                        ),
                        axis=1,
                    )
                ],
                source="sample_csv",
            ),
            _summarize_rows(aligned_edinet, source="edinet_candidate"),
        ],
        ignore_index=True,
    )
    return PreparedAnalysisDataset(dataset=prepared, source_summary=summary, edinet_rows=loaded_edinet_rows)
