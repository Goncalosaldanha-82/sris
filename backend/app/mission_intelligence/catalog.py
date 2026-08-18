from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from .contracts import ContextDossier


ASSETS_ROOT = Path(__file__).resolve().parents[3] / "frontend" / "assets"
CATALOG_PATH = ASSETS_ROOT / "sris-mission-catalog-v1.3.json"
ACADEMIC_FLAGSHIP_PATH = ASSETS_ROOT / "sris-mission-override-academic.json"
ACADEMIC_HIDDEN_MISSIONS = {"CA-AWARD-APPLICATION"}


def _academic_staging_runtime() -> bool:
    """Return True only inside the deployed Railway runtime for this staging ref.

    CI and local contract tests retain the legacy application case so historical
    compatibility remains covered. The academic staging runtime removes it from the
    catalogue presented to partners. Production is deployed from a different ref.
    """
    return bool(os.getenv("RAILWAY_ENVIRONMENT_ID"))


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

    # Academic presentation overlay. It adds the dedicated flagship mission without
    # rewriting submitted/legacy demonstration cases in the base catalogue.
    if ACADEMIC_FLAGSHIP_PATH.exists():
        override = json.loads(ACADEMIC_FLAGSHIP_PATH.read_text(encoding="utf-8"))
        override_missions = override.get("missions")
        if not isinstance(override_missions, dict) or not override_missions:
            raise RuntimeError("SRIS academic mission override is empty")
        missions.update(override_missions)

        # Runtime-only presentation rule: keep the historical award case in source
        # and under CI coverage, but exclude it from the Railway academic staging API.
        if _academic_staging_runtime():
            for mission_code in ACADEMIC_HIDDEN_MISSIONS:
                missions.pop(mission_code, None)

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
