import sqlite3
from pathlib import Path
from uuid import UUID
from .models import WorkflowRecord

class WorkflowStore:
    def __init__(self,path:Path):
        self.path=path; path.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(path) as c:
            c.execute("CREATE TABLE IF NOT EXISTS workflows(id TEXT PRIMARY KEY,payload TEXT NOT NULL)")
    def save(self,r:WorkflowRecord):
        with sqlite3.connect(self.path) as c:
            c.execute("INSERT OR REPLACE INTO workflows VALUES(?,?)",(str(r.workflow_id),r.model_dump_json()))
    def get(self,i:UUID)->WorkflowRecord:
        with sqlite3.connect(self.path) as c:
            row=c.execute("SELECT payload FROM workflows WHERE id=?",(str(i),)).fetchone()
        if not row: raise KeyError(i)
        return WorkflowRecord.model_validate_json(row[0])
    def list(self):
        with sqlite3.connect(self.path) as c:
            rows=c.execute("SELECT payload FROM workflows").fetchall()
        return [WorkflowRecord.model_validate_json(r[0]) for r in rows]
