from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.atlas_platform.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MemoryItem(Base):
    """Organization-level index entry for knowledge that can outlive one mission.

    Canonical mission records remain the source of truth. This table is a durable,
    queryable cross-mission index with temporal validity and supersession semantics.
    """

    __tablename__ = "mi_memory_items"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "mission_id",
            "canonical_record_id",
            name="uq_mi_memory_source_record",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    mission_id: Mapped[str | None] = mapped_column(
        ForeignKey("mi_missions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    canonical_record_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    item_type: Mapped[str] = mapped_column(String(60), index=True)
    title: Mapped[str] = mapped_column(String(500))
    summary: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(50), default="active", index=True)
    confidence: Mapped[str] = mapped_column(String(30), default="not_evaluable")
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    supersedes_id: Mapped[str | None] = mapped_column(
        ForeignKey("mi_memory_items.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    search_text: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class MemoryLink(Base):
    """Typed edge in the organizational knowledge graph."""

    __tablename__ = "mi_memory_links"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "source_item_id",
            "target_item_id",
            "relation_type",
            name="uq_mi_memory_link",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    source_item_id: Mapped[str] = mapped_column(
        ForeignKey("mi_memory_items.id", ondelete="CASCADE"), index=True
    )
    target_item_id: Mapped[str] = mapped_column(
        ForeignKey("mi_memory_items.id", ondelete="CASCADE"), index=True
    )
    relation_type: Mapped[str] = mapped_column(String(80), index=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EvidenceAsset(Base):
    """Immutable metadata ledger for original files/evidence objects.

    Bytes live in an object store. The database preserves identity, checksum,
    provenance and lifecycle independently of the storage provider.
    """

    __tablename__ = "mi_evidence_assets"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "sha256",
            name="uq_mi_evidence_asset_org_sha256",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    mission_id: Mapped[str | None] = mapped_column(
        ForeignKey("mi_missions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    storage_backend: Mapped[str] = mapped_column(String(40), default="external", index=True)
    object_key: Mapped[str] = mapped_column(String(1500))
    original_filename: Mapped[str] = mapped_column(String(1000))
    media_type: Mapped[str] = mapped_column(String(200), default="application/octet-stream")
    byte_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    state: Mapped[str] = mapped_column(String(40), default="registered", index=True)
    provenance_json: Mapped[str] = mapped_column(Text, default="{}")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
