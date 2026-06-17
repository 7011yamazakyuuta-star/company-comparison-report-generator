from datetime import date

from src.edinet_client import EdinetClient


def test_edinet_client_reads_api_key_from_environment(monkeypatch):
    monkeypatch.setenv("EDINET_API_KEY", "dummy-key")

    client = EdinetClient()
    result = client.fetch_documents_stub(date(2026, 6, 17))

    assert result["has_api_key"] is True
    assert "dummy-key" in result["url"]

