from datetime import date

import pandas as pd

from src.config_loader import load_presets
from src.data_loader import load_sample_dataset
from src.llm_prompt import build_llm_report_prompt


def test_llm_prompt_contains_report_inputs_and_avoids_banned_advice_terms():
    preset = load_presets()["friend_cafe_theme"]
    prompt = build_llm_report_prompt(
        selected_tickers=preset["companies"],
        preset={**preset, "preset_id": "friend_cafe_theme"},
        app_mode="assignment",
        industry_mode=preset["industry_mode"],
        dataset=load_sample_dataset(),
        as_of=date(2026, 6, 17),
    )

    assert "企業比較レポート作成プロンプト" in prompt
    assert "コメダホールディングス" in prompt
    assert "ドトール・日レスホールディングス" in prompt
    assert "分析品質スコア" in prompt
    assert "必須部分と＋αの区分" in prompt
    assert "＋α分析テーブル" in prompt
    assert "高度アルゴリズム: ROE要因分解" in prompt
    assert "高度アルゴリズム: 営業利益ブリッジ" in prompt
    assert "高度アルゴリズム: 経営分析論点" in prompt
    assert "データソースとEDINET反映状況" in prompt
    assert "EDINET CSV/XBRLを財務数値へ正規化して再計算する処理は未反映" in prompt
    assert "推定不可" in prompt
    assert "投資すべき" not in prompt


def test_llm_prompt_can_include_edinet_filing_metadata():
    preset = load_presets()["airline_assignment"]
    filings = pd.DataFrame(
        [
            {
                "doc_id": "S100TEST",
                "edinet_code": "E04272",
                "sec_code": "92010",
                "filer_name": "日本航空株式会社",
                "doc_description": "有価証券報告書",
                "submit_datetime": "2026-06-17 10:00",
                "xbrl_flag": "1",
                "csv_flag": "1",
            }
        ]
    )

    prompt = build_llm_report_prompt(
        selected_tickers=preset["companies"],
        preset={**preset, "preset_id": "airline_assignment"},
        app_mode="assignment",
        industry_mode=preset["industry_mode"],
        dataset=load_sample_dataset(),
        as_of=date(2026, 6, 17),
        edinet_filings=filings,
    )

    assert "EDINET取得済み書類メタデータ" in prompt
    assert "S100TEST" in prompt
    assert "日本航空株式会社" in prompt
    assert "CSV/XBRL有無を出典候補" in prompt
