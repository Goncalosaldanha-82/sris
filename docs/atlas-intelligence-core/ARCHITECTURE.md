# AIC Architecture v0.1

## Layer 1 — Memory access

Read-only access to the AMOS SQLite database.

## Layer 2 — Analytical modules

Each module emits explicit `IntelligenceFinding` objects with:

- type;
- severity;
- summary;
- affected objects;
- rationale;
- recommended action;
- confidence;
- status.

## Layer 3 — Impact analysis

Traverses the AMOS relation graph to show potentially affected objects.

## Layer 4 — Prioritization

Ranks findings using severity, confidence, scope and governance relevance.

## Layer 5 — Reporting

Generates versionable Markdown and JSON reports.

## Safety rule

The core cannot change hypotheses, theories, doctrine or code directly. It can only produce findings and recommendations for governed review.
