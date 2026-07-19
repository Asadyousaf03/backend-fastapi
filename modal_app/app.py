"""Modal application for pinned ResFinder + AMRFinderPlus compute.

Deploy:
    modal deploy modal_app/app.py

Requires Modal secrets:
    genomic-ast-db       -> DATABASE_URL (Postgres)
    genomic-ast-storage  -> STORAGE_BACKEND, S3_* credentials
"""

from __future__ import annotations

import os

import modal

from services.tools.versions import TOOL_PINNING

# Build a pinned scientific image (same pins as Dockerfile.tools).
image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install(
        "wget",
        "curl",
        "ca-certificates",
        "build-essential",
        "zlib1g-dev",
        "libcurl4-openssl-dev",
        "git",
        "ncbi-blast+",
        "hmmer",
    )
    .pip_install(
        "fastapi>=0.115.0",
        "uvicorn[standard]>=0.32.0",
        "pydantic>=2.0.0",
        "python-dotenv>=1.0.0",
        "sqlalchemy>=2.0.0",
        "psycopg[binary]>=3.2.0",
        "boto3>=1.34.0",
        "httpx>=0.27.0",
        "google-genai>=1.0.0",
        f"resfinder=={TOOL_PINNING.resfinder_version}",
        "cgelib>=0.7.3",
        "cgecore==2.0.1",
        "tabulate>=0.8.9",
        "pandas>=1.4.2",
        "biopython>=1.79",
    )
    .run_commands(
        # KMA
        "git clone --depth 1 https://bitbucket.org/genomicepidemiology/kma.git /tmp/kma"
        " && make -C /tmp/kma"
        " && cp /tmp/kma/kma /tmp/kma/kma_index /tmp/kma/kma_shm /usr/local/bin/",
        # ResFinder DB pin
        f"git clone https://bitbucket.org/genomicepidemiology/resfinder_db.git /opt/dbs/resfinder_db"
        f" && git -C /opt/dbs/resfinder_db checkout {TOOL_PINNING.resfinder_db_commit}"
        " && python /opt/dbs/resfinder_db/INSTALL.py /usr/local/bin/kma_index non_interactive",
        # PointFinder DB pin
        f"git clone https://bitbucket.org/genomicepidemiology/pointfinder_db.git /opt/dbs/pointfinder_db"
        f" && git -C /opt/dbs/pointfinder_db checkout {TOOL_PINNING.pointfinder_db_commit}"
        " && python /opt/dbs/pointfinder_db/INSTALL.py /usr/local/bin/kma_index non_interactive",
        # AMRFinderPlus binaries + pinned database archive
        "mkdir -p /opt/amrfinder /opt/dbs/amrfinder"
        f" && curl -fsSL https://github.com/ncbi/amr/releases/download/amrfinder_v{TOOL_PINNING.amrfinder_version}/amrfinder_binaries_v{TOOL_PINNING.amrfinder_version}.tar.gz -o /tmp/amrfinder.tar.gz"
        " && tar -xzf /tmp/amrfinder.tar.gz -C /opt/amrfinder"
        f" && mkdir -p /opt/dbs/amrfinder/{TOOL_PINNING.amrfinder_db_version}"
        f" && (curl -fsSL https://ftp.ncbi.nlm.nih.gov/pathogen/Antimicrobial_resistance/AMRFinderPlus/database/3.12/{TOOL_PINNING.amrfinder_db_version}.tar.gz -o /tmp/amrfinder_db.tar.gz"
        f"  || curl -fsSL https://ftp.ncbi.nlm.nih.gov/pathogen/Antimicrobial_resistance/AMRFinderPlus/database/{TOOL_PINNING.amrfinder_db_version}.tar.gz -o /tmp/amrfinder_db.tar.gz)"
        f" && tar -xzf /tmp/amrfinder_db.tar.gz -C /opt/dbs/amrfinder/{TOOL_PINNING.amrfinder_db_version} --strip-components=1"
        f" && (/opt/amrfinder/amrfinder_index /opt/dbs/amrfinder/{TOOL_PINNING.amrfinder_db_version} || amrfinder_index /opt/dbs/amrfinder/{TOOL_PINNING.amrfinder_db_version} || true)"
        " && rm -f /tmp/amrfinder.tar.gz /tmp/amrfinder_db.tar.gz",
    )
    .env(
        {
            "RESFINDER_DB": "/opt/dbs/resfinder_db",
            "POINTFINDER_DB": "/opt/dbs/pointfinder_db",
            "AMRFINDER_DB": f"/opt/dbs/amrfinder/{TOOL_PINNING.amrfinder_db_version}",
            "PATH": "/opt/amrfinder:/usr/local/bin:/usr/bin:/bin",
            "REQUIRE_REAL_TOOLS": "true",
            "ENABLE_DEMO_FALLBACK": "false",
            "TOOL_EXECUTION_MODE": "real",
        }
    )
    .add_local_dir(".", remote_path="/app", copy=True)
)

app = modal.App(os.environ.get("MODAL_APP_NAME", "genomic-ast"), image=image)
secrets = [
    modal.Secret.from_name("genomic-ast-db"),
    modal.Secret.from_name("genomic-ast-storage"),
]


@app.function(
    timeout=60 * 60,
    memory=8192,
    cpu=4,
    secrets=secrets,
)
def run_analysis(analysis_id: str) -> dict:
    import sys
    from pathlib import Path

    root = Path("/app")
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    os.environ.setdefault("COMPUTE_BACKEND", "local")
    os.environ.setdefault("REQUIRE_REAL_TOOLS", "true")
    os.environ.setdefault("ENABLE_DEMO_FALLBACK", "false")
    os.environ.setdefault("TOOL_EXECUTION_MODE", "real")
    os.environ.setdefault("RESFINDER_DB", "/opt/dbs/resfinder_db")
    os.environ.setdefault("POINTFINDER_DB", "/opt/dbs/pointfinder_db")
    os.environ.setdefault(
        "AMRFINDER_DB",
        f"/opt/dbs/amrfinder/{TOOL_PINNING.amrfinder_db_version}",
    )

    from services.pipeline import run_analysis_job

    run_analysis_job(analysis_id)
    return {"analysis_id": analysis_id, "status": "completed_dispatch"}
