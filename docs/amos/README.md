# ATLAS Memory Operating System — AMOS v0.1

## Purpose

AMOS connects the existing ATLAS components into one institutional memory architecture:

```text
ATLAS Chat Bridge
        ↓
ATLAS Knowledge Engine
        ↓
ATLAS Repository Agent
        ↓
AMOS Memory Store
        ↓
Relations + Events + Search + Snapshots
        ↓
GitHub / Human Review
```

## Components

### 1. Memory Store

SQLite database at:

```text
.atlas/amos/amos.db
```

Stores:

- memory objects;
- relations;
- events;
- searchable full-text index.

### 2. Repository Memory Indexer

Indexes Markdown assets under:

```text
docs/atlas/
```

It extracts:

- title;
- summary;
- type;
- state;
- source path;
- source identifier;
- tags.

### 3. Relation Builder

Builds relations from explicit references such as:

```text
HYP-001
MISSION-001
ADR-003
```

### 4. Event Ledger

Records creation, updates, relations, snapshots and errors.

### 5. Search

AMOS provides full-text search over institutional memory.

Example:

```bash
python -m app.amos.cli --repo . search "institutional continuity"
```

### 6. Snapshots

Creates versionable JSON snapshots in:

```text
docs/atlas/knowledge-vault/snapshots/
```

### 7. Status Report

Generates:

```text
docs/atlas/knowledge-vault/AMOS-STATUS.md
```

## Bootstrap

```bash
python -m app.amos.cli --repo . bootstrap
```

Or double-click:

```text
scripts/AMOS_BOOTSTRAP.cmd
```

## Refresh

```bash
python -m app.amos.cli --repo . refresh
```

## Local API

```bash
uvicorn app.amos.api:app --host 127.0.0.1 --port 8790
```

Endpoints:

- `GET /health`
- `POST /bootstrap`
- `POST /refresh`
- `GET /search?q=...`
- `POST /snapshot`

## Governance boundary

AMOS is a memory and orchestration layer.

It does not:

- prove scientific claims;
- approve hypotheses;
- replace human judgment;
- merge its own Pull Requests;
- silently alter foundational doctrine;
- directly read a live ChatGPT conversation without a connector.

Human review remains mandatory.
