from datetime import date
from uuid import uuid4

import pytest
import requests

from src.config_loader import PROJECT_ROOT
from src.edinet_client import EdinetApiError, EdinetClient, extract_document_rows
from src.edinet_files import save_raw_document
from src.edinet_repository import filter_filings, load_filings, save_filings


def test_edinet_client_reads_api_key_from_environment(monkeypatch):
    monkeypatch.setenv("EDINET_API_KEY", "dummy-key")

    client = EdinetClient()
    result = client.fetch_documents_stub(date(2026, 6, 17))

    assert result["has_api_key"] is True
    assert "dummy-key" not in result["url"]


def test_edinet_client_raises_without_api_key():
    client = EdinetClient(api_key="")

    with pytest.raises(EdinetApiError):
        client.fetch_documents(date(2026, 6, 17))


def test_edinet_client_fetch_documents_with_mock_session():
    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "metadata": {"status": "200"},
                "results": [
                    {
                        "docID": "S100TEST",
                        "edinetCode": "E00001",
                        "secCode": "12340",
                        "filerName": "テスト株式会社",
                        "docDescription": "有価証券報告書",
                        "submitDateTime": "2026-06-17 10:00",
                        "ordinanceCode": "010",
                        "formCode": "030000",
                        "docTypeCode": "120",
                        "xbrlFlag": "1",
                        "pdfFlag": "1",
                        "csvFlag": "1",
                    }
                ],
            }

    class FakeSession:
        def __init__(self):
            self.params = None

        def get(self, url, params, timeout):
            self.params = params
            return FakeResponse()

    session = FakeSession()
    client = EdinetClient(api_key="dummy-key", session=session)
    payload = client.fetch_documents(date(2026, 6, 17))
    rows = extract_document_rows(payload)

    assert session.params["Subscription-Key"] == "dummy-key"
    assert rows[0]["doc_id"] == "S100TEST"
    assert rows[0]["filer_name"] == "テスト株式会社"


def test_edinet_client_fetch_document_file_with_mock_session():
    class FakeResponse:
        status_code = 200
        content = b"PK\x03\x04fake-zip"
        headers = {"Content-Type": "application/zip"}

    class FakeSession:
        def __init__(self):
            self.params = None

        def get(self, url, params, timeout):
            self.params = params
            return FakeResponse()

    session = FakeSession()
    client = EdinetClient(api_key="dummy-key", session=session)
    document_file = client.fetch_document_file("S100TEST", file_type=5)

    assert session.params["Subscription-Key"] == "dummy-key"
    assert document_file.doc_id == "S100TEST"
    assert document_file.file_type == 5
    assert document_file.content.startswith(b"PK")


def test_edinet_client_sanitizes_request_errors():
    class FailingSession:
        def get(self, url, params, timeout):
            raise requests.exceptions.ProxyError("url with secret should not leak")

    client = EdinetClient(api_key="dummy-key", session=FailingSession())

    with pytest.raises(EdinetApiError) as exc_info:
        client.fetch_documents(date(2026, 6, 17))

    assert "dummy-key" not in str(exc_info.value)
    assert "接続できませんでした" in str(exc_info.value)


def test_save_and_load_filings():
    rows = [
        {
            "doc_id": "S100TEST",
            "edinet_code": "E00001",
            "sec_code": "12340",
            "filer_name": "テスト株式会社",
            "doc_description": "有価証券報告書",
            "submit_datetime": "2026-06-17 10:00",
            "ordinance_code": "010",
            "form_code": "030000",
            "doc_type_code": "120",
            "xbrl_flag": "1",
            "pdf_flag": "1",
            "csv_flag": "1",
            "raw_json": {"docID": "S100TEST"},
        }
    ]

    db_path = PROJECT_ROOT / "work" / "pytest_dbs" / f"{uuid4().hex}.sqlite"
    assert save_filings(rows, db_path=db_path) == 1
    loaded = load_filings(db_path=db_path)

    assert len(loaded) == 1
    assert loaded.loc[0, "doc_id"] == "S100TEST"


def test_filter_filings_and_save_raw_document():
    rows = [
        {
            "doc_id": "S100ANNUAL",
            "edinet_code": "E00001",
            "sec_code": "12340",
            "filer_name": "テスト株式会社",
            "doc_description": "有価証券報告書－第1期",
            "submit_datetime": "2026-06-17 10:00",
            "ordinance_code": "010",
            "form_code": "030000",
            "doc_type_code": "120",
            "xbrl_flag": "1",
            "pdf_flag": "1",
            "csv_flag": "1",
            "raw_json": {"docID": "S100ANNUAL"},
        },
        {
            "doc_id": "S100NOTICE",
            "edinet_code": "E00002",
            "sec_code": "56780",
            "filer_name": "サンプル株式会社",
            "doc_description": "確認書",
            "submit_datetime": "2026-06-17 11:00",
            "ordinance_code": "010",
            "form_code": "030000",
            "doc_type_code": "130",
            "xbrl_flag": "0",
            "pdf_flag": "0",
            "csv_flag": "0",
            "raw_json": {"docID": "S100NOTICE"},
        },
    ]
    db_path = PROJECT_ROOT / "work" / "pytest_dbs" / f"{uuid4().hex}.sqlite"
    save_filings(rows, db_path=db_path)
    loaded = load_filings(db_path=db_path)
    filtered = filter_filings(loaded, query="テスト", annual_only=True, csv_only=True)

    assert filtered["doc_id"].tolist() == ["S100ANNUAL"]

    class DocumentFile:
        doc_id = "S100ANNUAL"
        file_type = 5
        content = b"PK\x03\x04fake-zip"
        content_type = "application/zip"

    output_dir = PROJECT_ROOT / "work" / "pytest_raw_filings" / uuid4().hex
    saved_path = save_raw_document(DocumentFile(), output_dir=output_dir)

    assert saved_path.name == "csv.zip"
    assert saved_path.read_bytes().startswith(b"PK")
