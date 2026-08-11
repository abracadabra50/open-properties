"""Profile/config loading."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
LOCAL_PROFILES_DIRS = [Path.cwd() / "profiles", ROOT / "profiles"]


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def default_profile() -> Dict[str, Any]:
    return {
        "name": "default",
        "search": {"country": "GB", "transaction": "sale", "location": "edinburgh", "min_beds": 1, "max_price": None, "property_types": []},
        "areas": {"desired": [], "excluded": [], "premium": []},
        "deduplication": {"enabled": False, "threshold": 0.88, "candidate_threshold": 0.72},
        "scoring": {"enabled": False},
    }


def load_profile(name_or_path: str = "") -> Dict[str, Any]:
    if not name_or_path:
        return default_profile()

    candidate = Path(name_or_path)
    if not candidate.exists():
        if candidate.suffix != ".json":
            candidates = [directory / f"{name_or_path}.json" for directory in LOCAL_PROFILES_DIRS]
        else:
            candidates = [directory / name_or_path for directory in LOCAL_PROFILES_DIRS]
        candidate = next((path for path in candidates if path.exists()), candidates[0])

    if not candidate.exists():
        raise FileNotFoundError(f"Profile not found: {name_or_path}")

    with open(candidate) as f:
        loaded = json.load(f)
    return deep_merge(default_profile(), loaded)
