# AMOS Architecture v0.1

## Architectural layers

```text
Layer 1 — Intake
Chat Bridge, documents, repository files

Layer 2 — Interpretation
Knowledge Engine classification and routing

Layer 3 — Memory
AMOS objects, relations, events and provenance

Layer 4 — Governance
Repository Agent, draft PRs, human review

Layer 5 — Retrieval
Search, status reports, snapshots and APIs
```

## Memory object

Each memory object preserves:

- stable UUID;
- institutional type;
- epistemic state;
- title and summary;
- source path and source identifier;
- timestamps;
- tags;
- metadata.

## Memory relation

Relations are explicit and directional:

- derived from;
- supports;
- contradicts;
- revises;
- implements;
- validates;
- affects;
- related to;
- supersedes;
- produced by.

## Memory event

The event ledger records what happened to institutional memory and when.

## Current limitation

v0.1 builds relations from explicit identifiers and repository structure. It does not yet perform semantic graph inference using embeddings or an LLM.
