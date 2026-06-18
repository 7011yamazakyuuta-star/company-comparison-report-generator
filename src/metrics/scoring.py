from __future__ import annotations

import pandas as pd

from .financial import latest_metrics


SCORE_WEIGHTS = {
    "growth_score": 0.18,
    "profitability_score": 0.22,
    "stability_score": 0.20,
    "cashflow_score": 0.18,
    "efficiency_score": 0.10,
    "trend_resilience_score": 0.08,
    "valuation_reference_score": 0.04,
}

SCORE_LABELS = {
    "data_completeness": "データ充足率",
    "growth_score": "成長性",
    "profitability_score": "収益性",
    "stability_score": "安定性",
    "cashflow_score": "CF創出力",
    "efficiency_score": "効率性",
    "trend_resilience_score": "変動耐性",
    "valuation_reference_score": "倍率参考",
    "analysis_quality_score": "総合分析スコア",
    "analysis_band": "見方",
}

COMPLETENESS_COLUMNS = [
    "revenue_growth_rate",
    "operating_margin",
    "roa",
    "roe",
    "asset_turnover",
    "current_ratio",
    "equity_ratio",
    "debt_ratio",
    "fcf",
    "per",
    "pbr",
]

OUTLIER_LIMITS = {
    # Ratios are decimal values. These bands are intentionally wide; values
    # outside them usually indicate unit, sign, or scale problems in extracted
    # source data rather than meaningful operating performance.
    "operating_margin": (-1.0, 1.0),
    "net_margin": (-1.0, 1.0),
    "fcf_margin": (-1.5, 1.5),
}


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    denom = _numeric(denominator).replace(0, pd.NA)
    return _numeric(numerator).divide(denom)


def _relative_score(series: pd.Series, *, higher_is_better: bool = True) -> pd.Series:
    values = _numeric(series)
    valid = values.notna()
    scores = pd.Series(pd.NA, index=values.index, dtype="Float64")
    valid_count = int(valid.sum())
    if valid_count == 0:
        return scores
    if valid_count == 1:
        scores.loc[valid] = 50.0
        return scores
    ranks = values.loc[valid].rank(method="average", ascending=True)
    normalized = (ranks - 1) / (valid_count - 1) * 100
    if not higher_is_better:
        normalized = 100 - normalized
    scores.loc[valid] = normalized.round(1)
    return scores


def _valid_metric(frame: pd.DataFrame, column: str) -> pd.Series:
    values = _numeric(frame[column]) if column in frame.columns else pd.Series(pd.NA, index=frame.index, dtype="Float64")
    limits = OUTLIER_LIMITS.get(column)
    if limits is None:
        return values
    low, high = limits
    return values.mask((values < low) | (values > high))


def _outlier_flags(frame: pd.DataFrame) -> pd.Series:
    labels = {
        "operating_margin": "営業利益率",
        "net_margin": "当期利益率",
        "fcf_margin": "FCFマージン",
    }
    rows: list[str] = []
    for _, row in frame.iterrows():
        flags: list[str] = []
        for column, (low, high) in OUTLIER_LIMITS.items():
            value = pd.to_numeric(pd.Series([row.get(column)]), errors="coerce").iloc[0]
            if pd.notna(value) and (float(value) < low or float(value) > high):
                flags.append(labels[column])
        rows.append("、".join(flags))
    return pd.Series(rows, index=frame.index)


def _mean_scores(*scores: pd.Series) -> pd.Series:
    if not scores:
        return pd.Series(dtype="Float64")
    frame = pd.concat(scores, axis=1).astype("Float64")
    counts = frame.notna().sum(axis=1).astype("Float64").mask(lambda series: series == 0)
    return frame.sum(axis=1, min_count=1).divide(counts).round(1).astype("Float64")


def _weighted_score(frame: pd.DataFrame) -> pd.Series:
    results = []
    for _, row in frame.iterrows():
        weighted_total = 0.0
        weight_total = 0.0
        for column, weight in SCORE_WEIGHTS.items():
            value = row.get(column)
            if value is None or pd.isna(value):
                continue
            weighted_total += float(value) * weight
            weight_total += weight
        if weight_total == 0:
            results.append(pd.NA)
            continue
        completeness_factor = 0.72 + 0.28 * (float(row.get("data_completeness", 0) or 0) / 100)
        results.append(round((weighted_total / weight_total) * completeness_factor, 1))
    return pd.Series(results, index=frame.index, dtype="Float64")


def _band(score: object) -> str:
    if score is None or pd.isna(score):
        return "推定不可"
    value = float(score)
    if value >= 75:
        return "相対的に高い"
    if value >= 55:
        return "やや高い"
    if value >= 40:
        return "中位"
    return "要確認"


def build_company_scores(metrics: pd.DataFrame) -> pd.DataFrame:
    """Build relative comparison scores from already-computed financial metrics.

    Scores are only relative to the currently selected companies. They are
    analysis aids, not investment recommendations.
    """
    if metrics.empty:
        return pd.DataFrame()

    latest = latest_metrics(metrics).copy()
    if "_selection_order" in latest.columns:
        latest = latest.sort_values(["_selection_order", "ticker"]).reset_index(drop=True)
    else:
        latest = latest.sort_values("ticker").reset_index(drop=True)

    history = metrics.copy()
    if "fcf_margin" not in history.columns:
        history["fcf_margin"] = _safe_ratio(history.get("fcf", pd.Series(index=history.index)), history["revenue"])
    history["operating_cf_margin"] = _safe_ratio(history["cash_flow_operating"], history["revenue"])
    trend = history.groupby("ticker", as_index=False).agg(
        revenue_growth_volatility=("revenue_growth_rate", "std"),
        operating_margin_volatility=("operating_margin", "std"),
    )

    if "fcf_margin" not in latest.columns:
        latest["fcf_margin"] = _safe_ratio(latest.get("fcf", pd.Series(index=latest.index)), latest["revenue"])
    latest["operating_cf_margin"] = _safe_ratio(latest["cash_flow_operating"], latest["revenue"])
    latest = latest.merge(trend, on="ticker", how="left")
    latest["outlier_flags"] = _outlier_flags(latest)

    existing_completeness = [column for column in COMPLETENESS_COLUMNS if column in latest.columns]
    if existing_completeness:
        completeness_frame = pd.DataFrame(
            {column: _valid_metric(latest, column) for column in existing_completeness},
            index=latest.index,
        )
        latest["data_completeness"] = completeness_frame.notna().mean(axis=1).mul(100).round(1)
    else:
        latest["data_completeness"] = pd.NA

    latest["growth_score"] = _relative_score(_valid_metric(latest, "revenue_growth_rate"))
    latest["profitability_score"] = _mean_scores(
        _relative_score(_valid_metric(latest, "operating_margin")),
        _relative_score(latest["roa"]),
        _relative_score(latest["roe"]),
    )
    latest["stability_score"] = _mean_scores(
        _relative_score(latest["equity_ratio"]),
        _relative_score(latest["current_ratio"]),
        _relative_score(latest["debt_ratio"], higher_is_better=False),
        _relative_score(latest["fixed_long_term_adequacy_ratio"], higher_is_better=False),
    )
    latest["cashflow_score"] = _mean_scores(
        _relative_score(_valid_metric(latest, "fcf_margin")),
        _relative_score(latest["operating_cf_margin"]),
        _relative_score(latest["fcf"]),
    )
    latest["efficiency_score"] = _relative_score(latest["asset_turnover"])
    latest["trend_resilience_score"] = _mean_scores(
        _relative_score(latest["revenue_growth_volatility"], higher_is_better=False),
        _relative_score(latest["operating_margin_volatility"], higher_is_better=False),
    )
    latest["valuation_reference_score"] = _mean_scores(
        _relative_score(latest["per"], higher_is_better=False),
        _relative_score(latest["pbr"], higher_is_better=False),
    )
    latest["analysis_quality_score"] = _weighted_score(latest)
    latest["analysis_band"] = latest["analysis_quality_score"].map(_band)

    columns = [
        "ticker",
        "company_name",
        "fiscal_year",
        "data_completeness",
        "growth_score",
        "profitability_score",
        "stability_score",
        "cashflow_score",
        "efficiency_score",
        "trend_resilience_score",
        "valuation_reference_score",
        "analysis_quality_score",
        "analysis_band",
        "fcf_margin",
        "operating_cf_margin",
        "outlier_flags",
        "revenue_growth_volatility",
        "operating_margin_volatility",
    ]
    existing = [column for column in columns if column in latest.columns]
    return latest[existing].reset_index(drop=True)


def build_scoring_notes(scores: pd.DataFrame, missing_label: str = "推定不可") -> list[str]:
    if scores.empty:
        return [missing_label]
    notes = [
        "分析スコアは選択企業内の相対比較であり、株式取引の推奨ではありません。",
        "データ充足率が低い企業や欠損指標がある企業は、一次資料の確認が必要です。",
    ]
    if "data_completeness" in scores.columns and scores["data_completeness"].notna().any():
        weakest = scores.sort_values("data_completeness", na_position="last").head(1).iloc[0]
        notes.append(
            f"データ充足率の確認対象: {weakest.get('company_name', weakest.get('ticker', ''))} "
            f"({weakest.get('data_completeness', missing_label)}%)"
        )
    flagged = scores[scores.get("outlier_flags", pd.Series(index=scores.index)).astype(str).str.len() > 0]
    if not flagged.empty:
        targets = "、".join(
            f"{row.get('company_name', row.get('ticker', ''))}: {row.get('outlier_flags')}"
            for _, row in flagged.iterrows()
        )
        notes.append(f"異常値候補があるため、該当指標は相対スコアから除外しました。単位・スケール確認が必要です。対象: {targets}")
    return notes
