# supOS-bedrock: Open Foundation for Industrial Tools

One-command installation for supOS ecosystem with web-based orchestration.

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Status](https://img.shields.io/badge/status-development-yellow.svg)]()

> [!warning]
> Not ready for production-use, only for development.

> [!important]
> This is a drop-in reimagining of [supOS-CE](https://github.com/FREEZONEX/supOS-CE).

## The Problem

Industry suffers from "data spaghetti"—legacy systems don't fit Industry 4.0 standards. Unified Namespace offers solutions through open tools, but fragmented deployment creates friction. Industry won't adopt scattered services that need separate maintenance.

**Why platforms win:** Linux and Nextcloud succeeded as foundations where apps live together. Complexity managed once, not per service.

**This project:** Makes supOS installation work like [Nextcloud All-in-One](https://github.com/nextcloud/all-in-one). Single command installs core, web UI manages lifecycle.

## Quick Start
```bash
docker run -d \
  --name supos-bedrock \
  --restart always \
  -p 8080:8080 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /volumes/supos/data:/volumes/supos/data \
  -e HOST_IPS="$(hostname -I)" \
  leekaize/supos-bedrock:latest
```

Then access through web browser: `http://YOUR_SERVER_IP:8080`

### Requirements
- Docker 20.10+
- 4GB RAM minimum
- Ports 8080 and 8088 available

## What it does

- **Setup wizard** → Zero terminal config, admin created via UI
- **Modular apps** → Install Grafana, MinIO, ELK and other optional apps post-deployment
- **Integrated app store** → Add capabilities without reinstall
- **One-click updates** → Version management from UI
- **Automated backups** → Database exports + config snapshots

### v0.1 Roadmap (Hackathon Submission)

- [x] Single Docker command to run on both amd64 & arm64
- [x] GUI for first-run setup and installation
  - [x] System Check: Verify and suggest actions on volume, IP/domain and port.
  - [x] Admin Account: Set custom username, password and email. Used for supOS frontend and keycloak.
  - [x] Select Apps: Optional containers can be installed through GUI.
  - [x] Installation Logs: Show stages of installation with detailed logs.
- [x] GUI for orchestrator interface
  - [x] Redirect to Keycloak for access
  - [x] Container version update recommendations
  - [x] Optional containers install/uninstall
  - [x] Backup/restore functionality

### v0.2 Roadmap (Get Ready for Production Use)

- [ ] Fix Bugs Listed in GitHub Issue
  - [ ] Implement proper disable/block for default admin, necessary for security.
- [ ] Full-featured Backup/Restore
  - [ ] Backup system/containers config
- [ ] supOS-bedrock container update
- [ ] Establish standards
  - [ ] APIs
  - [ ] Set of files needed for each containers
- [ ] Implement within supOS-frontend
  - [ ] Show update notifications through APIs
  - [ ] Access orchestrator through homepage menu

## Architecture

**What supOS-bedrock adds on top of supOS-CE:**

**Orchestrator Layer (New):**
- Docker-in-Docker: Mounts `/var/run/docker.sock` to control host Docker daemon
- Flask backend (Python 3.12): Generates dynamic Compose commands, streams installation logs via polling API
- React frontend (Node.js 20): Setup wizard, container management UI, version comparison
- Multi-stage build: Compiles React to static assets, embeds workspace (scripts, compose files, configs)

**Installation Workflow (Replaces manual steps):**
- Automated system checks: Volume paths, port availability, IP detection
- Dynamic profile selection: `--profile grafana`, `--profile minio`, `--profile elk` generated based on UI selections
- Non-interactive mode: `bin/install.sh --non-interactive` called by orchestrator with pre-configured `.env`
- Real-time log streaming: Frontend polls `/api/install/logs` every 2 seconds during installation

**Version Management (New):**
- `builds.yaml` manifest: Defines recommended versions for each service
- GitHub integration: Orchestrator fetches manifest on startup
- Update detection: Compares running container versions against manifest, surfaces in UI
- One-click updates: Executes `docker compose pull` + `up -d` for selected services

**Backup System (New):**
- Borg Backup integration: Incremental snapshots with compression
- Configurable paths: UI-driven backup directory selection
- Restore capability: Point-in-time recovery from snapshots

## Development

> [!important]
> Recommended to use or refer to automated tasks in `.vscode/`.

Run orchestrator locally:
```bash
cd orchestrator
pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..
python app.py
# Access http://localhost:8080
```

Build image:
```bash
docker build -t supos-bedrock:dev .
```

**Key files:**
- `orchestrator/routes/installation.py` - Installation workflow, log streaming
- `orchestrator/routes/containers.py` - Container management, updates
- `builds.yaml` - Version manifest
- `bin/install.sh` - Core installation (now supports `--non-interactive`)
- `docker-compose-xxxx.yml` - Service definitions with profiles
