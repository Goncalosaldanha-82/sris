# ATLAS Repository Agent v0.1

## What it does

The agent receives a Markdown note or a structured JSON change set and prepares a governed repository update.

It:

1. extracts decisions, hypotheses, concepts, risks, actions and observations;
2. creates an immutable agent note;
3. updates the ATLAS Registry;
4. updates the scientific changelog;
5. updates the official project-state ledger;
6. creates a dedicated branch and a **draft pull request**;
7. requires explicit human review before merge.

It never:

- pushes directly to the base branch;
- approves its own work;
- silently rewrites foundational documents;
- treats extracted text as validated scientific evidence;
- deletes historical records.

## Required repository files

The agent can create missing files, but works best when these already exist:

```text
PROJECT-STATE.md
docs/atlas/ATLAS-REGISTRY.md
docs/atlas/CHANGELOG-SCIENTIFIC.md
```

## Local preview

```bash
python -m app.atlas_agent.cli   --input docs/atlas/inbox/update.md   --repo .   --mode preview
```

## Apply locally

```bash
python -m app.atlas_agent.cli   --input docs/atlas/inbox/update.md   --repo .   --mode local
```

Then inspect the diff manually:

```bash
git diff
```

## Create a draft GitHub pull request

Set:

```bash
GITHUB_TOKEN=...
GITHUB_REPOSITORY=owner/repository
```

Run:

```bash
python -m app.atlas_agent.cli   --input docs/atlas/inbox/update.md   --repo .   --mode github   --base-branch feature/ske-core
```

## Recommended Markdown input

```markdown
# Update title

## Decision

The repository is the official source of truth.
State: adopted.
Affected: ATLAS, ASM, SRIS.

## Hypothesis

Institutional reconstructability may support mission continuity.
State: candidate.

## Risk

Conversation-only knowledge may be lost.

## Action

Create a permanent registry entry.
```

## Structured JSON mode

For deterministic control, provide an `AtlasChangeSet` JSON file. Generate a template using the included example.

## GitHub Actions

The workflow `.github/workflows/atlas-repository-agent.yml` can be launched manually from the Actions tab. It runs tests and opens a draft PR.

## v0.1 limitations

- extraction is deterministic and heading-based;
- no direct ChatGPT conversation connector is included;
- no foundational document is rewritten automatically;
- semantic conflict detection is not yet included;
- literature verification is not included;
- GitHub mode creates one commit per updated file through the Contents API.

These limits are deliberate. v0.1 proves the governed update loop without granting an AI autonomous authority over the project.
