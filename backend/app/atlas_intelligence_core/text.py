from __future__ import annotations

import math
import re
from collections import Counter


STOPWORDS = {
    "a", "o", "os", "as", "de", "do", "da", "dos", "das", "e", "em", "para",
    "por", "com", "que", "um", "uma", "the", "and", "of", "to", "in", "for",
    "is", "are", "this", "that", "it", "as", "on", "be", "or", "an",
}


def tokens(text: str) -> list[str]:
    words = re.findall(r"[A-Za-zÀ-ÿ0-9_-]{3,}", text.lower())
    return [word for word in words if word not in STOPWORDS]


def cosine_similarity(a: str, b: str) -> float:
    left = Counter(tokens(a))
    right = Counter(tokens(b))
    if not left or not right:
        return 0.0
    dot = sum(value * right.get(key, 0) for key, value in left.items())
    norm_left = math.sqrt(sum(value * value for value in left.values()))
    norm_right = math.sqrt(sum(value * value for value in right.values()))
    if norm_left == 0 or norm_right == 0:
        return 0.0
    return dot / (norm_left * norm_right)


def contains_negation(text: str) -> bool:
    low = text.lower()
    terms = (
        "not ", "no ", "never ", "cannot ", "must not",
        "não ", "nunca ", "jamais ", "não pode", "não deve",
        "refuted", "refutada", "rejeitada",
    )
    return any(term in low for term in terms)
