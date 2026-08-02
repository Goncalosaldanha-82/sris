# ATLAS Knowledge Engine v0.1

## Purpose

Transforms a governed Markdown or JSON intake into structured, versioned and reviewable ATLAS knowledge assets.

## Capabilities

- classification;
- routing;
- stable ID allocation;
- asset creation;
- Registry update;
- Master Index update;
- Capture Log;
- duplicate-title and governance checks;
- draft pull request;
- mandatory human approval.

## Critical limitation

This v0.1 does **not** read this ChatGPT conversation automatically.

A future Chat Bridge must export or deliver conversation content to the intake file/API. The Knowledge Engine then performs the classification and organization.

## Preview

```bash
python -m app.atlas_knowledge_engine.cli   --input docs/atlas/inbox/knowledge-intake.md   --repo .   --mode preview
```

## Apply locally

```bash
python -m app.atlas_knowledge_engine.cli   --input docs/atlas/inbox/knowledge-intake.md   --repo .   --mode local
```

## Governance

The engine prepares knowledge. It cannot approve, validate or merge its own output.
