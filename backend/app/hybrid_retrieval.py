from __future__ import annotations

import hashlib
import json
import math
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.mission_intelligence.models import MissionAttachment


STOPWORDS = {
    "para", "como", "mais", "esta", "este", "isso", "sobre", "entre", "pela", "pelo",
    "uma", "umas", "uns", "que", "com", "sem", "dos", "das", "por", "não", "nos", "nas",
}


@dataclass(frozen=True)
class RetrievalChunk:
    attachment_id: str
    filename: str
    ordinal: int
    char_start: int
    char_end: int
    text: str
    content_sha256: str


def _flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _embedding_model() -> str:
    return os.getenv("SRIS_EMBEDDING_MODEL", "text-embedding-3-small").strip() or "text-embedding-3-small"


def _terms(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-ZÀ-ÿ0-9_-]{3,}", value.lower())
        if token not in STOPWORDS
    }


def _chunk_text(value: str, *, size: int = 2200, overlap: int = 280) -> list[tuple[int, int, str]]:
    clean = (value or "").strip()
    if not clean:
        return []
    size = max(600, size)
    overlap = min(max(0, overlap), size // 2)
    rows: list[tuple[int, int, str]] = []
    start = 0
    while start < len(clean):
        end = min(len(clean), start + size)
        if end < len(clean):
            boundary = max(clean.rfind("\n", start + size // 2, end), clean.rfind(". ", start + size // 2, end))
            if boundary > start:
                end = boundary + 1
        excerpt = clean[start:end].strip()
        if excerpt:
            rows.append((start, end, excerpt))
        if end >= len(clean):
            break
        start = max(start + 1, end - overlap)
    return rows


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _ensure_schema(db: Session) -> None:
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS pilot_semantic_chunks (
            organization_id VARCHAR(64) NOT NULL,
            mission_id VARCHAR(64) NOT NULL,
            attachment_id VARCHAR(64) NOT NULL,
            filename VARCHAR(500) NOT NULL,
            ordinal INTEGER NOT NULL,
            char_start INTEGER NOT NULL,
            char_end INTEGER NOT NULL,
            content_sha256 VARCHAR(64) NOT NULL,
            embedding_model VARCHAR(160) NOT NULL,
            embedding_json TEXT NOT NULL,
            embedding_dimensions INTEGER NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (organization_id, attachment_id, ordinal, embedding_model)
        )
    """))
    db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_pilot_semantic_chunks_mission
        ON pilot_semantic_chunks (organization_id, mission_id, attachment_id)
    """))


def _openai_embeddings(texts: list[str], model: str) -> list[list[float]]:
    if not texts:
        return []
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    body = json.dumps({"model": model, "input": texts}).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/embeddings",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"embedding provider rejected request ({exc.code}): {raw}") from exc
    except Exception as exc:
        raise RuntimeError("embedding provider unavailable") from exc
    data = sorted(payload.get("data") or [], key=lambda item: item.get("index", 0))
    vectors = [item.get("embedding") or [] for item in data]
    if len(vectors) != len(texts):
        raise RuntimeError("embedding provider returned an incomplete batch")
    return vectors


def _materialize_chunks(attachments: Iterable[MissionAttachment]) -> list[RetrievalChunk]:
    chunks: list[RetrievalChunk] = []
    for item in attachments:
        for ordinal, (start, end, excerpt) in enumerate(_chunk_text(item.extracted_text or "")):
            chunks.append(
                RetrievalChunk(
                    attachment_id=item.id,
                    filename=item.original_filename,
                    ordinal=ordinal,
                    char_start=start,
                    char_end=end,
                    text=excerpt,
                    content_sha256=hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
                )
            )
    return chunks


def _load_cached_embeddings(
    db: Session,
    *,
    organization_id: str,
    attachment_ids: list[str],
    model: str,
) -> dict[tuple[str, int, str], list[float]]:
    if not attachment_ids:
        return {}
    rows = db.execute(
        text("""
            SELECT attachment_id, ordinal, content_sha256, embedding_json
            FROM pilot_semantic_chunks
            WHERE organization_id=:org AND embedding_model=:model
        """),
        {"org": organization_id, "model": model},
    ).mappings().all()
    allowed = set(attachment_ids)
    out: dict[tuple[str, int, str], list[float]] = {}
    for row in rows:
        if row["attachment_id"] not in allowed:
            continue
        try:
            out[(row["attachment_id"], int(row["ordinal"]), row["content_sha256"])] = json.loads(row["embedding_json"])
        except Exception:
            continue
    return out


def _persist_embedding(
    db: Session,
    *,
    organization_id: str,
    mission_id: str,
    chunk: RetrievalChunk,
    model: str,
    vector: list[float],
) -> None:
    db.execute(text("""
        INSERT INTO pilot_semantic_chunks
        (organization_id, mission_id, attachment_id, filename, ordinal, char_start, char_end,
         content_sha256, embedding_model, embedding_json, embedding_dimensions)
        VALUES (:org, :mission, :attachment, :filename, :ordinal, :start, :end,
                :sha, :model, :embedding, :dimensions)
        ON CONFLICT (organization_id, attachment_id, ordinal, embedding_model)
        DO UPDATE SET filename=EXCLUDED.filename, char_start=EXCLUDED.char_start,
                      char_end=EXCLUDED.char_end, content_sha256=EXCLUDED.content_sha256,
                      embedding_json=EXCLUDED.embedding_json,
                      embedding_dimensions=EXCLUDED.embedding_dimensions,
                      created_at=CURRENT_TIMESTAMP
    """), {
        "org": organization_id,
        "mission": mission_id,
        "attachment": chunk.attachment_id,
        "filename": chunk.filename,
        "ordinal": chunk.ordinal,
        "start": chunk.char_start,
        "end": chunk.char_end,
        "sha": chunk.content_sha256,
        "model": model,
        "embedding": json.dumps(vector),
        "dimensions": len(vector),
    })


def _rrf(rank: int | None, *, k: int = 60) -> float:
    return 0.0 if rank is None else 1.0 / (k + rank)


def hybrid_retrieve(
    db: Session,
    *,
    organization_id: str,
    mission_id: str,
    query: str,
    attachments: list[MissionAttachment],
    limit: int = 8,
) -> tuple[list[dict], dict]:
    """Transparent hybrid retrieval.

    The vector is never the source of truth. Every candidate retains source identity,
    character offsets and content hash. Semantic failure degrades to lexical retrieval.
    """
    chunks = _materialize_chunks(attachments)
    if not chunks:
        return [], {"mode": "hybrid", "semantic_status": "no_documents", "embedding_model": None}

    query_terms = _terms(query)
    lexical_scores: dict[int, float] = {}
    for idx, chunk in enumerate(chunks):
        terms = _terms(chunk.text)
        overlap = len(query_terms.intersection(terms))
        lexical_scores[idx] = overlap / max(1.0, math.sqrt(len(terms)))
    lexical_order = sorted(range(len(chunks)), key=lambda i: lexical_scores[i], reverse=True)
    lexical_rank = {idx: rank for rank, idx in enumerate(lexical_order, start=1) if lexical_scores[idx] > 0}

    semantic_scores: dict[int, float] = {}
    semantic_rank: dict[int, int] = {}
    semantic_status = "disabled"
    model: str | None = None
    if _flag("SRIS_SEMANTIC_RETRIEVAL_ENABLED", True) and os.getenv("OPENAI_API_KEY", "").strip():
        model = _embedding_model()
        try:
            _ensure_schema(db)
            cache = _load_cached_embeddings(
                db,
                organization_id=organization_id,
                attachment_ids=[a.id for a in attachments],
                model=model,
            )
            missing: list[tuple[int, RetrievalChunk]] = []
            vectors: dict[int, list[float]] = {}
            for idx, chunk in enumerate(chunks):
                key = (chunk.attachment_id, chunk.ordinal, chunk.content_sha256)
                if key in cache:
                    vectors[idx] = cache[key]
                else:
                    missing.append((idx, chunk))
            batch_size = max(1, min(64, int(os.getenv("SRIS_EMBEDDING_BATCH_SIZE", "32"))))
            for offset in range(0, len(missing), batch_size):
                batch = missing[offset:offset + batch_size]
                embedded = _openai_embeddings([chunk.text for _, chunk in batch], model)
                for (idx, chunk), vector in zip(batch, embedded):
                    vectors[idx] = vector
                    _persist_embedding(
                        db,
                        organization_id=organization_id,
                        mission_id=mission_id,
                        chunk=chunk,
                        model=model,
                        vector=vector,
                    )
            query_vector = _openai_embeddings([query], model)[0]
            semantic_scores = {idx: _cosine(query_vector, vector) for idx, vector in vectors.items()}
            order = sorted(semantic_scores, key=lambda i: semantic_scores[i], reverse=True)
            semantic_rank = {idx: rank for rank, idx in enumerate(order, start=1)}
            semantic_status = "ready"
            db.commit()
        except Exception:
            db.rollback()
            semantic_scores = {}
            semantic_rank = {}
            semantic_status = "fallback_lexical"

    lexical_weight = float(os.getenv("SRIS_RETRIEVAL_LEXICAL_WEIGHT", "0.45"))
    semantic_weight = float(os.getenv("SRIS_RETRIEVAL_SEMANTIC_WEIGHT", "0.55"))
    combined: list[tuple[float, int]] = []
    for idx in range(len(chunks)):
        score = lexical_weight * _rrf(lexical_rank.get(idx)) + semantic_weight * _rrf(semantic_rank.get(idx))
        if score == 0 and idx in lexical_rank:
            score = lexical_weight * _rrf(lexical_rank[idx])
        combined.append((score, idx))
    combined.sort(reverse=True)

    results: list[dict] = []
    for hybrid_score, idx in combined[: max(1, limit)]:
        chunk = chunks[idx]
        if hybrid_score <= 0 and results:
            continue
        results.append({
            "attachment_id": chunk.attachment_id,
            "filename": chunk.filename,
            "ordinal": chunk.ordinal,
            "char_start": chunk.char_start,
            "char_end": chunk.char_end,
            "content_sha256": chunk.content_sha256,
            "text": chunk.text,
            "lexical_score": round(lexical_scores.get(idx, 0.0), 6),
            "lexical_rank": lexical_rank.get(idx),
            "semantic_score": round(semantic_scores.get(idx, 0.0), 6) if idx in semantic_scores else None,
            "semantic_rank": semantic_rank.get(idx),
            "hybrid_score": round(hybrid_score, 8),
            "embedding_model": model if idx in semantic_scores else None,
        })

    manifest = {
        "mode": "hybrid_rrf" if semantic_status == "ready" else "lexical_with_semantic_fallback",
        "semantic_status": semantic_status,
        "embedding_model": model,
        "chunks_considered": len(chunks),
        "selected_chunks": len(results),
        "lexical_weight": lexical_weight,
        "semantic_weight": semantic_weight,
        "provenance_contract": "source_id+filename+char_offsets+content_sha256",
    }
    return results, manifest
