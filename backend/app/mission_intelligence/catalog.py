from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


CATALOG_PATH = (
    Path(__file__).resolve().parents[3]
    / "frontend"
    / "assets"
    / "sris-mission-catalog-v1.3.json"
)


@lru_cache(maxsize=1)
def load_demo_catalog() -> dict[str, Any]:
    payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    if payload.get("schema") != "sris_mission_catalog":
        raise RuntimeError("Invalid SRIS mission catalog schema")
    if payload.get("schema_version") != "1.3":
        raise RuntimeError("Unsupported SRIS mission catalog version")
    missions = payload.get("missions")
    if not isinstance(missions, dict) or not missions:
        raise RuntimeError("SRIS mission catalog is empty")
    return payload


def demo_mission(mission_code: str) -> dict[str, Any] | None:
    return load_demo_catalog()["missions"].get(mission_code)
