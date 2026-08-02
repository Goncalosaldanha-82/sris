# ATLAS Repository Engine — ARE v0.1

## Purpose

ARE turns approved ATLAS knowledge into controlled repository changes.

## Capabilities

- repository scanning;
- persistent repository index;
- asset typing;
- explicit reference extraction;
- backlinks;
- dependency impact analysis;
- change planning;
- unified diff preview;
- safe file application;
- optional branch creation;
- optional commit and push;
- draft Pull Request client;
- mandatory human approval.

## Safety boundary

By default, ARE only scans, plans and previews.

Writing requires an explicit apply call.

Creating a branch, committing and pushing each require separate explicit flags.

ARE never merges a Pull Request.

## Scan

```bash
python -m app.atlas_repository_engine.cli --repo . scan
```

## Preview

```bash
python -m app.atlas_repository_engine.cli \
  --repo . \
  preview \
  --plan path/to/plan.json
```

## Apply without Git

```bash
python -m app.atlas_repository_engine.cli \
  --repo . \
  apply \
  --plan path/to/plan.json
```

## Apply, commit and push

```bash
python -m app.atlas_repository_engine.cli \
  --repo . \
  apply \
  --plan path/to/plan.json \
  --branch \
  --commit \
  --push
```
