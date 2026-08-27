from __future__ import annotations

from fastapi import HTTPException

from .models import CanonicalMission


def require_mutable_mission(mission: CanonicalMission) -> None:
    """Protect a terminal canonical mission from silent downstream mutation."""

    if mission.lifecycle_state in {"completed", "archived"}:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "mission_reactivation_required",
                "message": (
                    "Reative primeiro a missão. Uma missão concluída ou arquivada "
                    "permanece imutável até uma pessoa alterar explicitamente o seu estado."
                ),
                "mission_code": mission.code,
                "lifecycle_state": mission.lifecycle_state,
            },
        )
