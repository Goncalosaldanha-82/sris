# ATLAS Intelligence Core — AIC v0.1

## Purpose

AIC analyses AMOS institutional memory and converts it into governed intelligence findings.

It does not merely store knowledge. It asks:

- Are there possible contradictions?
- Are there duplicate knowledge objects?
- Which hypotheses or theories lack a validation path?
- Which important objects are disconnected?
- Which objects lack provenance?
- Which objects may be stale?
- What should be reviewed first?
- What other objects could be affected by a change?

## Architecture

```text
Chat Bridge
    ↓
Knowledge Engine
    ↓
AMOS
    ↓
ATLAS Intelligence Core
    ├── Duplicate Analyzer
    ├── Contradiction Analyzer
    ├── Orphan Analyzer
    ├── Validation Gap Analyzer
    ├── Staleness Analyzer
    ├── Provenance Analyzer
    ├── Impact Analyzer
    ├── Priority Engine
    └── Intelligence Report
```

## Run locally

```bash
python -m app.amos.cli --repo . bootstrap
python -m app.atlas_intelligence_core.cli --repo . analyze --no-refresh
```

Or double-click:

```text
scripts/AIC_ANALYZE.cmd
```

## Outputs

```text
docs/atlas/intelligence/AIC-STATUS.md
docs/atlas/intelligence/AIC-LATEST.json
```

## Impact analysis

First obtain a memory object UUID through AMOS search, then run:

```bash
python -m app.atlas_intelligence_core.cli \
  --repo . \
  impact <OBJECT_UUID> \
  --depth 3
```

## Local API

```bash
uvicorn app.atlas_intelligence_core.api:app \
  --host 127.0.0.1 \
  --port 8791
```

Endpoints:

- `GET /health`
- `POST /analyze`
- `GET /impact/{object_id}`

## Scientific and governance limits

AIC findings are diagnostic signals, not facts.

v0.1 uses:

- explicit AMOS relations;
- repository metadata;
- lexical similarity;
- rule-based negation;
- structural validation checks.

It does not yet use:

- embeddings;
- an external language model;
- literature verification;
- causal inference;
- autonomous approval;
- autonomous merge.

Every finding requires human review.
