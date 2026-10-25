# Base-Image per Digest gepinnt (python:3.12-slim, Stand 2026-10-24, gleicher Stand wie
# zammad-mcp), damit ein Build reproduzierbar ist. Aktualisieren: neuen Digest mit
#   docker buildx imagetools inspect python:3.12-slim
# ermitteln und hier eintragen.
FROM python:3.12-slim@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY pyproject.toml README.md ./
COPY wordpressmcp ./wordpressmcp
RUN pip install --no-cache-dir --no-deps . && mkdir -p /data && chown 1000:1000 /data

# Git-Commit und Version des Builds (von GitHub Actions gesetzt), get_version gibt beides zurück.
ARG GIT_SHA=unknown
ARG APP_VERSION=
ENV GIT_SHA=$GIT_SHA \
    APP_VERSION=$APP_VERSION \
    DATABASE_PATH=/data/wordpressmcp.sqlite3 \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8000 \
    PYTHONUNBUFFERED=1

# Kein root: die Word-Konvertierung verarbeitet Dateien von Dritten.
USER 1000:1000
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s CMD python -c "import os,urllib.request,urllib.parse;u=urllib.parse.urlparse(os.environ['PUBLIC_BASE_URL']);urllib.request.urlopen('http://127.0.0.1:8000'+u.path.rstrip('/')+'/healthz',timeout=4)" || exit 1

CMD ["wordpressmcp", "api"]
