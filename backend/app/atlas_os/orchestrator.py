from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID
from .models import *
from .store import WorkflowStore
from .triage import TriageEngine
from .materializer import Materializer

class AtlasOrchestrator:
    def __init__(self,root:Path):
        self.root=root.resolve()
        self.store=WorkflowStore(self.root/".atlas/os/workflows.db")
        self.triage=TriageEngine()
        self.mat=Materializer(self.root)
    def intake(self,req:IntakeRequest):
        r=WorkflowRecord(title=req.title,source_name=req.source_name,original_content=req.content)
        r.candidates=self.triage.classify(req.content)
        r.state=WorkflowState.REVIEW_REQUIRED
        r.updated_at=datetime.now(timezone.utc)
        self.store.save(r); return r
    def review(self,i:UUID,d:ReviewDecision):
        r=self.store.get(i)
        for c in r.candidates: c.approved=d.approvals.get(c.candidate_id,False)
        r.state=WorkflowState.APPROVED if any(c.approved for c in r.candidates) else WorkflowState.REJECTED
        r.updated_at=datetime.now(timezone.utc); self.store.save(r); return r
    def materialize(self,i:UUID):
        r=self.store.get(i)
        if r.state!=WorkflowState.APPROVED: raise ValueError("Workflow must be approved")
        r.output_paths=self.mat.run(r)
        r.state=WorkflowState.COMMIT_PROPOSED
        r.updated_at=datetime.now(timezone.utc); self.store.save(r); return r
    def get(self,i): return self.store.get(i)
    def list(self): return self.store.list()
