"""Staging checks. Live recovery requires an explicit request ID argument."""
from pathlib import Path
import argparse
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--recover-request")
parser.add_argument("--inspect-request")
parser.add_argument("--probe", action="store_true")
args = parser.parse_args()
subprocess.run([sys.executable, str(root / "tools/qa_invitation_transport.py")], cwd=root, check=True)
subprocess.run([sys.executable, str(root / "tools/access_release_checks.py")], cwd=root, check=True)
if args.recover_request:
    command = [sys.executable, str(root / "tools/repair_approved_invitation.py"), "--request-id", args.recover_request]
    if args.probe:
        command.append("--probe")
    subprocess.run(command, cwd=root, check=True)
if args.inspect_request:
    subprocess.run([sys.executable, str(root / "tools/inspect_approved_access.py"), "--request-id", args.inspect_request], cwd=root, check=True)
