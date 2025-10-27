# supOS-bedrock: Open Foundation for Industrial Platforms

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Status](https://img.shields.io/badge/status-development-yellow.svg)]()

> [!important]
> **This is a drop-in reimagining of [supOS-CE](https://github.com/FREEZONEX/supOS-CE).**
> Think Nextcloud AIO for industrial systems—install the core, choose your apps.

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

Then access through web browser: http://YOUR_SERVER_IP:8080

### Requirements
- Docker 20.10+
- 4GB RAM minimum
- Ports 8080 and 8088 available

### v0.1 Roadmap

- [x] Single Docker command to run on both amd64 & arm64
- [x] GUI for first-run setup and installation
  - [x] System Check: Verify and suggest actions on volume, IP/domain and port.
  - [ ] Admin Account: Set custom username, password and email. Used for supOS frontend and keycloak.
  - [ ] Select Apps: Optional containers can be installed through GUI.
  - [ ] Installation Logs: Show stages of installation with detailed logs.
- [ ] GUI for system update recommendations
- [ ] GUI for backup/restore

## What it does

- **Setup wizard** → Zero manual config. Admin created via UI.
- **Modular apps** → Install Grafana, MinIO, ELK post-deployment
- **Integrated app store** → Add capabilities without reinstall
- **One-click updates** → Version management from UI
- **Automated backups** → Database exports + config snapshots

**Philosophy:** Nextcloud did it for file sharing. We're doing it for industrial data.
