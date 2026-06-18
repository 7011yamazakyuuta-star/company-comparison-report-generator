from __future__ import annotations

import csv
import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd


FINANCIAL_TAG_ALIASES = {
    "revenue": [
        "RevenueFromContractsWithCustomersExcludingAssessedTax",
        "RevenueFromContractsWithCustomers",
        "NetSalesSummaryOfBusinessResults",
        "SalesRevenue",
        "NetSales",
        "Revenue",
        "OperatingRevenue",
        "Sales",
        "売上高",
        "営業収益",
        "収益",
    ],
    "operating_income": [
        "ProfitLossFromOperatingActivities",
        "OperatingIncomeLoss",
        "OperatingProfitLoss",
        "OperatingIncome",
        "OperatingProfit",
        "営業利益",
    ],
    "net_income": [
        "ProfitLossAttributableToOwnersOfParent",
        "ProfitAttributableToOwnersOfParent",
        "ProfitLossForPeriod",
        "NetIncomeLoss",
        "ProfitLoss",
        "NetIncome",
        "親会社株主に帰属する当期純利益",
        "当期純利益",
    ],
    "total_assets": [
        "Assets",
        "TotalAssets",
        "資産合計",
        "総資産",
    ],
    "equity": [
        "EquityAttributableToOwnersOfParent",
        "EquityAttributableToOwnersOfParentIFRSSummaryOfBusinessResults",
        "TotalEquity",
        "Equity",
        "NetAssets",
        "純資産",
        "純資産合計",
    ],
    "current_assets": [
        "AssetsCurrent",
        "CurrentAssets",
        "流動資産",
        "流動資産合計",
    ],
    "current_liabilities": [
        "LiabilitiesCurrent",
        "CurrentLiabilities",
        "流動負債",
        "流動負債合計",
    ],
    "fixed_assets": [
        "AssetsNoncurrent",
        "NonCurrentAssets",
        "NoncurrentAssets",
        "FixedAssets",
        "固定資産",
        "非流動資産",
    ],
    "long_term_liabilities": [
        "LiabilitiesNoncurrent",
        "NonCurrentLiabilities",
        "NoncurrentLiabilities",
        "LongTermLiabilities",
        "固定負債",
        "非流動負債",
    ],
    "cash_flow_operating": [
        "NetCashProvidedByUsedInOperatingActivities",
        "CashFlowsFromUsedInOperatingActivities",
        "CashFlowsFromOperatingActivities",
        "営業活動によるキャッシュ・フロー",
    ],
    "cash_flow_investing": [
        "NetCashProvidedByUsedInInvestmentActivities",
        "CashFlowsFromUsedInInvestmentActivities",
        "CashFlowsFromInvestingActivities",
        "投資活動によるキャッシュ・フロー",
    ],
    "cash_flow_financing": [
        "NetCashProvidedByUsedInFinancingActivities",
        "CashFlowsFromUsedInFinancingActivities",
        "CashFlowsFromFinancingActivities",
        "財務活動によるキャッシュ・フロー",
    ],
    "capex": [
        "PaymentsForAcquisitionOfPropertyPlantAndEquipment",
        "PurchaseOfPropertyPlantAndEquipmentAndIntangibleAssets",
        "PurchaseOfPropertyPlantAndEquipment",
        "PaymentsForPurchaseOfPropertyPlantAndEquipment",
        "AcquisitionOfPropertyPlantAndEquipment",
        "CapitalExpenditure",
        "有形固定資産の取得による支出",
        "設備投資",
    ],
}


@dataclass(frozen=True)
class EdinetCsvFact:
    source_file: str
    metric: str
    raw_key: str
    label: str
    context: str
    value: float


def list_csv_members(zip_path: Path) -> list[str]:
    with zipfile.ZipFile(zip_path) as archive:
        return [
            info.filename
            for info in archive.infolist()
            if not info.is_dir() and info.filename.lower().endswith((".csv", ".tsv", ".txt"))
        ]


def _decode_bytes(raw: bytes) -> str:
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig")

    for encoding in ("utf-8-sig", "cp932", "utf-8", "utf-16"):
        try:
            text = raw.decode(encoding)
        except UnicodeError:
            continue
        if "\x00" not in text[:200]:
            return text
    return raw.decode("utf-8", errors="replace")


def _sniff_delimiter(text: str) -> str:
    sample = text[:4096]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",\t").delimiter
    except csv.Error:
        return "\t" if "\t" in sample else ","


def _read_table(raw: bytes) -> pd.DataFrame:
    text = _decode_bytes(raw)
    delimiter = _sniff_delimiter(text)
    return pd.read_csv(io.StringIO(text), sep=delimiter, dtype=str, keep_default_na=False)


def _normalized(text: object) -> str:
    return re.sub(r"[\s_\-:：/・（）()]+", "", str(text or "")).casefold()


def _numeric_value(value: object, unit_text: object = "") -> float | None:
    text = str(value or "").strip()
    if not text or text in {"-", "－", "推定不可"}:
        return None
    text = text.replace(",", "").replace("△", "-").replace("▲", "-")
    if text.startswith("(") and text.endswith(")"):
        text = f"-{text[1:-1]}"
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        numeric = float(match.group(0))
    except ValueError:
        return None
    normalized_unit = _normalized(unit_text)
    if normalized_unit in {"jpy", "円", "日本円"} or "iso4217jpy" in normalized_unit:
        return numeric / 1_000_000
    return numeric


def _first_matching_column(columns: Iterable[str], candidates: Iterable[str]) -> str | None:
    normalized_columns = {column: _normalized(column) for column in columns}
    for candidate in candidates:
        normalized_candidate = _normalized(candidate)
        for column, normalized_column in normalized_columns.items():
            if normalized_column == normalized_candidate:
                return column
    for candidate in candidates:
        normalized_candidate = _normalized(candidate)
        for column, normalized_column in normalized_columns.items():
            if normalized_candidate in normalized_column:
                return column
    return None


def _row_text(row: pd.Series, columns: Iterable[str]) -> str:
    return " ".join(str(row.get(column, "")) for column in columns)


def _flatten_aliases() -> list[tuple[str, str, str]]:
    flattened: list[tuple[str, str, str]] = []
    for metric, aliases in FINANCIAL_TAG_ALIASES.items():
        for alias in aliases:
            normalized_alias = _normalized(alias)
            if normalized_alias:
                flattened.append((metric, alias, normalized_alias))
    return sorted(flattened, key=lambda item: len(item[2]), reverse=True)


def _metric_for_row(row_text: str) -> tuple[str, str] | None:
    normalized_row = _normalized(row_text)
    for metric, alias, normalized_alias in _flatten_aliases():
        if normalized_alias in normalized_row:
            return metric, alias
    return None


def _fact_score(fact: EdinetCsvFact, metric: str) -> int:
    text = _normalized(f"{fact.raw_key} {fact.label} {fact.context} {fact.source_file}")
    score = 0
    if "currentyear" in text or "current" in text:
        score += 30
    if "prioryear" in text or "previous" in text or "prior" in text:
        score -= 30
    if "consolidated" in text or "連結" in text:
        score += 12
    if "nonconsolidated" in text or "個別" in text:
        score -= 10
    flow_metrics = {
        "revenue",
        "operating_income",
        "net_income",
        "cash_flow_operating",
        "cash_flow_investing",
        "cash_flow_financing",
        "capex",
    }
    if metric in flow_metrics and "duration" in text:
        score += 10
    if metric not in flow_metrics and "instant" in text:
        score += 10
    if "quarter" in text or "interim" in text or "sixmonth" in text or "threemonth" in text:
        score -= 12
    if "segment" in text:
        score -= 8
    return score


def extract_financial_facts_from_zip(zip_path: Path) -> list[EdinetCsvFact]:
    facts: list[EdinetCsvFact] = []
    with zipfile.ZipFile(zip_path) as archive:
        for member_name in list_csv_members(zip_path):
            try:
                table = _read_table(archive.read(member_name))
            except Exception:
                continue
            if table.empty:
                continue
            value_column = _first_matching_column(
                table.columns,
                ["value", "値", "金額", "amount", "当期", "CurrentYearInstant", "CurrentYearDuration"],
            )
            if value_column is None:
                continue
            label_column = _first_matching_column(
                table.columns,
                ["label", "項目名", "勘定科目", "account", "name", "要素名"],
            )
            key_column = _first_matching_column(
                table.columns,
                ["element", "要素ID", "要素名", "tag", "concept", "name"],
            )
            context_column = _first_matching_column(
                table.columns,
                ["context", "コンテキスト", "contextref", "contextRef", "期間"],
            )
            unit_column = _first_matching_column(
                table.columns,
                ["unit", "unitRef", "ユニット", "単位", "単位ID"],
            )
            search_columns = [column for column in [key_column, label_column] if column]
            if not search_columns:
                search_columns = list(table.columns[: min(4, len(table.columns))])

            for row in table.itertuples(index=False):
                row_series = pd.Series(row, index=table.columns)
                row_match = _metric_for_row(_row_text(row_series, search_columns))
                if row_match is None:
                    continue
                value = _numeric_value(row_series.get(value_column), row_series.get(unit_column, "") if unit_column else "")
                if value is None:
                    continue
                metric, matched_alias = row_match
                facts.append(
                    EdinetCsvFact(
                        source_file=member_name,
                        metric=metric,
                        raw_key=str(row_series.get(key_column, matched_alias)) if key_column else matched_alias,
                        label=str(row_series.get(label_column, matched_alias)) if label_column else matched_alias,
                        context=str(row_series.get(context_column, "")) if context_column else "",
                        value=value,
                    )
                )
    return facts


def summarize_facts(facts: list[EdinetCsvFact]) -> pd.DataFrame:
    rows = [
        {
            "metric": fact.metric,
            "value": fact.value,
            "label": fact.label,
            "raw_key": fact.raw_key,
            "context": fact.context,
            "source_file": fact.source_file,
        }
        for fact in facts
    ]
    if not rows:
        return pd.DataFrame(columns=["metric", "value", "label", "raw_key", "context", "source_file"])
    return pd.DataFrame(rows)


def facts_to_financial_row(*, ticker: str, fiscal_year: int, facts: list[EdinetCsvFact]) -> dict[str, object]:
    row: dict[str, object] = {"ticker": str(ticker), "fiscal_year": int(fiscal_year)}
    for metric in FINANCIAL_TAG_ALIASES:
        metric_facts = [fact for fact in facts if fact.metric == metric]
        if not metric_facts:
            row[metric] = None
            continue
        best_fact = max(metric_facts, key=lambda fact: _fact_score(fact, metric))
        row[metric] = best_fact.value
    return row
