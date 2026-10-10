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
9. [Accessing the Web UI and Obsidian](#accessing-the-web-ui-and-obsidian)
10. [CI/CD — Scheduled Ingest](#cicd--scheduled-ingest)
11. [Configuration](#configuration)
12. [File Permissions on Linux Hosts](#file-permissions-on-linux-hosts)
13. [Export, Backup, and Restore Paths](#export-backup-and-restore-paths)
14. [Security](#security)
15. [Maintenance](#maintenance)
16. [Local Build and Test (Windows)](#local-build-and-test-windows)
17. [Troubleshooting](#troubleshooting)

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

For personal use, `pip install synthadoc` is the simpler path — but Docker still adds value: the container is fully isolated from your OS, Python environment, and system libraries. Only the mounted wiki folder is shared with the host. If isolation and a clean sandbox matter to you (especially on Windows, where Python environment conflicts are common), Docker is a reasonable personal choice too.

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
# -p HOST_PORT:7070  — 7070 is fixed inside the container; HOST_PORT is what you choose.
# Use 7070:7070 to keep the same port, or e.g. 7071:7070 to avoid conflicts.
docker run -d \
  --name my-wiki \
  -v ~/wikis/my-wiki:/wiki \
  -p 7070:7070 \
  --env-file .env \
  chenp/synthadoc:latest
```

The server starts in default mode — HTTP API, Web UI (`/app`), and MCP over HTTP (`/mcp`) are all available on the same port. Point your Obsidian plugin at `http://localhost:7070`.

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
docker compose exec sd-server synthadoc ingest raw_sources/report.pdf
```

### Multiple wikis

```bash
docker compose -f docker/compose/multi-wiki.yml up -d
# Wiki A: http://localhost:7070
# Wiki B: http://localhost:7071
```

Set `WIKI_A_PATH` and `WIKI_B_PATH` in your `.env` file alongside your API key:

```bash
# .env
ANTHROPIC_API_KEY=sk-ant-...

# Absolute paths to each wiki folder on the host
WIKI_A_PATH=/home/yourname/wikis/finance-wiki
WIKI_B_PATH=/home/yourname/wikis/legal-wiki
```

On Windows (inside WSL): use the WSL filesystem path (e.g. `/home/yourname/wikis/...`), not the Windows drive path (`/mnt/c/Users/...`).

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
base_url = "http://ollama:11434"
```

---

## Running CLI Commands Inside the Container

Any `synthadoc` CLI command can be run inside the container. Two things are
pre-configured so commands work without extra flags:

- **`SYNTHADOC_WIKI=/wiki`** is set in the image — the `-w` flag is not needed.
- **`WORKDIR /wiki`** is set in the image — relative paths like `raw_sources/report.pdf`
  resolve to `/wiki/raw_sources/report.pdf` automatically. Use the absolute path
  `/wiki/raw_sources/report.pdf` if you prefer to be explicit.

> **Why `--wait` matters in `docker exec`**
>
> Many `synthadoc` commands (lint, scaffold, workflow) queue a background job
> on the server and return immediately. Without `--wait`, `docker exec` exits
> right after queuing — before the job finishes — and you see no results.
> Add `--wait` to keep the process alive until the job completes.

All examples below use `docker exec <container-name>`, which works regardless
of how the container was started. The container name is whatever you passed to
`--name` in `docker run`, or the `container_name:` in your Compose file
(e.g. `synthadoc-wiki`).

If you are using Docker Compose, you can also address the container by its
**service name** using `docker compose exec <service-name>` — for example,
`docker compose exec sd-server synthadoc query "..."`. Either form works;
`docker exec` is shown here because it is universal.

### Querying the wiki

```bash
# Ask a question — streams the answer token by token
docker exec my-wiki synthadoc query "What are the key findings in Q3 report?"

# Force a fresh LLM call (skip the query cache)
docker exec my-wiki synthadoc query "What changed in the last audit?" --no-cache
```

### Cross-wiki queries (multi-wiki Compose only)

In the multi-wiki Compose setup, each wiki runs in its own container on the
same Docker network. If you configure cross-wiki routing in one wiki's
`CROSS_WIKI_ROUTING.md` to reference the other container by its service name
(e.g. `http://sd-server-b:7070`), you can fan out a single query across both.
This uses `docker compose exec` because Docker Compose service-name DNS
(`sd-server-b`) is only available inside the Compose network:

```bash
# Query wiki-a — fans out to wiki-b automatically via Docker internal network
docker compose -f docker/compose/multi-wiki.yml exec sd-server-a \
  synthadoc query "Total revenue across all entities?" --cross-wiki

# Scaffold the routing table for wiki-a
docker compose -f docker/compose/multi-wiki.yml exec sd-server-a \
  synthadoc cross-wiki routing init
```

### Ingesting content

```bash
# Ingest a single file (relative path resolves from /wiki/)
docker exec my-wiki synthadoc ingest raw_sources/report.pdf

# Batch-ingest an entire folder
docker exec my-wiki synthadoc ingest raw_sources/ --batch

# Ingest a URL
docker exec my-wiki synthadoc ingest https://example.com/article

# Ingest via web search (Tavily) — requires TAVILY_API_KEY in container env
docker exec my-wiki synthadoc ingest "search for: IFRS 17 insurance contract accounting"

# Watch job progress after queuing (ingest returns immediately)
docker exec my-wiki synthadoc jobs list --limit 5
```

### Linting

```bash
# Enqueue lint and wait for completion (--wait keeps docker exec alive)
docker exec my-wiki synthadoc lint run --wait

# Show lint report (contradictions, orphan pages, adversarial findings)
docker exec my-wiki synthadoc lint report

# Lint with URL source availability check
docker exec my-wiki synthadoc lint run --check-urls --wait
```

### Agentic workflows

```bash
# List all available workflows
docker exec my-wiki synthadoc workflow list

# Re-ingest all stale pages (agentic loop, streams progress)
docker exec my-wiki synthadoc workflow run --name ingest-lint

# Run the contradiction resolver (interactive — approves rewrites one by one)
docker exec -it my-wiki synthadoc workflow run --name contradiction-resolver

# Scan and fix broken wikilinks
docker exec my-wiki synthadoc workflow run --name broken-wikilinks
```

### Scaffold

```bash
# Regenerate index.md, AGENTS.md, and purpose.md using the LLM
# (queues a background job; monitor with jobs list)
docker exec my-wiki synthadoc scaffold
docker exec my-wiki synthadoc jobs list --limit 5
```

### Lifecycle (promote, archive, restore)

Pages start as `draft`. Use `lifecycle activate` to promote a reviewed page
to `active`, or `lifecycle archive` to retire it.

```bash
# Promote a draft page to active
docker exec my-wiki synthadoc lifecycle activate quarterly-report-q3 \
  --reason "Reviewed and approved"

# Archive a superseded page
docker exec my-wiki synthadoc lifecycle archive old-market-analysis \
  --reason "Superseded by 2026 report"

# Restore an archived page back to draft
docker exec my-wiki synthadoc lifecycle restore old-market-analysis \
  --reason "Needed for comparison"

# Show full lifecycle event log
docker exec my-wiki synthadoc lifecycle log

# Show lifecycle history for one page
docker exec my-wiki synthadoc lifecycle history quarterly-report-q3
```

### Scheduled jobs

```bash
# List all registered scheduled jobs
docker exec my-wiki synthadoc schedule list

# Schedule a nightly lint (cron: 2 AM every day)
docker exec my-wiki synthadoc schedule add \
  --op "lint run" --cron "0 2 * * *"

# Apply schedules declared in config.toml [schedule] blocks
docker exec my-wiki synthadoc schedule apply
```

### Monitoring and audit

```bash
# Show all recent jobs
docker exec my-wiki synthadoc jobs list --limit 20

# Server health and version
docker exec my-wiki synthadoc status

# Ingest cost and history
docker exec my-wiki synthadoc audit history

# Backup the wiki to a zip file (lands in the mounted /wiki folder)
docker exec my-wiki synthadoc backup
```

---

## Accessing the Web UI and Obsidian

Both interfaces are available automatically the moment the container starts — no extra steps or flags needed.

### Web UI

The HTTP server the container runs also serves the Web UI. Open it in any browser using the **host port** (the left side of `-p HOST:7070`):

The **host port** (the left side of `-p HOST:7070`) is the single point of contact for every client outside the container. The internal port `7070` is only used by processes inside the container itself (e.g. the HEALTHCHECK):

| Client | URL pattern |
|---|---|
| Browser (Web UI) | `http://localhost:<host-port>/app` |
| Obsidian plugin (Server URL) | `http://localhost:<host-port>` |
| MCP client | `http://localhost:<host-port>/mcp` |
| Health check / scripts | `http://localhost:<host-port>/health` |

Examples with different port mappings:

| docker run flag | All clients use |
|---|---|
| `-p 7070:7070` | `http://localhost:7070` |
| `-p 7099:7070` | `http://localhost:7099` |
| `-p 8080:7070` | `http://localhost:8080` |

For a team or remote server, replace `localhost` with the server's IP or hostname:
```
http://192.168.1.50:7070/app        # Web UI
http://192.168.1.50:7070/mcp        # MCP client
```

### Obsidian Plugin

Obsidian makes two independent connections — one to the wiki files, one to the server API:

**1 — Open the wiki folder in Obsidian**
Open the wiki folder from the host filesystem (e.g. `~/wikis/my-wiki`) as an Obsidian vault. The volume mount means the wiki files exist on the host and inside the container at `/wiki` simultaneously — Obsidian reads the host path directly, no difference from non-Docker use.

**2 — Point the plugin at the container**
In Obsidian → Settings → Synthadoc plugin → Server URL, set it to the host port:
```
http://localhost:7070
```
The plugin talks to the container's HTTP API exactly as it would to a locally running synthadoc process.

### MCP Client

Point your MCP client (Claude Desktop, Claude Code, etc.) at the host port:
```
http://localhost:<host-port>/mcp
```
No change to how MCP is configured — just substitute the host port for whatever you would use locally.

> **Note:** The container serves HTTP, Web UI, and MCP over HTTP (`/mcp`) all on the same port — no extra configuration needed. MCP stdio is not used in Docker (it requires a direct process connection). If you want to disable the `/mcp` endpoint, override the CMD with `--http-only`.

### Team deployments

On a shared server, the Web UI (`http://<server>:<port>/app`) becomes the primary interface for teammates who don't have Obsidian set up locally. The wiki owner can still use Obsidian locally by mounting the same wiki folder and pointing the plugin at the remote server URL.

---

## CI/CD — Scheduled Ingest

See `docker/examples/github-actions-ingest.yml` for a complete GitHub Actions workflow that runs daily batch ingest and lint against a running container on a self-hosted runner.

Key pattern:

```yaml
- name: Trigger batch ingest
  run: |
    # No -w needed — the container sets SYNTHADOC_WIKI=/wiki automatically
    docker exec synthadoc-wiki synthadoc ingest raw_sources/ --batch
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

> **macOS / Windows:** Docker Desktop maps file ownership transparently through
> its virtual machine layer. This section does not apply to those platforms.

The container process runs as **uid 1000** (an internal user named `synthadoc`).
Docker maps uids numerically — it does not look up user names — so the container
can write to a host directory only if the directory's owner uid matches the
process uid (1000).

**You do not need to create any user account on your host.** The fix is purely
about which uid owns the directory.

### Step 1 — Check your host uid

```bash
id -u    # prints your numeric user id, e.g. 1000 or 1001
```

### Step 2 — Pick the right fix

**Your host uid is already 1000** (the first user on most Linux systems):

No action needed. The container's uid 1000 and your uid 1000 match — Docker
mounts the directory and both sides can read and write it without any changes.

**Your host uid is NOT 1000:**

Option A — tell Docker to run the container as your uid (recommended, no sudo):

```bash
docker run -d \
  --user $(id -u):$(id -g) \
  -v ~/wikis/my-wiki:/wiki \
  -p 7070:7070 \
  --env-file .env \
  chenp/synthadoc:latest
```

In Docker Compose, add a `user` key to the service:

```yaml
services:
  sd-server:
    image: chenp/synthadoc:latest
    user: "1001:1001"   # replace with your uid:gid from `id -u` / `id -g`
    ...
```

Option B — change the host directory ownership to uid 1000 (requires sudo):

```bash
sudo chown -R 1000:1000 ~/wikis/my-wiki
```

This permanently assigns the directory to uid 1000. Useful on servers where you
always want containers to own the wiki data and your personal account is a
separate uid for administration only.

---

## Export, Backup, and Restore Paths

The container's only persistent storage is the `/wiki` mount. Any file written
**outside** `/wiki` goes into the container's ephemeral overlay filesystem:
it is invisible to your host, and is permanently lost when the container is
removed (`docker rm`). No error is reported — the command appears to succeed.

The image sets `WORKDIR /wiki`, so **relative paths and the default `.` all
resolve inside `/wiki/`** — which means the safe defaults work without extra flags.

### Backup

```bash
# Default (--output ".") writes the zip to /wiki/ → visible on host
docker exec my-wiki synthadoc backup

# Explicit subdirectory — also fine
docker exec my-wiki synthadoc backup --output /wiki/backups/
```

Avoid absolute host-style paths (`--output ~/backups/`): `~` expands to
`/home/synthadoc/` inside the container, not your home directory on the host.

### Restore

The zip file must be reachable inside the container. The easiest way is to
copy it into the mounted wiki directory first:

```bash
# On the host — copy the zip into the wiki mount
cp ~/downloads/synthadoc-backup-my-wiki-20261010.zip ~/wikis/my-wiki/

# Inside the container — restore from /wiki/ (default target is zip's parent = /wiki/)
docker exec -it my-wiki synthadoc restore /wiki/synthadoc-backup-my-wiki-20261010.zip
```

Alternatively, use `docker cp` to push the file directly into the container:

```bash
docker cp ~/downloads/synthadoc-backup-my-wiki-20261010.zip my-wiki:/wiki/
docker exec -it my-wiki synthadoc restore /wiki/synthadoc-backup-my-wiki-20261010.zip
```

### Export (CLI)

For formats that print to stdout (`json`, `llms.txt`, `llms-full.txt`,
`graphml`), redirect on the host side — no path issue:

```bash
docker exec my-wiki synthadoc export --format llms.txt > ~/wiki-export.txt
docker exec my-wiki synthadoc export --format json     > ~/wiki-export.json
```

For **OKF**, the CLI writes a directory tree to `--output`. Use a path inside
`/wiki/` so it lands on the host:

```bash
# Writes to /wiki/exports/<wiki>-okf-<date>/ → visible on host
docker exec my-wiki synthadoc export --format okf --output /wiki/exports/
```

> **Obsidian plugin OKF export does not have this limitation.** When you
> trigger the export from the Obsidian UI, the plugin fetches the manifest
> from the server and then writes files using **Obsidian's own filesystem API
> on your host machine**. The default path (`~/exports/…`) resolves on your
> host, not inside the container. No special Docker configuration is needed.

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
docker exec my-wiki synthadoc backup
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

The `Dockerfile` lives at the **repo root** — the top-level `synthadoc/` folder,
not the `docker/` subfolder (which only contains Compose files and examples).
Run the build from that directory:

```bash
# In PowerShell or WSL, cd to the repo root first
cd path/to/synthadoc   # e.g. C:\Users\you\Documents\my_workspace\synthadoc

docker build -t synthadoc:local .
```

The trailing `.` tells Docker to use the current directory as the build context
(where it reads the `Dockerfile` and packages source files).

The first build takes a few minutes (downloads `python:3.12-slim` and installs synthadoc). Subsequent builds are faster due to layer caching.

> **Local vs. production builds:** A local `docker build` installs synthadoc directly from your source tree, so it picks up any unreleased changes. The production CI build passes `--build-arg SYNTHADOC_VERSION=X.Y.Z` to install the exact release from PyPI instead, and it runs only after the PyPI publish workflow completes — so there is no race between the two.

Expected output (Docker BuildKit format):
```
[+] Building XX.Xs (13/13) FINISHED
 ...
 => => naming to docker.io/library/synthadoc:local
 => => unpacking to docker.io/library/synthadoc:local
```

If you see `(N/N) FINISHED` at the top and no `ERROR` lines, the image built successfully.

### Step 3 — Create a test wiki

You need a wiki on disk for the container to mount. If you already have one, skip this. Otherwise install the built-in demo:

```bash
synthadoc install history-of-computing --target ~/wikis --demo
```

This creates `~/wikis/history-of-computing/` pre-populated with demo content, so you have real pages to query straight away.

### Step 4 — Create a .env file

```bash
# ~/wikis/.env  (keep outside the wiki folder)
ANTHROPIC_API_KEY=sk-ant-...
TAVILY_API_KEY=tvly-...   # optional
```

### Step 5 — Run the container

**cmd.exe** (single line — backslash continuation does not work in cmd):

```
docker run -d --name synthadoc-test -v "%USERPROFILE%/wikis/history-of-computing:/wiki" -p 7099:7070 --env-file "%USERPROFILE%/wikis/.env" synthadoc:local
```

**WSL bash** (backslash continuation works here):

```bash
docker run -d \
  --name synthadoc-test \
  -v ~/wikis/history-of-computing:/wiki \
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

# Ingest it from inside the container (no -w needed — SYNTHADOC_WIKI=/wiki is set)
docker exec synthadoc-test synthadoc ingest raw_sources/docker-test.txt

# Check the job completed
docker exec synthadoc-test synthadoc jobs list --limit 5
```

### Step 8 — Tear down

```bash
docker stop synthadoc-test
docker rm synthadoc-test
```

The wiki files on the host are untouched — only the container is removed.

### Step 9 — Rebuild after a source change

When you change the Python source and want to test it in Docker, remove the
old container, rebuild the image from the repo root, then re-run Step 5:

**cmd.exe:**
```
docker rm -f synthadoc-test
cd C:\Users\ladmin\Documents\my_workspace\synthadoc
docker build -t synthadoc:local .
```

**WSL bash:**
```bash
docker rm -f synthadoc-test
cd ~/path/to/synthadoc
docker build -t synthadoc:local .
```

The local build installs synthadoc from your source tree, so it always
reflects your latest changes. Layer caching means only the layers after
the source copy are re-run — typically just the `pip install` step.

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
