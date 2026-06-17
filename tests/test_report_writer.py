from datetime import date
from pathlib import Path
from uuid import uuid4

from docx import Document

from src.config_loader import PROJECT_ROOT
from src.config_loader import load_presets
from src.data_loader import load_sample_dataset
from src.report_writer import build_report_package


def _document_text(path):
    document = Document(path)
    paragraph_text = [paragraph.text for paragraph in document.paragraphs]
    table_text = []
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                table_text.append(cell.text)
    return "\n".join(paragraph_text + table_text)


def test_report_contains_required_sections_and_warning():
    preset = load_presets()["friend_cafe_theme"]
    output_dir = PROJECT_ROOT / "work" / "pytest_reports" / uuid4().hex
    package = build_report_package(
        selected_tickers=preset["companies"],
        preset={**preset, "preset_id": "friend_cafe_theme"},
        app_mode="assignment",
        industry_mode=preset["industry_mode"],
        dataset=load_sample_dataset(),
        output_dir=output_dir,
        as_of=date(2026, 6, 17),
    )

    assert package.docx_path.exists()
    assert all(path.exists() for path in package.chart_paths.values())
    text = _document_text(package.docx_path)
    for heading in ["課題対応表", "＋α分析", "警告", "参考資料", "欠損データ注記"]:
        assert heading in text
    assert "JPX業種" in text
    assert "投資すべき" not in text
