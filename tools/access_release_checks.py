"""Staging gate: isolated integration tests, followed by read-only email audit."""
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
subprocess.run([sys.executable, str(root / "tools/qa_access_inbox.py")], cwd=root, check=True)
subprocess.run([sys.executable, str(root / "tools/live_email_readonly_audit.py")], cwd=root, check=True)
