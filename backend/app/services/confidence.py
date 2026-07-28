from __future__ import annotations

import math
from collections import defaultdict
from typing import Iterable


def _clip(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, float(value)))


def likelihood_ratio(direction: str, weight: float) -> float:
    """Return the explicit SRIS likelihood ratio for one evidence item.

    Supports evidence increases relative weight. Contradictory/refuting evidence
    decreases it by the reciprocal. Neutral/unknown directions do not update it.
    """
    lr = 1.0 + 6.0 * _clip(weight)
    if direction == "supports":
        return lr
    if direction in {"contradicts", "refutes"}:
        return 1.0 / lr
    return 1.0


def normalized_posteriors(
    hypotheses: Iterable[object],
    evidence_by_hypothesis: dict[str, list[tuple[str, float]]],
) -> dict[str, float]:
    """Calculate a normalized distribution across competing hypotheses.

    The hypotheses are treated as mutually competing within one investigation.
    Priors are first normalized. Evidence then updates relative mass and the final
    distribution is normalized so the posterior probabilities sum to one.
    """
    rows = list(hypotheses)
    if not rows:
        return {}

    raw_priors = [_clip(getattr(h, "prior", 0.0)) for h in rows]
    total_prior = sum(raw_priors)
    priors = (
        [p / total_prior for p in raw_priors]
        if total_prior > 0
        else [1.0 / len(rows)] * len(rows)
    )

    unnormalized: dict[str, float] = {}
    for h, prior in zip(rows, priors):
        mass = max(prior, 1e-15)
        for direction, weight in evidence_by_hypothesis.get(h.id, []):
            mass *= likelihood_ratio(direction, weight)
        unnormalized[h.id] = mass

    total = sum(unnormalized.values())
    if total <= 0 or not math.isfinite(total):
        return {h.id: round(1.0 / len(rows), 12) for h in rows}

    result = {key: value / total for key, value in unnormalized.items()}
    # Correct the final floating-point residue deterministically.
    keys = [h.id for h in rows]
    rounded = {key: round(result[key], 12) for key in keys}
    residue = 1.0 - sum(rounded.values())
    rounded[keys[-1]] = round(rounded[keys[-1]] + residue, 12)
    return rounded


def recalculate_investigation_posteriors(db, organization_id: str, investigation_id: str):
    """Persist the normalized posterior distribution for an investigation."""
    # Imported lazily to keep the pure algorithm easy to test.
    from app.models.models import Evidence, Hypothesis

    hypotheses = (
        db.query(Hypothesis)
        .filter_by(organization_id=organization_id, investigation_id=investigation_id)
        .order_by(Hypothesis.created_at.asc(), Hypothesis.id.asc())
        .all()
    )
    evidence = (
        db.query(Evidence)
        .filter_by(organization_id=organization_id, investigation_id=investigation_id)
        .all()
    )
    grouped: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for item in evidence:
        if item.hypothesis_id:
            grouped[item.hypothesis_id].append((item.direction, item.weight))

    distribution = normalized_posteriors(hypotheses, grouped)
    for hypothesis in hypotheses:
        hypothesis.confidence = distribution.get(hypothesis.id, 0.0)
    db.flush()
    return hypotheses, distribution


def expected_information_gain(
    current: dict[str, float],
    expected_effects: dict[str, float],
    weight: float,
) -> float:
    """Expected KL information gain for a binary future observation.

    expected_effects maps hypothesis IDs to values in [-1, 1]. Positive values
    predict support when the proposed observation is present; negative values
    predict contradiction. The two possible outcomes are treated symmetrically
    because a calibrated observation probability is not yet available.
    """
    if len(current) < 2:
        return 0.0
    base = {key: max(float(value), 1e-15) for key, value in current.items()}
    norm = sum(base.values()) or 1.0
    base = {key: value / norm for key, value in base.items()}

    total_kl = 0.0
    for outcome_sign in (1.0, -1.0):
        updated: dict[str, float] = {}
        for hypothesis_id, prior in base.items():
            effect = _clip(abs(expected_effects.get(hypothesis_id, 0.0)), 0.0, 1.0)
            signed = expected_effects.get(hypothesis_id, 0.0) * outcome_sign
            lr = 1.0 + 6.0 * _clip(weight) * effect
            factor = lr if signed >= 0 else 1.0 / max(lr, 1e-15)
            updated[hypothesis_id] = prior * factor
        updated_total = sum(updated.values()) or 1.0
        updated = {key: value / updated_total for key, value in updated.items()}
        kl = sum(
            q * math.log(q / base[key])
            for key, q in updated.items()
            if q > 1e-15 and base[key] > 1e-15
        )
        total_kl += 0.5 * kl
    return round(total_kl, 12)


def hypothesis_confidence(prior: float, evidence: list[tuple[str, float]]) -> float:
    """Legacy independent credibility calculation.

    Kept for compatibility with external imports. The SRIS API no longer calls
    this function for competing hypotheses; it normalizes the full set instead.
    """
    odds = _clip(prior) / max(1 - _clip(prior), 1e-9)
    for direction, weight in evidence:
        lr = likelihood_ratio(direction, weight)
        odds *= lr
    return round(odds / (1 + odds), 6)
