from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.atlas_platform.audit import record_audit
from app.atlas_platform.auth import require_org_role
from app.atlas_platform.database import get_db
from app.atlas_platform.models import Membership, Role

from .contracts import MissionDocumentV13
from .memory_models import EvidenceAsset, MemoryItem, MemoryLink
from .models import CanonicalMission

router = APIRouter(
    prefix="/api/organizations/{organization_id}/mission-intelligence/memory",
    tags=["Organizational Memory"],
)

INDEXABLE_KINDS = {
    "observation", "evidence", "hypothesis", "assumption", "alternative",
    "constraint", "decision", "execution", "outcome", "learning",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load(value: str | None, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except (TypeError, ValueError):
        return fallback


def _document(row: CanonicalMission) -> MissionDocumentV13:
    try:
        return MissionDocumentV13.model_validate_json(row.document_json)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="Invalid canonical mission document") from exc


def _item_view(item: MemoryItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "organization_id": item.organization_id,
        "mission_id": item.mission_id,
        "canonical_record_id": item.canonical_record_id,
        "item_type": item.item_type,
        "title": item.title,
        "summary": item.summary,
        "state": item.state,
        "confidence": item.confidence,
        "valid_from": item.valid_from,
        "valid_until": item.valid_until,
        "last_verified_at": item.last_verified_at,
        "supersedes_id": item.supersedes_id,
        "source_revision": item.source_revision,
        "source_content_hash": item.source_content_hash,
        "metadata": _load(item.metadata_json, {}),
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def _asset_view(asset: EvidenceAsset) -> dict[str, Any]:
    return {
        "id": asset.id,
        "mission_id": asset.mission_id,
        "storage_backend": asset.storage_backend,
        "object_key": asset.object_key,
        "original_filename": asset.original_filename,
        "media_type": asset.media_type,
        "byte_size": asset.byte_size,
        "sha256": asset.sha256,
        "state": asset.state,
        "provenance": _load(asset.provenance_json, {}),
        "metadata": _load(asset.metadata_json, {}),
        "created_at": asset.created_at,
    }


def _record_search_text(mission: CanonicalMission, record: Any) -> str:
    metadata = record.metadata if isinstance(record.metadata, dict) else {}
    return "\n".join(
        part for part in (
            mission.code,
            mission.title,
            mission.domain,
            record.canonical_id,
            record.kind.value,
            record.title,
            record.description,
            _dump(metadata),
        ) if part
    )


def sync_organization_memory(
    db: Session,
    *,
    organization_id: str,
    user_id: str | None,
) -> dict[str, int]:
    missions = (
        db.query(CanonicalMission)
        .filter(CanonicalMission.organization_id == organization_id)
        .order_by(CanonicalMission.created_at.asc())
        .all()
    )
    created = 0
    updated = 0
    links_created = 0
    indexed: dict[tuple[str, str], MemoryItem] = {}

    for mission in missions:
        document = _document(mission)
        for record in document.records:
            kind = record.kind.value
            if kind not in INDEXABLE_KINDS:
                continue
            item = (
                db.query(MemoryItem)
                .filter(
                    MemoryItem.organization_id == organization_id,
                    MemoryItem.mission_id == mission.id,
                    MemoryItem.canonical_record_id == record.canonical_id,
                )
                .one_or_none()
            )
            metadata = dict(record.metadata or {})
            metadata.update(
                source_mission_code=mission.code,
                source_mission_title=mission.title,
                source_domain=mission.domain,
                canonical_source=True,
                memory_contract_version="1.0",
            )
            verified = record.observed_at if kind in {"evidence", "outcome", "learning"} else None
            valid_from = record.observed_at
            if item is None:
                item = MemoryItem(
                    organization_id=organization_id,
                    mission_id=mission.id,
                    canonical_record_id=record.canonical_id,
                    item_type=kind,
                    title=record.title,
                    summary=record.description,
                    state=record.state or "active",
                    confidence=record.confidence.value,
                    valid_from=valid_from,
                    last_verified_at=verified,
                    source_revision=mission.revision,
                    source_content_hash=mission.content_hash,
                    search_text=_record_search_text(mission, record),
                    metadata_json=_dump(metadata),
                    created_by_user_id=user_id,
                )
                db.add(item)
                db.flush()
                created += 1
            elif item.source_content_hash != mission.content_hash or item.source_revision != mission.revision:
                item.item_type = kind
                item.title = record.title
                item.summary = record.description
                item.state = record.state or item.state
                item.confidence = record.confidence.value
                item.valid_from = valid_from or item.valid_from
                item.last_verified_at = verified or item.last_verified_at
                item.source_revision = mission.revision
                item.source_content_hash = mission.content_hash
                item.search_text = _record_search_text(mission, record)
                item.metadata_json = _dump(metadata)
                updated += 1
            indexed[(mission.id, record.canonical_id)] = item

    # Create a graph edge only when both canonical endpoints have durable items.
    for mission in missions:
        document = _document(mission)
        for relation in document.relations:
            source = indexed.get((mission.id, relation.source_id))
            target = indexed.get((mission.id, relation.target_id))
            if source is None or target is None:
                continue
            exists = (
                db.query(MemoryLink.id)
                .filter(
                    MemoryLink.organization_id == organization_id,
                    MemoryLink.source_item_id == source.id,
                    MemoryLink.target_item_id == target.id,
                    MemoryLink.relation_type == relation.relation_type,
                )
                .first()
            )
            if exists:
                continue
            db.add(
                MemoryLink(
                    organization_id=organization_id,
                    source_item_id=source.id,
                    target_item_id=target.id,
                    relation_type=relation.relation_type,
                    metadata_json=_dump({
                        "canonical_relation_id": relation.relation_id,
                        "explanation": relation.explanation,
                        "confidence": relation.confidence.value,
                    }),
                )
            )
            links_created += 1

    # Materialize cross-mission inheritance edges from reviewed learning metadata.
    by_source: dict[tuple[str, str], MemoryItem] = dict(indexed)
    for (_, _), inherited in list(indexed.items()):
        meta = _load(inherited.metadata_json, {})
        if not meta.get("inherited_learning"):
            continue
        source_mission_id = str(meta.get("source_mission_id") or "")
        source_learning_id = str(meta.get("source_learning_id") or "")
        source = by_source.get((source_mission_id, source_learning_id))
        if source is None:
            continue
        relation_type = "inherited_from"
        exists = (
            db.query(MemoryLink.id)
            .filter(
                MemoryLink.organization_id == organization_id,
                MemoryLink.source_item_id == inherited.id,
                MemoryLink.target_item_id == source.id,
                MemoryLink.relation_type == relation_type,
            )
            .first()
        )
        if not exists:
            db.add(MemoryLink(
                organization_id=organization_id,
                source_item_id=inherited.id,
                target_item_id=source.id,
                relation_type=relation_type,
                metadata_json=_dump({"cross_mission": True}),
            ))
            links_created += 1

    db.commit()
    return {"created": created, "updated": updated, "links_created": links_created}


class AssetRegisterRequest(BaseModel):
    mission_id: str | None = None
    storage_backend: str = Field(default="external", min_length=2, max_length=40)
    object_key: str = Field(min_length=1, max_length=1500)
    original_filename: str = Field(min_length=1, max_length=1000)
    media_type: str = Field(default="application/octet-stream", max_length=200)
    byte_size: int | None = Field(default=None, ge=0)
    sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    provenance: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemorySupersedeRequest(BaseModel):
    title: str = Field(min_length=3, max_length=500)
    summary: str = Field(min_length=10, max_length=30000)
    reason: str = Field(min_length=3, max_length=10000)
    state: str = Field(default="active", max_length=50)
    confidence: str = Field(default="not_evaluable", max_length=30)


@router.post("/sync")
def sync_memory(
    organization_id: str,
    membership: Membership = Depends(require_org_role(Role.OWNER.value, Role.ADMIN.value, Role.REVIEWER.value)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    result = sync_organization_memory(
        db, organization_id=organization_id, user_id=membership.user_id
    )
    record_audit(
        db,
        action="mission_intelligence.memory_synchronized",
        resource_type="organizational_memory",
        resource_id=organization_id,
        organization_id=organization_id,
        user_id=membership.user_id,
        payload=result,
    )
    db.commit()
    return {"status": "synchronized", **result}


@router.get("/status")
def memory_status(
    organization_id: str,
    _: Membership = Depends(require_org_role(Role.OWNER.value, Role.ADMIN.value, Role.REVIEWER.value, Role.CONTRIBUTOR.value, Role.OBSERVER.value)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    items = db.query(MemoryItem).filter(MemoryItem.organization_id == organization_id).all()
    links = db.query(MemoryLink).filter(MemoryLink.organization_id == organization_id).count()
    assets = db.query(EvidenceAsset).filter(EvidenceAsset.organization_id == organization_id).count()
    by_type: dict[str, int] = {}
    for item in items:
        by_type[item.item_type] = by_type.get(item.item_type, 0) + 1
    superseded = sum(1 for item in items if item.state == "superseded")
    return {
        "schema": "sris.long_term_memory",
        "schema_version": "1.0",
        "source_of_truth": "canonical_mission_store",
        "memory_is_model_independent": True,
        "retention_policy": "append_supersede_archive_no_silent_delete",
        "object_storage": "provider_independent_metadata_ledger",
        "semantic_search": "prepared_not_authoritative",
        "items": len(items),
        "links": links,
        "assets": assets,
        "superseded_items": superseded,
        "items_by_type": by_type,
    }


@router.get("/items")
def list_memory_items(
    organization_id: str,
    q: str = Query(default="", max_length=500),
    item_type: str | None = Query(default=None, max_length=60),
    state: str | None = Query(default=None, max_length=50),
    limit: int = Query(default=100, ge=1, le=500),
    _: Membership = Depends(require_org_role(Role.OWNER.value, Role.ADMIN.value, Role.REVIEWER.value, Role.CONTRIBUTOR.value, Role.OBSERVER.value)),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    query = db.query(MemoryItem).filter(MemoryItem.organization_id == organization_id)
    if item_type:
        query = query.filter(MemoryItem.item_type == item_type)
    if state:
        query = query.filter(MemoryItem.state == state)
    clean_q = re.sub(r"\s+", " ", q.strip())
    if clean_q:
        pattern = f"%{clean_q}%"
        query = query.filter(or_(MemoryItem.title.ilike(pattern), MemoryItem.summary.ilike(pattern), MemoryItem.search_text.ilike(pattern)))
    return [_item_view(item) for item in query.order_by(MemoryItem.updated_at.desc()).limit(limit).all()]


@router.get("/graph")
def memory_graph(
    organization_id: str,
    limit: int = Query(default=500, ge=1, le=2000),
    _: Membership = Depends(require_org_role(Role.OWNER.value, Role.ADMIN.value, Role.REVIEWER.value, Role.CONTRIBUTOR.value, Role.OBSERVER.value)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    items = db.query(MemoryItem).filter(MemoryItem.organization_id == organization_id).order_by(MemoryItem.updated_at.desc()).limit(limit).all()
    ids = {item.id for item in items}
    links = db.query(MemoryLink).filter(MemoryLink.organization_id == organization_id).all()
    links = [link for link in links if link.source_item_id in ids and link.target_item_id in ids]
    return {
        "nodes": [_item_view(item) for item in items],
        "edges": [{
            "id": link.id,
            "source": link.source_item_id,
            "target": link.target_item_id,
            "relation_type": link.relation_type,
            "metadata": _load(link.metadata_json, {}),
        } for link in links],
    }


@router.post("/assets", status_code=201)
def register_asset(
    organization_id: str,
    payload: AssetRegisterRequest,
    membership: Membership = Depends(require_org_role(Role.OWNER.value, Role.ADMIN.value, Role.REVIEWER.value, Role.CONTRIBUTOR.value)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if payload.mission_id:
        exists = db.query(CanonicalMission.id).filter(
            CanonicalMission.id == payload.mission_id,
            CanonicalMission.organization_id == organization_id,
        ).first()
        if not exists:
            raise HTTPException(status_code=404, detail="Mission not found")
    sha = payload.sha256.lower()
    existing = db.query(EvidenceAsset).filter(
        EvidenceAsset.organization_id == organization_id,
        EvidenceAsset.sha256 == sha,
    ).one_or_none()
    if existing:
        return {"status": "already_registered", "asset": _asset_view(existing)}
    asset = EvidenceAsset(
        organization_id=organization_id,
        mission_id=payload.mission_id,
        storage_backend=payload.storage_backend,
        object_key=payload.object_key,
        original_filename=payload.original_filename,
        media_type=payload.media_type,
        byte_size=payload.byte_size,
        sha256=sha,
        provenance_json=_dump(payload.provenance),
        metadata_json=_dump(payload.metadata),
        created_by_user_id=membership.user_id,
    )
    db.add(asset)
    db.flush()
    record_audit(
        db,
        action="mission_intelligence.evidence_asset_registered",
        resource_type="evidence_asset",
        resource_id=asset.id,
        organization_id=organization_id,
        user_id=membership.user_id,
        payload={"sha256": sha, "mission_id": payload.mission_id, "storage_backend": payload.storage_backend},
    )
    db.commit()
    db.refresh(asset)
    return {"status": "registered", "asset": _asset_view(asset)}


@router.get("/assets")
def list_assets(
    organization_id: str,
    mission_id: str | None = None,
    _: Membership = Depends(require_org_role(Role.OWNER.value, Role.ADMIN.value, Role.REVIEWER.value, Role.CONTRIBUTOR.value, Role.OBSERVER.value)),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    query = db.query(EvidenceAsset).filter(EvidenceAsset.organization_id == organization_id)
    if mission_id:
        query = query.filter(EvidenceAsset.mission_id == mission_id)
    return [_asset_view(asset) for asset in query.order_by(EvidenceAsset.created_at.desc()).all()]


@router.post("/items/{item_id}/supersede", status_code=201)
def supersede_memory_item(
    organization_id: str,
    item_id: str,
    payload: MemorySupersedeRequest,
    membership: Membership = Depends(require_org_role(Role.OWNER.value, Role.ADMIN.value, Role.REVIEWER.value)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    old = db.query(MemoryItem).filter(MemoryItem.id == item_id, MemoryItem.organization_id == organization_id).one_or_none()
    if old is None:
        raise HTTPException(status_code=404, detail="Memory item not found")
    if old.state == "superseded":
        raise HTTPException(status_code=409, detail="Memory item already superseded")
    now = _now()
    old.state = "superseded"
    old.valid_until = now
    meta = _load(old.metadata_json, {})
    new = MemoryItem(
        organization_id=organization_id,
        mission_id=None,
        canonical_record_id=None,
        item_type=old.item_type,
        title=payload.title,
        summary=payload.summary,
        state=payload.state,
        confidence=payload.confidence,
        valid_from=now,
        last_verified_at=now,
        supersedes_id=old.id,
        search_text=f"{payload.title}\n{payload.summary}\n{payload.reason}",
        metadata_json=_dump({
            "memory_contract_version": "1.0",
            "supersession_reason": payload.reason,
            "prior_source": meta,
            "human_reviewed": True,
        }),
        created_by_user_id=membership.user_id,
    )
    db.add(new)
    db.flush()
    db.add(MemoryLink(
        organization_id=organization_id,
        source_item_id=new.id,
        target_item_id=old.id,
        relation_type="supersedes",
        metadata_json=_dump({"reason": payload.reason}),
    ))
    record_audit(
        db,
        action="mission_intelligence.memory_item_superseded",
        resource_type="organizational_memory",
        resource_id=new.id,
        organization_id=organization_id,
        user_id=membership.user_id,
        payload={"supersedes_id": old.id, "reason": payload.reason},
    )
    db.commit()
    db.refresh(new)
    return {"status": "superseded", "prior_item_id": old.id, "item": _item_view(new)}
