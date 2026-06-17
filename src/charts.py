from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

from .company_master import company_name_map


plt.rcParams["font.family"] = ["Yu Gothic", "Meiryo", "MS Gothic", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


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
    return paths

