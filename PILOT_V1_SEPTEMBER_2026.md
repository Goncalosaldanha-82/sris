# SRIS Pilot V1 — September 2026

## Delivery target
Pilot-ready build before **2026-09-10**.

## Product thesis
A mission must start materially better because previous missions existed.

The pilot experience is independent from the legacy `frontend/atlas-os` UI. The old staging interface is not modified by this branch.

## Core user journey
1. Command — show what deserves attention and why.
2. New mission — describe the problem in natural language.
3. Preflight — recover related missions, prior learning, contradictions, stale knowledge and evidence gaps.
4. Mission cockpit — separate known / hypothesised / missing / inherited knowledge.
5. Next best action — identify the information or intervention with highest decision value.
6. Outcome — record what happened after action.
7. Learning — promote a learning with validity conditions and invalidation triggers.
8. Inheritance — require explicit still-valid / revalidate / invalidate review in a future mission.
9. Organizational memory — preserve history, supersession and cross-mission relationships.
10. Pilot Mode — measure baseline, intervention, outcomes and value produced by SRIS itself.

## Pilot proof metrics
- Time-to-informed-start.
- Learning reuse rate.
- Decision outcome closure.
- Decision Debt reduced.
- Context recovered without manual reconstruction.
- Evidence gaps resolved before intervention.
- Repeated-problem rate.

## Delivery gates
### Gate A — Experience foundation
New standalone frontend, responsive design, health state, navigation and Mission Intelligence cockpit.

### Gate B — Live data
Authentication, organization context, real mission list, mission document and learning inheritance APIs.

### Gate C — Action loop
Create mission, preflight, inheritance disposition, evidence gaps, decision/action/outcome and learning promotion.

### Gate D — Pilot Mode
Baseline snapshot, pilot scope, metric capture, outcome comparison and pilot evidence report.

### Gate E — Operational readiness
Attachment stress test, session/auth regression, DB migration, backup/rollback, mobile pass, error-state pass and Railway deployment validation.

## Non-negotiables
- No UI claims unsupported by stored data.
- AI/model is not the system of record.
- Canonical mission data and organizational memory remain the source of truth.
- Historical knowledge is superseded or invalidated, never silently erased.
- The pilot build must not require the legacy interface to operate.
