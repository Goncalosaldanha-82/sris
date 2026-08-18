from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .contracts import ContextDossier


ASSETS_ROOT = Path(__file__).resolve().parents[3] / "frontend" / "assets"
CATALOG_PATH = ASSETS_ROOT / "sris-mission-catalog-v1.3.json"
ACADEMIC_FLAGSHIP_PATH = ASSETS_ROOT / "sris-mission-override-academic.json"


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

    # Staging presentation overlay. It adds a dedicated academic flagship mission
    # without rewriting the submitted/legacy demonstration cases in the base catalog.
    if ACADEMIC_FLAGSHIP_PATH.exists():
        override = json.loads(ACADEMIC_FLAGSHIP_PATH.read_text(encoding="utf-8"))
        override_missions = override.get("missions")
        if not isinstance(override_missions, dict) or not override_missions:
            raise RuntimeError("SRIS academic mission override is empty")
        missions.update(override_missions)

    for code, mission in missions.items():
        dossier = mission.get("context_dossier")
        if dossier:
            parsed = ContextDossier.model_validate(dossier)
            if parsed.mission_id != code:
                raise RuntimeError(
                    f"Context dossier mission identity mismatch for {code}"
                )
    return payload


def demo_mission(mission_code: str) -> dict[str, Any] | None:
    return load_demo_catalog()["missions"].get(mission_code)
