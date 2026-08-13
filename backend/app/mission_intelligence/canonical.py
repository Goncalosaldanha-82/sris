from __future__ import annotations

import re
import unicodedata
from typing import Any

from .contracts import (
    AnalysisInput,
    ConfidenceLevel,
    MissionDocumentV13,
    MissionRecord,
    Provenance,
    RecordKind,
)


def _token(value: Any) -> str:
    raw = unicodedata.normalize("NFKD", str(value or ""))
    raw = "".join(char for char in raw if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "_", raw.lower()).strip("_")


def _kind(value: Any) -> RecordKind:
    token = _token(value)
    mapping = {
        "observacao": RecordKind.OBSERVATION,
        "representation": RecordKind.REPRESENTATION,
        "representacao": RecordKind.REPRESENTATION,
        "informacao": RecordKind.INFORMATION,
        "evidencia": RecordKind.EVIDENCE,
        "evidencia_documental": RecordKind.EVIDENCE,
        "evidencia_funcional": RecordKind.EVIDENCE,
        "evidencia_de_caso": RecordKind.EVIDENCE,
        "reconhecimento_externo": RecordKind.EVIDENCE,
        "conhecimento": RecordKind.KNOWLEDGE,
        "hipotese": RecordKind.HYPOTHESIS,
        "pressuposto": RecordKind.ASSUMPTION,
        "restricao": RecordKind.CONSTRAINT,
        "alternativa": RecordKind.ALTERNATIVE,
        "decisao": RecordKind.DECISION,
        "execucao": RecordKind.ACTION,
        "acao": RecordKind.ACTION,
        "resultado": RecordKind.OUTCOME,
        "aprendizagem": RecordKind.LEARNING,
    }
    return mapping.get(token, RecordKind.INFORMATION)


def _confidence(value: Any) -> ConfidenceLevel:
    token = _token(value)
    if token in {"elevada", "alto", "alta", "high"}:
        return ConfidenceLevel.HIGH
    if token in {"moderada", "moderado", "medium", "moderate"}:
        return ConfidenceLevel.MODERATE
    if token in {"baixa", "baixo", "low"}:
        return ConfidenceLevel.LOW
    return ConfidenceLevel.NOT_EVALUABLE


def _state(value: Any) -> str:
    token = _token(value)
    if "refutad" in token:
        return "refuted"
    if "violad" in token:
        return "violated"
    if "selecionad" in token or "decidid" in token:
        return "selected"
    if "concluid" in token or "completed" in token:
        return "completed"
    if "rejeitad" in token:
        return "rejected"
    if "confirmad" in token or "documentad" in token:
        return "documented"
    if "registad" in token or "observad" in token:
        return "observed"
    if "nao_avali" in token or "por_verificar" in token or "assumid" in token:
        return "unresolved"
    if "em_avaliacao" in token or "em_aberto" in token:
        return "open"
    if "nao_existe" in token or "nao_inici" in token or "indispon" in token:
        return "not_available"
    return token or "declared"


def legacy_to_canonical(
    mission: dict[str, Any],
    analysis_input: AnalysisInput | None = None,
) -> MissionDocumentV13:
    """Convert the presentation payload into the normative MDL 1.3 contract."""

    analysis = dict(mission.get("analysis") or {})
    analysis_requirements = dict(mission.get("analysis_requirements") or {})
    if "context_research" not in analysis_requirements:
        analysis_requirements["context_research"] = {
            "required": True,
            "reason": (
                "Every mission must investigate its material surroundings unless "
                "non-applicability is explicitly justified."
            ),
        }
    if analysis_input is not None:
        if analysis_input.title:
            analysis["title"] = analysis_input.title
        if analysis_input.context:
            analysis["context"] = analysis_input.context
        if analysis_input.central_question:
            analysis["central_question"] = analysis_input.central_question
        if analysis_input.available_evidence:
            analysis["available_evidence"] = analysis_input.available_evidence
        if analysis_input.unknowns:
            analysis["unknowns"] = analysis_input.unknowns

    records: list[MissionRecord] = []
    seen: set[str] = set()

    for item in mission.get("evidence") or []:
        canonical_id = str(item.get("id") or "").strip()
        if not canonical_id or canonical_id in seen:
            continue
        seen.add(canonical_id)
        records.append(
            MissionRecord(
                canonical_id=canonical_id,
                kind=_kind(item.get("type")),
                title=str(item.get("title") or canonical_id),
                description=str(item.get("description") or ""),
                state=_state(item.get("status")),
                confidence=_confidence(item.get("confidence")),
                provenance=Provenance(
                    origin_type="unspecified",
                    source=str(item.get("source") or ""),
                    method=str(item.get("method") or ""),
                    limitations=str(item.get("limitation") or item.get("limitations") or ""),
                    verification_status="declared",
                ),
                metadata={
                    "legacy_type": item.get("type"),
                    **dict(item.get("metadata") or {}),
                },
            )
        )

    for item in mission.get("learning") or []:
        canonical_id = str(item.get("id") or "").strip()
        if not canonical_id or canonical_id in seen:
            continue
        seen.add(canonical_id)
        records.append(
            MissionRecord(
                canonical_id=canonical_id,
                kind=RecordKind.LEARNING,
                title=str(item.get("title") or canonical_id),
                description=str(item.get("description") or ""),
                state="declared",
                confidence=ConfidenceLevel.NOT_EVALUABLE,
                provenance=Provenance(
                    origin_type="unspecified",
                    source=str(mission.get("id") or "SRIS"),
                    method="Registo importado do catálogo governado da missão.",
                    limitations=(
                        "O catálogo não identifica o autor original; a aprendizagem "
                        "continua sujeita a revisão e reutilização contextual."
                    ),
                    verification_status="declared",
                ),
            )
        )

    return MissionDocumentV13(
        mission_id=str(mission["id"]),
        title=str(mission["title"]),
        context=str(analysis.get("context") or mission.get("subtitle") or ""),
        central_question=str(analysis.get("central_question") or ""),
        records=records,
        relations=[],
        metadata={
            "source_format": "governed_demo_catalog",
            "decision_stage": mission.get("decision_stage") or "",
            "analysis_requirements": analysis_requirements,
            "context_dossier": dict(mission.get("context_dossier") or {}),
            "unstructured_input": {
                "available_evidence_claim": analysis.get("available_evidence") or "",
                "unknowns_claim": analysis.get("unknowns") or "",
                "epistemic_status": "context_only_not_canonical_evidence",
            },
        },
    )
