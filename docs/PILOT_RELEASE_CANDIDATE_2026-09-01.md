# SRIS Pilot & Mission Intelligence — release candidate

## Scope

This record applies only to branch `pilot-v1-september-2026`.

It does not assert deployment to Railway. The Railway service `sris-pilot-v1` remains connected to `demo-experience-2026-08-30` until a separate, explicit release decision is made.

## Candidate identity

- Product: SRIS Pilot & Mission Intelligence
- Candidate build: `20260901-pilot-mission-intelligence-rc1`
- Branch: `pilot-v1-september-2026`
- Deployment status: not deployed to the public Pilot V1 service
- Repository hygiene: diagnostic connector probes, upload-path probes and one-shot repair workflows are absent from the candidate tree

## Methodological contract

### Five user moments

1. Context
2. Evidence
3. Decision
4. Measurement
5. Memory

### Eight canonical records

1. Observation
2. Evidence
3. Hypothesis
4. Alternative
5. Decision
6. Action
7. Outcome
8. Learning

Context, Measurement and Memory are navigation and governance moments; they are not additional canonical records.

The Pilot V1 backend and frontend contracts have been reconciled so that automated tests protect this distinction instead of the obsolete eleven-step presentation.

## Universal configuration

The official profile catalog contains exactly six profiles:

1. Cross-sector
2. Hospitality
3. Public sector
4. Industrial operations
5. Territorial laboratory
6. Research and innovation

Programme or commercial origin is stored independently from the sector profile. Supported origins include direct pilots, Tourism Advance, Hospitality Open Innovation, public programmes, private clients and academic partnerships.

## Migration lineage

The only valid migration lineage after the existing Pilot V1 staging state is:

```text
20260827_0022
  -> 20260901_0023
  -> 20260901_0024
```

- `20260901_0023` creates the Pilot & Mission Intelligence platform tables.
- `20260901_0024` creates pilot value and collaboration tables.
- No revision named `20260831_0023` belongs to this lineage.
- The expected Alembic head is `20260901_0024`.

The permanent CI gate validates both a fresh database and the real staging upgrade path from `20260827_0022` to `20260901_0024`.

## Release gate

A Railway branch switch is prohibited until the exact candidate commit has passed:

- Python and JavaScript syntax checks;
- all frontend contracts;
- a fresh migration to head;
- the `20260827_0022 -> 20260901_0024` upgrade path;
- exactly one Alembic head;
- Pilot V1 contracts;
- Pilot & Mission Intelligence tests;
- pilot value, collaboration and reports;
- negative tenant isolation;
- identity lifecycle;
- learning inheritance and organizational memory.

## Controlled deployment procedure

After CI succeeds on the exact final commit:

1. create or verify a recoverable PostgreSQL backup/snapshot;
2. record the current Railway deployment and commit as rollback evidence;
3. change only the `sris-pilot-v1` service source from `demo-experience-2026-08-30` to `pilot-v1-september-2026`;
4. monitor the automatic `alembic upgrade head` operation;
5. verify `/health`, `/api/pilot/build` and `/api/pilot/release-state`;
6. execute `python -m alembic current -v` and `python -m alembic heads -v` inside the deployed container;
7. require both database revision and code head to equal `20260901_0024`;
8. run the authenticated empty-workspace, pilot, mission, persistence and export smoke tests.

No `stamp`, manual revision rewrite or blind schema mutation is permitted.
