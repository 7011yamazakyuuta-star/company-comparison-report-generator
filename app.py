from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from src.assignment_filters import check_assignment_conditions
from src.company_master import select_companies
from src.config_loader import load_industry_policy, load_presets, load_rubric
from src.data_loader import DEFAULT_DB_PATH, load_dataset
from src.edinet_client import EdinetApiError, EdinetClient, extract_document_rows
from src.edinet_files import save_raw_document
from src.edinet_repository import filter_filings, load_filings, save_filings
from src.report_writer import build_report_package


APP_MODE_LABELS = {
    "assignment": "課題モード",
    "general": "汎用モード",
}


def _apply_style() -> None:
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 2rem;
            max-width: 1180px;
        }
        h1, h2, h3 {
            letter-spacing: 0;
        }
        div[data-testid="stMetric"] {
            background: #f7f7f8;
            border: 1px solid #ececef;
            border-radius: 8px;
            padding: 12px 14px;
        }
        div[data-testid="stAlert"] {
            border-radius: 8px;
        }
        .small-note {
            color: #6e6e73;
            font-size: 0.92rem;
            line-height: 1.55;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _preset_label(item: tuple[str, dict]) -> str:
    preset_id, preset = item
    return f"{preset.get('name', preset_id)} ({preset_id})"


def _industry_mode_label(mode: str, policy: dict) -> str:
    config = policy["industry_modes"][mode]
    return f"{config.get('label', mode)}"


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


def _ordered_presets(presets: dict[str, dict]) -> list[tuple[str, dict]]:
    preferred_order = [
        "friend_cafe_theme",
        "strict_cafe_retail",
        "komeda_franchise_wholesale",
        "airline_assignment",
        "airline_general",
    ]
    items = [(preset_id, presets[preset_id]) for preset_id in preferred_order if preset_id in presets]
    items.extend((preset_id, preset) for preset_id, preset in presets.items() if preset_id not in preferred_order)
    return items


def _show_condition_warnings(warnings: list[str]) -> None:
    if warnings:
        for warning in warnings:
            st.warning(warning)
    else:
        st.success("警告はありません。")


def _render_edinet_panel() -> None:
    st.subheader("EDINETから書類一覧を取得")
    st.markdown(
        '<p class="small-note">まずは1日分の書類一覧だけを取得します。APIキーは表示しません。</p>',
        unsafe_allow_html=True,
    )

    client = EdinetClient()
    col_a, col_b, col_c = st.columns(3)
    col_a.metric("APIキー", "設定済み" if client.has_api_key else "未設定")
    col_b.metric("保存先", "SQLite")
    col_c.metric("取得単位", "1日分")

    target_date = st.date_input("取得日", value=date.today() - timedelta(days=1))
    doc_type = st.selectbox(
        "取得タイプ",
        options=[2, 1],
        format_func=lambda value: "書類一覧とメタデータ" if value == 2 else "書類一覧のみ",
    )

    if not client.has_api_key:
        st.info("`.env` の `EDINET_API_KEY` にAPIキーを保存すると取得できます。")

    if st.button("書類一覧を取得", type="primary", disabled=not client.has_api_key):
        with st.spinner("EDINETへ問い合わせています..."):
            try:
                payload = client.fetch_documents(target_date=target_date, doc_type=doc_type)
                rows = extract_document_rows(payload)
                saved_count = save_filings(rows)
            except EdinetApiError as exc:
                st.error(f"取得できませんでした: {exc}")
                return
            except Exception as exc:  # pragma: no cover - Streamlit safety net
                st.error(f"予期しないエラーです: {exc}")
                return

        st.success(f"{len(rows)}件を取得し、{saved_count}件を保存しました。")

    filings = load_filings(limit=100)
    st.caption(f"SQLiteキャッシュ: {DEFAULT_DB_PATH}")
    if filings.empty:
        st.info("保存済みのEDINET書類一覧はまだありません。")
    else:
        st.divider()
        st.subheader("保存済み一覧")
        filter_col_a, filter_col_b, filter_col_c = st.columns([2, 1, 1])
        query = filter_col_a.text_input("検索", placeholder="会社名、EDINETコード、docID")
        annual_only = filter_col_b.checkbox("有価証券報告書のみ", value=True)
        csv_only = filter_col_c.checkbox("CSVありのみ", value=True)
        filtered_filings = filter_filings(filings, query=query, annual_only=annual_only, csv_only=csv_only)
        st.dataframe(filtered_filings, use_container_width=True, hide_index=True)

        if filtered_filings.empty:
            st.info("条件に合う書類はありません。")
        else:
            options = filtered_filings["doc_id"].astype(str).tolist()
            label_lookup = {
                str(row.doc_id): f"{row.doc_id} | {row.filer_name} | {row.doc_description}"
                for row in filtered_filings.itertuples(index=False)
            }
            selected_doc_id = st.selectbox(
                "CSVを取得する書類",
                options=options,
                format_func=lambda doc_id: label_lookup.get(str(doc_id), str(doc_id)),
            )
            if st.button("この書類のCSVを取得", disabled=not client.has_api_key):
                with st.spinner("書類CSVを取得しています..."):
                    try:
                        document_file = client.fetch_document_file(str(selected_doc_id), file_type=5)
                        saved_path = save_raw_document(document_file)
                    except EdinetApiError as exc:
                        st.error(f"取得できませんでした: {exc}")
                        return
                    except Exception as exc:  # pragma: no cover - Streamlit safety net
                        st.error(f"予期しないエラーです: {exc}")
                        return
                st.success(f"保存しました: {saved_path}")


def main() -> None:
    st.set_page_config(page_title="企業比較レポート", layout="wide")
    _apply_style()

    rubric = load_rubric()
    industry_policy = load_industry_policy()
    presets = load_presets()
    dataset = load_dataset(use_sqlite=True)

    st.title("企業比較レポート")
    st.markdown(
        '<p class="small-note">日本の上場企業を選び、条件チェック、財務比較、Wordレポート生成までを一つの流れで進めます。</p>',
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.header("比較設定")
        selected_item = st.selectbox("比較セット", _ordered_presets(presets), format_func=_preset_label)
        preset_id, preset = selected_item
        default_mode = str(preset.get("default_app_mode", "assignment"))
        app_mode = st.radio(
            "利用目的",
            ["assignment", "general"],
            index=0 if default_mode == "assignment" else 1,
            format_func=lambda value: APP_MODE_LABELS[value],
        )
        industry_modes = list(industry_policy["industry_modes"].keys())
        default_industry = str(preset.get("industry_mode", rubric["assignment"]["default_industry_mode"]))
        industry_mode = st.selectbox(
            "業種の見方",
            industry_modes,
            index=industry_modes.index(default_industry),
            format_func=lambda mode: _industry_mode_label(mode, industry_policy),
        )
        manual_override = st.checkbox("企業を手動で選ぶ")
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

    selected_companies = select_companies(dataset.company_master, selected_tickers)
    preview = check_assignment_conditions(
        selected_companies,
        app_mode=app_mode,
        industry_mode=industry_mode,
        rubric=rubric,
        industry_policy=industry_policy,
        as_of=date.today(),
    )

    tab_compare, tab_checks, tab_report, tab_edinet = st.tabs(
        ["比較", "条件チェック", "レポート", "EDINET取得"]
    )

    with tab_compare:
        st.subheader("比較する企業")
        st.write(preset.get("description", ""))
        for note in preset.get("notes", []):
            st.info(note)
        st.dataframe(
            selected_companies[
                ["ticker", "company_name", "jpx_industry", "broad_sector", "business_theme", "listing_date", "listing_note"]
            ].rename(
                columns={
                    "ticker": "証券コード",
                    "company_name": "企業名",
                    "jpx_industry": "JPX業種",
                    "broad_sector": "広義セクター",
                    "business_theme": "事業テーマ",
                    "listing_date": "上場日",
                    "listing_note": "注記",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

    with tab_checks:
        st.subheader("課題条件の確認")
        _show_condition_warnings(list(preview["warnings"]))
        st.dataframe(preview["condition_table"], use_container_width=True, hide_index=True)
        st.subheader("企業別の上場条件")
        st.dataframe(preview["company_check_table"], use_container_width=True, hide_index=True)

    with tab_report:
        st.subheader("Wordレポートを生成")
        st.markdown(
            '<p class="small-note">表、グラフ、警告、欠損注記をまとめたWordファイルを作成します。</p>',
            unsafe_allow_html=True,
        )
        disabled = len(selected_tickers) < int(rubric["assignment"]["min_companies"])
        if st.button("レポートを生成", type="primary", disabled=disabled):
            with st.spinner("レポートを作成しています..."):
                package = build_report_package(
                    selected_tickers=selected_tickers,
                    preset={**preset, "preset_id": preset_id},
                    app_mode=app_mode,
                    industry_mode=industry_mode,
                    dataset=dataset,
                    as_of=date.today(),
                )
            st.success(f"生成しました: {package.docx_path.name}")

            with package.docx_path.open("rb") as f:
                st.download_button(
                    "Wordをダウンロード",
                    data=f.read(),
                    file_name=package.docx_path.name,
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )

            if package.warnings:
                st.subheader("警告")
                _show_condition_warnings(package.warnings)

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

    with tab_edinet:
        _render_edinet_panel()


if __name__ == "__main__":
    main()
