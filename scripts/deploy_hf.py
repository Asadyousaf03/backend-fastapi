"""Deploy the genomic AST API to a Hugging Face Docker Space.

Creates (or reuses) a Docker Space, injects secrets/variables, and uploads the
repository. Reads Supabase/S3 values from the local .env.cloud file and HF /
CORS settings from environment variables or CLI flags.

Usage (PowerShell):
    $env:HF_TOKEN="hf_xxx"
    $env:HF_USERNAME="your-username"
    $env:SPACE_NAME="genomic-ast"
    $env:CORS_ORIGINS="https://your-app.vercel.app"
    .\.venv\Scripts\python.exe scripts/deploy_hf.py
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = val.strip()
    return values


SPACE_README = """---
title: Genomic AST API
emoji: 🧬
colorFrom: indigo
colorTo: green
sdk: docker
app_port: 7860
pinned: false
short_description: Multi-pathogen genomic antibiogram (ResFinder + AMRFinderPlus)
---

# Genomic AST API

FastAPI backend running pinned ResFinder / PointFinder / AMRFinderPlus for
multi-pathogen antibiotic susceptibility prediction. See the source repository
for details. Health check: `/health`, tool readiness: `/ready`.
"""

IGNORE = [
    ".venv/*",
    ".git/*",
    "node_modules/*",
    "*.pyc",
    "__pycache__/*",
    "**/__pycache__/*",
    ".pytest_cache/*",
    ".env",
    ".env.cloud",
    ".env.*.local",
    "data/tmp_demo/*",
    "data/uploads/*",
    "data/genomic_ast.db",
    "README.md",
    "*.log",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", default=os.getenv("HF_TOKEN"))
    parser.add_argument("--username", default=os.getenv("HF_USERNAME"))
    parser.add_argument("--space", default=os.getenv("SPACE_NAME", "genomic-ast"))
    parser.add_argument("--cors", default=os.getenv("CORS_ORIGINS", ""))
    parser.add_argument("--private", action="store_true", default=False)
    args = parser.parse_args()

    if not args.token or not args.username:
        print("ERROR: HF_TOKEN and HF_USERNAME are required.", file=sys.stderr)
        return 2

    try:
        from huggingface_hub import HfApi
    except ImportError:
        print("ERROR: pip install huggingface_hub", file=sys.stderr)
        return 2

    cloud = load_env_file(ROOT / ".env.cloud")
    repo_id = f"{args.username}/{args.space}"
    space_url = f"https://{args.username.lower()}-{args.space.lower()}.hf.space"

    api = HfApi(token=args.token)

    print(f"Creating/using Space: {repo_id}")
    api.create_repo(
        repo_id=repo_id,
        repo_type="space",
        space_sdk="docker",
        private=args.private,
        exist_ok=True,
    )

    # Sensitive -> secrets; non-sensitive -> variables (both become env vars).
    secrets = {
        "DATABASE_URL": cloud.get("DATABASE_URL", ""),
        "S3_ACCESS_KEY": cloud.get("S3_ACCESS_KEY", ""),
        "S3_SECRET_KEY": cloud.get("S3_SECRET_KEY", ""),
        "S3_ENDPOINT_URL": cloud.get("S3_ENDPOINT_URL", ""),
    }
    if cloud.get("GEMINI_API_KEY"):
        secrets["GEMINI_API_KEY"] = cloud["GEMINI_API_KEY"]

    variables = {
        "ENVIRONMENT": "production",
        "STORAGE_BACKEND": "s3",
        "S3_BUCKET": cloud.get("S3_BUCKET", "genomic-ast"),
        "S3_REGION": cloud.get("S3_REGION", "us-east-1"),
        "COMPUTE_BACKEND": "local",
        "REQUIRE_REAL_TOOLS": "true",
        "TOOL_EXECUTION_MODE": "real",
        "ALLOW_FIXTURE_MODE": "false",
        "ENABLE_DEMO_FALLBACK": "false",
        "PUBLIC_API_BASE": space_url,
        "CORS_ORIGINS": args.cors or space_url,
    }

    for key, value in secrets.items():
        if value:
            api.add_space_secret(repo_id=repo_id, key=key, value=value)
            print(f"  secret set: {key}")
    for key, value in variables.items():
        api.add_space_variable(repo_id=repo_id, key=key, value=value)
        print(f"  variable set: {key}={value}")

    print("Uploading repository (this can take a few minutes)...")
    api.upload_folder(
        folder_path=str(ROOT),
        repo_id=repo_id,
        repo_type="space",
        ignore_patterns=IGNORE,
        commit_message="Deploy genomic AST API to HF Space",
    )

    api.upload_file(
        path_or_fileobj=SPACE_README.encode("utf-8"),
        path_in_repo="README.md",
        repo_id=repo_id,
        repo_type="space",
        commit_message="Add Space metadata",
    )

    print("\nDeploy triggered. The Space will build the Docker image now.")
    print(f"Space URL:  {space_url}")
    print(f"Build logs: https://huggingface.co/spaces/{repo_id}?logs=build")
    print(f"\nSet Vercel NEXT_PUBLIC_API_URL={space_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
