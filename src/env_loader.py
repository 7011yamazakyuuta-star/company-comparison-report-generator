from __future__ import annotations

import os
from pathlib import Path

from .config_loader import PROJECT_ROOT


def load_env_file(path: Path = PROJECT_ROOT / ".env") -> None:
    """Load simple KEY=VALUE pairs without adding a runtime dependency."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def get_runtime_secret(key: str, default: str | None = None) -> str | None:
    """Read a secret from .env, environment variables, or Streamlit secrets."""
    load_env_file()
    value = os.environ.get(key)
    if value:
        return value
    try:
        import streamlit as st

        secret_value = st.secrets.get(key)
    except Exception:
        return default
    if secret_value is None:
        return default
    return str(secret_value)
