from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

from .company_master import company_name_map


try:
    import japanize_matplotlib  # noqa: F401
except ImportError:
    plt.rcParams["font.family"] = ["Yu Gothic", "Meiryo", "MS Gothic", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


DIAGNOSTIC_COLUMNS = [
    "revenue",
    "operating_income",
    "net_income",
    "total_assets",
    "equity",
    "cash_flow_operating",
    "capex",
    "fcf",
]

CF_COLUMNS = {
    "cash_flow_operating": "営業CF",
    "capex": "投資CF/設備投資",
    "fcf": "FCF",
}


def _latest_by_company(metrics: pd.DataFrame, master: pd.DataFrame) -> pd.DataFrame:
    names = company_name_map(master)
    if metrics.empty:
        latest = master[["ticker"]].drop_duplicates().copy()
        latest["company_name"] = latest["ticker"].map(names).fillna(latest["ticker"])
        return latest
    sort_columns = ["ticker", "fiscal_year"] if "fiscal_year" in metrics.columns else ["ticker"]
    latest = metrics.sort_values(sort_columns).groupby("ticker", as_index=False).tail(1).copy()
    latest["company_name"] = latest["ticker"].astype(str).map(names).fillna(latest["ticker"].astype(str))
    return latest.reset_index(drop=True)


def _plot_lines(
    metrics: pd.DataFrame,
    master: pd.DataFrame,
    y_columns: list[str],
    labels: list[str],
    title: str,
    output_path: Path,
    percent: bool = False,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    names = company_name_map(master)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    plotted = False

    for ticker, group in metrics.sort_values("fiscal_year").groupby("ticker"):
        for y_column, metric_label in zip(y_columns, labels, strict=False):
            if y_column not in group.columns:
                continue
            y = pd.to_numeric(group[y_column], errors="coerce")
            if y.dropna().empty:
                continue
            values = y * 100 if percent else y
            label = f"{names.get(ticker, ticker)} {metric_label}" if len(y_columns) > 1 else names.get(ticker, ticker)
            ax.plot(group["fiscal_year"], values, marker="o", label=label)
            plotted = True

    if not plotted:
        ax.text(0.5, 0.5, "推定不可", ha="center", va="center", transform=ax.transAxes)
    ax.set_title(title)
    ax.set_xlabel("年度")
    ax.set_ylabel("％" if percent else "百万円")
    ax.grid(True, alpha=0.25)
    if plotted:
        ax.legend(fontsize=8, loc="best")
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path


def _plot_data_completeness(metrics: pd.DataFrame, master: pd.DataFrame, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    latest = _latest_by_company(metrics, master)
    columns = [column for column in DIAGNOSTIC_COLUMNS if column in latest.columns]
    if columns:
        values = latest[columns].notna().mean(axis=1).mul(100)
    else:
        values = pd.Series([0] * len(latest), index=latest.index, dtype="float")
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.bar(latest["company_name"].astype(str), values, color="#2f80ed")
    ax.set_title("データ充足率")
    ax.set_ylabel("％")
    ax.set_ylim(0, 100)
    ax.tick_params(axis="x", rotation=20)
    ax.grid(axis="y", alpha=0.22)
    for idx, value in enumerate(values):
        ax.text(idx, min(float(value) + 2, 98), f"{float(value):.0f}%", ha="center", fontsize=8)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path


def _plot_missing_counts(metrics: pd.DataFrame, master: pd.DataFrame, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    latest = _latest_by_company(metrics, master)
    columns = [column for column in DIAGNOSTIC_COLUMNS if column in latest.columns]
    if columns:
        values = latest[columns].isna().sum(axis=1)
    else:
        values = pd.Series([len(DIAGNOSTIC_COLUMNS)] * len(latest), index=latest.index, dtype="int")
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.bar(latest["company_name"].astype(str), values, color="#ff9f0a")
    ax.set_title("企業別欠損項目数")
    ax.set_ylabel("項目数")
    ax.tick_params(axis="x", rotation=20)
    ax.grid(axis="y", alpha=0.22)
    for idx, value in enumerate(values):
        ax.text(idx, float(value) + 0.1, f"{int(value)}", ha="center", fontsize=8)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path


def _plot_cashflow_items(metrics: pd.DataFrame, master: pd.DataFrame, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    latest = _latest_by_company(metrics, master)
    names = latest["company_name"].astype(str)
    columns = [column for column in CF_COLUMNS if column in latest.columns]
    fig, ax = plt.subplots(figsize=(8, 4.2))
    plotted = False
    if columns:
        width = 0.8 / max(len(columns), 1)
        positions = range(len(latest))
        for offset, column in enumerate(columns):
            values = pd.to_numeric(latest[column], errors="coerce")
            if values.notna().any():
                x = [position - 0.4 + width / 2 + offset * width for position in positions]
                ax.bar(x, values.fillna(0), width=width, label=CF_COLUMNS[column])
                plotted = True
        ax.set_xticks(list(positions), names, rotation=20)
    if not plotted:
        ax.text(0.5, 0.5, "取得済みCF項目なし", ha="center", va="center", transform=ax.transAxes)
        ax.set_xticks([])
    ax.set_title("取得済みCF項目")
    ax.set_ylabel("百万円")
    ax.grid(axis="y", alpha=0.22)
    if plotted:
        ax.legend(fontsize=8, loc="best")
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path


def create_charts(metrics: pd.DataFrame, master: pd.DataFrame, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    chart_specs = {
        "revenue_trend": (["revenue"], ["売上高"], "売上高推移", False),
        "operating_margin_trend": (["operating_margin"], ["営業利益率"], "営業利益率推移", True),
        "roa_roe_trend": (["roa", "roe"], ["ROA", "ROE"], "ROA/ROE推移", True),
        "equity_ratio_trend": (["equity_ratio"], ["自己資本比率"], "自己資本比率推移", True),
        "cashflow_fcf_trend": (["cash_flow_operating", "fcf"], ["営業CF", "FCF"], "営業CF/FCF推移", False),
    }
    paths: dict[str, Path] = {}
    for slug, (columns, labels, title, percent) in chart_specs.items():
        paths[slug] = _plot_lines(
            metrics=metrics,
            master=master,
            y_columns=columns,
            labels=labels,
            title=title,
            output_path=output_dir / f"{slug}.png",
            percent=percent,
        )
    diagnostic_specs = {
        "data_completeness_diagnostic": _plot_data_completeness,
        "missing_items_diagnostic": _plot_missing_counts,
        "cashflow_items_diagnostic": _plot_cashflow_items,
    }
    for slug, plotter in diagnostic_specs.items():
        paths[slug] = plotter(metrics, master, output_dir / f"{slug}.png")
    return paths
