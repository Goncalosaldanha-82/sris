"""Staging gate: private analytics authorization plus existing activation checks."""
from pathlib import Path
import subprocess
import sys

root=Path(__file__).resolve().parents[1]
for script in ("qa_private_analytics.py", "activation_release_checks.py", "audit_analytics_owner.py"):
    subprocess.run([sys.executable,str(root/"tools"/script)],cwd=root,check=True)
