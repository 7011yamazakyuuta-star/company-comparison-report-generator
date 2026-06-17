from __future__ import annotations

from pathlib import Path

from .config_loader import PROJECT_ROOT
from .edinet_client import EdinetDocumentFile


RAW_FILINGS_DIR = PROJECT_ROOT / "output" / "raw_filings"


FILE_TYPE_LABELS = {
    1: "xbrl",
    2: "pdf",
    3: "attachments",
    4: "english",
    5: "csv",
}


def _extension_for(file_type: int, content_type: str = "") -> str:
    lowered = content_type.lower()
    if file_type == 2 or "pdf" in lowered:
        return ".pdf"
    if "zip" in lowered or file_type in {1, 3, 4, 5}:
        return ".zip"
    return ".bin"


def save_raw_document(document_file: EdinetDocumentFile, output_dir: Path = RAW_FILINGS_DIR) -> Path:
    label = FILE_TYPE_LABELS.get(document_file.file_type, f"type_{document_file.file_type}")
    extension = _extension_for(document_file.file_type, document_file.content_type)
    target_dir = output_dir / document_file.doc_id
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{label}{extension}"
    path.write_bytes(document_file.content)
    return path

