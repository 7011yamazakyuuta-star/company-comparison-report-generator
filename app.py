from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import date, timedelta
from html import escape

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from src.advanced_diagnostics import build_advanced_diagnostics
from src.analysis_engine import (
    build_dupont_driver_table,
    build_management_issue_table,
    build_profit_bridge_table,
    build_sensitivity_risk_table,
)
from src.analysis_dataset import (
    DATA_SOURCE_EDINET_OVERLAY,
    DATA_SOURCE_SAMPLE,
    PreparedAnalysisDataset,
    build_data_source_audit,
    prepare_analysis_dataset,
)
from src.assignment_filters import check_assignment_conditions
from src.company_master import select_companies
from src.config_loader import load_industry_policy, load_presets, load_rubric
from src.course_framework import build_plus_alpha_analysis_table, build_required_plus_alpha_table
from src.data_loader import DEFAULT_DB_PATH, load_dataset
from src.edinet_client import EdinetApiError, EdinetClient, extract_document_rows
from src.edinet_company_directory import overlay_dataset_company_master
from src.edinet_files import save_raw_document
from src.edinet_lookup import fetch_document_rows_for_tickers, fetch_document_rows_in_period, sec_code_candidates
from src.edinet_parser import extract_financial_facts_from_zip, facts_to_financial_row, summarize_facts
from src.edinet_repository import (
    filter_filings,
    load_edinet_financial_rows,
    load_extracted_facts,
    load_filings,
    save_extracted_facts,
    save_filings,
)
from src.llm_prompt import build_llm_report_prompt
from src.metrics.financial import compute_financial_metrics
from src.metrics.scoring import SCORE_LABELS, build_company_scores
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

DETAIL_SECTION_LABELS = [
    ("compare", "比較"),
    ("checks", "条件チェック"),
    ("report", "レポート"),
    ("edinet", "EDINET取得"),
]

AUTO_THEME_CHOICES = [
    ("friend_cafe_theme", "カフェをテーマで比較", "コメダHDとドトール・日レスHD。事業テーマ比較なので課題では警告も確認できます。"),
    ("strict_cafe_retail", "課題向けカフェ小売", "ドトール・日レスHDとサンマルクHD。JPX業種一致を重視します。"),
    ("cafe_three_theme", "カフェ3社を広く比較", "コメダHD、ドトール・日レスHD、サンマルクHD。業態の違いを見ます。"),
    ("komeda_franchise_wholesale", "FC・卸売モデル比較", "コメダHDと神戸物産。FC展開と供給モデルを比べます。"),
    ("food_retail_general", "食関連4社を俯瞰", "カフェ、外食、食品小売・卸売を広めに並べ、事業モデルの差を見ます。"),
    ("airline_assignment", "航空会社を課題向けに比較", "日本航空、スターフライヤー、スカイマーク。再上場注記も扱います。"),
    ("airline_relisting_focus", "航空の再上場後を比較", "JAL、スカイマーク、スターフライヤーを回復局面の視点で見ます。"),
    ("airline_general", "航空会社を広く比較", "ANA HDも含めた汎用比較。課題条件より業界理解を優先します。"),
    ("airline_full_general", "航空4社フル比較", "JAL、ANA HD、スターフライヤー、スカイマークを汎用モードで並べます。"),
    ("custom_selection", "自由に企業を選ぶ", "証券コード、企業名、JPX業種、事業テーマから検索して2社以上を選びます。"),
]

AUTO_THEME_LABELS = {choice_id: title for choice_id, title, _body in AUTO_THEME_CHOICES}
AUTO_THEME_DESCRIPTIONS = {choice_id: body for choice_id, _title, body in AUTO_THEME_CHOICES}
PRESET_BUTTON_LABELS = {
    "friend_cafe_theme": "友人カフェ",
    "strict_cafe_retail": "カフェ小売",
    "cafe_three_theme": "カフェ3社",
    "komeda_franchise_wholesale": "FC・卸売",
    "food_retail_general": "食関連4社",
    "airline_assignment": "航空課題",
    "airline_relisting_focus": "航空再上場",
    "airline_general": "航空汎用",
    "airline_full_general": "航空4社",
}

EDINET_LOOKBACK_PRESETS = [
    ("quick", 30, "軽め", "最近提出された書類を素早く確認します。"),
    ("standard", 45, "標準", "API回数と見つけやすさのバランスを取ります。"),
    ("wide", 90, "広め", "提出日が少しずれた企業も拾いやすくします。"),
    ("max", 120, "最大", "見つからない時の最終確認向けです。"),
]


@dataclass
class ReportEdinetPreflight:
    filings: pd.DataFrame
    financial_rows: pd.DataFrame
    messages: list[str]
    warnings: list[str]


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
            --liquid-shadow: 0 22px 60px rgba(28, 44, 74, 0.12);
            --liquid-inner: inset 0 1px 0 rgba(255, 255, 255, 0.96);
            --liquid-blue: rgba(0, 113, 227, 0.88);
            --liquid-blue-soft: rgba(110, 184, 255, 0.62);
        }
        html, body, [class*="css"] {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Hiragino Sans",
                "Yu Gothic UI", "Meiryo", sans-serif;
        }
        html,
        body,
        [data-testid="stRoot"] {
            background: var(--app-bg) !important;
            color: var(--app-text) !important;
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
            max-width: 1380px;
            color: var(--app-text);
        }
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"],
        section[data-testid="stSidebar"],
        section.main {
            background: var(--app-bg) !important;
            color: var(--app-text) !important;
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
        div[data-testid="stWidgetLabel"] p,
        label p,
        label span {
            color: #424245 !important;
            opacity: 1 !important;
            font-weight: 620;
            text-shadow: none !important;
        }
        body:has(.workflow-mode-auto) [data-testid="stSidebar"],
        body:has(.workflow-mode-auto) [data-testid="stSidebarContent"],
        body:has(.workflow-mode-auto) [data-testid="stSidebarUserContent"] {
            display: none !important;
            visibility: hidden !important;
            width: 0 !important;
            min-width: 0 !important;
            max-width: 0 !important;
            overflow: hidden !important;
            border: 0 !important;
            box-shadow: none !important;
        }
        body:has(.workflow-mode-auto) [data-testid="stSidebarCollapsedControl"],
        body:has(.workflow-mode-auto) [data-testid="stSidebarCollapseButton"],
        body:has(.workflow-mode-auto) [data-testid*="SidebarCollapsed"],
        body:has(.workflow-mode-auto) [data-testid*="SidebarCollapse"] {
            display: none !important;
            visibility: hidden !important;
        }
        body:has(.workflow-mode-auto) [data-testid="stMain"],
        body:has(.workflow-mode-auto) section.main {
            margin-left: 0 !important;
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
        div[data-testid="stSidebar"] div[data-testid="stWidgetLabel"] p,
        div[data-testid="stSidebar"] label p,
        div[data-testid="stSidebar"] label span,
        div[data-testid="stSidebar"] .stMarkdown p {
            color: #424245 !important;
            opacity: 1 !important;
            font-weight: 620;
        }
        div[data-testid="stSidebar"] .stCaptionContainer p,
        div[data-testid="stSidebar"] .quiet-caption,
        div[data-testid="stSidebar"] .small-note {
            color: var(--app-muted) !important;
            font-weight: 500;
        }
        div[data-testid="stSidebar"] h1,
        div[data-testid="stSidebar"] h2,
        div[data-testid="stSidebar"] h3,
        div[data-testid="stSidebar"] strong {
            color: var(--app-text) !important;
        }
        section[data-testid="stSidebar"] div[data-testid="stWidgetLabel"] p,
        section[data-testid="stSidebar"] label p,
        section[data-testid="stSidebar"] label span {
            color: #424245 !important;
            opacity: 1 !important;
            font-weight: 620;
            text-shadow: none !important;
        }
        section[data-testid="stSidebar"] .stCaptionContainer p,
        section[data-testid="stSidebar"] .stMarkdown p {
            color: var(--app-muted) !important;
            opacity: 1 !important;
            text-shadow: none !important;
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
            text-decoration: none !important;
            display: inline-flex;
            align-items: center;
            border-radius: 18px;
            padding: 0.08rem 0.12rem;
            transition:
                color 160ms ease,
                background 160ms ease,
                transform 160ms cubic-bezier(0.2, 0.8, 0.2, 1);
        }
        .app-title,
        .app-title:visited,
        .app-title:focus,
        .app-title:focus-visible,
        .app-title:active {
            color: var(--app-text) !important;
            text-decoration: none !important;
            border-bottom: 0 !important;
            box-shadow: none !important;
        }
        .app-title:hover {
            color: #0066cc !important;
            background: rgba(255, 255, 255, 0.42);
            text-decoration: none !important;
            transform: translateY(-1px);
        }
        .app-title:active {
            transform: scale(0.99);
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
            border: 1px solid rgba(255, 255, 255, 0.9);
            border-radius: 26px;
            background:
                linear-gradient(145deg, rgba(255, 255, 255, 0.78), rgba(255, 255, 255, 0.44)),
                radial-gradient(circle at 16% 8%, rgba(255, 255, 255, 0.96), transparent 30%),
                radial-gradient(circle at 88% 12%, rgba(190, 216, 255, 0.30), transparent 36%);
            box-shadow:
                var(--liquid-inner),
                inset 0 -1px 0 rgba(255, 255, 255, 0.44),
                var(--liquid-shadow);
            backdrop-filter: blur(30px) saturate(1.65);
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
            margin: 1.15rem 0 1.2rem;
        }
        .wizard-progress-track {
            position: relative;
            height: 0.62rem;
            overflow: hidden;
            border-radius: 999px;
            border: 1px solid rgba(255, 255, 255, 0.74);
            background:
                linear-gradient(180deg, rgba(255, 255, 255, 0.72), rgba(245, 245, 247, 0.46));
            box-shadow:
                var(--liquid-inner),
                inset 0 -1px 0 rgba(40, 63, 96, 0.05),
                0 10px 30px rgba(30, 38, 55, 0.08);
            backdrop-filter: blur(20px) saturate(1.5);
        }
        .wizard-progress-fill {
            position: absolute;
            left: 0;
            top: 0;
            bottom: 0;
            width: var(--progress);
            border-radius: inherit;
            background:
                linear-gradient(90deg, rgba(119, 200, 255, 0.78), rgba(0, 113, 227, 0.90), rgba(71, 146, 255, 0.78)),
                radial-gradient(circle at calc(var(--progress) - 8%) 35%, rgba(255, 255, 255, 0.72), transparent 26%);
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.62),
                0 8px 22px rgba(0, 113, 227, 0.18);
            transition: width 420ms cubic-bezier(0.2, 0.85, 0.2, 1);
        }
        .wizard-progress-fill::after {
            content: "";
            position: absolute;
            inset: 0;
            background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.42), transparent);
            transform: translateX(-68%);
            animation: liquid-sheen 2.8s ease-in-out infinite;
        }
        .wizard-progress-labels {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            margin-top: 0.45rem;
            color: rgba(110, 110, 115, 0.72);
            font-size: 0.78rem;
            font-weight: 650;
        }
        .wizard-progress-labels span.is-active {
            color: #0066cc;
        }
        .choice-copy {
            position: relative;
            display: block;
            min-height: 6.35rem;
            padding: 1rem 1rem 0.75rem;
            border: 1px solid rgba(255, 255, 255, 0.9);
            border-radius: 20px;
            background:
                linear-gradient(145deg, rgba(255, 255, 255, 0.68), rgba(255, 255, 255, 0.34)),
                radial-gradient(circle at 12% 0%, rgba(255, 255, 255, 0.94), transparent 30%);
            box-shadow:
                var(--liquid-inner),
                0 12px 34px rgba(30, 38, 55, 0.08);
            backdrop-filter: blur(24px) saturate(1.55);
            transition:
                transform 180ms cubic-bezier(0.2, 0.8, 0.2, 1),
                box-shadow 180ms ease,
                background 180ms ease,
                border-color 180ms ease;
        }
        .choice-copy,
        .choice-copy:visited,
        .choice-copy:hover,
        .choice-copy:active,
        .choice-copy:focus {
            color: inherit !important;
            text-decoration: none !important;
        }
        .choice-copy.choice-link {
            cursor: pointer;
        }
        .choice-copy.choice-link:hover {
            border-color: rgba(111, 168, 255, 0.58);
            background:
                linear-gradient(145deg, rgba(255, 255, 255, 0.80), rgba(243, 249, 255, 0.48)),
                radial-gradient(circle at 12% 0%, rgba(255, 255, 255, 0.96), transparent 32%);
            box-shadow:
                var(--liquid-inner),
                0 0 0 3px rgba(0, 113, 227, 0.06),
                0 16px 42px rgba(30, 38, 55, 0.10);
            transform: translateY(-1px);
        }
        .choice-copy.choice-link:active {
            transform: translateY(0) scale(0.992);
        }
        .choice-copy.is-selected {
            background:
                linear-gradient(145deg, rgba(255, 255, 255, 0.82), rgba(236, 246, 255, 0.52)),
                radial-gradient(circle at 12% 0%, rgba(255, 255, 255, 0.98), transparent 34%);
            border-color: rgba(111, 168, 255, 0.62);
            box-shadow:
                var(--liquid-inner),
                0 0 0 3px rgba(0, 113, 227, 0.08),
                0 16px 42px rgba(0, 113, 227, 0.16);
            transform: translateY(-1px);
        }
        .choice-copy.is-selected::after {
            content: "選択中";
            position: absolute;
            top: 0.72rem;
            right: 0.78rem;
            padding: 0.18rem 0.52rem;
            border-radius: 999px;
            color: #0066cc;
            background: rgba(230, 242, 255, 0.88);
            border: 1px solid rgba(111, 168, 255, 0.35);
            font-size: 0.72rem;
            font-weight: 720;
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.86);
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
        .choice-button-wrap + div[data-testid="stButton"] button {
            position: relative;
            justify-content: flex-start;
            align-items: flex-start;
            text-align: left;
            min-height: 6.35rem;
            width: 100%;
            padding: 1rem 1rem 0.75rem;
            border-radius: 20px;
            border: 1px solid rgba(255, 255, 255, 0.9);
            background:
                linear-gradient(145deg, rgba(255, 255, 255, 0.68), rgba(255, 255, 255, 0.34)),
                radial-gradient(circle at 12% 0%, rgba(255, 255, 255, 0.94), transparent 30%);
            box-shadow:
                var(--liquid-inner),
                0 12px 34px rgba(30, 38, 55, 0.08);
            backdrop-filter: blur(24px) saturate(1.55);
        }
        .choice-button-wrap + div[data-testid="stButton"] button p {
            color: var(--app-text) !important;
            font-size: 1rem;
            font-weight: 700;
            line-height: 1.55;
            text-align: left;
        }
        .choice-button-wrap + div[data-testid="stButton"] button:hover {
            border-color: rgba(111, 168, 255, 0.58);
            background:
                linear-gradient(145deg, rgba(255, 255, 255, 0.80), rgba(243, 249, 255, 0.48)),
                radial-gradient(circle at 12% 0%, rgba(255, 255, 255, 0.96), transparent 32%);
            box-shadow:
                var(--liquid-inner),
                0 0 0 3px rgba(0, 113, 227, 0.06),
                0 16px 42px rgba(30, 38, 55, 0.10);
        }
        .choice-button-wrap.is-selected + div[data-testid="stButton"] button {
            border-color: rgba(111, 168, 255, 0.62);
            background:
                linear-gradient(145deg, rgba(255, 255, 255, 0.82), rgba(236, 246, 255, 0.52)),
                radial-gradient(circle at 12% 0%, rgba(255, 255, 255, 0.98), transparent 34%);
            box-shadow:
                var(--liquid-inner),
                0 0 0 3px rgba(0, 113, 227, 0.08),
                0 16px 42px rgba(0, 113, 227, 0.16);
        }
        .choice-button-wrap.is-selected + div[data-testid="stButton"] button::after {
            content: "選択中";
            position: absolute;
            top: 0.72rem;
            right: 0.78rem;
            padding: 0.18rem 0.52rem;
            border-radius: 999px;
            color: #0066cc;
            background: rgba(230, 242, 255, 0.88);
            border: 1px solid rgba(111, 168, 255, 0.35);
            font-size: 0.72rem;
            font-weight: 720;
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.86);
        }
        .wizard-action-spacer {
            height: 1.05rem;
        }
        .detail-section-nav {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 0.55rem;
            width: 100%;
            max-width: 980px;
            margin: 1rem 0 1.25rem;
            padding: 0.38rem;
            border-radius: 24px;
            border: 1px solid rgba(255, 255, 255, 0.92);
            background:
                linear-gradient(145deg, rgba(255, 255, 255, 0.80), rgba(255, 255, 255, 0.52)),
                radial-gradient(circle at 8% 0%, rgba(255, 255, 255, 0.96), transparent 36%);
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.94),
                0 14px 36px rgba(30, 38, 55, 0.10);
            backdrop-filter: blur(24px) saturate(1.58);
        }
        .detail-section-nav a {
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 3.35rem;
            border-radius: 18px;
            color: var(--app-text) !important;
            background:
                linear-gradient(145deg, rgba(255, 255, 255, 0.86), rgba(255, 255, 255, 0.62));
            border: 1px solid rgba(255, 255, 255, 0.92);
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.94),
                0 8px 22px rgba(30, 38, 55, 0.06);
            font-size: 1rem;
            font-weight: 760;
            text-decoration: none !important;
            transition:
                transform 170ms cubic-bezier(0.2, 0.8, 0.2, 1),
                background 190ms ease,
                box-shadow 190ms ease;
        }
        .detail-section-nav a:hover {
            transform: translateY(-1px);
            background: rgba(255, 255, 255, 0.94);
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.96),
                0 12px 28px rgba(30, 38, 55, 0.10);
        }
        .detail-section-nav a.is-active {
            color: #ffffff !important;
            background:
                linear-gradient(180deg, rgba(0, 126, 245, 0.96), rgba(0, 102, 214, 0.96));
            border-color: rgba(255, 255, 255, 0.58);
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.44),
                0 14px 34px rgba(0, 113, 227, 0.30);
        }
        @media (max-width: 720px) {
            .detail-section-nav {
                grid-template-columns: repeat(2, minmax(0, 1fr));
                border-radius: 20px;
            }
            .detail-section-nav a {
                min-height: 3rem;
                font-size: 0.92rem;
            }
        }
        div:has(> .detail-section-segmented-marker) + div[data-testid="stSegmentedControl"] {
            max-width: 980px;
            margin: 1rem 0 1.25rem;
        }
        div:has(> .detail-section-segmented-marker) + div[data-testid="stSegmentedControl"] div[role="group"] {
            width: 100%;
            gap: 0.55rem;
            padding: 0.38rem;
            border-radius: 24px;
            border: 1px solid rgba(255, 255, 255, 0.92);
            background:
                linear-gradient(145deg, rgba(255, 255, 255, 0.80), rgba(255, 255, 255, 0.52)),
                radial-gradient(circle at 8% 0%, rgba(255, 255, 255, 0.96), transparent 36%);
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.94),
                0 14px 36px rgba(30, 38, 55, 0.10);
            backdrop-filter: blur(24px) saturate(1.58);
        }
        div:has(> .detail-section-segmented-marker) + div[data-testid="stSegmentedControl"] button {
            min-height: 3.35rem;
            border-radius: 18px !important;
            font-size: 1rem;
            font-weight: 760;
            background:
                linear-gradient(145deg, rgba(255, 255, 255, 0.86), rgba(255, 255, 255, 0.62));
            border: 1px solid rgba(255, 255, 255, 0.92) !important;
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.94),
                0 8px 22px rgba(30, 38, 55, 0.06);
        }
        div:has(> .detail-section-segmented-marker) + div[data-testid="stSegmentedControl"] button[kind="primary"],
        div:has(> .detail-section-segmented-marker) + div[data-testid="stSegmentedControl"] button[aria-pressed="true"],
        div:has(> .detail-section-segmented-marker) + div[data-testid="stSegmentedControl"] button[aria-selected="true"] {
            color: #ffffff !important;
            background:
                linear-gradient(180deg, rgba(0, 126, 245, 0.96), rgba(0, 102, 214, 0.96)) !important;
            border-color: rgba(255, 255, 255, 0.58) !important;
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.44),
                0 14px 34px rgba(0, 113, 227, 0.30) !important;
        }
        div:has(> .detail-section-segmented-marker) + div[data-testid="stSegmentedControl"] button[kind="primary"] p,
        div:has(> .detail-section-segmented-marker) + div[data-testid="stSegmentedControl"] button[aria-pressed="true"] p,
        div:has(> .detail-section-segmented-marker) + div[data-testid="stSegmentedControl"] button[aria-selected="true"] p {
            color: #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
        }
        @media (max-width: 720px) {
            div:has(> .detail-section-segmented-marker) + div[data-testid="stSegmentedControl"] div[role="group"] {
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                border-radius: 20px;
            }
            div:has(> .detail-section-segmented-marker) + div[data-testid="stSegmentedControl"] button {
                min-height: 3rem;
                font-size: 0.92rem;
            }
        }
        .main-section-nav-marker + div[data-testid="stButton"] button {
            min-height: 3.35rem;
            border-radius: 18px;
            font-size: 1rem;
            font-weight: 760;
            letter-spacing: 0;
            background:
                linear-gradient(145deg, rgba(255, 255, 255, 0.86), rgba(255, 255, 255, 0.62));
            border: 1px solid rgba(255, 255, 255, 0.92);
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.94),
                0 12px 30px rgba(30, 38, 55, 0.09);
            backdrop-filter: blur(22px) saturate(1.5);
        }
        .main-section-nav-marker + div[data-testid="stButton"] button p {
            font-size: 1rem;
            font-weight: 760;
        }
        .main-section-nav-marker.is-active + div[data-testid="stButton"] button {
            color: #ffffff !important;
            background:
                linear-gradient(180deg, rgba(0, 126, 245, 0.96), rgba(0, 102, 214, 0.96)) !important;
            border-color: rgba(255, 255, 255, 0.58) !important;
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.44),
                0 14px 34px rgba(0, 113, 227, 0.30) !important;
        }
        .main-section-nav-marker.is-active + div[data-testid="stButton"] button p {
            color: #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
        }
        .main-section-nav-marker + div[data-testid="stButton"] {
            margin-bottom: 1rem;
        }
        .template-summary,
        .search-panel,
        .edinet-focus-panel {
            margin: 0.75rem 0 1rem;
            padding: 1rem;
            border: 1px solid rgba(255, 255, 255, 0.9);
            border-radius: 18px;
            background:
                linear-gradient(145deg, rgba(255, 255, 255, 0.78), rgba(255, 255, 255, 0.48)),
                radial-gradient(circle at 8% 0%, rgba(255, 255, 255, 0.92), transparent 34%);
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.9),
                0 12px 34px rgba(30, 38, 55, 0.08);
            backdrop-filter: blur(22px) saturate(1.5);
        }
        .edinet-filter-title {
            color: var(--app-text);
            font-size: 0.96rem;
            font-weight: 760;
            margin: 0.15rem 0 0.22rem;
        }
        .edinet-filter-body {
            color: var(--app-muted);
            font-size: 0.78rem;
            line-height: 1.45;
            min-height: 2.25rem;
            margin-bottom: 0.45rem;
        }
        .edinet-filter-help {
            margin: 0.45rem 0 0.75rem;
            padding: 0.68rem 0.82rem;
            border-radius: 14px;
            border: 1px solid rgba(0, 113, 227, 0.16);
            background:
                linear-gradient(145deg, rgba(236, 246, 255, 0.86), rgba(255, 255, 255, 0.64));
            color: #3f4652;
            font-size: 0.82rem;
            line-height: 1.55;
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.92),
                0 8px 24px rgba(30, 38, 55, 0.06);
        }
        .edinet-filter-help strong {
            color: #1d1d1f;
            font-weight: 760;
        }
        .edinet-period-help,
        .edinet-period-summary {
            margin: 0.45rem 0 0.75rem;
            padding: 0.78rem 0.9rem;
            border-radius: 16px;
            border: 1px solid rgba(255, 255, 255, 0.88);
            background:
                linear-gradient(145deg, rgba(255, 255, 255, 0.82), rgba(245, 248, 253, 0.58)),
                radial-gradient(circle at 8% 0%, rgba(255, 255, 255, 0.95), transparent 35%);
            color: #424245;
            font-size: 0.85rem;
            line-height: 1.55;
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.92),
                0 10px 28px rgba(30, 38, 55, 0.07);
            backdrop-filter: blur(18px) saturate(1.45);
        }
        .edinet-period-title {
            color: var(--app-text);
            font-size: 1rem;
            font-weight: 760;
            margin-bottom: 0.2rem;
        }
        .edinet-period-summary {
            display: flex;
            justify-content: space-between;
            gap: 0.85rem;
            align-items: center;
            border-color: rgba(0, 113, 227, 0.18);
            background:
                linear-gradient(145deg, rgba(235, 246, 255, 0.88), rgba(255, 255, 255, 0.64));
        }
        .edinet-period-summary strong {
            color: #1d1d1f;
            font-weight: 760;
        }
        .edinet-period-badge {
            flex: 0 0 auto;
            border-radius: 999px;
            padding: 0.28rem 0.62rem;
            color: #0b63ce;
            background: rgba(0, 113, 227, 0.1);
            font-size: 0.78rem;
            font-weight: 720;
        }
        div:has(> .edinet-period-marker) + div[data-testid="stSegmentedControl"] div[role="group"] {
            min-height: 3.25rem;
            padding: 0.25rem;
            border-radius: 18px;
            border: 1px solid rgba(255, 255, 255, 0.92);
            background: rgba(255, 255, 255, 0.72);
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.94),
                0 12px 32px rgba(30, 38, 55, 0.08);
            backdrop-filter: blur(18px) saturate(1.45);
        }
        div:has(> .edinet-period-marker) + div[data-testid="stSegmentedControl"] button {
            min-height: 2.65rem !important;
            border-radius: 14px !important;
            font-weight: 700 !important;
        }
        div:has(> .edinet-period-marker) + div[data-testid="stSegmentedControl"] button[kind="primary"],
        div:has(> .edinet-period-marker) + div[data-testid="stSegmentedControl"] button[aria-pressed="true"],
        div:has(> .edinet-period-marker) + div[data-testid="stSegmentedControl"] button[aria-selected="true"] {
            background:
                linear-gradient(135deg, rgba(0, 113, 227, 0.9), rgba(98, 163, 244, 0.9)) !important;
            color: #ffffff !important;
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.45),
                0 10px 22px rgba(0, 113, 227, 0.2) !important;
        }
        div:has(> .edinet-period-marker) + div[data-testid="stSegmentedControl"] button[kind="primary"] p,
        div:has(> .edinet-period-marker) + div[data-testid="stSegmentedControl"] button[aria-pressed="true"] p,
        div:has(> .edinet-period-marker) + div[data-testid="stSegmentedControl"] button[aria-selected="true"] p {
            color: #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
        }
        @media (max-width: 720px) {
            .edinet-period-summary {
                display: block;
            }
            .edinet-period-badge {
                display: inline-flex;
                margin-top: 0.55rem;
            }
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.edinet-filter-title) {
            border-radius: 16px !important;
            border-color: rgba(255, 255, 255, 0.92) !important;
            background:
                linear-gradient(145deg, rgba(255, 255, 255, 0.82), rgba(255, 255, 255, 0.56)) !important;
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.94),
                0 10px 26px rgba(30, 38, 55, 0.07) !important;
            backdrop-filter: blur(18px) saturate(1.4);
        }
        .template-summary-title {
            color: var(--app-text);
            font-size: 1.05rem;
            font-weight: 720;
            margin-bottom: 0.28rem;
        }
        .template-summary-body {
            color: var(--app-muted);
            font-size: 0.9rem;
            line-height: 1.55;
            margin: 0;
        }
        .template-chip-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.45rem;
            margin-top: 0.7rem;
        }
        .template-chip-row span {
            display: inline-flex;
            align-items: center;
            min-height: 1.85rem;
            border-radius: 999px;
            padding: 0.22rem 0.64rem;
            color: var(--app-muted);
            background: rgba(255, 255, 255, 0.72);
            border: 1px solid rgba(255, 255, 255, 0.88);
            font-size: 0.8rem;
            font-weight: 650;
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.9);
        }
        .company-selection-list {
            display: grid;
            gap: 0.45rem;
            margin: 0.65rem 0 0.35rem;
        }
        .company-selection-row {
            display: grid;
            grid-template-columns: 4.2rem 1fr;
            gap: 0.55rem;
            align-items: center;
            padding: 0.55rem 0.65rem;
            border-radius: 12px;
            border: 1px solid rgba(255, 255, 255, 0.86);
            background: rgba(255, 255, 255, 0.68);
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.9),
                0 6px 18px rgba(30, 38, 55, 0.06);
        }
        .company-selection-code {
            color: #0066cc;
            font-size: 0.84rem;
            font-weight: 720;
        }
        .company-selection-name {
            color: var(--app-text);
            min-width: 0;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            font-size: 0.88rem;
            font-weight: 650;
        }
        .company-selection-meta {
            grid-column: 1 / -1;
            color: var(--app-muted);
            font-size: 0.78rem;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .company-remove-caption {
            color: var(--app-muted);
            font-size: 0.78rem;
            line-height: 1.45;
            margin: 0.1rem 0 0.35rem;
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
        .sidebar-mode-switch {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 0.25rem;
            margin: 0.35rem 0 1.15rem;
            padding: 0.25rem;
            border: 1px solid rgba(255, 255, 255, 0.86);
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.56);
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.92),
                0 10px 30px rgba(30, 38, 55, 0.08);
            backdrop-filter: blur(20px) saturate(1.55);
        }
        .sidebar-mode-switch a {
            min-height: 2.35rem;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border-radius: 999px;
            color: var(--app-muted) !important;
            text-decoration: none !important;
            font-weight: 650;
            transition:
                color 180ms ease,
                background 220ms cubic-bezier(0.2, 0.8, 0.2, 1),
                transform 180ms cubic-bezier(0.2, 0.8, 0.2, 1),
                box-shadow 220ms ease;
        }
        .sidebar-mode-switch a.is-active {
            color: var(--app-text) !important;
            background: rgba(255, 255, 255, 0.90);
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.96),
                0 8px 22px rgba(30, 38, 55, 0.10);
        }
        .sidebar-mode-switch a:active {
            transform: scale(0.985);
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
            color: #6e6e73 !important;
            opacity: 1 !important;
        }
        div[data-testid="stMetricLabel"] *,
        div[data-testid="stMetricLabel"] p {
            color: #6e6e73 !important;
            opacity: 1 !important;
            text-shadow: none !important;
        }
        div[data-testid="stMetricValue"] {
            color: var(--app-text);
            font-size: 1.12rem;
            font-weight: 650;
        }
        div[data-testid="stAlert"] {
            border-radius: 8px;
            border-color: rgba(154, 103, 0, 0.24) !important;
            background: rgba(255, 248, 224, 0.94) !important;
            color: #2f2300 !important;
        }
        div[data-testid="stAlert"] *,
        div[data-testid="stAlert"] p {
            color: #2f2300 !important;
            opacity: 1 !important;
            text-shadow: none !important;
        }
        div[data-testid="stDataFrame"] {
            border-radius: 8px;
            overflow: hidden;
        }
        .stButton > button,
        .stDownloadButton > button {
            border-radius: 16px;
            min-height: 2.45rem;
            font-weight: 650;
            border: 1px solid rgba(255, 255, 255, 0.82);
            background:
                linear-gradient(145deg, rgba(255, 255, 255, 0.74), rgba(255, 255, 255, 0.48));
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
        .stButton > button p,
        .stDownloadButton > button p {
            white-space: normal;
            line-height: 1.35;
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
            background:
                linear-gradient(180deg, rgba(64, 154, 255, 0.94), rgba(0, 113, 227, 0.94)),
                radial-gradient(circle at 28% 0%, rgba(255, 255, 255, 0.45), transparent 38%);
            border-color: rgba(255, 255, 255, 0.42);
            color: #ffffff;
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.38),
                0 10px 28px rgba(0, 113, 227, 0.28);
        }
        .stButton > button[kind="primary"] p,
        .stDownloadButton > button[kind="primary"] p {
            color: #ffffff !important;
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
        .stButton > button:disabled,
        .stDownloadButton > button:disabled {
            color: #6e6e73 !important;
            background:
                linear-gradient(145deg, rgba(245, 245, 247, 0.92), rgba(232, 232, 237, 0.82)) !important;
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.82),
                0 6px 18px rgba(0, 0, 0, 0.05) !important;
            border-color: rgba(210, 210, 215, 0.76) !important;
            transform: none;
            opacity: 1 !important;
        }
        .stButton > button:disabled p,
        .stDownloadButton > button:disabled p {
            color: #6e6e73 !important;
            opacity: 1 !important;
            -webkit-text-fill-color: #6e6e73 !important;
        }
        div:has(> div[data-baseweb="tab-list"]),
        div:has(> div > div[data-baseweb="tab-list"]) {
            width: 100% !important;
            max-width: 980px !important;
        }
        div[data-baseweb="tab-list"] {
            display: flex !important;
            gap: 0.48rem;
            width: 100% !important;
            max-width: 980px !important;
            border: 1px solid rgba(255, 255, 255, 0.9);
            border-radius: 22px;
            padding: 0.36rem;
            background:
                linear-gradient(145deg, rgba(255, 255, 255, 0.78), rgba(255, 255, 255, 0.50)),
                radial-gradient(circle at 8% 0%, rgba(255, 255, 255, 0.94), transparent 36%);
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.94),
                0 14px 36px rgba(30, 38, 55, 0.10);
            backdrop-filter: blur(24px) saturate(1.58);
            margin: 1rem 0 1.25rem;
            overflow-x: auto;
            scrollbar-width: none;
        }
        div[data-baseweb="tab-list"]::-webkit-scrollbar {
            display: none;
        }
        div[data-baseweb="tab-highlight"],
        div[data-baseweb="tab-border"] {
            display: none !important;
            visibility: hidden !important;
            height: 0 !important;
            background: transparent !important;
            border: 0 !important;
            box-shadow: none !important;
        }
        button[data-baseweb="tab"] {
            background: transparent;
            border-radius: 16px;
            color: var(--app-muted);
            flex: 1 1 0;
            min-width: 12.2rem;
            font-weight: 720;
            font-size: 0.96rem;
            letter-spacing: 0;
            padding: 0.78rem 1.1rem;
            min-height: 3.15rem;
            border-bottom: 0 !important;
            transition:
                color 180ms ease,
                background 220ms cubic-bezier(0.2, 0.8, 0.2, 1),
                box-shadow 220ms ease,
                transform 220ms cubic-bezier(0.2, 0.8, 0.2, 1);
        }
        button[data-baseweb="tab"]::after,
        button[data-baseweb="tab"]::before {
            display: none !important;
            content: none !important;
        }
        button[data-baseweb="tab"][aria-selected="true"] {
            color: #ffffff;
            background:
                linear-gradient(180deg, rgba(0, 126, 245, 0.96), rgba(0, 102, 214, 0.96));
            border-bottom: 0;
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.44),
                0 10px 26px rgba(0, 113, 227, 0.28);
            animation: liquid-slide-in 260ms cubic-bezier(0.2, 0.8, 0.2, 1);
        }
        button[data-baseweb="tab"][aria-selected="true"] p,
        button[data-baseweb="tab"][aria-selected="true"] span {
            color: #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
        }
        button[data-baseweb="tab"]:hover:not([aria-selected="true"]) {
            color: var(--app-text);
            background: rgba(255, 255, 255, 0.72);
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.92),
                0 6px 18px rgba(30, 38, 55, 0.07);
        }
        button[data-baseweb="tab"]:focus,
        button[data-baseweb="tab"]:focus-visible {
            outline: none !important;
            box-shadow:
                0 0 0 3px rgba(0, 113, 227, 0.14),
                inset 0 1px 0 rgba(255, 255, 255, 0.9) !important;
        }
        @media (max-width: 720px) {
            div[data-baseweb="tab-list"] {
                width: 100%;
                border-radius: 18px;
                gap: 0.35rem;
            }
            button[data-baseweb="tab"] {
                flex: 0 0 auto;
                min-width: 8.4rem;
                min-height: 2.85rem;
                padding: 0.68rem 0.85rem;
                font-size: 0.9rem;
            }
        }
        div[data-baseweb="tab-list"]:has(button:nth-of-type(5)) {
            gap: 0.32rem;
            width: fit-content;
            max-width: 100%;
            border-radius: 999px;
            padding: 0.24rem;
            margin: 0.7rem 0 0.9rem;
            background: rgba(255, 255, 255, 0.58);
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.88),
                0 8px 24px rgba(30, 38, 55, 0.07);
        }
        div[data-baseweb="tab-list"]:has(button:nth-of-type(5)) button[data-baseweb="tab"] {
            flex: 0 0 auto;
            min-width: auto;
            min-height: 2.25rem;
            border-radius: 999px;
            padding: 0.52rem 0.86rem;
            font-size: 0.86rem;
            font-weight: 650;
        }
        div[data-baseweb="tab-list"]:has(button:nth-of-type(5)) button[data-baseweb="tab"][aria-selected="true"] {
            color: var(--app-text);
            background: rgba(255, 255, 255, 0.88);
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.92),
                0 4px 14px rgba(30, 38, 55, 0.08);
        }
        div[data-baseweb="tab-list"]:has(button:nth-of-type(5)) button[data-baseweb="tab"][aria-selected="true"] p,
        div[data-baseweb="tab-list"]:has(button:nth-of-type(5)) button[data-baseweb="tab"][aria-selected="true"] span {
            color: var(--app-text) !important;
            -webkit-text-fill-color: var(--app-text) !important;
        }
        div[data-testid="stExpander"] {
            border: 1px solid rgba(210, 210, 215, 0.72) !important;
            border-radius: 14px !important;
            overflow: hidden;
            background:
                linear-gradient(145deg, rgba(255, 255, 255, 0.78), rgba(255, 255, 255, 0.54)) !important;
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.86),
                0 10px 28px rgba(30, 38, 55, 0.06) !important;
            backdrop-filter: blur(18px) saturate(1.4);
        }
        div[data-testid="stExpander"] details,
        div[data-testid="stExpander"] details[open] {
            background: transparent !important;
            color: var(--app-text) !important;
        }
        div[data-testid="stExpander"] summary,
        div[data-testid="stExpander"] summary:hover,
        div[data-testid="stExpander"] summary:focus,
        div[data-testid="stExpander"] summary:focus-visible,
        div[data-testid="stExpander"] summary:active,
        div[data-testid="stExpander"] details[open] summary {
            background: rgba(255, 255, 255, 0.72) !important;
            color: var(--app-text) !important;
            border: 0 !important;
            outline: 0 !important;
            box-shadow: none !important;
        }
        div[data-testid="stExpander"] summary *,
        div[data-testid="stExpander"] details[open] summary * {
            color: var(--app-text) !important;
            -webkit-text-fill-color: var(--app-text) !important;
        }
        div[data-testid="stExpanderDetails"] {
            background: rgba(255, 255, 255, 0.66) !important;
            color: var(--app-text) !important;
            border-top: 1px solid rgba(210, 210, 215, 0.58) !important;
        }
        div[data-testid="stCodeBlock"] {
            border-radius: 14px !important;
            overflow: hidden;
            border: 1px solid rgba(210, 210, 215, 0.72) !important;
            box-shadow: 0 10px 28px rgba(30, 38, 55, 0.06) !important;
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
        div[data-baseweb="textarea"] > div,
        textarea {
            border-radius: 8px !important;
            background: rgba(255, 255, 255, 0.94) !important;
            border: 1px solid rgba(198, 198, 203, 0.92) !important;
            border-color: rgba(198, 198, 203, 0.92) !important;
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.96),
                0 1px 2px rgba(30, 38, 55, 0.04);
            backdrop-filter: blur(14px) saturate(1.35);
            color: var(--app-text) !important;
        }
        div[data-baseweb="input"] > div:hover,
        div[data-baseweb="textarea"] > div:hover,
        textarea:hover {
            background: rgba(255, 255, 255, 0.98) !important;
            border-color: rgba(134, 134, 139, 0.64) !important;
        }
        div[data-baseweb="input"] > div:focus-within,
        div[data-baseweb="textarea"] > div:focus-within,
        textarea:focus {
            background: #ffffff !important;
            border-color: rgba(0, 113, 227, 0.72) !important;
            box-shadow:
                0 0 0 3px rgba(0, 113, 227, 0.12),
                inset 0 1px 0 rgba(255, 255, 255, 0.98) !important;
            outline: none !important;
        }
        div[data-baseweb="input"] input,
        div[data-baseweb="textarea"] textarea,
        textarea {
            background: transparent !important;
            border: 0 !important;
            box-shadow: none !important;
            color: var(--app-text) !important;
            -webkit-text-fill-color: var(--app-text) !important;
        }
        div[data-baseweb="input"] input:disabled,
        div[data-baseweb="textarea"] textarea:disabled,
        div[data-baseweb="input"][aria-disabled="true"] > div,
        div[data-baseweb="textarea"][aria-disabled="true"] > div {
            background: rgba(245, 245, 247, 0.82) !important;
            color: #86868b !important;
            -webkit-text-fill-color: #86868b !important;
            opacity: 1 !important;
        }
        div[data-baseweb="select"] input,
        div[data-baseweb="select"] input:focus,
        div[data-baseweb="select"] div[contenteditable="true"],
        div[data-baseweb="select"] div[contenteditable="true"]:focus {
            width: 1px !important;
            min-width: 1px !important;
            max-width: 1px !important;
            height: 1.2em !important;
            min-height: 0 !important;
            padding: 0 !important;
            margin: 0 !important;
            border: 0 !important;
            border-radius: 0 !important;
            background: transparent !important;
            box-shadow: none !important;
            outline: none !important;
            color: transparent !important;
            -webkit-text-fill-color: transparent !important;
            caret-color: transparent !important;
        }
        div[data-baseweb="select"] svg,
        div[data-baseweb="select"] [data-baseweb="icon"] {
            color: #86868b !important;
            opacity: 1 !important;
            fill: #86868b !important;
        }
        div[data-baseweb="input"] input::placeholder,
        div[data-baseweb="textarea"] textarea::placeholder,
        textarea::placeholder {
            color: #86868b !important;
            opacity: 1 !important;
            -webkit-text-fill-color: #86868b !important;
        }
        div[data-baseweb="popover"],
        div[role="listbox"],
        ul[role="listbox"] {
            background: rgba(255, 255, 255, 0.96) !important;
            color: var(--app-text) !important;
            border: 1px solid rgba(210, 210, 215, 0.8) !important;
            box-shadow: 0 18px 50px rgba(30, 38, 55, 0.16) !important;
            backdrop-filter: blur(24px) saturate(1.45);
        }
        div[role="option"] {
            color: var(--app-text) !important;
            background: transparent !important;
        }
        div[role="option"]:hover,
        div[role="option"][aria-selected="true"] {
            background: rgba(0, 113, 227, 0.09) !important;
        }
        div[data-baseweb="select"] [data-baseweb="tag"] {
            display: inline-flex !important;
            align-items: center !important;
            gap: 0.45rem !important;
            min-height: 2.25rem !important;
            height: auto !important;
            max-width: 100% !important;
            padding: 0.34rem 0.68rem !important;
            border-radius: 18px !important;
            background:
                linear-gradient(145deg, rgba(0, 113, 227, 0.86), rgba(84, 174, 255, 0.72)) !important;
            border: 1px solid rgba(255, 255, 255, 0.52) !important;
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.42),
                0 8px 20px rgba(0, 113, 227, 0.18) !important;
        }
        div[data-baseweb="select"] [data-baseweb="tag"] > div:first-child {
            min-width: 0 !important;
            max-width: min(28rem, calc(100vw - 9rem)) !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
            white-space: nowrap !important;
        }
        div[data-baseweb="select"] [data-baseweb="tag"] span,
        div[data-baseweb="select"] [data-baseweb="tag"] div {
            line-height: 1.25 !important;
            white-space: nowrap !important;
        }
        div[data-baseweb="select"] [data-baseweb="tag"] svg,
        div[data-baseweb="select"] [data-baseweb="tag"] button {
            flex: 0 0 auto !important;
            margin: 0 !important;
            position: static !important;
        }
        div[data-baseweb="select"] [data-baseweb="tag"] button {
            width: 1.5rem !important;
            height: 1.5rem !important;
            border-radius: 999px !important;
            background: rgba(255, 255, 255, 0.22) !important;
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
        div[data-baseweb="slider"] {
            position: relative;
            padding-top: 1.2rem;
        }
        div[data-baseweb="slider"]::before {
            content: "低め　　　標準　　　高め";
            position: absolute;
            top: -0.05rem;
            left: 0.15rem;
            right: 0.15rem;
            color: rgba(110, 110, 115, 0.46);
            font-size: 0.74rem;
            font-weight: 650;
            pointer-events: none;
            transition:
                color 180ms ease,
                transform 180ms cubic-bezier(0.2, 0.8, 0.2, 1),
                opacity 180ms ease;
        }
        div[data-baseweb="slider"]:focus-within::before,
        div[data-baseweb="slider"]:active::before {
            color: rgba(0, 113, 227, 0.72);
            opacity: 0.96;
            transform: translateX(5px);
        }
        div[data-baseweb="slider"] [role="slider"]:active {
            transform: scaleX(1.18) scaleY(1.04);
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
        section[data-testid="stSidebar"] .company-selection-row {
            grid-template-columns: 3.7rem minmax(0, 1fr);
            gap: 0.45rem;
            padding: 0.5rem 0.56rem;
            border-color: rgba(210, 210, 215, 0.68);
        }
        section[data-testid="stSidebar"] .company-selection-code {
            font-size: 0.8rem;
        }
        section[data-testid="stSidebar"] .company-selection-name {
            font-size: 0.82rem;
        }
        section[data-testid="stSidebar"] .company-selection-meta {
            font-size: 0.72rem;
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
        .report-note {
            color: #6e6e73;
            font-size: 0.95rem;
            line-height: 1.55;
            margin: 1rem 0 0;
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
        @keyframes liquid-sheen {
            0% {
                transform: translateX(-78%);
                opacity: 0;
            }
            34% {
                opacity: 0.82;
            }
            100% {
                transform: translateX(78%);
                opacity: 0;
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
        @media (min-width: 1500px) {
            .block-container {
                max-width: 1480px;
                padding-left: 2.5rem;
                padding-right: 2.5rem;
            }
            .app-title {
                font-size: 3.25rem;
            }
            .auto-shell {
                padding: 1.55rem;
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
            <h1><a class="app-title" href="/?home=1" target="_self">比較レポートを作る。</a></h1>
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


def _reset_to_home() -> None:
    for key in [
        "wizard_step",
        "wizard_purpose_choice",
        "wizard_theme_choice",
        "wizard_industry_choice",
        "workflow_mode_pending",
        "manual_override",
        "detail_section",
    ]:
        if key in st.session_state:
            del st.session_state[key]
    st.session_state.workflow_mode = "auto"


def _consume_home_query() -> None:
    if st.query_params.get("home") == "1":
        _reset_to_home()
        st.query_params.clear()
        st.rerun()


def _query_param_scalar(name: str) -> str | None:
    value = st.query_params.get(name)
    if isinstance(value, list):
        return str(value[0]) if value else None
    return str(value) if value is not None else None


def _consume_choice_query() -> None:
    allowed_state_keys = {"wizard_purpose_choice", "wizard_industry_choice"}
    state_key = _query_param_scalar("choice_state")
    value = _query_param_scalar("choice_value")
    if state_key not in allowed_state_keys or not value:
        return
    st.session_state[state_key] = value
    for key in ("choice_state", "choice_value"):
        try:
            del st.query_params[key]
        except KeyError:
            pass
    st.rerun()


def _consume_detail_section_query() -> None:
    allowed = {section for section, _label in DETAIL_SECTION_LABELS}
    section = _query_param_scalar("detail_section")
    if section not in allowed:
        return
    st.session_state.workflow_mode = "detail"
    st.session_state.detail_section = section
    try:
        del st.query_params["detail_section"]
    except KeyError:
        pass
    st.rerun()


def _render_section_intro(eyebrow: str, title: str, lede: str) -> None:
    st.markdown(f'<div class="section-eyebrow">{eyebrow}</div>', unsafe_allow_html=True)
    st.subheader(title)
    st.markdown(f'<p class="section-lede">{lede}</p>', unsafe_allow_html=True)


def _render_progress(current_step: int) -> None:
    progress = (current_step + 1) / len(WIZARD_STEP_LABELS) * 100
    labels = []
    for index, label in enumerate(WIZARD_STEP_LABELS):
        state = "is-active" if index <= current_step else ""
        labels.append(f'<span class="{state}">{label}</span>')
    st.markdown(
        f"""
        <div class="wizard-progress">
            <div class="wizard-progress-track" style="--progress: {progress:.1f}%;">
                <div class="wizard-progress-fill"></div>
            </div>
            <div class="wizard-progress-labels">{"".join(labels)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _set_state_and_rerun(**updates: object) -> None:
    for key, value in updates.items():
        st.session_state[key] = value
    st.rerun()


def _render_choice(title: str, body: str, *, selected: bool = False, href: str | None = None) -> None:
    selected_class = " is-selected" if selected else ""
    link_class = " choice-link" if href else ""
    safe_title = escape(title)
    safe_body = escape(body)
    if href:
        safe_href = escape(href, quote=True)
        st.markdown(
            f"""
            <a class="choice-copy{selected_class}{link_class}" href="{safe_href}" target="_self">
                <div class="choice-title">{safe_title}</div>
                <div class="choice-body">{safe_body}</div>
            </a>
            """,
            unsafe_allow_html=True,
        )
        return
    st.markdown(
        f"""
        <div class="choice-copy{selected_class}">
            <div class="choice-title">{safe_title}</div>
            <div class="choice-body">{safe_body}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_selectable_option(
    *,
    title: str,
    body: str,
    value: str,
    state_key: str,
    button_key: str,
) -> None:
    selected = st.session_state.get(state_key) == value
    selected_class = " is-selected" if selected else ""
    st.markdown(f'<div class="choice-button-wrap{selected_class}"></div>', unsafe_allow_html=True)
    if st.button(f"{title}\n\n{body}", width="stretch", key=button_key):
        _set_state_and_rerun(**{state_key: value})


def _render_proceed_button(label: str, *, enabled: bool, key: str, **updates: object) -> None:
    if st.button(label, type="primary" if enabled else "secondary", disabled=not enabled, width="stretch", key=key):
        _set_state_and_rerun(**updates)


def _set_detail_section(section: str) -> None:
    st.session_state.detail_section = section
    st.rerun()


def _render_detail_section_nav() -> str:
    allowed = {section for section, _label in DETAIL_SECTION_LABELS}
    current = str(st.session_state.get("detail_section", "compare"))
    if current not in allowed:
        current = "compare"
        st.session_state.detail_section = current

    labels = dict(DETAIL_SECTION_LABELS)
    st.markdown('<div class="detail-section-segmented-marker"></div>', unsafe_allow_html=True)
    selected = st.segmented_control(
        "表示セクション",
        options=[section for section, _label in DETAIL_SECTION_LABELS],
        default=current,
        required=True,
        format_func=lambda section: labels.get(str(section), str(section)),
        key="detail_section",
        label_visibility="collapsed",
        width="stretch",
    )
    return str(selected or current)


def _clear_detail_manual_state(*, clear_selection: bool = False) -> None:
    for key in list(st.session_state.keys()):
        if key.startswith("detail_manual_"):
            del st.session_state[key]
    if clear_selection:
        st.session_state.custom_selected_tickers = []


def _set_company_select_mode(mode: str) -> None:
    st.session_state.company_select_mode = mode
    st.session_state.manual_override = mode == "manual"
    if mode == "preset":
        _clear_detail_manual_state(clear_selection=False)
    st.rerun()


def _render_company_mode_buttons(current_mode: str) -> str:
    col_preset, col_manual = st.columns(2, gap="small")
    with col_preset:
        if st.button(
            "プリセット",
            type="primary" if current_mode == "preset" else "secondary",
            width="stretch",
            key="company_mode_button_preset",
        ):
            _set_company_select_mode("preset")
    with col_manual:
        if st.button(
            "手動検索",
            type="primary" if current_mode == "manual" else "secondary",
            width="stretch",
            key="company_mode_button_manual",
        ):
            _set_company_select_mode("manual")
    return str(st.session_state.get("company_select_mode", current_mode))


def _set_industry_mode(mode: str) -> None:
    st.session_state.industry_mode = mode
    st.rerun()


def _render_industry_mode_buttons(current_mode: str, industry_policy: dict) -> str:
    modes = ["strict_jpx_industry", "business_theme", "broad_sector"]
    st.markdown('<div class="quiet-caption">業種の見方</div>', unsafe_allow_html=True)
    for mode in modes:
        label = _industry_mode_label(mode, industry_policy)
        if st.button(
            label,
            type="primary" if current_mode == mode else "secondary",
            width="stretch",
            key=f"industry_mode_button_{mode}",
        ):
            _set_industry_mode(mode)
    return str(st.session_state.get("industry_mode", current_mode))


def _set_selected_preset_id(preset_id: str) -> None:
    st.session_state.selected_preset_id = preset_id
    st.session_state.selected_preset_id_last = preset_id
    st.rerun()


def _render_preset_buttons(ordered_preset_ids: list[str], presets: dict[str, dict], current_preset_id: str) -> str:
    current = presets[current_preset_id]
    current_label = escape(str(current.get("name", current_preset_id)))
    current_desc = escape(str(current.get("description", "")))
    st.markdown("**比較セット**")
    st.markdown(
        f"""
        <div class="template-summary">
            <div class="template-summary-title">{current_label}</div>
            <p class="template-summary-body">{current_desc}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    for index in range(0, len(ordered_preset_ids), 2):
        cols = st.columns(2, gap="small")
        for col, preset_id in zip(cols, ordered_preset_ids[index : index + 2], strict=False):
            label = PRESET_BUTTON_LABELS.get(preset_id, str(presets[preset_id].get("name", preset_id)))
            with col:
                if st.button(
                    label,
                    type="primary" if preset_id == current_preset_id else "secondary",
                    width="stretch",
                    key=f"preset_button_{preset_id}",
                ):
                    _set_selected_preset_id(preset_id)
    return str(st.session_state.get("selected_preset_id", current_preset_id))


def _set_doc_type(value: int) -> None:
    st.session_state.edinet_doc_type = value
    st.rerun()


def _render_doc_type_buttons() -> int:
    if "edinet_doc_type" not in st.session_state:
        st.session_state.edinet_doc_type = 2
    current = int(st.session_state.edinet_doc_type)
    st.markdown('<div class="quiet-caption">取得タイプ</div>', unsafe_allow_html=True)
    col_meta, col_list = st.columns(2, gap="small")
    with col_meta:
        if st.button(
            "書類一覧とメタデータ",
            type="primary" if current == 2 else "secondary",
            width="stretch",
            key="edinet_doc_type_2",
        ):
            _set_doc_type(2)
    with col_list:
        if st.button(
            "書類一覧のみ",
            type="primary" if current == 1 else "secondary",
            width="stretch",
            key="edinet_doc_type_1",
        ):
            _set_doc_type(1)
    return int(st.session_state.get("edinet_doc_type", current))


def _render_edinet_filter_toggle(
    *,
    title: str,
    body: str,
    key: str,
    value: bool,
    disabled: bool = False,
) -> bool:
    with st.container(border=True):
        st.markdown(
            f"""
            <div class="edinet-filter-title">{escape(title)}</div>
            <div class="edinet-filter-body">{escape(body)}</div>
            """,
            unsafe_allow_html=True,
        )
        return st.toggle(
            title,
            value=value,
            key=key,
            disabled=disabled,
            label_visibility="collapsed",
            width="stretch",
        )


def _render_edinet_filter_help() -> None:
    st.markdown(
        """
        <div class="edinet-filter-help">
            <strong>初期設定はレポート生成向けです。</strong>
            「有報だけ」+「CSVあり」は、自動分析しやすい有価証券報告書を優先します。
            結果が少ない時は「CSVあり」をOFFにすると、PDF/XBRLのみの書類も探しやすくなります。
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_edinet_lookback_selector(target_date: date) -> int:
    preset_map = {preset_id: (days, label, body) for preset_id, days, label, body in EDINET_LOOKBACK_PRESETS}
    preset_ids = [preset_id for preset_id, _days, _label, _body in EDINET_LOOKBACK_PRESETS]
    if st.session_state.get("edinet_lookback_preset") not in preset_map:
        st.session_state.edinet_lookback_preset = "standard"

    st.markdown(
        """
        <div class="edinet-period-help">
            <div class="edinet-period-title">検索期間</div>
            EDINETは1日ごとの書類一覧を確認します。短いほど速く、長いほど提出日がずれた会社を見つけやすくなります。
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown('<div class="edinet-period-marker"></div>', unsafe_allow_html=True)
    selected = st.segmented_control(
        "検索期間",
        options=preset_ids,
        required=True,
        format_func=lambda preset_id: f"{preset_map[str(preset_id)][0]}日 {preset_map[str(preset_id)][1]}",
        key="edinet_lookback_preset",
        label_visibility="collapsed",
        width="stretch",
    )
    selected_id = str(selected or st.session_state.get("edinet_lookback_preset", "standard"))
    days, label, body = preset_map.get(selected_id, preset_map["standard"])
    start_date = target_date - timedelta(days=days - 1)
    st.markdown(
        f"""
        <div class="edinet-period-summary">
            <div>
                <strong>{start_date:%Y-%m-%d} 〜 {target_date:%Y-%m-%d}</strong> の書類一覧を確認します。{escape(body)}
            </div>
            <div class="edinet-period-badge">最大 {days}日分</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    return int(days)


def _render_template_picker(
    *,
    available_choices: list[tuple[str, str, str]],
    presets: dict[str, dict],
    industry_policy: dict,
) -> str | None:
    option_ids = [choice_id for choice_id, _title, _body in available_choices]
    if st.session_state.get("wizard_theme_choice") not in option_ids:
        st.session_state.wizard_theme_choice = None
    current = st.session_state.get("wizard_theme_choice")

    st.markdown('<div class="quiet-caption">題材テンプレート</div>', unsafe_allow_html=True)
    for index in range(0, len(available_choices), 2):
        cols = st.columns(2, gap="small")
        for col, (choice_id, title, body) in zip(cols, available_choices[index : index + 2], strict=False):
            with col:
                _render_selectable_option(
                    title=title,
                    body=body,
                    value=choice_id,
                    state_key="wizard_theme_choice",
                    button_key=f"wizard_theme_{choice_id}",
                )

    selected = st.session_state.get("wizard_theme_choice")
    if not selected:
        return None

    preset = presets.get(str(selected), {})
    companies = preset.get("companies", [])
    mode = str(preset.get("industry_mode", "自由選択")) if preset else "自由選択"
    mode_label = industry_policy.get("industry_modes", {}).get(mode, {}).get("label", mode)
    company_text = f"{len(companies)}社" if companies else "手動選択"
    purpose = APP_MODE_LABELS.get(str(preset.get("default_app_mode", "")), "自由設定") if preset else "自由設定"
    description = AUTO_THEME_DESCRIPTIONS.get(str(selected), str(preset.get("description", "")))
    st.markdown(
        f"""
        <div class="template-summary">
            <div class="template-summary-title">{AUTO_THEME_LABELS.get(str(selected), selected)}</div>
            <p class="template-summary-body">{description}</p>
            <div class="template-chip-row">
                <span>{company_text}</span>
                <span>{mode_label}</span>
                <span>{purpose}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    return str(selected)


def _filter_company_master(company_master: pd.DataFrame, query: str) -> pd.DataFrame:
    query = str(query or "").strip()
    if not query:
        return company_master.copy()
    search_columns = [
        "ticker",
        "company_name",
        "edinet_code",
        "jpx_industry",
        "broad_sector",
        "business_theme",
        "business_summary",
    ]
    mask = pd.Series(False, index=company_master.index)
    for column in search_columns:
        if column in company_master.columns:
            mask = mask | company_master[column].astype(str).str.contains(query, case=False, na=False, regex=False)
    return company_master[mask].copy()


def _company_label_lookup(company_master: pd.DataFrame) -> dict[str, str]:
    labels = {}
    for row in company_master.itertuples(index=False):
        labels[str(row.ticker)] = f"{row.ticker} {row.company_name}"
    return labels


def _parse_ticker_text(text: str) -> list[str]:
    normalized = str(text or "").replace("　", " ").replace(",", " ").replace("、", " ").replace("\n", " ")
    tickers = []
    for token in normalized.split():
        digits = "".join(char for char in token if char.isdigit())
        if len(digits) >= 4:
            tickers.append(digits[:4])
    return list(dict.fromkeys(tickers))


def _edinet_lookup_preview_table(rows: list[dict]) -> pd.DataFrame:
    columns = ["証券コード", "提出者名", "EDINETコード", "書類名", "提出日時", "CSV"]
    if not rows:
        return pd.DataFrame(columns=columns)

    frame = pd.DataFrame(rows).drop(columns=["raw_json"], errors="ignore")
    if frame.empty:
        return pd.DataFrame(columns=columns)

    def column(name: str) -> pd.Series:
        if name in frame.columns:
            return frame[name]
        return pd.Series([""] * len(frame), index=frame.index)

    sec_code = column("sec_code").astype(str).str.extract(r"(\d{4})", expand=False)
    display = pd.DataFrame(
        {
            "証券コード": sec_code.fillna(column("sec_code")),
            "提出者名": column("filer_name"),
            "EDINETコード": column("edinet_code"),
            "書類名": column("doc_description"),
            "提出日時": column("submit_datetime"),
            "CSV": column("csv_flag").astype(str).map({"1": "あり", "0": "なし"}).fillna(column("csv_flag")),
        }
    )
    return display.drop_duplicates().head(8)


def _transfer_tickers_to_edinet_tab(tickers: list[str]) -> None:
    st.session_state["edinet_ticker_lookup"] = " ".join(tickers)
    st.session_state["detail_section"] = "edinet"
    st.rerun()


def _ticker_from_sec_code(sec_code: object) -> str:
    digits = "".join(char for char in str(sec_code or "") if char.isdigit())
    return digits[:4] if len(digits) >= 4 else ""


def _infer_fiscal_year_from_filing(row: pd.Series | dict) -> int:
    value = row.get("submit_datetime", "") if isinstance(row, dict) else row.get("submit_datetime", "")
    parsed = pd.to_datetime(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(parsed):
        return date.today().year
    return int(parsed.year)


def _latest_csv_filings_by_ticker(filings: pd.DataFrame, selected_tickers: list[str]) -> pd.DataFrame:
    if filings.empty:
        return filings.copy()
    if "sec_code" not in filings.columns:
        return pd.DataFrame(columns=list(filings.columns) + ["_ticker"])

    rows = []
    for ticker in selected_tickers:
        candidates = sec_code_candidates(ticker)
        ticker_filings = filings[
            filings["sec_code"].fillna("").astype(str).str.replace(r"\D", "", regex=True).isin(candidates)
        ].copy()
        if ticker_filings.empty:
            continue
        ticker_filings["_ticker"] = str(ticker)
        ticker_filings["_submit_sort"] = pd.to_datetime(ticker_filings.get("submit_datetime", ""), errors="coerce")
        rows.append(ticker_filings.sort_values(["_submit_sort", "doc_id"], ascending=[False, False]).head(1))
    if not rows:
        return pd.DataFrame(columns=list(filings.columns) + ["_ticker"])
    return pd.concat(rows, ignore_index=True).drop(columns=["_submit_sort"], errors="ignore")


def _fetch_report_edinet_filings(
    selected_tickers: list[str],
    *,
    lookback_days: int = 120,
    annual_only: bool = True,
    csv_only: bool = False,
) -> pd.DataFrame:
    client = EdinetClient()
    if not client.has_api_key or not selected_tickers:
        return pd.DataFrame()

    matched_rows = fetch_document_rows_for_tickers(
        client,
        selected_tickers,
        end_date=date.today(),
        lookback_days=lookback_days,
        doc_type=2,
        annual_only=annual_only,
        csv_only=csv_only,
    )
    if matched_rows:
        save_filings(matched_rows)
        _clear_filings_cache()
    return pd.DataFrame(matched_rows).drop(columns=["raw_json"], errors="ignore")


def _extract_report_edinet_financial_rows(
    client: EdinetClient,
    filings: pd.DataFrame,
    selected_tickers: list[str],
) -> ReportEdinetPreflight:
    messages: list[str] = []
    warnings: list[str] = []
    latest_filings = _latest_csv_filings_by_ticker(filings, selected_tickers)
    if latest_filings.empty:
        return ReportEdinetPreflight(filings=filings, financial_rows=pd.DataFrame(), messages=messages, warnings=warnings)

    for row in latest_filings.to_dict("records"):
        doc_id = str(row.get("doc_id", "")).strip()
        ticker = str(row.get("_ticker") or _ticker_from_sec_code(row.get("sec_code"))).strip()
        if not doc_id or not ticker:
            continue
        existing_facts = load_extracted_facts(doc_id=doc_id)
        if not existing_facts.empty:
            messages.append(f"{ticker}: {doc_id} は解析済みです。")
            continue

        try:
            document_file = client.fetch_document_file(doc_id, file_type=5)
            saved_path = save_raw_document(document_file)
            facts = extract_financial_facts_from_zip(saved_path)
        except EdinetApiError as exc:
            warnings.append(f"{ticker}: {doc_id} のCSV取得をスキップしました: {exc}")
            continue
        except Exception as exc:  # pragma: no cover - Streamlit safety net
            warnings.append(f"{ticker}: {doc_id} のCSV解析をスキップしました: {exc}")
            continue

        if not facts:
            warnings.append(f"{ticker}: {doc_id} から主要財務タグを抽出できませんでした。")
            continue
        fiscal_year = _infer_fiscal_year_from_filing(row)
        saved_count = save_extracted_facts(doc_id=doc_id, ticker=ticker, fiscal_year=fiscal_year, facts=facts)
        messages.append(f"{ticker}: {doc_id} から主要財務タグを{saved_count}件保存しました。")

    financial_rows = load_edinet_financial_rows(tickers=selected_tickers)
    return ReportEdinetPreflight(
        filings=filings,
        financial_rows=financial_rows,
        messages=messages,
        warnings=warnings,
    )


def _render_report_edinet_status(preflight: ReportEdinetPreflight, selected_tickers: list[str]) -> None:
    client = EdinetClient()
    if not client.has_api_key:
        st.info("EDINET_API_KEYが未設定のため、Word生成前の自動EDINET確認はスキップされます。")
        return
    if preflight.filings.empty:
        st.caption("Word生成時にEDINET書類一覧も確認します。見つからない場合はサンプルCSV中心で作成します。")
        return
    st.success(f"EDINET書類メタデータを{len(preflight.filings)}件確認しました。")
    st.dataframe(
        _edinet_lookup_preview_table(preflight.filings.to_dict("records")),
        use_container_width=True,
        hide_index=True,
    )
    for message in preflight.messages[:8]:
        st.caption(message)
    for warning in preflight.warnings[:8]:
        st.warning(warning)
    if not preflight.financial_rows.empty:
        st.caption(f"EDINET解析済み財務行: {len(preflight.financial_rows)}件。今回のWord生成では取得済み行を優先候補として使います。")


def _run_report_edinet_preflight(selected_tickers: list[str]) -> ReportEdinetPreflight:
    try:
        filings = _fetch_report_edinet_filings(selected_tickers, annual_only=True, csv_only=True)
        client = EdinetClient()
        return _extract_report_edinet_financial_rows(client, filings, selected_tickers)
    except EdinetApiError as exc:
        st.warning(f"EDINET自動確認はスキップしました: {exc}")
    except Exception as exc:  # pragma: no cover - Streamlit safety net
        st.warning(f"EDINET自動確認中に予期しないエラーがありました: {exc}")
    return ReportEdinetPreflight(filings=pd.DataFrame(), financial_rows=pd.DataFrame(), messages=[], warnings=[])


def _company_preview_table(company_master: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    if not tickers:
        return pd.DataFrame(columns=["証券コード", "企業名", "JPX業種", "テーマ", "EDINETコード"])
    selected = select_companies(company_master, tickers)
    columns = ["ticker", "company_name", "jpx_industry", "business_theme", "edinet_code"]
    return selected[[column for column in columns if column in selected.columns]].rename(
        columns={
            "ticker": "証券コード",
            "company_name": "企業名",
            "jpx_industry": "JPX業種",
            "business_theme": "テーマ",
            "edinet_code": "EDINETコード",
        }
    )


def _render_company_selection_list(company_master: pd.DataFrame, tickers: list[str]) -> None:
    preview = _company_preview_table(company_master, tickers)
    if preview.empty:
        return
    rows = []
    for row in preview.to_dict("records"):
        code = escape(str(row.get("証券コード", "")))
        name = escape(str(row.get("企業名", "")))
        industry = escape(str(row.get("JPX業種", "")))
        theme = escape(str(row.get("テーマ", "")))
        edinet_code = escape(str(row.get("EDINETコード", "")))
        rows.append(
            f'<div class="company-selection-row">'
            f'<div class="company-selection-code">{code}</div>'
            f'<div class="company-selection-name">{name}</div>'
            f'<div class="company-selection-meta">{industry} / {theme} / EDINET {edinet_code}</div>'
            f'</div>'
        )
    st.markdown(
        f'<div class="company-selection-list">{"".join(rows)}</div>',
        unsafe_allow_html=True,
    )


def _render_company_search_selector(
    *,
    company_master: pd.DataFrame,
    default_tickers: list[str],
    key_prefix: str,
    label: str = "比較企業",
    compact: bool = False,
) -> list[str]:
    label_lookup = _company_label_lookup(company_master)
    valid_tickers = set(company_master["ticker"].astype(str))
    selected_state_key = f"{key_prefix}_selected_tickers"
    notice_key = f"{key_prefix}_edinet_lookup_notice"
    if st.session_state.get(notice_key):
        st.success(str(st.session_state[notice_key]))
        del st.session_state[notice_key]
    current_default = [
        str(ticker)
        for ticker in st.session_state.get(selected_state_key, default_tickers)
        if str(ticker) in valid_tickers
    ]

    if compact:
        st.caption("まず登録済み企業から選びます。候補にない場合はEDINET取得タブで証券コードから書類を探せます。")
        direct_text = st.text_input(
            "証券コードを直接入力",
            placeholder="例: 7203, 2802, 7011",
            key=f"{key_prefix}_ticker_direct",
        )
        query = st.text_input(
            "企業名・業種で検索",
            placeholder="例: ○○自動車、□□食品、××工業",
            key=f"{key_prefix}_company_query",
        )
    else:
        direct_col, query_col = st.columns([0.95, 1.35])
        direct_text = direct_col.text_input(
            "証券コードを直接入力",
            placeholder="例: 7203, 2802, 7011",
            key=f"{key_prefix}_ticker_direct",
        )
        query = query_col.text_input(
            "企業名・業種で検索",
            placeholder="例: ○○自動車、□□食品、××工業",
            key=f"{key_prefix}_company_query",
        )

    requested_tickers = _parse_ticker_text(direct_text)
    direct_tickers = [ticker for ticker in requested_tickers if ticker in valid_tickers]
    missing_direct_tickers = [ticker for ticker in requested_tickers if ticker not in valid_tickers]
    selected_pool = list(dict.fromkeys(current_default))
    query_filtered = _filter_company_master(company_master, query)
    if direct_tickers:
        direct_filtered = company_master[company_master["ticker"].astype(str).isin(direct_tickers)].copy()
        if query:
            filtered = pd.concat([direct_filtered, query_filtered], ignore_index=True).drop_duplicates("ticker")
        else:
            filtered = direct_filtered
    else:
        filtered = query_filtered
    filtered = filtered.head(25)

    if compact:
        st.markdown('<div class="company-remove-caption">候補から追加</div>', unsafe_allow_html=True)
        candidate_tickers = [
            str(ticker)
            for ticker in filtered["ticker"].astype(str).tolist()[:8]
            if str(ticker) not in set(selected_pool)
        ]
        if candidate_tickers:
            for ticker in candidate_tickers:
                if st.button(f"{label_lookup.get(ticker, ticker)} を追加", width="stretch", key=f"{key_prefix}_candidate_{ticker}"):
                    selected_pool = list(dict.fromkeys([*selected_pool, ticker]))
                    st.session_state[selected_state_key] = selected_pool
                    st.rerun()
        else:
            st.caption("追加できる候補はありません。")
        selected = [str(ticker) for ticker in st.session_state.get(selected_state_key, selected_pool) if str(ticker) in valid_tickers]
        st.markdown('<div class="company-remove-caption">選択中の企業</div>', unsafe_allow_html=True)
        _render_company_selection_list(company_master, selected)
        for ticker in selected:
            if st.button(f"{label_lookup.get(ticker, ticker)} を外す", width="stretch", key=f"{key_prefix}_remove_{ticker}"):
                st.session_state[selected_state_key] = [item for item in selected if item != ticker]
                st.rerun()
    else:
        st.markdown("**候補から追加**")
        candidate_tickers = [
            str(ticker)
            for ticker in filtered["ticker"].astype(str).tolist()[:12]
            if str(ticker) not in set(selected_pool)
        ]
        if candidate_tickers:
            for index in range(0, len(candidate_tickers), 2):
                cols = st.columns(2, gap="small")
                for col, ticker in zip(cols, candidate_tickers[index : index + 2], strict=False):
                    with col:
                        if st.button(
                            f"{label_lookup.get(ticker, ticker)} を追加",
                            width="stretch",
                            key=f"{key_prefix}_candidate_{ticker}",
                        ):
                            selected_pool = list(dict.fromkeys([*selected_pool, ticker]))
                            st.session_state[selected_state_key] = selected_pool
                            st.rerun()
        else:
            st.caption("追加できる候補はありません。")

        selected = [
            str(ticker)
            for ticker in st.session_state.get(selected_state_key, selected_pool)
            if str(ticker) in valid_tickers
        ]
        st.markdown(f"**{label}**")
        _render_company_selection_list(company_master, selected)
        for index in range(0, len(selected), 2):
            cols = st.columns(2, gap="small")
            for col, ticker in zip(cols, selected[index : index + 2], strict=False):
                with col:
                    if st.button(
                        f"{label_lookup.get(ticker, ticker)} を外す",
                        width="stretch",
                        key=f"{key_prefix}_remove_{ticker}",
                    ):
                        st.session_state[selected_state_key] = [item for item in selected if item != ticker]
                        st.rerun()

    if missing_direct_tickers:
        missing_text = ", ".join(missing_direct_tickers)
        st.warning(f"{missing_text} は登録済み企業マスターに見つかりません。EDINET取得タブでは書類検索を続けられます。")
        st.caption("その他の企業は、EDINET APIの書類一覧から提出者名とEDINETコードを確認できます。")
        client = EdinetClient()
        lookup_rows_key = f"{key_prefix}_edinet_lookup_rows"
        lookup_tickers_key = f"{key_prefix}_edinet_lookup_tickers"
        quick_col, detail_col = st.columns(2, gap="small")
        with quick_col:
            if st.button(
                "EDINETで未登録コードを確認",
                disabled=not client.has_api_key,
                width="stretch",
                key=f"{key_prefix}_edinet_quick_lookup",
            ):
                with st.spinner("EDINETの書類一覧を確認しています..."):
                    try:
                        matched_rows = fetch_document_rows_for_tickers(
                            client,
                            missing_direct_tickers,
                            end_date=date.today(),
                            lookback_days=120,
                            doc_type=2,
                            annual_only=False,
                            csv_only=False,
                        )
                        saved_count = save_filings(matched_rows)
                        _clear_filings_cache()
                    except EdinetApiError as exc:
                        st.error(f"EDINETで確認できませんでした: {exc}")
                        matched_rows = []
                    except Exception as exc:  # pragma: no cover - Streamlit safety net
                        st.error(f"予期しないエラーです: {exc}")
                        matched_rows = []
                st.session_state[lookup_rows_key] = matched_rows
                st.session_state[lookup_tickers_key] = missing_direct_tickers
                st.session_state["edinet_ticker_lookup"] = missing_text
                if matched_rows:
                    st.session_state[notice_key] = (
                        f"EDINETで{len(matched_rows)}件見つかりました。候補辞書を更新しました。"
                    )
                    st.rerun()
                else:
                    st.info("指定期間内のEDINET書類一覧では見つかりませんでした。期間を広げてEDINET取得タブで確認できます。")
        with detail_col:
            if st.button(
                "EDINET取得タブで詳しく探す",
                width="stretch",
                key=f"{key_prefix}_edinet_open_tab",
            ):
                _transfer_tickers_to_edinet_tab(missing_direct_tickers)
        if not client.has_api_key:
            st.info("EDINET_API_KEYをStreamlit Secretsまたは.envに設定すると、未登録コードをAPIで確認できます。")

        prior_rows = st.session_state.get(lookup_rows_key, [])
        prior_tickers = st.session_state.get(lookup_tickers_key, [])
        if prior_rows and set(prior_tickers) == set(missing_direct_tickers):
            st.dataframe(_edinet_lookup_preview_table(prior_rows), use_container_width=True, hide_index=True)
    if filtered.empty:
        st.info("登録済み企業に候補がありません。検索語を短くするか、EDINET取得タブで証券コードから書類を探してください。")
    else:
        st.caption(f"候補: {len(filtered)}社表示 / 選択中: {len(selected)}社")
    return selected


def _make_custom_preset(
    *,
    selected_tickers: list[str],
    company_master: pd.DataFrame,
    app_mode: str,
    industry_mode: str,
) -> dict:
    companies = select_companies(company_master, selected_tickers)
    themes = sorted({str(value) for value in companies.get("business_theme", pd.Series(dtype=str)).dropna()})
    theme_label = " / ".join(themes[:3]) if themes else "自由選択"
    return {
        "preset_id": "custom_selection",
        "name": "自由選択",
        "description": "証券コード、企業名、業種、事業テーマ検索から選んだ企業を比較します。",
        "companies": selected_tickers,
        "industry_mode": industry_mode,
        "default_app_mode": app_mode,
        "comparison_theme": theme_label,
        "expected_warnings": [],
        "notes": ["検索で選んだカスタム比較です。課題モードでは条件チェック結果を確認してください。"],
    }


def _compute_metrics_for_selection(dataset, selected_tickers: list[str]) -> pd.DataFrame:
    selected_financials = dataset.financials[dataset.financials["ticker"].isin(selected_tickers)].copy()
    selected_market = dataset.market_data[dataset.market_data["ticker"].isin(selected_tickers)].copy()
    selected_manual = dataset.manual_kpis[dataset.manual_kpis["ticker"].isin(selected_tickers)].copy()
    selected_companies = select_companies(dataset.company_master, selected_tickers).copy()
    selected_companies["_selection_order"] = range(len(selected_companies))
    metrics = compute_financial_metrics(selected_financials, selected_market, selected_manual)
    metrics = metrics.merge(
        selected_companies[["ticker", "company_name", "_selection_order"]],
        on="ticker",
        how="left",
    )
    return metrics.sort_values(["_selection_order", "fiscal_year"]).reset_index(drop=True)


def _render_analysis_data_source_panel(prepared: PreparedAnalysisDataset) -> None:
    st.markdown("**分析データ**")
    st.caption("通常はサンプルCSVを使います。EDINET候補は抽出済みデータの検証用で、欠損がある場合は慎重に確認してください。")
    mode_options = [DATA_SOURCE_SAMPLE, DATA_SOURCE_EDINET_OVERLAY]
    if st.session_state.get("analysis_data_source_mode") not in mode_options:
        st.session_state.analysis_data_source_mode = DATA_SOURCE_SAMPLE
    selected = st.segmented_control(
        "分析データ",
        options=mode_options,
        required=True,
        format_func=lambda value: "EDINET候補を優先" if value == DATA_SOURCE_EDINET_OVERLAY else "サンプルCSV",
        key="analysis_data_source_mode",
        label_visibility="collapsed",
        width="stretch",
    )
    if selected == DATA_SOURCE_EDINET_OVERLAY and prepared.edinet_rows.empty:
        st.info("保存済みEDINET抽出候補はまだありません。EDINET取得タブでCSV ZIPを取得・解析すると候補が表示されます。")
    elif selected == DATA_SOURCE_EDINET_OVERLAY:
        st.info("同じ証券コード・年度のEDINET候補がある場合だけ、サンプルCSVより優先します。欠損値はレポート上で注記対象です。")

    if not prepared.source_summary.empty:
        audit_table = build_data_source_audit(prepared.source_summary)
        if not audit_table.empty:
            st.markdown("**データ監査**")
            st.dataframe(
                audit_table.rename(
                    columns={
                        "ticker": "証券コード",
                        "fiscal_year": "年度",
                        "data_source": "データソース",
                        "doc_id": "docID",
                        "coverage_rate": "主要項目カバー率",
                        "status": "状態",
                        "note": "確認メモ",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )
        st.markdown("**データソース詳細**")
        st.dataframe(
            prepared.source_summary.rename(
                columns={
                    "ticker": "証券コード",
                    "fiscal_year": "年度",
                    "data_source": "データソース",
                    "doc_id": "docID",
                    "available_metrics": "取得済み項目数",
                    "missing_metrics": "欠損項目数",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )


def _score_preview_table(scores: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "ticker",
        "company_name",
        "data_completeness",
        "growth_score",
        "profitability_score",
        "stability_score",
        "cashflow_score",
        "analysis_quality_score",
        "analysis_band",
    ]
    existing = [column for column in columns if column in scores.columns]
    labels = {
        "ticker": "証券コード",
        "company_name": "企業名",
        **SCORE_LABELS,
    }
    return scores[existing].rename(columns=labels)


def _build_prompt_download(
    *,
    selected_tickers: list[str],
    preset_id: str,
    preset: dict,
    app_mode: str,
    industry_mode: str,
    dataset,
    data_source_audit: pd.DataFrame | None = None,
) -> tuple[str, str]:
    edinet_filings = _load_filings_cached(200)
    edinet_filings = _filter_filings_by_tickers(edinet_filings, selected_tickers).head(20)
    prompt = build_llm_report_prompt(
        selected_tickers=selected_tickers,
        preset={**preset, "preset_id": preset_id},
        app_mode=app_mode,
        industry_mode=industry_mode,
        dataset=dataset,
        as_of=date.today(),
        edinet_filings=edinet_filings,
        data_source_audit=data_source_audit,
    )
    file_name = f"{preset_id}_llm_report_prompt.md"
    return file_name, prompt


def _render_llm_prompt_panel(*, file_name: str, prompt_text: str, key_prefix: str) -> None:
    st.markdown("**LLM用プロンプト**")
    st.code(prompt_text, language="markdown", wrap_lines=True, height=420)
    encoded_prompt = base64.b64encode(prompt_text.encode("utf-8")).decode("ascii")
    copy_html = f"""
    <button
      type="button"
      style="
        width: 100%;
        border: 1px solid rgba(0, 113, 227, 0.24);
        border-radius: 999px;
        padding: 12px 16px;
        background: linear-gradient(180deg, rgba(255,255,255,0.92), rgba(245,248,255,0.78));
        color: #0066cc;
        font-weight: 700;
        font-size: 15px;
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.95), 0 10px 26px rgba(0,113,227,0.12);
        cursor: pointer;
      "
      onclick="const raw = atob('{encoded_prompt}'); const bytes = Uint8Array.from(raw, c => c.charCodeAt(0)); const text = new TextDecoder().decode(bytes); navigator.clipboard.writeText(text).then(() => this.textContent = 'コピーしました').catch(() => this.textContent = 'コピーできませんでした')"
    >
      プロンプトをコピー
    </button>
    """
    components.html(copy_html, height=58)
    st.download_button(
        "Markdownをダウンロード",
        data=prompt_text.encode("utf-8"),
        file_name=file_name,
        mime="text/markdown",
        width="stretch",
        key=f"{key_prefix}_download_llm_prompt",
    )


def _render_plus_alpha_preview(
    metrics: pd.DataFrame,
    selected_companies: pd.DataFrame,
    missing_label: str,
    *,
    app_mode: str,
    industry_mode: str,
    expanded: bool = False,
) -> None:
    with st.expander("必須部分と＋αの見方", expanded=expanded):
        st.caption("必須は課題の最低限、＋αは差の理由や今後の見方まで踏み込む追加分析です。")
        st.dataframe(build_required_plus_alpha_table(), use_container_width=True, hide_index=True)
        tab_alpha, tab_dupont, tab_bridge, tab_risk, tab_issue = st.tabs(
            ["＋α詳細", "ROE要因", "利益ブリッジ", "感応度・リスク", "論点"]
        )
        with tab_alpha:
            plus_alpha = build_plus_alpha_analysis_table(metrics, selected_companies, missing_label=missing_label)
            st.dataframe(plus_alpha, use_container_width=True, hide_index=True)
        with tab_dupont:
            st.dataframe(build_dupont_driver_table(metrics, missing_label), use_container_width=True, hide_index=True)
        with tab_bridge:
            st.dataframe(build_profit_bridge_table(metrics, missing_label), use_container_width=True, hide_index=True)
        with tab_risk:
            st.dataframe(
                build_sensitivity_risk_table(metrics, missing_label=missing_label),
                use_container_width=True,
                hide_index=True,
            )
        with tab_issue:
            st.dataframe(
                build_management_issue_table(
                    metrics,
                    selected_companies,
                    app_mode=app_mode,
                    industry_mode=industry_mode,
                    missing_label=missing_label,
                ),
                use_container_width=True,
                hide_index=True,
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
    presets: dict[str, dict],
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
        cols = st.columns(2)
        with cols[0]:
            _render_selectable_option(
                title="大学課題として作る",
                body="上場日、上場後3年以上、同一業種、除外業種を自動チェックします。",
                value="assignment",
                state_key="wizard_purpose_choice",
                button_key="wizard_purpose_assignment",
            )
        with cols[1]:
            _render_selectable_option(
                title="自由に比較する",
                body="金融・医療も含め、事業テーマや広義セクターで柔軟に比較します。",
                value="general",
                state_key="wizard_purpose_choice",
                button_key="wizard_purpose_general",
            )
        purpose_choice = st.session_state.get("wizard_purpose_choice")
        st.markdown('<div class="wizard-action-spacer"></div>', unsafe_allow_html=True)
        _render_proceed_button(
            "進む",
            enabled=bool(purpose_choice),
            key="wizard_purpose_proceed",
            app_mode=purpose_choice or app_mode,
            wizard_step=1,
        )
        return

    if current_step == 1:
        available_choices = [
            choice for choice in AUTO_THEME_CHOICES if choice[0] == "custom_selection" or choice[0] in presets
        ]
        theme_choice = _render_template_picker(
            available_choices=available_choices,
            presets=presets,
            industry_policy=industry_policy,
        )
        custom_selected = list(st.session_state.get("custom_selected_tickers", []))
        if theme_choice == "custom_selection":
            st.markdown('<div class="soft-divider"></div>', unsafe_allow_html=True)
            custom_selected = _render_company_search_selector(
                company_master=dataset.company_master,
                default_tickers=custom_selected or selected_tickers,
                key_prefix="wizard_custom",
            )
            st.session_state.custom_selected_tickers = custom_selected
            ready = len(custom_selected) >= int(rubric["assignment"]["min_companies"])
            _render_proceed_button(
                "選んだ企業で進む",
                enabled=ready,
                key="wizard_custom_proceed",
                manual_override=True,
                custom_selected_tickers=custom_selected,
                wizard_step=2,
            )
        else:
            ready = bool(theme_choice and theme_choice in presets)
            chosen_preset = presets.get(str(theme_choice), {})
            _render_proceed_button(
                "この比較で進む",
                enabled=ready,
                key="wizard_theme_proceed",
                selected_preset_id=theme_choice or preset_id,
                manual_override=False,
                custom_selected_tickers=list(chosen_preset.get("companies", selected_tickers)),
                industry_mode=str(chosen_preset.get("industry_mode", industry_mode)),
                wizard_step=2,
            )

        if st.button("戻る", width="stretch", key="wizard_back_to_purpose"):
            _set_state_and_rerun(wizard_step=0, wizard_purpose_choice=None)
        return

    if current_step == 2:
        cols = st.columns(3)
        mode_copy = {
            "strict_jpx_industry": ("JPX業種で厳密に比較", "大学課題の標準。業種一致の説明がしやすい見方です。"),
            "business_theme": ("事業テーマで比較", "カフェ、航空、外食など実際の事業の近さを優先します。"),
            "broad_sector": ("広い分類で比較", "食関連、店舗ビジネス、運輸など大きな括りで見ます。"),
        }
        for col, mode in zip(cols, ["strict_jpx_industry", "business_theme", "broad_sector"], strict=False):
            with col:
                title, body = mode_copy[mode]
                _render_selectable_option(
                    title=title,
                    body=body,
                    value=mode,
                    state_key="wizard_industry_choice",
                    button_key=f"wizard_industry_{mode}",
                )
        industry_choice = st.session_state.get("wizard_industry_choice")
        chosen_mode = str(industry_choice or industry_mode)
        if app_mode == "assignment" and chosen_mode != "strict_jpx_industry":
            st.warning("課題モードではJPX業種一致が標準です。テーマ比較や広義セクターは警告付きになります。")
        st.markdown('<div class="wizard-action-spacer"></div>', unsafe_allow_html=True)
        _render_proceed_button(
            "進む",
            enabled=bool(industry_choice),
            key="wizard_industry_proceed",
            industry_mode=chosen_mode,
            wizard_step=3,
        )
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

    if len(selected_tickers) >= int(rubric["assignment"]["min_companies"]):
        metrics_preview = _compute_metrics_for_selection(dataset, selected_tickers)
        scores = build_company_scores(metrics_preview)
        st.subheader("分析品質サマリー")
        st.caption("選択企業内での相対スコアです。投資判断ではなく、比較レポートの読み取り補助として使います。")
        st.dataframe(_score_preview_table(scores), use_container_width=True, hide_index=True)
        _render_plus_alpha_preview(
            metrics_preview,
            selected_companies,
            str(rubric["assignment"]["missing_value_label"]),
            app_mode=app_mode,
            industry_mode=industry_mode,
        )

    prompt_file_name = ""
    prompt_text = ""
    prompt_ready = len(selected_tickers) >= int(rubric["assignment"]["min_companies"])
    if prompt_ready:
        prompt_file_name, prompt_text = _build_prompt_download(
            selected_tickers=selected_tickers,
            preset_id=preset_id,
            preset=preset,
            app_mode=app_mode,
            industry_mode=industry_mode,
            dataset=dataset,
        )

    actions = st.columns([1.2, 1, 1])
    with actions[0]:
        disabled = len(selected_tickers) < int(rubric["assignment"]["min_companies"])
        if st.button("Wordレポートを作成", type="primary", disabled=disabled, width="stretch", key="wizard_generate_report"):
            with st.spinner("レポートを作成しています..."):
                preflight = _run_report_edinet_preflight(selected_tickers)
                report_prepared = prepare_analysis_dataset(
                    dataset,
                    selected_tickers,
                    source_mode=DATA_SOURCE_EDINET_OVERLAY,
                    edinet_rows=preflight.financial_rows,
                )
                package = build_report_package(
                    selected_tickers=selected_tickers,
                    preset={**preset, "preset_id": preset_id},
                    app_mode=app_mode,
                    industry_mode=industry_mode,
                    dataset=report_prepared.dataset,
                    as_of=date.today(),
                    edinet_filings=preflight.filings,
                )
            st.success(f"生成しました: {package.docx_path.name}")
            _render_report_edinet_status(preflight, selected_tickers)
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
    if prompt_ready:
        _render_llm_prompt_panel(
            file_name=prompt_file_name,
            prompt_text=prompt_text,
            key_prefix="wizard",
        )


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


def _filter_filings_by_tickers(filings: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    if filings.empty or not tickers or "sec_code" not in filings.columns:
        return filings
    candidates: set[str] = set()
    for ticker in tickers:
        candidates.update(sec_code_candidates(ticker))
    return filings[
        filings["sec_code"].fillna("").astype(str).str.replace(r"\D", "", regex=True).isin(candidates)
    ].reset_index(drop=True)


@st.cache_data(ttl=30, show_spinner=False)
def _load_filings_cached(limit: int) -> pd.DataFrame:
    return load_filings(limit=limit)


@st.cache_data(ttl=30, show_spinner=False)
def _load_filings_for_company_directory(limit: int) -> pd.DataFrame:
    return load_filings(limit=limit)


def _clear_filings_cache() -> None:
    _load_filings_cached.clear()
    _load_filings_for_company_directory.clear()


def _load_dataset_with_edinet_directory():
    dataset = _load_dataset_with_edinet_directory()
    try:
        filings = _load_filings_for_company_directory(50_000)
    except Exception:
        return dataset
    return overlay_dataset_company_master(dataset, filings)


def _ordered_presets(presets: dict[str, dict]) -> list[tuple[str, dict]]:
    preferred_order = [
        "friend_cafe_theme",
        "strict_cafe_retail",
        "cafe_three_theme",
        "komeda_franchise_wholesale",
        "food_retail_general",
        "airline_assignment",
        "airline_relisting_focus",
        "airline_general",
        "airline_full_general",
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


def _render_edinet_panel(selected_companies: pd.DataFrame | None = None) -> None:
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
    st.info(
        "通常表示はサンプルCSVを基準にします。EDINET連携は、証券コードから書類一覧を検索し、"
        "CSV ZIPの保存、主要財務タグ候補の抽出、Word生成時の候補反映まで対応しています。"
        "欠損が多い場合はサンプルCSVや注記と照合してください。"
    )

    selected_companies = selected_companies if selected_companies is not None else pd.DataFrame()
    selected_tickers = (
        selected_companies["ticker"].dropna().astype(str).tolist()
        if not selected_companies.empty and "ticker" in selected_companies.columns
        else []
    )

    if selected_tickers:
        st.markdown(
            f"""
            <div class="edinet-focus-panel">
                <div class="template-summary-title">選択中企業からEDINETを探す</div>
                <p class="template-summary-body">
                    現在の比較企業の証券コードを使って、直近のEDINET書類一覧を取得し、有価証券報告書とCSV有無で絞り込みます。
                </p>
                <div class="template-chip-row">
                    {"".join(f"<span>{ticker}</span>" for ticker in selected_tickers)}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
    )

    target_date = st.date_input("取得日", value=date.today() - timedelta(days=1))
    doc_type = _render_doc_type_buttons()

    if not client.has_api_key:
        st.info("`.env` の `EDINET_API_KEY` にAPIキーを保存すると取得できます。")

    if st.button("書類一覧を取得", type="primary", disabled=not client.has_api_key):
        with st.spinner("EDINETへ問い合わせています..."):
            try:
                payload = client.fetch_documents(target_date=target_date, doc_type=doc_type)
                rows = extract_document_rows(payload)
                saved_count = save_filings(rows)
                _clear_filings_cache()
            except EdinetApiError as exc:
                st.error(f"取得できませんでした: {exc}")
                return
            except Exception as exc:  # pragma: no cover - Streamlit safety net
                st.error(f"予期しないエラーです: {exc}")
                return

        st.success(f"{len(rows)}件を取得し、{saved_count}件を保存しました。")

    st.markdown("**企業候補辞書を広げる**")
    st.caption(
        "指定期間内のEDINET提出者から、証券コード・提出者名・EDINETコードをSQLiteに蓄積します。"
        "検索候補は次の再描画から自動で増えます。財務CSV本体はWord生成時や個別CSV取得時に取得します。"
    )
    directory_days = st.selectbox(
        "辞書更新期間",
        options=[30, 45, 90, 120],
        index=1,
        format_func=lambda value: f"直近{value}日分",
        key="edinet_directory_lookback_days",
    )
    if st.button(
        "期間内の提出者で候補辞書を更新",
        disabled=not client.has_api_key,
        width="stretch",
        key="edinet_update_company_directory",
    ):
        with st.spinner("EDINETの提出者一覧を日付ごとに確認しています..."):
            try:
                rows = fetch_document_rows_in_period(
                    client,
                    end_date=target_date,
                    lookback_days=int(directory_days),
                    doc_type=doc_type,
                    annual_only=False,
                    csv_only=False,
                )
                saved_count = save_filings(rows)
                _clear_filings_cache()
            except EdinetApiError as exc:
                st.error(f"取得できませんでした: {exc}")
                return
            except Exception as exc:  # pragma: no cover - Streamlit safety net
                st.error(f"予期しないエラーです: {exc}")
                return
        st.success(f"{len(rows)}件の提出者候補を確認し、{saved_count}件を保存しました。")

    st.divider()
    _render_section_intro(
        "Ticker lookup",
        "証券コードからEDINET書類を探す",
        "EDINETは日付別の書類一覧APIなので、指定期間を取得して証券コードで絞り込みます。",
    )
    ticker_default = " ".join(selected_tickers)
    ticker_text = st.text_input(
        "証券コード",
        value=ticker_default,
        placeholder="例: 3543 3087 9201",
        key="edinet_ticker_lookup",
    )
    lookup_tickers = _parse_ticker_text(ticker_text)
    lookback_days = _render_edinet_lookback_selector(target_date)
    st.markdown("**検索条件**")
    _render_edinet_filter_help()
    lookup_filter_cols = st.columns(2, gap="small")
    with lookup_filter_cols[0]:
        lookup_annual_only = _render_edinet_filter_toggle(
            title="有報だけ",
            body="有価証券報告書に限定して探します。",
            key="edinet_lookup_annual",
            value=True,
        )
    with lookup_filter_cols[1]:
        lookup_csv_only = _render_edinet_filter_toggle(
            title="CSVあり",
            body="CSV形式で取得できる書類だけに絞ります。",
            key="edinet_lookup_csv",
            value=True,
        )

    if st.button(
        "証券コードでEDINET検索",
        type="primary",
        disabled=not client.has_api_key or not lookup_tickers,
        width="stretch",
    ):
        with st.spinner("EDINET書類一覧を日付ごとに確認しています..."):
            try:
                matched_rows = fetch_document_rows_for_tickers(
                    client,
                    lookup_tickers,
                    end_date=target_date,
                    lookback_days=lookback_days,
                    doc_type=doc_type,
                    annual_only=lookup_annual_only,
                    csv_only=lookup_csv_only,
                )
                saved_count = save_filings(matched_rows)
                _clear_filings_cache()
            except EdinetApiError as exc:
                st.error(f"取得できませんでした: {exc}")
                return
            except Exception as exc:  # pragma: no cover - Streamlit safety net
                st.error(f"予期しないエラーです: {exc}")
                return
        if matched_rows:
            st.success(f"{len(matched_rows)}件見つかり、{saved_count}件を保存しました。")
            st.dataframe(pd.DataFrame(matched_rows).drop(columns=["raw_json"], errors="ignore"), use_container_width=True, hide_index=True)
        else:
            st.info("指定期間内に条件へ合う書類は見つかりませんでした。検索期間を広げてください。")

    filings = _load_filings_cached(100)
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
        query = st.text_input("検索", placeholder="会社名、EDINETコード、docID")
        st.markdown("**絞り込み**")
        _render_edinet_filter_help()
        filter_col_b, filter_col_c, filter_col_d = st.columns(3, gap="small")
        with filter_col_b:
            annual_only = _render_edinet_filter_toggle(
                title="有報だけ",
                body="有価証券報告書に限定します。",
                key="edinet_saved_annual_only",
                value=True,
            )
        with filter_col_c:
            csv_only = _render_edinet_filter_toggle(
                title="CSVあり",
                body="CSV取得に対応した書類だけ表示します。",
                key="edinet_saved_csv_only",
                value=True,
            )
        with filter_col_d:
            selected_only = _render_edinet_filter_toggle(
                title="選択企業",
                body="現在の比較企業に関連する書類だけ表示します。",
                key="edinet_saved_selected_only",
                value=bool(selected_tickers),
                disabled=not selected_tickers,
            )
        filtered_filings = filter_filings(filings, query=query, annual_only=annual_only, csv_only=csv_only)
        if selected_only:
            filtered_filings = _filter_filings_by_tickers(filtered_filings, selected_tickers)
        st.dataframe(filtered_filings, use_container_width=True, hide_index=True)

        if filtered_filings.empty:
            st.info("条件に合う書類はありません。")
        else:
            options = filtered_filings["doc_id"].astype(str).tolist()
            label_lookup = {
                str(row.doc_id): f"{row.doc_id} | {row.filer_name} | {row.doc_description}"
                for row in filtered_filings.itertuples(index=False)
            }
            selected_doc_id = str(st.session_state.get("edinet_selected_doc_id", ""))
            if selected_doc_id not in options:
                selected_doc_id = options[0]
                st.session_state.edinet_selected_doc_id = selected_doc_id
            st.markdown("**CSVを取得する書類**")
            st.markdown(f"選択中: {escape(label_lookup.get(selected_doc_id, selected_doc_id))}")
            visible_options = options[:10]
            for doc_id in visible_options:
                button_type = "primary" if doc_id == selected_doc_id else "secondary"
                if st.button(
                    label_lookup.get(doc_id, doc_id),
                    type=button_type,
                    width="stretch",
                    key=f"edinet_select_doc_{doc_id}",
                ):
                    st.session_state.edinet_selected_doc_id = doc_id
                    st.rerun()
            if len(options) > len(visible_options):
                st.caption(f"{len(options)}件中{len(visible_options)}件を表示しています。検索欄で絞り込めます。")
            saved_facts = load_extracted_facts(doc_id=selected_doc_id)
            if not saved_facts.empty:
                st.markdown("**保存済みのCSV解析結果**")
                st.caption(f"{len(saved_facts)}件の主要財務タグ候補がSQLiteに保存されています。")
                st.dataframe(saved_facts.head(12), use_container_width=True, hide_index=True)
                saved_rows = load_edinet_financial_rows(
                    tickers=saved_facts["ticker"].dropna().astype(str).unique().tolist()
                )
                saved_rows = saved_rows[saved_rows["doc_id"].astype(str) == selected_doc_id]
                if not saved_rows.empty:
                    st.markdown("**保存済みの分析用データ候補**")
                    st.dataframe(saved_rows.head(5), use_container_width=True, hide_index=True)
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
                try:
                    facts = extract_financial_facts_from_zip(saved_path)
                except Exception:
                    facts = []
                if facts:
                    doc_row = filtered_filings[filtered_filings["doc_id"].astype(str) == selected_doc_id].head(1)
                    ticker_for_preview = (
                        str(doc_row["sec_code"].iloc[0])[:4]
                        if not doc_row.empty and "sec_code" in doc_row.columns
                        else ""
                    )
                    fiscal_year = target_date.year
                    saved_count = save_extracted_facts(
                        doc_id=selected_doc_id,
                        ticker=ticker_for_preview,
                        fiscal_year=fiscal_year,
                        facts=facts,
                    )
                    st.caption(
                        f"CSV ZIPから主要財務タグ候補を抽出し、SQLiteに{saved_count}件保存しました。"
                        "同じ証券コード・年度のEDINET候補は、検証モードやWord生成前確認で優先候補として使えます。"
                    )
                    st.dataframe(summarize_facts(facts).head(30), use_container_width=True, hide_index=True)
                    normalized_preview = facts_to_financial_row(
                        ticker=ticker_for_preview,
                        fiscal_year=fiscal_year,
                        facts=facts,
                    )
                    st.markdown("**分析用データ候補**")
                    st.dataframe(pd.DataFrame([normalized_preview]), use_container_width=True, hide_index=True)
                else:
                    st.caption(
                        "保存したCSV ZIPから主要財務タグ候補はまだ抽出できませんでした。"
                        "タグ揺れやCSV構造に合わせたマッピングを追加していきます。"
                    )


def main() -> None:
    st.set_page_config(
        page_title="企業比較レポート",
        page_icon="assets/favicon.svg",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _apply_style()
    _consume_home_query()

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
    if "wizard_purpose_choice" not in st.session_state:
        st.session_state.wizard_purpose_choice = None
    if "wizard_theme_choice" not in st.session_state:
        st.session_state.wizard_theme_choice = None
    if "wizard_industry_choice" not in st.session_state:
        st.session_state.wizard_industry_choice = None
    if "selected_preset_id" not in st.session_state or st.session_state.selected_preset_id not in presets:
        st.session_state.selected_preset_id = ordered_preset_ids[0]
    active_preset = presets[st.session_state.selected_preset_id]
    if "app_mode" not in st.session_state:
        st.session_state.app_mode = str(active_preset.get("default_app_mode", "assignment"))
    if "manual_override" not in st.session_state:
        st.session_state.manual_override = False
    if "company_select_mode" not in st.session_state:
        st.session_state.company_select_mode = "manual" if bool(st.session_state.manual_override) else "preset"
    if st.session_state.company_select_mode not in {"preset", "manual"}:
        st.session_state.company_select_mode = "preset"
    st.session_state.manual_override = st.session_state.company_select_mode == "manual"
    if "selected_preset_id_last" not in st.session_state:
        st.session_state.selected_preset_id_last = st.session_state.selected_preset_id
    if "custom_selected_tickers" not in st.session_state:
        st.session_state.custom_selected_tickers = []
    if "analysis_data_source_mode" not in st.session_state:
        st.session_state.analysis_data_source_mode = DATA_SOURCE_SAMPLE
    industry_modes = list(industry_policy["industry_modes"].keys())
    if "industry_mode" not in st.session_state or st.session_state.industry_mode not in industry_modes:
        st.session_state.industry_mode = str(active_preset.get("industry_mode", rubric["assignment"]["default_industry_mode"]))
    _consume_choice_query()
    _consume_detail_section_query()

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
    workflow_marker = "detail" if workflow_mode == "detail" else "auto"
    st.markdown(
        f'<div class="workflow-mode-marker workflow-mode-{workflow_marker}"></div>',
        unsafe_allow_html=True,
    )

    preset_id = st.session_state.selected_preset_id
    preset = presets[preset_id]
    app_mode = str(st.session_state.app_mode)
    industry_mode = str(st.session_state.industry_mode)
    manual_override = bool(st.session_state.manual_override)
    selected_tickers = list(preset["companies"])

    if workflow_mode == "detail":
        with st.sidebar:
            st.header("比較設定")
            st.caption("プリセットで始めるか、証券コード・企業名・業種から手動で選びます。")
            st.markdown("**企業選択**")
            company_select_mode = str(st.session_state.get("company_select_mode", "preset"))
            if company_select_mode not in {"preset", "manual"}:
                company_select_mode = "preset"
                st.session_state.company_select_mode = "preset"
            company_select_mode = _render_company_mode_buttons(company_select_mode)
            if company_select_mode not in {"preset", "manual"}:
                company_select_mode = "preset"
                st.session_state.company_select_mode = "preset"
            manual_override = company_select_mode == "manual"
            st.session_state.manual_override = manual_override
            if not manual_override:
                _clear_detail_manual_state(clear_selection=False)

            if manual_override:
                st.caption("手動検索では比較セットを使いません。企業を2社以上選ぶと、その組み合わせで分析します。")
            else:
                _clear_detail_manual_state(clear_selection=False)
                preset_id = _render_preset_buttons(ordered_preset_ids, presets, preset_id)
                if preset_id != st.session_state.get("selected_preset_id_last"):
                    st.session_state.selected_preset_id_last = preset_id
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
            industry_mode = str(st.session_state.get("industry_mode", industry_mode))
            if industry_mode not in industry_modes:
                industry_mode = str(active_preset.get("industry_mode", rubric["assignment"]["default_industry_mode"]))
                st.session_state.industry_mode = industry_mode
            industry_mode = _render_industry_mode_buttons(industry_mode, industry_policy)
            manual_search_slot = st.empty()
            if manual_override:
                with manual_search_slot.container():
                    selected_tickers = list(st.session_state.get("custom_selected_tickers", []))
                    selected_tickers = _render_company_search_selector(
                        company_master=dataset.company_master,
                        default_tickers=selected_tickers,
                        key_prefix="detail_manual",
                        compact=True,
                    )
                    st.session_state.custom_selected_tickers = selected_tickers
            else:
                manual_search_slot.empty()
                selected_tickers = list(preset["companies"])

    if manual_override:
        selected_tickers = list(st.session_state.get("custom_selected_tickers", selected_tickers))
        preset = _make_custom_preset(
            selected_tickers=selected_tickers,
            company_master=dataset.company_master,
            app_mode=app_mode,
            industry_mode=industry_mode,
        )
        preset_id = "custom_selection"

    selected_companies = select_companies(dataset.company_master, selected_tickers)
    analysis_source_mode = (
        DATA_SOURCE_SAMPLE
        if workflow_mode == "auto"
        else str(st.session_state.get("analysis_data_source_mode", DATA_SOURCE_SAMPLE))
    )
    prepared_analysis = prepare_analysis_dataset(
        dataset,
        selected_tickers,
        source_mode=analysis_source_mode,
    )
    analysis_dataset = prepared_analysis.dataset
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
            presets=presets,
            app_mode=app_mode,
            industry_mode=industry_mode,
            selected_tickers=selected_tickers,
            selected_companies=selected_companies,
            preview=preview,
            dataset=analysis_dataset,
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

    detail_section = _render_detail_section_nav()

    if detail_section == "compare":
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

    elif detail_section == "checks":
        _render_section_intro(
            "Assignment check",
            "課題条件の確認",
            "大学課題モードでは、上場日、上場後年数、業種一致、除外業種をYAMLの条件に沿って確認します。",
        )
        _show_condition_warnings(warning_list)
        st.dataframe(preview["condition_table"], use_container_width=True, hide_index=True)
        st.subheader("企業別の上場条件")
        st.dataframe(preview["company_check_table"], use_container_width=True, hide_index=True)

    elif detail_section == "report":
        _render_section_intro(
            "Report",
            "Wordレポートを生成",
            "表、グラフ、警告、欠損注記、参考資料をまとめた日本語Wordファイルを作成します。",
        )
        disabled = len(selected_tickers) < int(rubric["assignment"]["min_companies"])
        _render_analysis_data_source_panel(prepared_analysis)
        if not disabled:
            report_metrics_preview = _compute_metrics_for_selection(analysis_dataset, selected_tickers)
            _render_plus_alpha_preview(
                report_metrics_preview,
                selected_companies,
                str(rubric["assignment"]["missing_value_label"]),
                app_mode=app_mode,
                industry_mode=industry_mode,
            )
            prompt_file_name, prompt_text = _build_prompt_download(
                selected_tickers=selected_tickers,
                preset_id=preset_id,
                preset=preset,
                app_mode=app_mode,
                industry_mode=industry_mode,
                dataset=analysis_dataset,
                data_source_audit=build_data_source_audit(prepared_analysis.source_summary),
            )
        else:
            prompt_file_name = ""
            prompt_text = ""
        generate_clicked = st.button("レポートを生成", type="primary", disabled=disabled, width="stretch")
        st.markdown(
            '<p class="report-note">Word生成はLLMなしの確定出力です。'
            'LLM用プロンプトはClaudeなどで文章を磨くための草稿依頼です。</p>',
            unsafe_allow_html=True,
        )
        if not disabled:
            _render_llm_prompt_panel(
                file_name=prompt_file_name,
                prompt_text=prompt_text,
                key_prefix="detail",
            )
        if generate_clicked:
            with st.spinner("レポートを作成しています..."):
                preflight = _run_report_edinet_preflight(selected_tickers)
                report_prepared = prepare_analysis_dataset(
                    dataset,
                    selected_tickers,
                    source_mode=DATA_SOURCE_EDINET_OVERLAY,
                    edinet_rows=preflight.financial_rows,
                )
                package = build_report_package(
                    selected_tickers=selected_tickers,
                    preset={**preset, "preset_id": preset_id},
                    app_mode=app_mode,
                    industry_mode=industry_mode,
                    dataset=report_prepared.dataset,
                    as_of=date.today(),
                    edinet_filings=preflight.filings,
                )
            st.success(f"生成しました: {package.docx_path.name}")
            _render_report_edinet_status(preflight, selected_tickers)

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

            st.subheader("分析品質サマリー")
            st.dataframe(_score_preview_table(package.quality_scores), use_container_width=True, hide_index=True)

            st.subheader("グラフ")
            columns = st.columns(2)
            for idx, (slug, path) in enumerate(package.chart_paths.items()):
                with columns[idx % 2]:
                    st.image(str(path), caption=slug, use_container_width=True)

            if package.missing_notes:
                st.subheader("欠損データ注記")
                for note in package.missing_notes:
                    st.write(f"- {note}")

    elif detail_section == "edinet":
        _render_edinet_panel(selected_companies=selected_companies)


if __name__ == "__main__":
    main()
