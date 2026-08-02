from pathlib import Path
from app.atlas_os.models import IntakeRequest, ReviewDecision, WorkflowState
from app.atlas_os.orchestrator import AtlasOrchestrator

def test_flow(tmp_path:Path):
    o=AtlasOrchestrator(tmp_path)
    r=o.intake(IntakeRequest(title="Test",content="# Decision\n\nGitHub is source of truth.\n# Risk\n\nChat loss."))
    assert r.state==WorkflowState.REVIEW_REQUIRED and len(r.candidates)==2
    rr=o.review(r.workflow_id,ReviewDecision(approvals={c.candidate_id:True for c in r.candidates}))
    assert rr.state==WorkflowState.APPROVED
    f=o.materialize(r.workflow_id)
    assert f.state==WorkflowState.COMMIT_PROPOSED and len(f.output_paths)==2
