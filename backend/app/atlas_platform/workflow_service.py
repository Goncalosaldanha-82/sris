from __future__ import annotations

import difflib
import json
import re
from pathlib import Path

from sqlalchemy.orm import Session

from .audit import record_audit
from .models import KnowledgeObject
from .workflow_models import (
    RepositoryChange,
    Workflow,
    WorkflowCandidate,
    WorkflowHistory,
    WorkflowState,
)


HEADING_MAP = {
    "decision": "decision",
    "decisão": "decision",
    "hypothesis": "hypothesis",
    "hipótese": "hypothesis",
    "concept": "concept",
    "conceito": "concept",
    "mission": "mission",
    "missão": "mission",
    "theory": "theory",
    "teoria": "theory",
    "risk": "risk",
    "risco": "risk",
    "action": "action",
    "ação": "action",
    "observation": "observation",
    "observação": "observation",
    "architecture": "architecture",
    "arquitetura": "architecture",
}


class WorkflowService:
    def __init__(self, repository_root: Path | None = None) -> None:
        self.repository_root = (repository_root or Path(".")).resolve()

    def create(
        self,
        db: Session,
        *,
        organization_id: str,
        user_id: str,
        title: str,
        source_name: str,
        source_type: str,
        content: str,
    ) -> Workflow:
        workflow = Workflow(
            organization_id=organization_id,
            created_by_user_id=user_id,
            title=title,
            source_name=source_name,
            source_type=source_type,
            original_content=content,
            normalized_content=self._normalize(content),
            state=WorkflowState.RECEIVED.value,
        )
        db.add(workflow)
        db.flush()

        self._transition(
            db,
            workflow,
            WorkflowState.NORMALIZED,
            "Content normalized",
            user_id,
        )

        candidates = self._classify(workflow.normalized_content or "")
        for candidate in candidates:
            db.add(
                WorkflowCandidate(
                    workflow_id=workflow.id,
                    candidate_type=candidate["type"],
                    title=candidate["title"],
                    summary=candidate["summary"],
                    confidence=f'{candidate["confidence"]:.2f}',
                    source_excerpt=candidate["excerpt"],
                )
            )

        self._transition(
            db,
            workflow,
            WorkflowState.CLASSIFIED,
            f"{len(candidates)} candidates extracted",
            user_id,
        )
        self._transition(
            db,
            workflow,
            WorkflowState.REVIEW_REQUIRED,
            "Human review required",
            user_id,
        )

        record_audit(
            db,
            action="workflow.created",
            resource_type="workflow",
            resource_id=workflow.id,
            organization_id=organization_id,
            user_id=user_id,
            payload={"candidate_count": len(candidates)},
        )
        db.commit()
        db.refresh(workflow)
        return workflow

    def review(
        self,
        db: Session,
        *,
        workflow: Workflow,
        approvals: dict[str, bool],
        comment: str | None,
        user_id: str,
    ) -> Workflow:
        if workflow.state != WorkflowState.REVIEW_REQUIRED.value:
            raise ValueError("Workflow is not awaiting review")

        any_approved = False
        for candidate in workflow.candidates:
            approved = approvals.get(candidate.id, False)
            candidate.approved = "true" if approved else "false"
            candidate.reviewer_comment = comment
            any_approved = any_approved or approved

        target = WorkflowState.APPROVED if any_approved else WorkflowState.REJECTED
        self._transition(
            db,
            workflow,
            target,
            comment or ("Candidates approved" if any_approved else "All candidates rejected"),
            user_id,
        )
        record_audit(
            db,
            action="workflow.reviewed",
            resource_type="workflow",
            resource_id=workflow.id,
            organization_id=workflow.organization_id,
            user_id=user_id,
            payload={"approved": any_approved},
        )
        db.commit()
        db.refresh(workflow)
        return workflow

    def materialize(
        self,
        db: Session,
        *,
        workflow: Workflow,
        user_id: str,
    ) -> Workflow:
        if workflow.state != WorkflowState.APPROVED.value:
            raise ValueError("Workflow must be approved before materialization")

        changed_paths: list[str] = []
        diff_chunks: list[str] = []

        for candidate in workflow.candidates:
            if candidate.approved != "true":
                continue

            obj = KnowledgeObject(
                organization_id=workflow.organization_id,
                object_type=candidate.candidate_type,
                title=candidate.title,
                summary=candidate.summary,
                state="candidate",
                created_by_user_id=user_id,
            )
            db.add(obj)
            db.flush()

            relative_path = self._materialized_path(candidate)
            target = self.repository_root / relative_path
            before = target.read_text(encoding="utf-8") if target.exists() else ""
            after = self._render_markdown(workflow, candidate, obj.id)

            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(after, encoding="utf-8")

            changed_paths.append(relative_path)
            diff_chunks.extend(
                difflib.unified_diff(
                    before.splitlines(),
                    after.splitlines(),
                    fromfile=f"a/{relative_path}",
                    tofile=f"b/{relative_path}",
                    lineterm="",
                )
            )

        self._transition(
            db,
            workflow,
            WorkflowState.MATERIALIZED,
            f"{len(changed_paths)} knowledge assets materialized",
            user_id,
        )
        self._transition(db, workflow, WorkflowState.INDEXED, "Ready for AMOS indexing", user_id)
        self._transition(db, workflow, WorkflowState.ANALYZED, "Ready for AIC analysis", user_id)
        self._transition(
            db,
            workflow,
            WorkflowState.COMMIT_PROPOSED,
            "Repository proposal created",
            user_id,
        )

        short = workflow.id.split("-")[0]
        change = RepositoryChange(
            workflow_id=workflow.id,
            branch_name=f"atlas/workflow-{short}",
            commit_message=f"ATLAS workflow: {workflow.title[:60]}",
            changed_paths_json=json.dumps(changed_paths, ensure_ascii=False),
            diff_text="\n".join(diff_chunks),
            status="pending_human_approval",
        )
        db.add(change)

        record_audit(
            db,
            action="workflow.materialized",
            resource_type="workflow",
            resource_id=workflow.id,
            organization_id=workflow.organization_id,
            user_id=user_id,
            payload={"changed_paths": changed_paths},
        )
        db.commit()
        db.refresh(workflow)
        return workflow

    def proposal(self, workflow: Workflow) -> dict:
        if not workflow.repository_changes:
            raise ValueError("No repository proposal available")
        change = workflow.repository_changes[-1]
        return {
            "branch_name": change.branch_name,
            "commit_message": change.commit_message,
            "changed_paths": json.loads(change.changed_paths_json),
            "diff_text": change.diff_text or "",
            "status": change.status,
        }

    def _transition(
        self,
        db: Session,
        workflow: Workflow,
        target: WorkflowState,
        note: str,
        actor_user_id: str,
    ) -> None:
        previous = workflow.state
        workflow.state = target.value
        db.add(
            WorkflowHistory(
                workflow_id=workflow.id,
                from_state=previous,
                to_state=target.value,
                note=note,
                actor_user_id=actor_user_id,
            )
        )

    @staticmethod
    def _normalize(content: str) -> str:
        content = content.replace("\r\n", "\n").replace("\r", "\n")
        return re.sub(r"\n{3,}", "\n\n", content).strip()

    @staticmethod
    def _classify(content: str) -> list[dict]:
        pattern = re.compile(r"(?m)^#{1,4}\s+(.+?)\s*$")
        matches = list(pattern.finditer(content))
        candidates: list[dict] = []

        for index, match in enumerate(matches):
            heading = match.group(1).strip()
            body_start = match.end()
            body_end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
            body = content[body_start:body_end].strip()
            low = heading.lower()

            candidate_type = None
            for token, mapped in HEADING_MAP.items():
                if token in low:
                    candidate_type = mapped
                    break

            if candidate_type and body:
                candidates.append(
                    {
                        "type": candidate_type,
                        "title": heading,
                        "summary": re.sub(r"\s+", " ", body)[:10000],
                        "excerpt": body[:2000],
                        "confidence": 0.85,
                    }
                )

        if not candidates:
            candidates.append(
                {
                    "type": "observation",
                    "title": "Unstructured intake",
                    "summary": re.sub(r"\s+", " ", content)[:10000],
                    "excerpt": content[:2000],
                    "confidence": 0.35,
                }
            )
        return candidates

    @staticmethod
    def _materialized_path(candidate: WorkflowCandidate) -> str:
        route = {
            "decision": ("docs/atlas/research-notes", "DR"),
            "hypothesis": ("docs/atlas/hypotheses", "HYP"),
            "concept": ("docs/atlas/ontology", "CONCEPT"),
            "mission": ("docs/atlas/missions", "MISSION"),
            "theory": ("docs/atlas/theories", "THEORY"),
            "risk": ("docs/atlas/research-notes", "RISK"),
            "action": ("docs/atlas/missions", "ACTION"),
            "observation": ("docs/atlas/research-notes", "OBS"),
            "architecture": ("docs/atlas/research-notes", "ARCH"),
        }[candidate.candidate_type]

        folder, prefix = route
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", candidate.title).strip("-").lower()[:70]
        return f"{folder}/{prefix}-{candidate.id[:8]}-{slug}.md"

    @staticmethod
    def _render_markdown(
        workflow: Workflow,
        candidate: WorkflowCandidate,
        knowledge_object_id: str,
    ) -> str:
        return f"""# {candidate.title}

**Knowledge Object:** `{knowledge_object_id}`  
**Workflow:** `{workflow.id}`  
**Type:** `{candidate.candidate_type}`  
**State:** `candidate`  
**Human approved:** `true`  

## Summary

{candidate.summary}

## Source excerpt

{candidate.source_excerpt or "Not supplied."}

## Governance notice

> This asset was created after explicit human review and remains subject to future validation.
"""
