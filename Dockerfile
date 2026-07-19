# Cloud Run image: NCBI AMRFinderPlus base + ResFinder/PointFinder + FastAPI.
# Base already contains pinned amrfinder 4.2.7 + DB 2026-05-15.1.
FROM ncbi/amr:4.2.7-2026-05-15.1

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RESFINDER_VERSION=4.7.2 \
    RESFINDER_DB_COMMIT=eecf0aa207594fe6d51badf808473de62b28cb06 \
    POINTFINDER_DB_COMMIT=44ce624a806c6d2b70f7e39841a5f9cb4d9010aa \
    RESFINDER_DB=/opt/dbs/resfinder_db \
    POINTFINDER_DB=/opt/dbs/pointfinder_db \
    AMRFINDER_DB=/opt/dbs/amrfinder/2026-05-15.1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:/usr/local/bin:/usr/bin:/bin" \
    HOME=/app

USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      wget \
      git \
      build-essential \
      zlib1g-dev \
      libcurl4-openssl-dev \
      python3 \
      python3-pip \
      python3-venv \
      ncbi-blast+ \
      hmmer \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip setuptools wheel

# KMA (required by ResFinder for indexing/reads)
WORKDIR /tmp
RUN git clone --depth 1 https://bitbucket.org/genomicepidemiology/kma.git \
    && make -C kma \
    && cp kma/kma kma/kma_index kma/kma_shm /usr/local/bin/ \
    && rm -rf kma

# ResFinder software
RUN pip install --no-cache-dir \
      "resfinder==${RESFINDER_VERSION}" \
      "cgelib>=0.7.3" \
      "cgecore==2.0.1" \
      "tabulate>=0.8.9" \
      "pandas>=1.4.2" \
      "biopython>=1.79"

# Pinned ResFinder / PointFinder databases
# INSTALL.py expects to be run with cwd == the DB directory (reads ./config).
RUN mkdir -p /opt/dbs \
    && git clone https://bitbucket.org/genomicepidemiology/resfinder_db.git ${RESFINDER_DB} \
    && git -C ${RESFINDER_DB} checkout ${RESFINDER_DB_COMMIT} \
    && (cd ${RESFINDER_DB} && python INSTALL.py /usr/local/bin/kma_index non_interactive) \
    && git clone https://bitbucket.org/genomicepidemiology/pointfinder_db.git ${POINTFINDER_DB} \
    && git -C ${POINTFINDER_DB} checkout ${POINTFINDER_DB_COMMIT} \
    && (cd ${POINTFINDER_DB} && python INSTALL.py /usr/local/bin/kma_index non_interactive)

# Resolve AMRFinder DB path from the NCBI base image into a stable symlink.
RUN set -eux; \
    if [ -d /usr/local/share/amrfinder/data/latest ]; then \
      DB=/usr/local/share/amrfinder/data/latest; \
    elif [ -d /amrfinder_database ]; then \
      DB=/amrfinder_database; \
    elif [ -d /usr/local/amrfinderplus/data/latest ]; then \
      DB=/usr/local/amrfinderplus/data/latest; \
    else \
      DB="$(find / -type d -name '2026-05-15.1' 2>/dev/null | head -n 1)"; \
    fi; \
    test -n "$DB"; \
    test -d "$DB"; \
    mkdir -p /opt/dbs/amrfinder; \
    ln -sfn "$DB" /opt/dbs/amrfinder/2026-05-15.1; \
    echo "AMRFINDER_DB_RESOLVED=$DB"; \
    command -v amrfinder; \
    amrfinder --database_version || true

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY . /app

RUN mkdir -p /app/data/uploads /tmp/genomic-ast-uploads \
    && chmod -R 777 /app/data /tmp/genomic-ast-uploads

EXPOSE 8080

CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
