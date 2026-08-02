import re
from .models import Candidate, CandidateType

MAP = {
 "decision":CandidateType.DECISION, "decisão":CandidateType.DECISION,
 "hypothesis":CandidateType.HYPOTHESIS, "hipótese":CandidateType.HYPOTHESIS,
 "concept":CandidateType.CONCEPT, "conceito":CandidateType.CONCEPT,
 "mission":CandidateType.MISSION, "missão":CandidateType.MISSION,
 "theory":CandidateType.THEORY, "teoria":CandidateType.THEORY,
 "risk":CandidateType.RISK, "risco":CandidateType.RISK,
 "action":CandidateType.ACTION, "ação":CandidateType.ACTION,
 "observation":CandidateType.OBSERVATION, "observação":CandidateType.OBSERVATION,
 "architecture":CandidateType.ARCHITECTURE, "arquitetura":CandidateType.ARCHITECTURE,
}

class TriageEngine:
    def classify(self, content: str) -> list[Candidate]:
        pat = re.compile(r"(?m)^#{1,4}\s+(.+?)\s*$")
        ms = list(pat.finditer(content))
        out = []
        for i,m in enumerate(ms):
            heading=m.group(1).strip()
            body=content[m.end(): ms[i+1].start() if i+1<len(ms) else len(content)].strip()
            kind=None
            low=heading.lower()
            for token,val in MAP.items():
                if token in low: kind=val; break
            if kind and body:
                out.append(Candidate(type=kind,title=heading,summary=re.sub(r"\s+"," ",body)[:10000],confidence=.85))
        if not out:
            out=[Candidate(type=CandidateType.OBSERVATION,title="Unstructured intake",summary=re.sub(r"\s+"," ",content)[:10000],confidence=.35)]
        return out
