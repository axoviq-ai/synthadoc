# Synthadoc Docker Deployment Guide

## Table of Contents

1. [Why Docker](#why-docker)
2. [Architecture](#architecture)
3. [Prerequisites](#prerequisites)
4. [API Key Setup](#api-key-setup)
5. [Quick Start](#quick-start)
6. [Platform-Native Runtimes](#platform-native-runtimes)
7. [Docker Compose](#docker-compose)
8. [Running CLI Commands Inside the Container](#running-cli-commands-inside-the-container)
9. [CI/CD — Scheduled Ingest](#cicd--scheduled-ingest)
10. [Configuration](#configuration)
11. [File Permissions on Linux Hosts](#file-permissions-on-linux-hosts)
12. [Security](#security)
13. [Maintenance](#maintenance)
14. [Local Build and Test (Windows)](#local-build-and-test-windows)
15. [Troubleshooting](#troubleshooting)

---

## Why Docker

`pip install synthadoc` is the recommended path for personal, single-machine use. Docker is the right choice when you need to go beyond that:

| Use case | Why Docker helps |
|---|---|
| **Team / shared server** | One wiki instance on a server that teammates reach over the network — no per-user Python environment required |
| **CI/CD pipelines** | Reproducible runtime for scheduled ingest, lint, and lifecycle jobs in GitHub Actions, GitLab CI, or any OCI-compatible runner |
| **Windows isolation** | Avoids Python path and encoding edge cases; the container is always Linux regardless of the host OS |
| **Reproducible deployments** | Pinned image tag guarantees the same runtime version across dev, staging, and production |
| **Sidecar LLM (Ollama)** | Run Synthadoc alongside a local Ollama instance in one Compose stack — no cloud API key needed |

Docker does **not** replace `pip install` for personal use — it adds no benefit there and adds operational overhead.

---

## Architecture

```
Host machine
├── ~/wikis/my-wiki/          ← wiki files live here (Obsidian reads these directly)
│   ├── .synthadoc/
│   │   ├── config.toml
│   │   └── synthadoc.db
│   ├── raw_sources/
│   └── pages/
│
└── Docker container (synthadoc:latest)
    ├── /wiki  →  bind-mounted from ~/wikis/my-wiki
    ├── port 7070  →  mapped to host port of your choice
    └── synthadoc serve -w /wiki --host 0.0.0.0
```

**Design decisions:**

- **One wiki per container** — matches the one-process/one-port model; run multiple containers on different host ports for multiple wikis
- **Wiki files on the host** — the container mounts the wiki as a volume, so Obsidian and other tools access the files normally without going through the container
- **No registry inside the container** — the server always starts with an explicit `-w /wiki` path; the synthadoc registry is not used
- **Fixed internal port 7070** — the container always listens on 7070; map it to any host port you like (`-p 7071:7070`, `-p 8080:7070`, etc.)
- **API keys via environment variables only** — never baked into the image
- **Non-root user** — the container runs as uid 1000 (`synthadoc`) for standard container hardening

---

## Prerequisites

| Platform | Runtime | Requirement |
|---|---|---|
| **Linux** | Docker Engine | Standard `docker` install — [docs.docker.com/engine/install](https://docs.docker.com/engine/install/) |
| **macOS (Apple Silicon)** | Apple `container` (built-in) | macOS 26 (Tahoe)+, M1 or later — no install needed |
| **macOS (Apple Silicon)** | Docker Desktop | Alternative if macOS < 26 |
| **macOS (Intel)** | Docker Desktop | Required — Apple's `container` tool does not support Intel. Affects Mac Pro 2019, MacBook Air/Pro pre-2020, iMac pre-2021 |
| **Windows** | WSL Containers (`wslc`) | Windows 11, WSL 2.9.3+ — no install needed |
| **Windows** | Docker Desktop | Alternative, or required for Docker Compose |

All runtimes use the same OCI image — no separate image per platform.

---

## API Key Setup

Create a `.env` file (add it to `.gitignore` — **never commit it**):

```bash
# .env

# LLM provider — exactly one required
ANTHROPIC_API_KEY=sk-ant-...
# OPENAI_API_KEY=sk-...
# GEMINI_API_KEY=AI...
# GROQ_API_KEY=gsk_...

# Web search — optional, enables "search for:" ingest jobs
TAVILY_API_KEY=tvly-...
```

Pass it to the container with `--env-file .env`. This keeps keys out of shell history and out of `docker inspect` output. **Do not use `-e KEY=value` on the command line** — the value ends up in shell history and is visible to anyone with Docker access on the host.

For Docker Compose, place the `.env` file in the same directory as your Compose file — Compose picks it up automatically, no extra flags needed.

---

## Quick Start

```bash
# Pull the latest image
docker pull chenp/synthadoc:latest

# Run a wiki
docker run -d \
  --name my-wiki \
  -v ~/wikis/my-wiki:/wiki \
  -p 7070:7070 \
  --env-file .env \
  chenp/synthadoc:latest
```

The server starts in HTTP-only mode. Point your Obsidian plugin at `http://localhost:7070`.

Check that it is running:

```bash
docker ps
curl http://localhost:7070/health
```

Stop and remove:

```bash
docker stop my-wiki && docker rm my-wiki
```

---

## Platform-Native Runtimes

### macOS 26+ (Apple Silicon — M1 or later)

Apple's built-in `container` tool ships with macOS 26 (Tahoe) and runs OCI images without Docker Desktop. Replace `docker` with `container`:

```bash
container run -d \
  --name my-wiki \
  -v ~/wikis/my-wiki:/wiki \
  -p 7070:7070 \
  --env-file .env \
  chenp/synthadoc:latest
```

> **Intel Macs (Mac Pro 2019, MacBook Air/Pro pre-2020):** Apple's `container` tool requires Apple Silicon. Use Docker Desktop on Intel hardware.

### Windows 11 (WSL 2.9.3+)

WSL Containers (`wslc`) ship with WSL 2.9.3+ on Windows 11. Run inside WSL:

```bash
wslc run -d \
  --name my-wiki \
  -v ~/wikis/my-wiki:/wiki \
  -p 7070:7070 \
  --env-file .env \
  chenp/synthadoc:latest
```

> **Windows performance tip:** keep your wiki folder inside the WSL2 filesystem (e.g. `/home/yourname/wikis/my-wiki`) rather than on the Windows drive (`/mnt/c/Users/...`). Volume mounts from the Windows drive are significantly slower for file-heavy operations like ingest.

> **Docker Compose** is not yet supported by `wslc`. Use Docker Desktop if you need Compose.

---

## Docker Compose

Compose files are in `docker/compose/` in the repo. Copy and customise the one that fits your setup. Requires Docker Desktop on Windows and macOS (the platform-native tools do not support Compose yet).

### Single wiki

```bash
cp docker/compose/single-wiki.yml docker-compose.yml
# Edit WIKI_PATH in docker-compose.yml or set it in .env
docker compose up -d
```

Access at `http://localhost:7070`.

Run a CLI command inside the running container:

```bash
docker compose exec sd-server synthadoc ingest raw_sources/report.pdf -w /wiki
```

### Multiple wikis

```bash
docker compose -f docker/compose/multi-wiki.yml up -d
# Wiki A: http://localhost:7070
# Wiki B: http://localhost:7071
```

Set `WIKI_A_PATH` and `WIKI_B_PATH` in your `.env` file.

### Local LLM with Ollama (no cloud API key)

```bash
docker compose -f docker/compose/with-ollama.yml up -d

# Pull a model into Ollama
docker compose -f docker/compose/with-ollama.yml exec ollama ollama pull llama3.2
```

Then configure the wiki's `config.toml`:

```toml
[agents.default]
provider = "ollama"
model = "llama3.2"

[agents.ollama]
base_url = "http://ollama:11434"
```

---

## Running CLI Commands Inside the Container

Any `synthadoc` CLI command can be run inside the container. The wiki is at `/wiki`.

```bash
# Ingest a file from raw_sources/
docker exec my-wiki synthadoc ingest raw_sources/report.pdf -w /wiki

# Run lint on all pages
docker exec my-wiki synthadoc lint run -w /wiki --wait

# List recent jobs
docker exec my-wiki synthadoc jobs list -w /wiki --limit 20

# Check server health
docker exec my-wiki synthadoc status -w /wiki
```

For Compose deployments, use `docker compose exec sd-server` in place of `docker exec my-wiki`.

---

## CI/CD — Scheduled Ingest

See `docker/examples/github-actions-ingest.yml` for a complete GitHub Actions workflow that runs daily batch ingest and lint against a running container on a self-hosted runner.

Key pattern:

```yaml
- name: Trigger batch ingest
  run: |
    docker exec synthadoc-wiki \
      synthadoc ingest raw_sources/ --batch -w /wiki
```

The container must already be running on the runner host (started by your Compose stack or a systemd/launchd service).

---

## Configuration

Synthadoc reads its configuration from `.synthadoc/config.toml` inside the wiki directory. Because the wiki is mounted as a volume, you edit this file on the host — no need to rebuild or restart the image.

```toml
# ~/wikis/my-wiki/.synthadoc/config.toml

[server]
port = 7070          # internal port — always 7070 inside the container
host = "0.0.0.0"     # set by --host flag in CMD; do not change here

[agents.default]
provider = "anthropic"
model = "claude-opus-4-6"
```

To change the provider, edit `config.toml` and restart the container:

```bash
docker restart my-wiki
```

Or pass `--provider` at runtime without editing the file:

```bash
docker run ... chenp/synthadoc:latest \
  synthadoc serve -w /wiki --host 0.0.0.0 --http-only --provider openai
```

---

## File Permissions on Linux Hosts

The container runs as uid 1000 (`synthadoc`). If your host wiki directory is owned by a different uid, the container cannot write to it and ingest jobs will fail with permission errors.

Fix by passing your host uid/gid at run time:

```bash
docker run -d \
  --user $(id -u):$(id -g) \
  -v ~/wikis/my-wiki:/wiki \
  -p 7070:7070 \
  --env-file .env \
  chenp/synthadoc:latest
```

Or pre-set the ownership on the host:

```bash
sudo chown -R 1000:1000 ~/wikis/my-wiki
```

---

## Security

Synthadoc has **no built-in authentication**. For localhost-only use this is fine. For any deployment reachable beyond localhost:

- Put a reverse proxy (nginx, Traefik, Caddy) with TLS and basic auth in front of the container
- Restrict the mapped port to a specific interface: `-p 127.0.0.1:7070:7070` binds only to localhost even if the container listens on `0.0.0.0`
- On team servers, use a VPN or SSH tunnel rather than exposing the port directly

**API keys:** always use `--env-file .env`, never `-e KEY=value` on the command line. Store the `.env` file with restricted permissions (`chmod 600 .env`).

---

## Maintenance

### Updating the image

```bash
docker pull chenp/synthadoc:latest
docker stop my-wiki && docker rm my-wiki
# Re-run the same docker run command as before
docker run -d --name my-wiki ...
```

Wiki data is safe — it lives in the host volume, not inside the container.

### Viewing logs

```bash
# Live logs
docker logs -f my-wiki

# Last 100 lines
docker logs --tail 100 my-wiki
```

Synthadoc also writes structured logs to `.synthadoc/logs/` inside the wiki directory on the host.

### Backup

Back up the wiki directory on the host as you would any directory:

```bash
tar -czf my-wiki-backup-$(date +%Y%m%d).tar.gz ~/wikis/my-wiki/
```

Or use the built-in backup command from inside the container:

```bash
docker exec my-wiki synthadoc backup -w /wiki
# The .zip lands in ~/wikis/my-wiki/ on the host
```

### Health check

The image includes a HEALTHCHECK that polls `/health` every 30 seconds. View status:

```bash
docker inspect --format='{{.State.Health.Status}}' my-wiki
# healthy | starting | unhealthy
```

### Pinning a version

For production deployments, pin to a specific release tag instead of `latest`:

```bash
docker pull chenp/synthadoc:1.3.3
docker run ... chenp/synthadoc:1.3.3
```

---

## Local Build and Test (Windows)

Use this when you want to verify the Dockerfile works before publishing a release.
Building images requires **Docker Desktop** — `wslc` is runtime-only and cannot build.

### Step 1 — Install Docker Desktop

1. Download from [docs.docker.com/desktop/install/windows-install](https://docs.docker.com/desktop/install/windows-install/)
2. Run the installer — it uses your existing WSL2 backend automatically
3. After install, open a new terminal and verify:

```bash
docker --version
docker buildx version
```

### Step 2 — Build the image from source

From the repo root (where `Dockerfile` lives):

```bash
docker build -t synthadoc:local .
```

The first build takes a few minutes (downloads `python:3.12-slim` and installs synthadoc from PyPI). Subsequent builds are faster due to layer caching.

Expected output ends with:
```
Successfully built <image-id>
Successfully tagged synthadoc:local
```

### Step 3 — Create a test wiki

You need a wiki on disk for the container to mount. If you already have one, skip this. Otherwise create a minimal one:

```bash
synthadoc install test-docker-wiki --target ~/wikis
```

This creates `~/wikis/test-docker-wiki/` with the wiki structure.

### Step 4 — Create a .env file

```bash
# ~/wikis/.env  (keep outside the wiki folder)
ANTHROPIC_API_KEY=sk-ant-...
# TAVILY_API_KEY=tvly-...   # optional
```

### Step 5 — Run the container

```bash
docker run -d \
  --name synthadoc-test \
  -v ~/wikis/test-docker-wiki:/wiki \
  -p 7099:7070 \
  --env-file ~/wikis/.env \
  synthadoc:local
```

Using port `7099` (instead of `7070`) avoids conflicting with any locally running synthadoc instance.

### Step 6 — Verify it started

```bash
# Check the container is running
docker ps

# Check startup logs
docker logs synthadoc-test

# Hit the health endpoint
curl http://localhost:7099/health
```

Expected response:
```json
{"status": "ok", ...}
```

### Step 7 — Run a quick ingest test

```bash
# Drop a small test file into raw_sources on the host
echo "Synthadoc Docker test document." > ~/wikis/test-docker-wiki/raw_sources/docker-test.txt

# Ingest it from inside the container
docker exec synthadoc-test synthadoc ingest raw_sources/docker-test.txt -w /wiki

# Check the job completed
docker exec synthadoc-test synthadoc jobs list -w /wiki --limit 5
```

### Step 8 — Tear down

```bash
docker stop synthadoc-test
docker rm synthadoc-test
```

The wiki files on the host (`~/wikis/test-docker-wiki/`) are untouched — only the container is removed.

---

## Troubleshooting

**Container exits immediately**

```bash
docker logs my-wiki
```

Common causes: missing API key (`ANTHROPIC_API_KEY` not set), wiki path does not exist at `/wiki`, or port 7070 already in use on the host.

**Permission denied on wiki files**

The container user (uid 1000) cannot write to the mounted directory. See [File Permissions on Linux Hosts](#file-permissions-on-linux-hosts).

**Port already in use**

Map to a different host port: `-p 7071:7070`.

**Health check shows `unhealthy`**

```bash
docker logs my-wiki        # check for startup errors
curl http://localhost:7070/health
```

If the server started but `/health` does not respond, the wiki may have failed validation (e.g. corrupted database). Check the logs and try `synthadoc status -w /wiki` inside the container.

**`wslc` or `container` command not found**

- `container`: requires macOS 26 (Tahoe) on Apple Silicon. Not available on Intel Macs or macOS < 26.
- `wslc`: requires WSL 2.9.3+ on Windows 11. Update WSL: `wsl --update`.

**Slow file operations on Windows**

Move the wiki folder from the Windows drive into the WSL2 filesystem. See the [Windows performance tip](#windows-11-wsl-293) above.
