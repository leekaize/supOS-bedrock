FROM node:20-alpine AS frontend-builder
WORKDIR /build
COPY orchestrator/frontend/package*.json ./
RUN npm install
COPY orchestrator/frontend/ ./
RUN npm run build

# ==================== PYTHON STAGE ====================
FROM python:3.12-slim
WORKDIR /app

# System dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl gettext xz-utils git gcc python3-dev borgbackup && \
    rm -rf /var/lib/apt/lists/*

# Docker CLI (architecture detection)
RUN ARCH=$(uname -m) && \
    if [ "$ARCH" = "aarch64" ]; then DOCKER_ARCH="aarch64"; else DOCKER_ARCH="x86_64"; fi && \
    curl -fsSLO https://download.docker.com/linux/static/stable/${DOCKER_ARCH}/docker-28.5.1.tgz && \
    tar xzvf docker-28.5.1.tgz --strip 1 -C /usr/local/bin docker/docker && \
    rm docker-28.5.1.tgz

# Docker Compose
RUN ARCH=$(uname -m) && \
    if [ "$ARCH" = "aarch64" ]; then COMPOSE_ARCH="aarch64"; else COMPOSE_ARCH="x86_64"; fi && \
    mkdir -p $HOME/.docker/cli-plugins && \
    curl -fsSL https://github.com/docker/compose/releases/download/v2.40.0/docker-compose-linux-${COMPOSE_ARCH} -o $HOME/.docker/cli-plugins/docker-compose && \
    chmod +x $HOME/.docker/cli-plugins/docker-compose

# Python dependencies
COPY orchestrator/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Flask application
COPY orchestrator/*.py .
COPY orchestrator/routes/ ./routes/

# Built React frontend
COPY --from=frontend-builder /build/dist/ /app/static/

# Embed workspace (scripts, compose files, configs)
COPY bin/ /workspace/bin/
COPY docker-compose-4c8g.yml docker-compose-8c16g.yml /workspace/
COPY mount/ /workspace/mount/
COPY builds.yaml /workspace/
COPY .env /workspace/

# Permissions and directories
RUN find /workspace/bin -type f -name "*.sh" -exec chmod +x {} \; && \
    mkdir -p /workspace/logs /app/config

# Set workspace environment
ENV SUPOS_WORKSPACE=/workspace

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/api/health || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "600", "--log-level", "info", "--access-logfile", "-", "--error-logfile", "-", "app:app"]
