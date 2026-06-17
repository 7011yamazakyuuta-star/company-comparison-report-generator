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

WORKFLOW_MODE_LABELS = {
    "auto": "オートマ作成",
    "detail": "詳細設定",
}

WIZARD_STEP_LABELS = ["目的", "テーマ", "業種", "作成"]


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
            min-height: 0;
            height: 0;
            background: transparent;
            border-bottom: 0;
            backdrop-filter: blur(18px);
        }
        div[data-testid="stToolbar"],
        div[data-testid="stDecoration"],
        div[data-testid="stStatusWidget"] {
            display: none !important;
            visibility: hidden !important;
            height: 0 !important;
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
            border-bottom: 0 !important;
            box-shadow: none !important;
        }
        div[data-testid="stSidebarContent"] {
            padding-top: 1.35rem;
            border-bottom: 0 !important;
            box-shadow: none !important;
        }
        div[data-testid="stSidebarUserContent"] {
            border-bottom: 0 !important;
            box-shadow: none !important;
        }
        div[data-testid="stSidebar"] h2,
        div[data-testid="stSidebar"] h3 {
            font-size: 1rem;
        }
        .app-header {
            padding: 1rem 0 1.7rem;
            border-bottom: 0;
            margin-bottom: 0.65rem;
        }
        .app-kicker {
            color: var(--app-muted);
            font-size: 0.82rem;
            font-weight: 650;
            margin-bottom: 0.35rem;
        }
        .app-title {
            color: var(--app-text);
            font-size: 3rem;
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
        .store-strip {
            display: flex;
            gap: 0.75rem;
            align-items: center;
            flex-wrap: wrap;
            margin-top: 1.2rem;
        }
        .store-chip {
            border: 1px solid rgba(255, 255, 255, 0.84);
            border-radius: 999px;
            padding: 0.48rem 0.75rem;
            background: rgba(255, 255, 255, 0.62);
            color: var(--app-muted);
            font-size: 0.86rem;
            font-weight: 650;
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.9),
                0 8px 22px rgba(0, 0, 0, 0.06);
            backdrop-filter: blur(18px) saturate(1.45);
        }
        .auto-shell {
            margin-top: 1.1rem;
            padding: 1.35rem;
            border: 1px solid rgba(255, 255, 255, 0.86);
            border-radius: 22px;
            background:
                linear-gradient(180deg, rgba(255, 255, 255, 0.82), rgba(255, 255, 255, 0.62)),
                radial-gradient(circle at 85% 0%, rgba(255, 255, 255, 0.94), transparent 34%);
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.95),
                0 18px 52px rgba(0, 0, 0, 0.08);
            backdrop-filter: blur(24px) saturate(1.5);
        }
        .auto-kicker {
            color: var(--app-muted);
            font-size: 0.78rem;
            font-weight: 700;
            margin-bottom: 0.35rem;
        }
        .auto-title {
            font-size: 1.7rem;
            line-height: 1.25;
            font-weight: 720;
            color: var(--app-text);
            margin: 0;
        }
        .auto-lede {
            color: var(--app-muted);
            font-size: 0.96rem;
            line-height: 1.65;
            margin: 0.55rem 0 0;
            max-width: 720px;
        }
        .wizard-progress {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 0.45rem;
            margin: 1.15rem 0 1.2rem;
        }
        .wizard-dot {
            height: 0.42rem;
            border-radius: 999px;
            background: rgba(210, 210, 215, 0.72);
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8);
            overflow: hidden;
        }
        .wizard-dot.is-active,
        .wizard-dot.is-done {
            background: linear-gradient(90deg, rgba(29, 29, 31, 0.82), rgba(110, 110, 115, 0.62));
        }
        .wizard-dot.is-active {
            animation: liquid-slide-in 260ms cubic-bezier(0.2, 0.8, 0.2, 1);
        }
        .choice-copy {
            min-height: 6.35rem;
            padding: 1rem 1rem 0.75rem;
            border: 1px solid rgba(255, 255, 255, 0.82);
            border-radius: 18px;
            background: rgba(255, 255, 255, 0.52);
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.88),
                0 10px 28px rgba(0, 0, 0, 0.06);
            backdrop-filter: blur(18px) saturate(1.45);
        }
        .choice-title {
            color: var(--app-text);
            font-size: 1.04rem;
            font-weight: 700;
            margin-bottom: 0.3rem;
        }
        .choice-body {
            color: var(--app-muted);
            font-size: 0.88rem;
            line-height: 1.55;
        }
        .review-line {
            display: flex;
            gap: 0.8rem;
            align-items: flex-start;
            padding: 0.7rem 0;
            border-bottom: 1px solid rgba(210, 210, 215, 0.58);
        }
        .review-label {
            color: var(--app-muted);
            flex: 0 0 8.5rem;
            font-size: 0.86rem;
            font-weight: 650;
        }
        .review-value {
            color: var(--app-text);
            font-size: 0.94rem;
            line-height: 1.55;
        }
        .workflow-switch {
            margin: 0.4rem 0 0.85rem;
            max-width: 28rem;
        }
        .soft-divider {
            height: 1px;
            width: 100%;
            margin: 1.2rem 0;
            background: rgba(210, 210, 215, 0.7);
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
            transition:
                transform 160ms cubic-bezier(0.2, 0.8, 0.2, 1),
                box-shadow 160ms ease,
                background 160ms ease,
                border-color 160ms ease;
        }
        button:focus,
        button:focus-visible,
        input:focus,
        textarea:focus,
        [tabindex]:focus,
        [role="button"]:focus {
            outline: none !important;
        }
        div[data-testid="stSidebar"] button:focus,
        div[data-testid="stSidebar"] button:focus-visible,
        div[data-testid="stSidebar"] input:focus,
        div[data-testid="stSidebar"] [data-baseweb="select"] > div:focus-within,
        div[data-testid="stSidebar"] [data-baseweb="input"] > div:focus-within {
            outline: none !important;
            border-color: rgba(255, 255, 255, 0.92) !important;
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.95),
                0 0 0 3px rgba(210, 210, 215, 0.32) !important;
        }
        div[data-testid="stSidebar"] [style*="background-color: rgb(0, 104, 201)"],
        div[data-testid="stSidebar"] [style*="background: rgb(0, 104, 201)"],
        div[data-testid="stSidebar"] [style*="border-color: rgb(0, 104, 201)"] {
            background-color: rgba(210, 210, 215, 0.72) !important;
            border-color: rgba(210, 210, 215, 0.72) !important;
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
            transform: translateX(2px) translateY(0) scale(0.985);
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
            transition:
                color 180ms ease,
                background 220ms cubic-bezier(0.2, 0.8, 0.2, 1),
                box-shadow 220ms ease,
                transform 220ms cubic-bezier(0.2, 0.8, 0.2, 1);
        }
        button[data-baseweb="tab"][aria-selected="true"] {
            color: var(--app-text);
            background: rgba(255, 255, 255, 0.86);
            border-bottom: 0;
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.92),
                0 4px 14px rgba(0, 0, 0, 0.08);
            animation: liquid-slide-in 260ms cubic-bezier(0.2, 0.8, 0.2, 1);
        }
        div[data-testid="stSegmentedControl"],
        div[data-testid="stButtonGroup"] {
            margin-bottom: 0.25rem;
        }
        div[data-testid="stSegmentedControl"] div[role="group"],
        div[data-testid="stButtonGroup"] div[role="radiogroup"] {
            display: flex;
            gap: 0.22rem;
            width: 100%;
            padding: 0.22rem;
            border: 1px solid rgba(255, 255, 255, 0.82);
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.52);
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.88),
                0 8px 24px rgba(0, 0, 0, 0.07);
            backdrop-filter: blur(18px) saturate(1.5);
        }
        div[data-testid="stSegmentedControl"] button,
        div[data-testid="stButtonGroup"] button {
            flex: 1 1 0;
            min-height: 2.1rem;
            border-radius: 999px !important;
            color: var(--app-muted);
            font-weight: 650;
            background: transparent;
            border-color: transparent;
            box-shadow: none;
            transition:
                color 180ms ease,
                background 240ms cubic-bezier(0.2, 0.8, 0.2, 1),
                box-shadow 240ms ease,
                transform 240ms cubic-bezier(0.2, 0.8, 0.2, 1);
        }
        div[data-testid="stSegmentedControl"] button[aria-pressed="true"],
        div[data-testid="stSegmentedControl"] button[aria-selected="true"],
        div[data-testid="stSegmentedControl"] button[kind="primary"],
        div[data-testid="stButtonGroup"] button[data-testid="stBaseButton-segmented_controlActive"] {
            color: var(--app-text);
            background: rgba(255, 255, 255, 0.88);
            border-color: rgba(255, 255, 255, 0.92);
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.95),
                0 5px 16px rgba(0, 0, 0, 0.1);
            animation: liquid-slide-in 260ms cubic-bezier(0.2, 0.8, 0.2, 1);
        }
        div[data-testid="stSegmentedControl"] button:active,
        div[data-testid="stButtonGroup"] button:active {
            transform: translateX(4px) scale(0.985);
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
            transition:
                transform 90ms cubic-bezier(0.2, 0.8, 0.2, 1),
                box-shadow 120ms ease;
            touch-action: pan-x;
        }
        div[data-baseweb="slider"] [role="slider"]:active {
            transform: scale(1.08);
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.95),
                0 10px 24px rgba(0, 113, 227, 0.22);
        }
        div[data-testid="stCheckbox"] label {
            display: flex !important;
            align-items: center !important;
            gap: 0.65rem !important;
            width: 100% !important;
            min-height: 2.2rem;
            cursor: pointer;
        }
        div[data-testid="stCheckbox"] label > div:first-child {
            flex: 0 0 38px !important;
            width: 38px !important;
            height: 22px !important;
            border: 1px solid rgba(255, 255, 255, 0.86);
            border-radius: 999px !important;
            background: rgba(255, 255, 255, 0.58);
            box-shadow:
                inset 0 1px 1px rgba(255, 255, 255, 0.9),
                0 6px 16px rgba(0, 0, 0, 0.08);
            backdrop-filter: blur(14px) saturate(1.4);
            transition:
                background 220ms ease,
                box-shadow 220ms ease,
                border-color 220ms ease;
        }
        div[data-testid="stCheckbox"] label > div:first-child > div {
            width: 18px !important;
            height: 18px !important;
            border-radius: 999px !important;
            background: rgba(255, 255, 255, 0.94);
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.95),
                0 4px 10px rgba(0, 0, 0, 0.16);
            transition:
                transform 240ms cubic-bezier(0.2, 0.9, 0.2, 1),
                box-shadow 180ms ease;
        }
        div[data-testid="stCheckbox"] label:has(input[aria-checked="true"]) > div:first-child {
            background: linear-gradient(180deg, rgba(0, 126, 245, 0.9), rgba(0, 102, 214, 0.9));
            border-color: rgba(255, 255, 255, 0.5);
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.38),
                0 8px 18px rgba(0, 113, 227, 0.25);
        }
        div[data-testid="stCheckbox"] label:has(input[aria-checked="true"]) > div:first-child > div {
            transform: translateX(16px);
        }
        div[data-testid="stCheckbox"] label:active > div:first-child > div {
            transform: scaleX(1.16);
        }
        div[data-testid="stCheckbox"] label:has(input[aria-checked="true"]):active > div:first-child > div {
            transform: translateX(16px) scaleX(1.16);
        }
        div[data-testid="stCheckbox"] div[data-testid="stWidgetLabel"] {
            flex: 1 1 auto !important;
            width: auto !important;
        }
        div[data-testid="stCheckbox"] div[data-testid="stWidgetLabel"] p {
            margin: 0;
            writing-mode: horizontal-tb;
            white-space: normal;
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
        @keyframes liquid-slide-in {
            0% {
                transform: translateX(-8px) scale(0.97);
                opacity: 0.72;
            }
            58% {
                transform: translateX(2px) scale(1.015);
                opacity: 1;
            }
            100% {
                transform: translateX(0) scale(1);
                opacity: 1;
            }
        }
        @media (prefers-reduced-motion: reduce) {
            *,
            *::before,
            *::after {
                animation-duration: 0.01ms !important;
                animation-iteration-count: 1 !important;
                transition-duration: 0.01ms !important;
                scroll-behavior: auto !important;
            }
        }
        @media (max-width: 640px) {
            .block-container {
                padding-left: 1rem;
                padding-right: 1rem;
            }
            .app-title {
                font-size: 2.1rem;
            }
            .auto-shell {
                border-radius: 18px;
                padding: 1rem;
            }
            .wizard-progress {
                gap: 0.3rem;
            }
            .review-line {
                display: block;
            }
            .review-label {
                margin-bottom: 0.2rem;
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
            <h1 class="app-title">比較レポートを作る。</h1>
            <p class="app-lede">
                上場企業の選定、課題条件チェック、財務指標の比較、Wordレポート生成まで。
                質問に答えるだけで、提出用のたたき台まで進めます。
            </p>
            <div class="store-strip">
                <div class="store-chip">サンプルCSV対応</div>
                <div class="store-chip">EDINET取得対応</div>
                <div class="store-chip">Wordレポート生成</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_section_intro(eyebrow: str, title: str, lede: str) -> None:
    st.markdown(f'<div class="section-eyebrow">{eyebrow}</div>', unsafe_allow_html=True)
    st.subheader(title)
    st.markdown(f'<p class="section-lede">{lede}</p>', unsafe_allow_html=True)


def _render_progress(current_step: int) -> None:
    dots = []
    for index, label in enumerate(WIZARD_STEP_LABELS):
        state = "is-done" if index < current_step else "is-active" if index == current_step else ""
        dots.append(f'<div class="wizard-dot {state}" title="{label}"></div>')
    st.markdown(f'<div class="wizard-progress">{"".join(dots)}</div>', unsafe_allow_html=True)


def _set_state_and_rerun(**updates: object) -> None:
    for key, value in updates.items():
        st.session_state[key] = value
    st.rerun()


def _render_choice(title: str, body: str) -> None:
    st.markdown(
        f"""
        <div class="choice-copy">
            <div class="choice-title">{title}</div>
            <div class="choice-body">{body}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_review_line(label: str, value: str) -> None:
    st.markdown(
        f"""
        <div class="review-line">
            <div class="review-label">{label}</div>
            <div class="review-value">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _wizard_preset_choice(
    preset_id: str,
    app_mode: str,
    industry_mode: str,
    wizard_step: int = 2,
) -> None:
    _set_state_and_rerun(
        selected_preset_id=preset_id,
        app_mode=app_mode,
        industry_mode=industry_mode,
        manual_override=False,
        wizard_step=wizard_step,
    )


def _render_auto_mode(
    *,
    preset_id: str,
    preset: dict,
    app_mode: str,
    industry_mode: str,
    selected_tickers: list[str],
    selected_companies: pd.DataFrame,
    preview: dict,
    dataset,
    industry_policy: dict,
    rubric: dict,
) -> None:
    current_step = int(st.session_state.get("wizard_step", 0))
    current_step = max(0, min(current_step, len(WIZARD_STEP_LABELS) - 1))
    step_copy = {
        0: (
            "Question 1",
            "何として使いますか？",
            "課題提出向けか、自由な企業比較かを選びます。",
        ),
        1: (
            "Question 2",
            "どの比較から始めますか？",
            "近いものを選ぶだけで、企業セットと基本条件をそろえます。",
        ),
        2: (
            "Question 3",
            "業種の見方を選びます。",
            "課題提出ではJPX業種一致が基本です。テーマ比較は便利ですが、警告付きで扱います。",
        ),
        3: (
            "Ready",
            "この内容で作成できます。",
            "条件チェックを確認し、必要ならこのままWordレポートを生成します。",
        ),
    }
    step_kicker, step_title, step_lede = step_copy[current_step]

    st.markdown(
        f"""
        <div class="auto-shell">
            <div class="auto-kicker">{step_kicker}</div>
            <h2 class="auto-title">{step_title}</h2>
            <p class="auto-lede">
                {step_lede}
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _render_progress(current_step)

    if current_step == 0:
        purpose_choice = st.segmented_control(
            "用途を選択",
            options=["assignment", "general"],
            default=None,
            format_func=lambda value: "大学課題として作る" if value == "assignment" else "自由に比較する",
            label_visibility="collapsed",
            key="wizard_purpose_choice",
            width="stretch",
        )
        if purpose_choice:
            _set_state_and_rerun(app_mode=purpose_choice, wizard_step=1)
        _render_choice(
            "選ぶだけで次へ進みます",
            "課題モードでは条件チェックを厳しめに、汎用モードでは比較分析の自由度を優先します。",
        )
        return

    if current_step == 1:
        first_row = st.columns(2)
        with first_row[0]:
            _render_choice("カフェをテーマで比較", "コメダHDとドトール・日レスHD。事業テーマ比較なので課題では警告も確認できます。")
            if st.button("カフェテーマで進む", type="primary", width="stretch", key="wizard_friend_cafe"):
                _wizard_preset_choice("friend_cafe_theme", app_mode, "business_theme")
        with first_row[1]:
            _render_choice("課題向けカフェ小売", "ドトール・日レスHDとサンマルクHD。JPX業種一致を重視します。")
            if st.button("小売比較で進む", width="stretch", key="wizard_strict_cafe"):
                _wizard_preset_choice("strict_cafe_retail", "assignment", "strict_jpx_industry")

        second_row = st.columns(2)
        with second_row[0]:
            _render_choice("航空会社を課題向けに比較", "日本航空、スターフライヤー、スカイマーク。再上場注記も扱います。")
            if st.button("航空課題で進む", width="stretch", key="wizard_airline_assignment"):
                _wizard_preset_choice("airline_assignment", "assignment", "strict_jpx_industry")
        with second_row[1]:
            _render_choice("航空会社を広く比較", "ANA HDも含めた汎用比較。課題条件より業界理解を優先します。")
            if st.button("航空汎用で進む", width="stretch", key="wizard_airline_general"):
                _wizard_preset_choice("airline_general", "general", "strict_jpx_industry")

        if st.button("戻る", width="stretch", key="wizard_back_to_purpose"):
            _set_state_and_rerun(wizard_step=0, wizard_purpose_choice=None)
        return

    if current_step == 2:
        industry_choice = st.segmented_control(
            "業種判定を選択",
            options=["strict_jpx_industry", "business_theme", "broad_sector"],
            default=None,
            format_func=lambda mode: _industry_mode_label(mode, industry_policy),
            label_visibility="collapsed",
            key="wizard_industry_choice",
            width="stretch",
        )
        if industry_choice:
            _set_state_and_rerun(industry_mode=industry_choice, wizard_step=3)
        _render_choice(
            "課題ならJPX業種一致が基本",
            "テーマ比較や広義セクターは便利ですが、大学課題モードでは警告付きで扱います。",
        )
        if app_mode == "assignment" and industry_mode != "strict_jpx_industry":
            st.warning("課題モードではJPX業種一致が標準です。テーマ比較や広義セクターは警告付きになります。")
        if st.button("戻る", width="stretch", key="wizard_back_to_theme"):
            _set_state_and_rerun(wizard_step=1)
        return

    company_names = " / ".join(selected_companies["company_name"].astype(str).tolist())
    _render_review_line("比較セット", str(preset.get("name", preset_id)))
    _render_review_line("企業", company_names)
    _render_review_line("利用目的", APP_MODE_LABELS.get(app_mode, app_mode))
    _render_review_line("業種判定", _industry_mode_label(industry_mode, industry_policy))
    _render_review_line("警告", f"{len(preview['warnings'])}件" if preview["warnings"] else "なし")

    if preview["warnings"]:
        for warning in preview["warnings"]:
            st.warning(warning)
    else:
        st.success("条件チェック上の警告はありません。")

    actions = st.columns([1.2, 1, 1])
    with actions[0]:
        disabled = len(selected_tickers) < int(rubric["assignment"]["min_companies"])
        if st.button("Wordレポートを作成", type="primary", disabled=disabled, width="stretch", key="wizard_generate_report"):
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
                    width="stretch",
                    key="wizard_download_report",
                )
            st.dataframe(_latest_metric_preview(package.metrics), use_container_width=True, hide_index=True)
    with actions[1]:
        if st.button("条件を選び直す", width="stretch", key="wizard_back_to_industry"):
            _set_state_and_rerun(wizard_step=2, wizard_industry_choice=None)
    with actions[2]:
        if st.button("詳細設定を開く", width="stretch", key="wizard_open_detail"):
            _set_state_and_rerun(workflow_mode_pending="detail")


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
        annual_only = filter_col_b.toggle("有価証券報告書のみ", value=True, width="stretch")
        csv_only = filter_col_c.toggle("CSVありのみ", value=True, width="stretch")
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
    st.set_page_config(page_title="企業比較レポート", layout="wide", initial_sidebar_state="expanded")
    _apply_style()

    rubric = load_rubric()
    industry_policy = load_industry_policy()
    presets = load_presets()
    dataset = load_dataset(use_sqlite=True)
    ordered_preset_ids = [preset_id for preset_id, _ in _ordered_presets(presets)]

    if "workflow_mode" not in st.session_state:
        st.session_state.workflow_mode = "auto"
    if "workflow_mode_pending" in st.session_state:
        st.session_state.workflow_mode = st.session_state.workflow_mode_pending
        del st.session_state["workflow_mode_pending"]
    if "wizard_step" not in st.session_state:
        st.session_state.wizard_step = 0
    if "selected_preset_id" not in st.session_state or st.session_state.selected_preset_id not in presets:
        st.session_state.selected_preset_id = ordered_preset_ids[0]
    active_preset = presets[st.session_state.selected_preset_id]
    if "app_mode" not in st.session_state:
        st.session_state.app_mode = str(active_preset.get("default_app_mode", "assignment"))
    if "manual_override" not in st.session_state:
        st.session_state.manual_override = False
    industry_modes = list(industry_policy["industry_modes"].keys())
    if "industry_mode" not in st.session_state or st.session_state.industry_mode not in industry_modes:
        st.session_state.industry_mode = str(active_preset.get("industry_mode", rubric["assignment"]["default_industry_mode"]))

    _render_app_header()

    st.markdown('<div class="workflow-switch">', unsafe_allow_html=True)
    workflow_mode = st.segmented_control(
        "作成モード",
        options=["auto", "detail"],
        required=True,
        format_func=lambda value: WORKFLOW_MODE_LABELS[value],
        key="workflow_mode",
        label_visibility="collapsed",
        width="stretch",
    )
    st.markdown("</div>", unsafe_allow_html=True)
    if workflow_mode is None:
        workflow_mode = "auto"

    preset_id = st.session_state.selected_preset_id
    preset = presets[preset_id]
    app_mode = str(st.session_state.app_mode)
    industry_mode = str(st.session_state.industry_mode)
    manual_override = bool(st.session_state.manual_override)
    selected_tickers = list(preset["companies"])

    if workflow_mode == "detail":
        with st.sidebar:
            st.header("比較設定")
            st.caption("プリセットから始めて、必要なら企業や業種判定を切り替えます。")
            preset_id = st.selectbox(
                "比較セット",
                ordered_preset_ids,
                format_func=lambda value: _preset_label((value, presets[value])),
                key="selected_preset_id",
            )
            preset = presets[preset_id]
            app_mode = st.segmented_control(
                "利用目的",
                options=["assignment", "general"],
                required=True,
                format_func=lambda value: APP_MODE_LABELS[value],
                width="stretch",
                key="app_mode",
            )
            if app_mode is None:
                app_mode = str(preset.get("default_app_mode", "assignment"))
            industry_mode = st.selectbox(
                "業種の見方",
                industry_modes,
                format_func=lambda mode: _industry_mode_label(mode, industry_policy),
                key="industry_mode",
            )
            manual_override = st.toggle("企業を手動で選ぶ", width="stretch", key="manual_override")
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

    if workflow_mode == "auto":
        _render_auto_mode(
            preset_id=preset_id,
            preset=preset,
            app_mode=app_mode,
            industry_mode=industry_mode,
            selected_tickers=selected_tickers,
            selected_companies=selected_companies,
            preview=preview,
            dataset=dataset,
            industry_policy=industry_policy,
            rubric=rubric,
        )
        return

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
