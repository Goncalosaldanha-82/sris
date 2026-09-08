"""Non-sending release gates; optional strictly read-only staging terms audit."""
import argparse
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--inspect-request')
args = parser.parse_args()
for script in ['qa_activation_and_licence.py', 'invitation_release_checks.py']:
    subprocess.run([sys.executable, str(root/'tools'/script)], cwd=root, check=True)
if args.inspect_request:
    subprocess.run([sys.executable, str(root/'tools/read_access_terms.py'), '--request-id', args.inspect_request], cwd=root, check=True)
