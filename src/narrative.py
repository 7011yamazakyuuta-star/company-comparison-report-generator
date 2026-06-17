from __future__ import annotations

import pandas as pd

from .metrics.financial import METRIC_LABELS


def build_selection_reason(companies: pd.DataFrame, preset: dict[str, object], industry_result: dict[str, object]) -> str:
    names = "、".join(companies["company_name"].astype(str))
    theme = preset.get("comparison_theme") or "選択テーマ"
    mode_label = industry_result.get("mode_label", industry_result.get("mode", ""))
    return f"{names}を、{theme}の観点で比較対象に設定した。業種判定は「{mode_label}」を用い、課題条件との関係は条件適合表で確認する。"


def business_descriptions(companies: pd.DataFrame) -> pd.DataFrame:
    return companies[["ticker", "company_name", "jpx_industry", "business_theme", "business_summary"]].rename(
        columns={
            "ticker": "証券コード",
            "company_name": "企業名",
            "jpx_industry": "JPX業種",
            "business_theme": "事業テーマ",
            "business_summary": "事業内容",
        }
    )


def causal_matrix(companies: pd.DataFrame) -> pd.DataFrame:
    theme = "、".join(companies["business_theme"].dropna().astype(str).unique())
    return pd.DataFrame(
        [
            {
                "原因": "需要環境",
                "中間要因": f"{theme}に対する利用頻度・客単価・稼働率",
                "財務への影響": "売上高成長率、営業利益率",
                "確認データ": "売上高、営業利益、手入力KPI",
            },
            {
                "原因": "費用構造",
                "中間要因": "変動費率、固定費、店舗・機材・物流などの稼働",
                "財務への影響": "損益分岐点、安全余裕率、営業レバレッジ",
                "確認データ": "営業利益、固定費推定、変動費率",
            },
            {
                "原因": "資産効率",
                "中間要因": "設備、店舗、機材、在庫、資本構成の使い方",
                "財務への影響": "ROA、ROE、総資産回転率",
                "確認データ": "総資産、自己資本、当期利益",
            },
            {
                "原因": "財務安定性",
                "中間要因": "短期支払能力、自己資本、長期資金との対応",
                "財務への影響": "流動比率、自己資本比率、固定長期適合率",
                "確認データ": "流動資産、流動負債、固定資産、長期負債",
            },
        ]
    )


def nine_perspectives(companies: pd.DataFrame) -> pd.DataFrame:
    company_text = "、".join(companies["company_name"].astype(str))
    rows = [
        ("市場", "対象市場の成長性、需要変動、景気感応度を見る。"),
        ("顧客", "顧客層、利用頻度、継続接点、価格許容度を見る。"),
        ("競合", "同業・代替サービスとの違い、価格・立地・品質の競争軸を見る。"),
        ("商品・サービス", "主力商品、サービス品質、差別化要素を見る。"),
        ("価格", "単価、値上げ余地、割引依存度を見る。"),
        ("チャネル", "店舗、Web、法人、FCなど顧客接点を見る。"),
        ("オペレーション", "原材料、物流、設備、稼働率、人件費の管理を見る。"),
        ("財務", "収益性、効率性、安全性、キャッシュ創出力を見る。"),
        ("リスク", "規制、災害、燃料・原材料、為替、人材などの不確実性を見る。"),
    ]
    return pd.DataFrame([{"視点": name, "確認観点": text, "対象": company_text} for name, text in rows])


def _format_percent(value: object, missing_label: str) -> str:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return missing_label
    return f"{numeric * 100:.1f}%"


def _format_number(value: object, missing_label: str) -> str:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return missing_label
    return f"{numeric:,.1f}"


def build_profitability_commentary(latest: pd.DataFrame, missing_label: str) -> list[str]:
    paragraphs = []
    for _, row in latest.iterrows():
        paragraphs.append(
            f"{row['company_name']}は、売上高成長率が{_format_percent(row.get('revenue_growth_rate'), missing_label)}、"
            f"営業利益率が{_format_percent(row.get('operating_margin'), missing_label)}、"
            f"ROAが{_format_percent(row.get('roa'), missing_label)}、ROEが{_format_percent(row.get('roe'), missing_label)}である。"
            f"ROAは当期利益率と総資産回転率、ROEはそれに財務レバレッジを加えて確認する。"
        )
    return paragraphs


def build_stability_commentary(latest: pd.DataFrame, missing_label: str) -> list[str]:
    paragraphs = []
    for _, row in latest.iterrows():
        paragraphs.append(
            f"{row['company_name']}は、流動比率が{_format_percent(row.get('current_ratio'), missing_label)}、"
            f"自己資本比率が{_format_percent(row.get('equity_ratio'), missing_label)}、"
            f"負債比率が{_format_percent(row.get('debt_ratio'), missing_label)}、"
            f"固定比率が{_format_percent(row.get('fixed_ratio'), missing_label)}、"
            f"固定長期適合率が{_format_percent(row.get('fixed_long_term_adequacy_ratio'), missing_label)}である。"
        )
    return paragraphs


def build_cashflow_commentary(latest: pd.DataFrame, missing_label: str) -> list[str]:
    paragraphs = []
    for _, row in latest.iterrows():
        paragraphs.append(
            f"{row['company_name']}の営業CFは{_format_number(row.get('cash_flow_operating'), missing_label)}百万円、"
            f"FCFは{_format_number(row.get('fcf'), missing_label)}百万円である。"
            "営業CFとFCFの差は設備投資や維持投資の負担を考える手がかりになる。"
        )
    return paragraphs


def build_alpha_commentary(latest: pd.DataFrame, missing_label: str) -> pd.DataFrame:
    rows = []
    for _, row in latest.iterrows():
        rows.append(
            {
                "企業名": row["company_name"],
                "損益分岐点": _format_number(row.get("break_even_sales"), missing_label),
                "安全余裕率": _format_percent(row.get("safety_margin"), missing_label),
                "営業レバレッジ": _format_number(row.get("operating_leverage"), missing_label),
                "4P": row.get("four_p") if pd.notna(row.get("four_p")) else missing_label,
                "4C": row.get("four_c") if pd.notna(row.get("four_c")) else missing_label,
                "顧客関係": row.get("customer_relationship")
                if pd.notna(row.get("customer_relationship"))
                else missing_label,
                "バリューチェーン": row.get("value_chain_note") if pd.notna(row.get("value_chain_note")) else missing_label,
                "PER": _format_number(row.get("per"), missing_label),
                "PBR": _format_number(row.get("pbr"), missing_label),
            }
        )
    return pd.DataFrame(rows)


def collect_missing_notes(metrics: pd.DataFrame, missing_label: str) -> list[str]:
    latest = metrics.sort_values(["ticker", "fiscal_year"]).groupby("ticker", as_index=False).tail(1)
    monitored = [
        "revenue_growth_rate",
        "operating_margin",
        "roa",
        "roe",
        "current_ratio",
        "equity_ratio",
        "fcf",
        "break_even_sales",
        "safety_margin",
        "operating_leverage",
        "per",
        "pbr",
    ]
    notes: list[str] = []
    for _, row in latest.iterrows():
        for column in monitored:
            if column in row and pd.isna(row[column]):
                notes.append(f"{row['company_name']}の{METRIC_LABELS.get(column, column)}はデータ不足または算定条件未充足のため{missing_label}。")
    return notes
