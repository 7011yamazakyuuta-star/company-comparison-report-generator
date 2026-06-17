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
        :root {
            --app-bg: #f5f5f7;
            --app-surface: #ffffff;
            --app-surface-soft: #fbfbfd;
            --app-border: #d2d2d7;
            --app-border-soft: #e5e5ea;
            --app-text: #1d1d1f;
            --app-muted: #6e6e73;
            --app-blue: #0071e3;
            --app-blue-hover: #0077ed;
            --app-green: #248a3d;
            --app-red: #d70015;
        }
        html, body, [class*="css"] {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Hiragino Sans",
                "Yu Gothic UI", "Meiryo", sans-serif;
        }
        .stApp {
            background: var(--app-bg);
            color: var(--app-text);
        }
        header[data-testid="stHeader"] {
            background: rgba(245, 245, 247, 0.86);
            border-bottom: 1px solid rgba(210, 210, 215, 0.74);
            backdrop-filter: blur(18px);
        }
        .block-container {
            padding-top: 1.35rem;
            padding-bottom: 3rem;
            max-width: 1220px;
        }
        h1, h2, h3 {
            letter-spacing: 0;
            color: var(--app-text);
        }
        h1 {
            font-size: 2.25rem;
            line-height: 1.12;
            font-weight: 700;
            margin-bottom: 0.35rem;
        }
        h2, h3 {
            font-weight: 650;
        }
        p, label, span {
            letter-spacing: 0;
        }
        div[data-testid="stSidebar"] {
            background: var(--app-surface-soft);
            border-right: 1px solid var(--app-border);
        }
        div[data-testid="stSidebarContent"] {
            padding-top: 1.35rem;
        }
        div[data-testid="stSidebar"] h2,
        div[data-testid="stSidebar"] h3 {
            font-size: 1rem;
        }
        .app-header {
            padding: 0.8rem 0 1.35rem;
            border-bottom: 1px solid var(--app-border);
            margin-bottom: 1.1rem;
        }
        .app-kicker {
            color: var(--app-muted);
            font-size: 0.82rem;
            font-weight: 650;
            margin-bottom: 0.35rem;
        }
        .app-title {
            color: var(--app-text);
            font-size: 2.35rem;
            line-height: 1.1;
            font-weight: 720;
            margin: 0;
        }
        .app-lede {
            color: var(--app-muted);
            font-size: 1rem;
            line-height: 1.65;
            max-width: 760px;
            margin: 0.75rem 0 0;
        }
        .section-eyebrow {
            color: var(--app-muted);
            font-size: 0.78rem;
            font-weight: 650;
            margin-bottom: 0.2rem;
        }
        .section-lede {
            color: var(--app-muted);
            font-size: 0.94rem;
            line-height: 1.65;
            margin: -0.1rem 0 1rem;
        }
        div[data-testid="stMetric"] {
            background: rgba(255, 255, 255, 0.72);
            border: 1px solid rgba(255, 255, 255, 0.86);
            border-radius: 8px;
            padding: 13px 15px;
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.86),
                0 8px 24px rgba(0, 0, 0, 0.06);
            backdrop-filter: blur(18px) saturate(1.45);
        }
        div[data-testid="stMetricLabel"] {
            color: var(--app-muted);
        }
        div[data-testid="stMetricValue"] {
            color: var(--app-text);
            font-size: 1.12rem;
            font-weight: 650;
        }
        div[data-testid="stAlert"] {
            border-radius: 8px;
            border-color: var(--app-border-soft);
        }
        div[data-testid="stDataFrame"] {
            border-radius: 8px;
            overflow: hidden;
        }
        .stButton > button,
        .stDownloadButton > button {
            border-radius: 8px;
            min-height: 2.45rem;
            font-weight: 650;
            border: 1px solid rgba(255, 255, 255, 0.82);
            background: rgba(255, 255, 255, 0.64);
            color: var(--app-text);
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.9),
                0 8px 22px rgba(0, 0, 0, 0.08);
            backdrop-filter: blur(18px) saturate(1.5);
            transition: transform 120ms ease, box-shadow 120ms ease, background 120ms ease;
        }
        .stButton > button:hover,
        .stDownloadButton > button:hover {
            background: rgba(255, 255, 255, 0.78);
            border-color: rgba(255, 255, 255, 0.95);
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.95),
                0 10px 28px rgba(0, 0, 0, 0.1);
            transform: translateY(-1px);
            color: var(--app-text);
        }
        .stButton > button:active,
        .stDownloadButton > button:active {
            transform: translateY(0);
            box-shadow:
                inset 0 1px 2px rgba(0, 0, 0, 0.08),
                0 4px 14px rgba(0, 0, 0, 0.06);
        }
        .stButton > button[kind="primary"],
        .stDownloadButton > button[kind="primary"] {
            background: linear-gradient(180deg, rgba(0, 119, 237, 0.92), rgba(0, 94, 196, 0.92));
            border-color: rgba(255, 255, 255, 0.42);
            color: #ffffff;
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.38),
                0 10px 28px rgba(0, 113, 227, 0.28);
        }
        .stButton > button[kind="primary"]:hover,
        .stDownloadButton > button[kind="primary"]:hover {
            background: linear-gradient(180deg, rgba(0, 126, 245, 0.96), rgba(0, 102, 214, 0.96));
            border-color: rgba(255, 255, 255, 0.56);
            color: #ffffff;
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.46),
                0 12px 32px rgba(0, 113, 227, 0.34);
        }
        div[data-baseweb="tab-list"] {
            gap: 0.35rem;
            width: fit-content;
            max-width: 100%;
            border: 1px solid rgba(255, 255, 255, 0.82);
            border-radius: 999px;
            padding: 0.25rem;
            background: rgba(255, 255, 255, 0.56);
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.88),
                0 10px 30px rgba(0, 0, 0, 0.08);
            backdrop-filter: blur(20px) saturate(1.55);
            margin-top: 0.7rem;
        }
        button[data-baseweb="tab"] {
            background: transparent;
            border-radius: 999px;
            color: var(--app-muted);
            font-weight: 650;
            padding: 0.55rem 1rem;
            min-height: 2.2rem;
        }
        button[data-baseweb="tab"][aria-selected="true"] {
            color: var(--app-text);
            background: rgba(255, 255, 255, 0.86);
            border-bottom: 0;
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.92),
                0 4px 14px rgba(0, 0, 0, 0.08);
        }
        div[data-baseweb="input"] > div,
        div[data-baseweb="select"] > div,
        textarea,
        input {
            border-radius: 8px !important;
            background: rgba(255, 255, 255, 0.72) !important;
            border-color: rgba(255, 255, 255, 0.85) !important;
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.86);
            backdrop-filter: blur(14px) saturate(1.35);
        }
        div[data-baseweb="slider"] [role="slider"] {
            border: 1px solid rgba(255, 255, 255, 0.9);
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.9),
                0 8px 18px rgba(0, 0, 0, 0.12);
            backdrop-filter: blur(12px) saturate(1.4);
        }
        .stCheckbox label,
        .stRadio label {
            color: var(--app-text);
        }
        hr {
            border-color: var(--app-border);
        }
        .small-note {
            color: var(--app-muted);
            font-size: 0.92rem;
            line-height: 1.55;
        }
        .quiet-caption {
            color: var(--app-muted);
            font-size: 0.86rem;
            line-height: 1.5;
        }
        .status-ok {
            color: var(--app-green);
            font-weight: 650;
        }
        .status-warn {
            color: var(--app-red);
            font-weight: 650;
        }
        @media (max-width: 640px) {
            .block-container {
                padding-left: 1rem;
                padding-right: 1rem;
            }
            .app-title {
                font-size: 1.9rem;
            }
            div[data-baseweb="tab-list"] {
                width: 100%;
                gap: 0.18rem;
                justify-content: space-between;
            }
            button[data-baseweb="tab"] {
                flex: 1 1 auto;
                padding: 0.48rem 0.42rem;
                font-size: 0.86rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_app_header() -> None:
    st.markdown(
        """
        <div class="app-header">
            <div class="app-kicker">Company Comparison Report Generator</div>
            <h1 class="app-title">上場企業比較レポート</h1>
            <p class="app-lede">
                企業選定、課題条件チェック、財務指標の比較、Wordレポート生成までを
                一つの作業画面で進めます。サンプルCSVとEDINET取得を同じ流れで扱えます。
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_section_intro(eyebrow: str, title: str, lede: str) -> None:
    st.markdown(f'<div class="section-eyebrow">{eyebrow}</div>', unsafe_allow_html=True)
    st.subheader(title)
    st.markdown(f'<p class="section-lede">{lede}</p>', unsafe_allow_html=True)


def _render_workspace_summary(
    preset_id: str,
    preset: dict,
    selected_companies: pd.DataFrame,
    app_mode: str,
    industry_mode: str,
    industry_policy: dict,
    warnings: list[str],
) -> None:
    company_names = " / ".join(selected_companies["company_name"].astype(str).tolist())
    warning_label = f"{len(warnings)}件" if warnings else "なし"
    mode_label = APP_MODE_LABELS.get(app_mode, app_mode)
    industry_label = _industry_mode_label(industry_mode, industry_policy)

    col_a, col_b, col_c, col_d = st.columns([1.35, 0.8, 1, 0.8])
    col_a.metric("比較セット", preset.get("name", preset_id))
    col_b.metric("企業数", f"{len(selected_companies)}社")
    col_c.metric("モード", mode_label)
    col_d.metric("警告", warning_label)
    st.caption(f"選択中: {company_names} / 業種判定: {industry_label}")


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
    _render_section_intro(
        "EDINET",
        "書類一覧とCSVを取得",
        "まずは1日分の書類一覧を取得し、必要な有価証券報告書だけCSV ZIPとして保存します。APIキーは画面に表示しません。",
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
        _render_section_intro(
            "Saved filings",
            "保存済み一覧",
            "会社名、EDINETコード、docIDで絞り込み、CSVを取得する書類を選びます。",
        )
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

    _render_app_header()

    with st.sidebar:
        st.header("比較設定")
        st.caption("プリセットから始めて、必要なら企業や業種判定を切り替えます。")
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
    warning_list = list(preview["warnings"])

    _render_workspace_summary(
        preset_id=preset_id,
        preset=preset,
        selected_companies=selected_companies,
        app_mode=app_mode,
        industry_mode=industry_mode,
        industry_policy=industry_policy,
        warnings=warning_list,
    )

    tab_compare, tab_checks, tab_report, tab_edinet = st.tabs(
        ["比較", "条件チェック", "レポート", "EDINET取得"]
    )

    with tab_compare:
        _render_section_intro(
            "Company set",
            "比較する企業",
            "企業の上場日、JPX業種、広義セクター、事業テーマを確認します。",
        )
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
        _render_section_intro(
            "Assignment check",
            "課題条件の確認",
            "大学課題モードでは、上場日、上場後年数、業種一致、除外業種をYAMLの条件に沿って確認します。",
        )
        _show_condition_warnings(warning_list)
        st.dataframe(preview["condition_table"], use_container_width=True, hide_index=True)
        st.subheader("企業別の上場条件")
        st.dataframe(preview["company_check_table"], use_container_width=True, hide_index=True)

    with tab_report:
        _render_section_intro(
            "Report",
            "Wordレポートを生成",
            "表、グラフ、警告、欠損注記、参考資料をまとめた日本語Wordファイルを作成します。",
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
