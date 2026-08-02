import os
from pathlib import Path
from uuid import UUID
from fastapi import FastAPI
from .models import IntakeRequest, ReviewDecision
from .orchestrator import AtlasOrchestrator

root=Path(os.getenv("ATLAS_REPOSITORY_ROOT",".")).resolve()
o=AtlasOrchestrator(root)
app=FastAPI(title="ATLAS OS",version="0.1.0")

@app.get("/health")
def health(): return {"status":"ok","repository_root":str(root)}
@app.post("/workflows")
def create(req:IntakeRequest): return o.intake(req)
@app.get("/workflows")
def list_workflows(): return o.list()
@app.get("/workflows/{workflow_id}")
def get_workflow(workflow_id:UUID): return o.get(workflow_id)
@app.post("/workflows/{workflow_id}/review")
def review(workflow_id:UUID,d:ReviewDecision): return o.review(workflow_id,d)
@app.post("/workflows/{workflow_id}/materialize")
def materialize(workflow_id:UUID): return o.materialize(workflow_id)
