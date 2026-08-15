from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import hmac
import os
import re
import unicodedata
from uuid import uuid4

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.atlas_platform.config import settings

from .models import (
    IntelligenceRun,
    MissionArchiveChunk,
    MissionArchiveChunkTerm,
    MissionAttachment,
)


ARCHIVE_INDEX_VERSION = "sris-mi-archive-retrieval-1.0"
ARCHIVE_CHUNK_CHARACTERS = 3_600
ARCHIVE_CHUNK_OVERLAP = 360
MAX_INDEX_TERMS_PER_CHUNK = 160
MAX_QUERY_TERMS = 32
DEFAULT_RETRIEVAL_CHUNKS = 24
DATABASE_ID_BATCH = 400

_TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{1,79}")
_STOP_WORDS = {
    "a",
    "ao",
    "aos",
    "as",
    "com",
    "como",
    "da",
    "das",
    "de",
    "do",
    "dos",
    "e",
    "em",
    "entre",
    "esta",
    "este",
    "foi",
    "mais",
    "na",
    "nas",
    "no",
    "nos",
    "o",
    "os",
    "ou",
    "para",
    "pela",
    "pelo",
    "por",
    "que",
    "se",
    "sem",
    "ser",
    "sua",
    "um",
    "uma",
    "the",
    "and",
    "for",
    "from",
    "into",
    "of",
    "on",
    "or",
    "that",
    "this",
    "to",
    "with",
}


@dataclass(frozen=True)
class ArchiveExcerpt:
    chunk_id: str
    attachment_id: str | None
    filename: str
    question_id: str | None
    ordinal: int
    char_start: int
    char_end: int
    content_sha256: str
    text: str
    relevance_score: int
    source_type: str = "attachment"
    source_id: str | None = None

    def prompt_view(self, *, character_limit: int) -> dict:
        clipped = self.text[:character_limit]
        return {
            "chunk_id": self.chunk_id,
            "source_type": self.source_type,
            "source_id": self.source_id or self.attachment_id,
            "attachment_id": self.attachment_id,
            "source_label": self.filename,
            "question_id": self.question_id,
            "ordinal": self.ordinal,
            "character_range": [self.char_start, self.char_end],
            "content_sha256": self.content_sha256,
            "excerpt": clipped,
            "excerpt_truncated": len(clipped) < len(self.text),
            "verification_status": "in_review",
            "source_class": (
                "user_supplied_document"
                if self.source_type == "attachment"
                else "preserved_mission_report"
            ),
        }


@dataclass(frozen=True)
class MissionArchiveContext:
    excerpts: tuple[ArchiveExcerpt, ...]
    manifest: dict
    direct_binary_attachment_ids: tuple[str, ...] = ()

    @property
    def reference_ids(self) -> set[str]:
        return {
            item.attachment_id
            for item in self.excerpts
            if item.attachment_id is not None
        } | set(self.direct_binary_attachment_ids)


def _derived_key(organization_id: str, *, purpose: bytes) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=organization_id.encode("utf-8"),
        info=purpose,
    ).derive(settings.jwt_secret.encode("utf-8"))


def _encrypt_chunk(
    text: str,
    *,
    organization_id: str,
    chunk_id: str,
) -> bytes:
    nonce = os.urandom(12)
    aad = f"{organization_id}:{chunk_id}:archive-chunk".encode("utf-8")
    key = _derived_key(organization_id, purpose=b"sris-mi-archive-chunk-v1")
    return nonce + AESGCM(key).encrypt(nonce, text.encode("utf-8"), aad)


def _decrypt_chunk(row: MissionArchiveChunk) -> str:
    nonce, ciphertext = row.encrypted_text[:12], row.encrypted_text[12:]
    aad = f"{row.organization_id}:{row.id}:archive-chunk".encode("utf-8")
    key = _derived_key(
        row.organization_id,
        purpose=b"sris-mi-archive-chunk-v1",
    )
    return AESGCM(key).decrypt(nonce, ciphertext, aad).decode("utf-8")


def lexical_terms(value: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    normalized = "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    ).casefold()
    return [
        token
        for token in _TOKEN_PATTERN.findall(normalized)
        if token not in _STOP_WORDS and (len(token) >= 3 or token.isdigit())
    ]


def lexical_relevance(value: str, query_terms: set[str]) -> int:
    if not query_terms:
        return 0
    counts = Counter(lexical_terms(value))
    return sum(min(4, counts.get(term, 0)) for term in query_terms)


def _term_hash(organization_id: str, term: str) -> str:
    key = _derived_key(
        organization_id,
        purpose=b"sris-mi-archive-search-v1",
    )
    return hmac.new(key, term.encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def _chunk_ranges(text: str):
    if not text:
        return
    start = 0
    length = len(text)
    while start < length:
        hard_end = min(length, start + ARCHIVE_CHUNK_CHARACTERS)
        end = hard_end
        if hard_end < length:
            paragraph = text.rfind("\n", start + ARCHIVE_CHUNK_CHARACTERS // 2, hard_end)
            sentence = text.rfind(". ", start + ARCHIVE_CHUNK_CHARACTERS // 2, hard_end)
            boundary = max(paragraph, sentence + 1 if sentence >= 0 else -1)
            if boundary > start:
                end = boundary
        chunk = text[start:end].strip()
        if chunk:
            yield start, end, chunk
        if end >= length:
            break
        start = max(start + 1, end - ARCHIVE_CHUNK_OVERLAP)


def _salient_terms(text: str) -> list[str]:
    counts = Counter(lexical_terms(text))
    ranked = sorted(
        counts,
        key=lambda term: (
            any(character.isdigit() for character in term),
            len(term),
            min(counts[term], 5),
            term,
        ),
        reverse=True,
    )
    return ranked[:MAX_INDEX_TERMS_PER_CHUNK]


def index_attachment_text(
    db: Session,
    *,
    attachment: MissionAttachment,
    extracted_text: str,
) -> int:
    """Replace one attachment's derived index while preserving its original."""

    return index_archive_source(
        db,
        organization_id=attachment.organization_id,
        mission_id=attachment.mission_id,
        source_type="attachment",
        source_id=attachment.id,
        source_label=attachment.original_filename,
        text=extracted_text,
        attachment_id=attachment.id,
        question_id=attachment.question_id,
    )


def index_archive_source(
    db: Session,
    *,
    organization_id: str,
    mission_id: str,
    source_type: str,
    source_id: str,
    source_label: str,
    text: str,
    attachment_id: str | None = None,
    question_id: str | None = None,
) -> int:
    """Index any preserved Mission source without changing the original.

    Attachments, dialogue reports and governed external-research dossiers all
    use the same encrypted retrieval plane. The authoritative source remains
    in its original table; these chunks are replaceable derived material.
    """

    existing = (
        db.query(MissionArchiveChunk)
        .filter(
            MissionArchiveChunk.organization_id == organization_id,
            MissionArchiveChunk.mission_id == mission_id,
            MissionArchiveChunk.source_type == source_type,
            MissionArchiveChunk.source_id == source_id,
        )
        .all()
    )
    for row in existing:
        db.delete(row)
    db.flush()

    created = 0
    for ordinal, (start, end, chunk_text) in enumerate(
        _chunk_ranges(text),
        start=1,
    ):
        chunk_id = str(uuid4())
        digest = hashlib.sha256(chunk_text.encode("utf-8")).hexdigest()
        chunk = MissionArchiveChunk(
            id=chunk_id,
            organization_id=organization_id,
            mission_id=mission_id,
            source_type=source_type,
            source_id=source_id,
            source_label=source_label,
            attachment_id=attachment_id,
            ordinal=ordinal,
            char_start=start,
            char_end=end,
            char_count=len(chunk_text),
            content_sha256=digest,
            encrypted_text=_encrypt_chunk(
                chunk_text,
                organization_id=organization_id,
                chunk_id=chunk_id,
            ),
        )
        db.add(chunk)
        searchable = " ".join(
            filter(
                None,
                (
                    source_label,
                    question_id or "",
                    chunk_text,
                ),
            )
        )
        for term in _salient_terms(searchable):
            db.add(
                MissionArchiveChunkTerm(
                    chunk_id=chunk_id,
                    term_hash=_term_hash(organization_id, term),
                )
            )
        created += 1
    return created


def _intelligence_run_archive_text(run: IntelligenceRun) -> str:
    sections = [
        f"Tipo de relatório: {run.execution_mode}",
        f"Estado: {run.status}",
        f"Snapshot: {run.snapshot_hash}",
        "Entrada preservada:\n" + (run.input_json or "{}"),
        "Relatório determinístico:\n" + (run.deterministic_json or "{}"),
    ]
    if run.ai_json:
        sections.append(
            "Inteligência e pesquisa externa preservadas:\n" + run.ai_json
        )
    if run.error:
        sections.append("Ocorrência registada:\n" + run.error)
    return "\n\n".join(sections)


def index_intelligence_run(db: Session, *, run: IntelligenceRun) -> int:
    """Make a preserved report/research run retrievable in later turns."""

    return index_archive_source(
        db,
        organization_id=run.organization_id,
        mission_id=run.mission_id,
        source_type="intelligence_run",
        source_id=run.id,
        source_label=f"Relatório Mission Intelligence · {run.execution_mode}",
        text=_intelligence_run_archive_text(run),
    )


def backfill_mission_run_archive(
    db: Session,
    *,
    organization_id: str,
    mission_id: str,
    batch_size: int = 32,
) -> int:
    """Lazily add legacy reports and external research to retrieval."""

    rows = (
        db.query(IntelligenceRun)
        .outerjoin(
            MissionArchiveChunk,
            and_(
                MissionArchiveChunk.organization_id == organization_id,
                MissionArchiveChunk.mission_id == mission_id,
                MissionArchiveChunk.source_type == "intelligence_run",
                MissionArchiveChunk.source_id == IntelligenceRun.id,
            ),
        )
        .filter(
            IntelligenceRun.organization_id == organization_id,
            IntelligenceRun.mission_id == mission_id,
            MissionArchiveChunk.id.is_(None),
        )
        .order_by(IntelligenceRun.created_at.desc())
        .limit(batch_size)
        .all()
    )
    for run in rows:
        index_intelligence_run(db, run=run)
    if rows:
        db.flush()
    return len(rows)


def retrieve_mission_archive(
    db: Session,
    *,
    organization_id: str,
    mission_id: str,
    query_text: str,
    priority_attachment_ids: list[str],
    max_chunks: int = DEFAULT_RETRIEVAL_CHUNKS,
) -> MissionArchiveContext:
    """Retrieve a bounded, auditable working set from an unbounded archive."""

    totals = (
        db.query(
            func.count(MissionAttachment.id),
            func.coalesce(func.sum(MissionAttachment.byte_size), 0),
        )
        .filter(
            MissionAttachment.organization_id == organization_id,
            MissionAttachment.mission_id == mission_id,
        )
        .one()
    )
    total_chunks = (
        db.query(func.count(MissionArchiveChunk.id))
        .filter(
            MissionArchiveChunk.organization_id == organization_id,
            MissionArchiveChunk.mission_id == mission_id,
        )
        .scalar()
        or 0
    )
    indexed_attachments = (
        db.query(func.count(func.distinct(MissionArchiveChunk.attachment_id)))
        .filter(
            MissionArchiveChunk.organization_id == organization_id,
            MissionArchiveChunk.mission_id == mission_id,
        )
        .scalar()
        or 0
    )
    source_counts = {
        source_type: int(source_count)
        for source_type, source_count in (
            db.query(
                MissionArchiveChunk.source_type,
                func.count(func.distinct(MissionArchiveChunk.source_id)),
            )
            .filter(
                MissionArchiveChunk.organization_id == organization_id,
                MissionArchiveChunk.mission_id == mission_id,
            )
            .group_by(MissionArchiveChunk.source_type)
            .all()
        )
    }
    source_counts["attachment"] = int(totals[0] or 0)

    query_terms = lexical_terms(query_text)[:MAX_QUERY_TERMS]
    hashes = [_term_hash(organization_id, term) for term in dict.fromkeys(query_terms)]
    scored_rows: list[tuple[MissionArchiveChunk, int]] = []
    if hashes and max_chunks > 0:
        score = (
            db.query(
                MissionArchiveChunkTerm.chunk_id.label("chunk_id"),
                func.count(MissionArchiveChunkTerm.term_hash).label("matches"),
            )
            .join(
                MissionArchiveChunk,
                MissionArchiveChunk.id == MissionArchiveChunkTerm.chunk_id,
            )
            .filter(
                MissionArchiveChunk.organization_id == organization_id,
                MissionArchiveChunk.mission_id == mission_id,
                MissionArchiveChunkTerm.term_hash.in_(hashes),
            )
            .group_by(MissionArchiveChunkTerm.chunk_id)
            .subquery()
        )
        scored_rows = [
            (chunk, int(matches))
            for chunk, matches in (
                db.query(MissionArchiveChunk, score.c.matches)
                .join(score, score.c.chunk_id == MissionArchiveChunk.id)
                .order_by(score.c.matches.desc(), MissionArchiveChunk.ordinal.asc())
                .limit(max_chunks * 4)
                .all()
            )
        ]

    priority = set(priority_attachment_ids)
    by_id: dict[str, tuple[MissionArchiveChunk, int]] = {}
    for chunk, score_value in scored_rows:
        boosted = score_value + (100 if chunk.attachment_id in priority else 0)
        current = by_id.get(chunk.id)
        if current is None or boosted > current[1]:
            by_id[chunk.id] = (chunk, boosted)

    if priority and max_chunks > 0:
        priority_values = list(priority)
        for offset in range(0, len(priority_values), DATABASE_ID_BATCH):
            batch = priority_values[offset : offset + DATABASE_ID_BATCH]
            priority_rows = (
                db.query(MissionArchiveChunk)
                .filter(
                    MissionArchiveChunk.organization_id == organization_id,
                    MissionArchiveChunk.mission_id == mission_id,
                    MissionArchiveChunk.attachment_id.in_(batch),
                    MissionArchiveChunk.ordinal <= 3,
                )
                .order_by(
                    MissionArchiveChunk.attachment_id.asc(),
                    MissionArchiveChunk.ordinal.asc(),
                )
                .limit(max_chunks * 3)
                .all()
            )
            for chunk in priority_rows:
                by_id.setdefault(chunk.id, (chunk, 100))

    ranked_candidates = sorted(
        by_id.values(),
        key=lambda item: (
            -item[1],
            item[0].source_type,
            item[0].source_id,
            item[0].ordinal,
        ),
    )
    ranked: list[tuple[MissionArchiveChunk, int]] = []
    selected_chunk_ids: set[str] = set()
    selected_sources_for_diversity: set[tuple[str, str]] = set()
    for candidate in ranked_candidates:
        source_key = (candidate[0].source_type, candidate[0].source_id)
        if source_key in selected_sources_for_diversity:
            continue
        ranked.append(candidate)
        selected_chunk_ids.add(candidate[0].id)
        selected_sources_for_diversity.add(source_key)
        if len(ranked) >= max_chunks:
            break
    if len(ranked) < max_chunks:
        for candidate in ranked_candidates:
            if candidate[0].id in selected_chunk_ids:
                continue
            ranked.append(candidate)
            selected_chunk_ids.add(candidate[0].id)
            if len(ranked) >= max_chunks:
                break
    excerpts = tuple(
        ArchiveExcerpt(
            chunk_id=chunk.id,
            attachment_id=chunk.attachment_id,
            filename=chunk.source_label,
            question_id=(
                chunk.attachment.question_id if chunk.attachment is not None else None
            ),
            ordinal=chunk.ordinal,
            char_start=chunk.char_start,
            char_end=chunk.char_end,
            content_sha256=chunk.content_sha256,
            text=_decrypt_chunk(chunk),
            relevance_score=score_value,
            source_type=chunk.source_type,
            source_id=chunk.source_id,
        )
        for chunk, score_value in ranked
    )

    no_text_rows = []
    if priority:
        priority_values = list(priority)
        for offset in range(0, len(priority_values), DATABASE_ID_BATCH):
            batch = priority_values[offset : offset + DATABASE_ID_BATCH]
            no_text_rows.extend(
                db.query(MissionAttachment)
                .filter(
                    MissionAttachment.organization_id == organization_id,
                    MissionAttachment.mission_id == mission_id,
                    MissionAttachment.id.in_(batch),
                    MissionAttachment.extraction_status.in_(
                        {"visual_ready", "provider_ready"}
                    ),
                )
                .order_by(MissionAttachment.byte_size.asc())
                .limit(2)
                .all()
            )
        no_text_rows.sort(key=lambda row: row.byte_size)
    direct_binary_ids = tuple(row.id for row in no_text_rows[:2])
    selected_attachment_ids = sorted(
        {
            item.attachment_id
            for item in excerpts
            if item.attachment_id is not None
        }
        | set(direct_binary_ids)
    )
    selected_source_ids = sorted(
        {
            f"{item.source_type}:{item.source_id or item.attachment_id}"
            for item in excerpts
        }
        | {f"attachment:{item}" for item in direct_binary_ids}
    )
    manifest = {
        "archive_version": ARCHIVE_INDEX_VERSION,
        "archive_total_attachments": int(totals[0] or 0),
        "archive_total_bytes": int(totals[1] or 0),
        "archive_indexed_attachments": int(indexed_attachments),
        "archive_total_sources": int(totals[0] or 0)
        + sum(
            count
            for source_type, count in source_counts.items()
            if source_type != "attachment"
        ),
        "archive_source_counts": source_counts,
        "archive_total_chunks": int(total_chunks),
        "retrieval_query_term_count": len(hashes),
        "selected_chunk_count": len(excerpts),
        "selected_attachment_ids": selected_attachment_ids,
        "selected_source_ids": selected_source_ids,
        "direct_binary_attachment_ids": list(direct_binary_ids),
        "priority_attachment_count": len(priority_attachment_ids),
        "priority_attachment_set_sha256": hashlib.sha256(
            "\n".join(sorted(priority)).encode("utf-8")
        ).hexdigest(),
        "selection_mode": "relevance_with_current_turn_priority",
        "completeness": "selective_working_set_from_preserved_archive",
    }
    return MissionArchiveContext(
        excerpts=excerpts,
        manifest=manifest,
        direct_binary_attachment_ids=direct_binary_ids,
    )
