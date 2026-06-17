from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from src.assignment_filters import check_assignment_conditions
from src.company_master import select_companies
from src.config_loader import load_industry_policy, load_presets, load_rubric
from src.data_loader import DEFAULT_DB_PATH, load_dataset
from src.report_writer import build_report_package


APP_MODE_LABELS = {
    "assignment": "課題モード",
    "general": "汎用モード",
}


def _preset_label(item: tuple[str, dict]) -> str:
    preset_id, preset = item
    return f"{preset_id} | {preset.get('name', preset_id)}"


def _industry_mode_label(mode: str, policy: dict) -> str:
    config = policy["industry_modes"][mode]
    return f"{mode} | {config.get('label', mode)}"


def _latest_metric_preview(metrics: pd.DataFrame) -> pd.DataFrame:
    latest = metrics.sort_values(["ticker", "fiscal_year"]).groupby("ticker", as_index=False).tail(1)
    columns = [
        "ticker",
        "company_name",
        "fiscal_year",
        "revenue_growth_rate",
        "operating_margin",
        "roa",
        "roe",
        "equity_ratio",
        "fcf",
        "per",
        "pbr",
    ]
    existing = [column for column in columns if column in latest.columns]
    return latest[existing].rename(
        columns={
            "ticker": "証券コード",
            "company_name": "企業名",
            "fiscal_year": "年度",
            "revenue_growth_rate": "売上高成長率",
            "operating_margin": "営業利益率",
            "roa": "ROA",
            "roe": "ROE",
            "equity_ratio": "自己資本比率",
            "fcf": "FCF",
            "per": "PER",
            "pbr": "PBR",
        }
    )


def main() -> None:
    st.set_page_config(page_title="日本上場企業比較レポートMVP", layout="wide")
    st.title("日本上場企業比較レポート生成ツール MVP")

    rubric = load_rubric()
    industry_policy = load_industry_policy()
    presets = load_presets()
    dataset = load_dataset(use_sqlite=True)

    preferred_order = [
        "friend_cafe_theme",
        "strict_cafe_retail",
        "komeda_franchise_wholesale",
        "airline_assignment",
        "airline_general",
    ]
    preset_items = [(preset_id, presets[preset_id]) for preset_id in preferred_order if preset_id in presets]
    preset_items.extend((preset_id, preset) for preset_id, preset in presets.items() if preset_id not in preferred_order)
    with st.sidebar:
        st.header("分析条件")
        selected_item = st.selectbox("プリセット", preset_items, format_func=_preset_label)
        preset_id, preset = selected_item
        default_mode = str(preset.get("default_app_mode", "assignment"))
        app_mode = st.radio(
            "分析モード",
            ["assignment", "general"],
            index=0 if default_mode == "assignment" else 1,
            format_func=lambda value: APP_MODE_LABELS[value],
            horizontal=True,
        )
        industry_modes = list(industry_policy["industry_modes"].keys())
        default_industry = str(preset.get("industry_mode", rubric["assignment"]["default_industry_mode"]))
        industry_mode = st.selectbox(
            "業種判定モード",
            industry_modes,
            index=industry_modes.index(default_industry),
            format_func=lambda mode: _industry_mode_label(mode, industry_policy),
        )
        manual_override = st.checkbox("企業を手動で上書き")
        if manual_override:
            options = dataset.company_master["ticker"].tolist()
            name_lookup = dict(zip(dataset.company_master["ticker"], dataset.company_master["company_name"], strict=False))
            selected_tickers = st.multiselect(
                "比較企業",
                options,
                default=list(preset["companies"]),
                format_func=lambda ticker: f"{ticker} {name_lookup.get(ticker, '')}",
            )
        else:
            selected_tickers = list(preset["companies"])

        st.caption(f"SQLiteキャッシュ: {DEFAULT_DB_PATH}")

    st.subheader("プリセット概要")
    st.write(preset.get("description", ""))
    if preset.get("notes"):
        for note in preset["notes"]:
            st.info(note)

    selected_companies = select_companies(dataset.company_master, selected_tickers)
    st.subheader("比較企業")
    st.dataframe(
        selected_companies[
            ["ticker", "company_name", "jpx_industry", "broad_sector", "business_theme", "listing_date", "listing_note"]
        ],
        use_container_width=True,
        hide_index=True,
    )

    preview = check_assignment_conditions(
        selected_companies,
        app_mode=app_mode,
        industry_mode=industry_mode,
        rubric=rubric,
        industry_policy=industry_policy,
        as_of=date.today(),
    )

    st.subheader("条件チェック")
    warning_messages = preview["warnings"]
    if warning_messages:
        for warning in warning_messages:
            st.warning(warning)
    else:
        st.success("現時点の条件チェックで警告はありません。")
    st.dataframe(preview["condition_table"], use_container_width=True, hide_index=True)
    with st.expander("企業別上場条件"):
        st.dataframe(preview["company_check_table"], use_container_width=True, hide_index=True)

    disabled = len(selected_tickers) < int(rubric["assignment"]["min_companies"])
    if st.button("分析してWordレポートを生成", type="primary", disabled=disabled):
        with st.spinner("分析とWordレポート生成中..."):
            package = build_report_package(
                selected_tickers=selected_tickers,
                preset={**preset, "preset_id": preset_id},
                app_mode=app_mode,
                industry_mode=industry_mode,
                dataset=dataset,
                as_of=date.today(),
            )
        st.success(f"Wordレポートを生成しました: {package.docx_path.name}")

        with package.docx_path.open("rb") as f:
            st.download_button(
                "Wordレポートをダウンロード",
                data=f.read(),
                file_name=package.docx_path.name,
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

        if package.warnings:
            st.subheader("警告")
            for warning in package.warnings:
                st.warning(warning)

        st.subheader("最新年度の主要指標")
        st.dataframe(_latest_metric_preview(package.metrics), use_container_width=True, hide_index=True)

        st.subheader("グラフ")
        columns = st.columns(2)
        for idx, (slug, path) in enumerate(package.chart_paths.items()):
            with columns[idx % 2]:
                st.image(str(path), caption=slug, use_container_width=True)

        if package.missing_notes:
            st.subheader("欠損データ注記")
            for note in package.missing_notes:
                st.write(f"- {note}")


if __name__ == "__main__":
    main()
