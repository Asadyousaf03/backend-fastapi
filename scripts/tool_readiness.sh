#!/usr/bin/env bash
set -euo pipefail

echo "=== Genomic AST tool readiness ==="
python3 - <<'PY'
import shutil
import subprocess
from pathlib import Path

def run(cmd):
    try:
        return subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT).strip()
    except Exception as exc:
        return f"ERROR: {exc}"

print("resfinder:", shutil.which("resfinder") or shutil.which("python3"))
print("amrfinder:", shutil.which("amrfinder"))
print("blastn:", shutil.which("blastn"))
print("kma:", shutil.which("kma"))

for env_name in ("RESFINDER_DB", "POINTFINDER_DB", "AMRFINDER_DB"):
    path = Path(__import__("os").environ.get(env_name, ""))
    print(f"{env_name}:", path, "exists=" + str(path.exists() if str(path) else False))

print("amrfinder --database_version:", run(["amrfinder", "--database_version"]))
PY

echo "OK"
