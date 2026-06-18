from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as f:
        loaded = yaml.safe_load(f) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return loaded


def load_rubric(root: Path = PROJECT_ROOT) -> dict[str, Any]:
    return load_yaml(root / "config" / "rubric" / "assignment_rubric.yaml")


def load_industry_policy(root: Path = PROJECT_ROOT) -> dict[str, Any]:
    return load_yaml(root / "config" / "industry_policy.yaml")


def load_analysis_policy(root: Path = PROJECT_ROOT) -> dict[str, Any]:
    return load_yaml(root / "config" / "analysis_policy.yaml")


def load_presets(root: Path = PROJECT_ROOT) -> dict[str, dict[str, Any]]:
    preset_dir = root / "config" / "presets"
    presets: dict[str, dict[str, Any]] = {}
    for path in sorted(preset_dir.glob("*.yaml")):
        preset = load_yaml(path)
        preset_id = str(preset.get("preset_id") or path.stem)
        presets[preset_id] = preset
    return presets
