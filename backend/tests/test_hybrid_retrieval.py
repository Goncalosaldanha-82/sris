from __future__ import annotations

from app.hybrid_retrieval import _chunk_text, _cosine, _rrf, _terms


def test_chunk_text_preserves_explicit_offsets() -> None:
    source = "A" * 900 + ". " + "B" * 900 + ". " + "C" * 900
    chunks = _chunk_text(source, size=1000, overlap=120)
    assert len(chunks) >= 3
    for start, end, excerpt in chunks:
        assert 0 <= start < end <= len(source)
        assert excerpt
        assert excerpt in source[start:end]


def test_cosine_similarity_is_interpretable() -> None:
    assert round(_cosine([1.0, 0.0], [1.0, 0.0]), 6) == 1.0
    assert round(_cosine([1.0, 0.0], [0.0, 1.0]), 6) == 0.0


def test_terms_and_rrf_support_hybrid_fusion() -> None:
    terms = _terms("Risco de incêndio florestal e disponibilidade hídrica")
    assert "incêndio" in terms
    assert "florestal" in terms
    assert _rrf(1) > _rrf(5) > 0
    assert _rrf(None) == 0.0
