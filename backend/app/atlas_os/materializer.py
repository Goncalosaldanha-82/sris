from pathlib import Path
from re import sub
from .models import WorkflowRecord, CandidateType

ROUTES={
CandidateType.DECISION:("docs/atlas/research-notes","DR"),
CandidateType.HYPOTHESIS:("docs/atlas/hypotheses","HYP"),
CandidateType.CONCEPT:("docs/atlas/ontology","CONCEPT"),
CandidateType.MISSION:("docs/atlas/missions","MISSION"),
CandidateType.THEORY:("docs/atlas/theories","THEORY"),
CandidateType.RISK:("docs/atlas/research-notes","RISK"),
CandidateType.ACTION:("docs/atlas/missions","ACTION"),
CandidateType.OBSERVATION:("docs/atlas/research-notes","OBS"),
CandidateType.ARCHITECTURE:("docs/atlas/research-notes","ARCH"),
}

class Materializer:
    def __init__(self,root:Path): self.root=root
    def run(self,w:WorkflowRecord):
        paths=[]
        for c in [x for x in w.candidates if x.approved]:
            folder,prefix=ROUTES[c.type]
            d=self.root/folder; d.mkdir(parents=True,exist_ok=True)
            n=len(list(d.glob(f"{prefix}-*.md")))+1
            rel=f"{folder}/{prefix}-{n:03d}-{sub(r'[^a-zA-Z0-9]+','-',c.title).strip('-').lower()[:60]}.md"
            (self.root/rel).write_text(
                f"# {prefix}-{n:03d} — {c.title}\n\n"
                f"**Workflow:** `{w.workflow_id}`  \n**Human approved:** `true`\n\n"
                f"## Summary\n\n{c.summary}\n",encoding="utf-8")
            paths.append(rel)
        return paths
