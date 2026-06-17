from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from typing import Any
from urllib.parse import urlencode


EDINET_DOCUMENTS_ENDPOINT = "https://api.edinet-fsa.go.jp/api/v2/documents.json"


@dataclass
class EdinetClient:
    api_key: str | None = None

    def __post_init__(self) -> None:
        if self.api_key is None:
            self.api_key = os.environ.get("EDINET_API_KEY")

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key)

    def build_documents_url(self, target_date: date, doc_type: int = 2) -> str:
        params: dict[str, Any] = {"date": target_date.isoformat(), "type": doc_type}
        if self.api_key:
            params["Subscription-Key"] = self.api_key
        return f"{EDINET_DOCUMENTS_ENDPOINT}?{urlencode(params)}"

    def fetch_documents_stub(self, target_date: date, doc_type: int = 2) -> dict[str, Any]:
        return {
            "status": "stub",
            "message": "EDINET API接続とXBRL解析は後続拡張で実装予定です。",
            "has_api_key": self.has_api_key,
            "url": self.build_documents_url(target_date, doc_type),
        }

