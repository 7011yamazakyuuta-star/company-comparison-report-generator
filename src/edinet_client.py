from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from urllib.parse import urlencode

import requests

from .env_loader import load_env_file


EDINET_DOCUMENTS_ENDPOINT = "https://api.edinet-fsa.go.jp/api/v2/documents.json"
EDINET_DOCUMENT_ENDPOINT = "https://api.edinet-fsa.go.jp/api/v2/documents/{doc_id}"


class EdinetApiError(RuntimeError):
    """Raised when EDINET API access cannot be completed."""


@dataclass
class EdinetClient:
    api_key: str | None = None
    timeout_seconds: int = 30
    session: Any = field(default=None, repr=False)

    def __post_init__(self) -> None:
        load_env_file()
        if self.api_key is None:
            self.api_key = os.environ.get("EDINET_API_KEY")
        if self.session is None:
            self.session = requests.Session()

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key)

    def _auth_params(self) -> dict[str, str]:
        if not self.api_key:
            raise EdinetApiError("EDINET_API_KEY is not set. Add it to .env or the environment.")
        return {"Subscription-Key": self.api_key}

    def build_documents_url(self, target_date: date, doc_type: int = 2, include_api_key: bool = False) -> str:
        params: dict[str, Any] = {"date": target_date.isoformat(), "type": doc_type}
        if include_api_key and self.api_key:
            params["Subscription-Key"] = self.api_key
        return f"{EDINET_DOCUMENTS_ENDPOINT}?{urlencode(params)}"

    def build_document_url(self, doc_id: str, file_type: int = 5, include_api_key: bool = False) -> str:
        params: dict[str, Any] = {"type": file_type}
        if include_api_key and self.api_key:
            params["Subscription-Key"] = self.api_key
        endpoint = EDINET_DOCUMENT_ENDPOINT.format(doc_id=doc_id)
        return f"{endpoint}?{urlencode(params)}"

    def fetch_documents(self, target_date: date, doc_type: int = 2) -> dict[str, Any]:
        params: dict[str, Any] = {"date": target_date.isoformat(), "type": doc_type}
        params.update(self._auth_params())
        try:
            response = self.session.get(EDINET_DOCUMENTS_ENDPOINT, params=params, timeout=self.timeout_seconds)
        except requests.RequestException:
            raise EdinetApiError(
                "EDINET APIへ接続できませんでした。ネットワーク、プロキシ、またはEDINET側の状態を確認してください。"
            ) from None
        if response.status_code != 200:
            raise EdinetApiError(f"EDINET documents API failed: HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError:
            raise EdinetApiError("EDINET APIの応答をJSONとして読めませんでした。") from None
        if not isinstance(payload, dict):
            raise EdinetApiError("EDINET documents API returned an unexpected response.")
        return payload

    def fetch_documents_stub(self, target_date: date, doc_type: int = 2) -> dict[str, Any]:
        return {
            "status": "stub",
            "message": "EDINET API接続とXBRL解析は後続拡張で実装予定です。",
            "has_api_key": self.has_api_key,
            "url": self.build_documents_url(target_date, doc_type),
        }


def extract_document_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    results = payload.get("results") or []
    if not isinstance(results, list):
        return rows

    for item in results:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "doc_id": item.get("docID") or item.get("docId") or "",
                "edinet_code": item.get("edinetCode") or "",
                "sec_code": item.get("secCode") or "",
                "filer_name": item.get("filerName") or "",
                "doc_description": item.get("docDescription") or "",
                "submit_datetime": item.get("submitDateTime") or "",
                "ordinance_code": item.get("ordinanceCode") or "",
                "form_code": item.get("formCode") or "",
                "doc_type_code": item.get("docTypeCode") or "",
                "xbrl_flag": item.get("xbrlFlag") or "",
                "pdf_flag": item.get("pdfFlag") or "",
                "csv_flag": item.get("csvFlag") or "",
                "raw_json": item,
            }
        )
    return rows
