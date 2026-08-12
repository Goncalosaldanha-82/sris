# SRIS · Mission Intelligence 2.0

Operational SRIS foundation powered by ATLAS Core, with canonical mission
intelligence, deterministic analysis and a governed, persistent AI dialogue that
creates questions, hypotheses, alternatives, criteria and experiments for human
review without mutating the canonical mission.

Active reasoning, dialogue state and granular proposal review:
[Mission Intelligence interactive v2](docs/MISSION-INTELLIGENCE-INTERACTIVE-V2.md).

Deterministic foundation and legacy advisory mode:
[Mission Intelligence & AI v1](docs/MISSION-INTELLIGENCE-AI-V1.md).

Single-organization pilot authorization, per-organization quotas and cost controls:
[AI Governance v1](docs/MISSION-INTELLIGENCE-AI-GOVERNANCE-V1.md).

Controlled production activation:
[MI + AI pilot runbook](docs/MI-AI-PILOT-ACTIVATION-RUNBOOK.md).

Production assessment:
[application audit — 2026-08-08](docs/APP-AUDIT-2026-08-08.md).

One-time creation or repair of the institutional owner:
[institutional access activation](docs/SRIS-INSTITUTIONAL-ACCESS-ACTIVATION.md).

Invite-only account creation, roles and password recovery:
[identity and access lifecycle](docs/SRIS-IDENTITY-AND-ACCESS.md).

## Install

```bash
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[test]"
```

Only `backend/app` is installed as Python packages.

## Verify

```text
scripts/VERIFY_ATLAS_CORE.cmd
```

## Run

```bash
docker compose up --build
```

API: `http://localhost:8000`  
OpenAPI: `http://localhost:8000/docs`

Database schema changes are controlled exclusively by Alembic.
