"""JSON IO helpers."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List


def load_properties(path: str) -> List[Dict[str, Any]]:
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data.get("properties", [])
    if isinstance(data, list):
        return data
    raise ValueError(f"Unsupported JSON shape in {path}")


def dump_result(result: Dict[str, Any], jsonl: bool = False) -> None:
    if jsonl:
        for prop in result.get("properties", []):
            print(json.dumps(prop, ensure_ascii=False, sort_keys=True))
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))


def write_json(path: str, result: Dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
