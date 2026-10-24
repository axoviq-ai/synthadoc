# Synthadoc Docker Deployment Guide

## Table of Contents

1. [Why Docker](#why-docker)
2. [Architecture](#architecture)
3. [Prerequisites](#prerequisites)
4. [API Key Setup](#api-key-setup)
5. [Quick Start](#quick-start)
6. [Running CLI Commands Inside the Container](#running-cli-commands-inside-the-container)
7. [Accessing the Web UI and Obsidian](#accessing-the-web-ui-and-obsidian)
8. [Configuration](#configuration)
9. [Maintenance](#maintenance)

**Appendix**

- [A. Platform-Native Runtimes](#a-platform-native-runtimes)
- [B. Docker Compose](#b-docker-compose)
- [C. CI/CD — Scheduled Ingest](#c-cicd--scheduled-ingest)
- [D. File Permissions on Linux Hosts](#d-file-permissions-on-linux-hosts)
- [E. Export, Backup, and Restore Paths](#e-export-backup-and-restore-paths)
- [F. Security](#f-security)
- [G. Local Build and Test (Windows)](#g-local-build-and-test-windows)
- [H. Troubleshooting](#h-troubleshooting)

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
├── ~/wikis/history-of-computing/          ← wiki files live here (Obsidian reads these directly)
│   ├── .synthadoc/
│   │   ├── config.toml
│   │   └── synthadoc.db
│   ├── raw_sources/
│   └── pages/
│
└── Docker container (synthadoc:latest)
    ├── /wiki  →  bind-mounted from ~/wikis/history-of-computing
    ├── port 7070  →  mapped to host port 7070 (same as assigned)
    └── synthadoc serve -w /wiki --host 0.0.0.0
```

**Design decisions:**

- **One wiki per container** — matches the one-process/one-port model; run multiple containers on different host ports for multiple wikis
- **Wiki files on the host** — the container mounts the wiki as a volume, so Obsidian and other tools access the files normally without going through the container
- **No registry inside the container** — the server always starts with an explicit `-w /wiki` path; the synthadoc registry is not used
- **Port matches the installed wiki** — the container reads the port from the wiki's `config.toml` (set by `synthadoc install`). Map it symmetrically: `-p 7070:7070` for a wiki assigned 7070, `-p 7071:7071` for one assigned 7071. Obsidian and other tools need no reconfiguration when switching between Docker and native `synthadoc serve`.
- **API keys via environment variables only** — never baked into the image
- **Non-root user** — the container runs as uid 1000 (`synthadoc`) for standard container hardening

---

## Prerequisites

| Platform | Runtime | Requirement |
|---|---|---|
| **Linux** | Docker Engine | Standard `docker` install — [docs.docker.com/engine/install](https://docs.docker.com/engine/install/) |
| **Linux** | Docker Compose | Required for multi-wiki and CI/CD setups — [docs.docker.com/compose/install/linux](https://docs.docker.com/compose/install/linux/) |
| **macOS (Apple Silicon)** | Apple `container` (built-in) | macOS 26 (Tahoe)+, M1 or later — no install needed |
| **macOS (Apple Silicon)** | Docker Desktop | Alternative if macOS < 26; includes Compose — [docs.docker.com/desktop/install/mac-install](https://docs.docker.com/desktop/install/mac-install/) |
| **macOS (Intel)** | Docker Desktop | Required — Apple's `container` tool does not support Intel. Affects Mac Pro 2019, MacBook Air/Pro pre-2020, iMac pre-2021; includes Compose — [docs.docker.com/desktop/install/mac-install](https://docs.docker.com/desktop/install/mac-install/) |
| **Windows** | WSL Containers (`wslc`) | Windows 11, WSL 2.9.3+ — no install needed |
| **Windows** | Docker Desktop | Alternative, or required for Docker Compose; includes Compose — [docs.docker.com/desktop/install/windows-install](https://docs.docker.com/desktop/install/windows-install/) |

All runtimes use the same OCI image — no separate image per platform.

**No Python needed on the host.** Every `synthadoc` command in this guide, including creating a wiki, runs inside a container. Besides a container runtime you only need a text editor (to set the LLM provider in `config.toml`) and, optionally, Obsidian.

**How commands are shown.** Commands are written for **Linux / macOS** (bash or zsh), with long commands split across lines using `\`. Where Windows differs, a collapsible **Windows (Command Prompt)** block follows with single-line commands that paste directly into `cmd.exe`. On Windows:

- `\` line continuation does not work in Command Prompt, so use the single-line versions.
- `~` is not expanded inside `docker -v` paths, so the Windows versions use `"%USERPROFILE%\wikis\…"`.
- `docker exec …` commands are identical on every platform and are shown once.
- Using PowerShell instead? Replace `%USERPROFILE%` with `$env:USERPROFILE`, and type `curl.exe` instead of `curl` (in PowerShell, `curl` is an alias for `Invoke-WebRequest`).

---

## API Key Setup

Create a `.env` file in your wikis folder, `~/wikis/.env`, outside any wiki folder. Never commit it to git. It holds the API key for the LLM provider you will select in the wiki's `config.toml` (Step 3), plus optional extras. For example, to use MiniMax:

```bash
# ~/wikis/.env

# LLM provider — exactly one required; it must match the provider selected in config.toml
MINIMAX_API_KEY=sk-...
# ANTHROPIC_API_KEY=sk-ant-...
# OPENAI_API_KEY=sk-...
# GEMINI_API_KEY=AI...
# GROQ_API_KEY=gsk_...
# DEEPSEEK_API_KEY=sk-...

# Web search — optional, enables "search for:" ingest jobs
TAVILY_API_KEY=tvly-...
```

On Windows, create it with `notepad "%USERPROFILE%\wikis\.env"` (after `~/wikis` exists, Step 2) and save it as plain text.

Pass it to the container with `--env-file`. This keeps keys out of your shell history and off the command line. **Do not use `-e KEY=value` on the command line**, because the value ends up in shell history. Either way, anyone with Docker access on the host can read the container's environment with `docker inspect`, so restrict who can use Docker on shared servers.

For Docker Compose, keep the `.env` file in the same folder as the Compose file. Compose reads it automatically, and the Compose examples load it into the container with `env_file`.

---

## Quick Start

### Step 1 — Pull the image

```bash
docker pull chenp/synthadoc:latest
```

This step is optional the first time: `docker run` downloads the image automatically if it is not on your machine yet. Once an image is cached locally, though, `docker run` keeps using it, so run `docker pull` again whenever you want the newest `:latest` build.

### Step 2 — Install a wiki

The container serves a wiki folder that lives on the host, so create that folder first. You don't need Python or `synthadoc` on the host. Run `synthadoc install` in a **one-off container** that mounts the *parent* folder (`~/wikis`); it writes the new wiki there and exits (`--rm`):

Create the parent folder first (on Linux, Docker would otherwise create it owned by root):

```bash
mkdir -p ~/wikis
```

<details>
<summary>Windows (Command Prompt)</summary>

```bat
if not exist "%USERPROFILE%\wikis" mkdir "%USERPROFILE%\wikis"
```

</details>

**Option A — Demo wiki** (used in this guide): pre-populated with sample pages, ready to query immediately:

```bash
docker run --rm -v ~/wikis:/wikis chenp/synthadoc:latest \
  synthadoc install history-of-computing --target /wikis --demo
```

<details>
<summary>Windows (Command Prompt)</summary>

```bat
docker run --rm -v "%USERPROFILE%\wikis:/wikis" chenp/synthadoc:latest synthadoc install history-of-computing --target /wikis --demo
```

</details>

**Option B — Template wiki**: scaffolded for a specific domain. Browse the 30 available templates first, then install:

```bash
docker run --rm chenp/synthadoc:latest synthadoc templates list

docker run --rm -v ~/wikis:/wikis chenp/synthadoc:latest \
  synthadoc install my-market-wiki --target /wikis --template research/market-research
```

<details>
<summary>Windows (Command Prompt)</summary>

```bat
docker run --rm chenp/synthadoc:latest synthadoc templates list
docker run --rm -v "%USERPROFILE%\wikis:/wikis" chenp/synthadoc:latest synthadoc install my-market-wiki --target /wikis --template research/market-research
```

</details>

**Option C — Custom domain wiki**: no template; provide a `--domain` description:

```bash
docker run --rm -v ~/wikis:/wikis chenp/synthadoc:latest \
  synthadoc install my-wiki --target /wikis --domain "Your domain description"
```

<details>
<summary>Windows (Command Prompt)</summary>

```bat
docker run --rm -v "%USERPROFILE%\wikis:/wikis" chenp/synthadoc:latest synthadoc install my-wiki --target /wikis --domain "Your domain description"
```

</details>

Install makes no LLM call, so no API key is needed for this step. `/wikis` is only the path inside the one-off container; the wiki is created on the host at `~/wikis/<name>`.

> **Installing a second wiki?** Each one-off container starts with an empty wiki registry, so `install` always assigns port 7070. Pass a free port explicitly for every additional wiki, e.g. `--port 7071`.

> **Already have `synthadoc` installed on the host?** `synthadoc install history-of-computing --target ~/wikis --demo` does the same thing. Its registry also assigns the next free port automatically.

---

This guide continues with the Option A demo. After running the install command, you will see:

```
Wiki 'history-of-computing' installed.
  Port   7070
  Plugin Obsidian plugin ready
```

Note the assigned port (`7070` above) — you will use it in Step 4. Ignore any "Next steps" that mention `synthadoc use` or `synthadoc serve`; with Docker you start a container in Step 4 instead.

### Step 3 — Set your LLM provider

Open `~/wikis/history-of-computing/.synthadoc/config.toml`. The `[agents]` section has one active `default =` line and commented-out alternatives for every supported provider. It looks like this out of the box:

```toml
[agents]
default = { provider = "gemini", model = "gemini-2.5-flash-lite" }
# Alternatives (uncomment and restart to switch):
# default = { provider = "gemini",    model = "gemini-2.5-flash" }
# default = { provider = "minimax",   model = "MiniMax-M3",  thinking = "disabled" }
# default = { provider = "groq",      model = "openai/gpt-oss-20b" }
# default = { provider = "anthropic", model = "claude-sonnet-5-5" }
# default = { provider = "anthropic", model = "claude-opus-5-5" }
# default = { provider = "anthropic", model = "claude-haiku-5-5" }
# default = { provider = "anthropic", model = "claude-sonnet-4-6" }
# default = { provider = "anthropic", model = "claude-opus-4-8" }
# default = { provider = "deepseek",  model = "deepseek-flash" }
# default = { provider = "ollama",    model = "llama3.2" }
# NOTE: opencode / claude-code providers require a local binary — not supported in Docker
# ...
```

To switch providers: **comment out the active line** and **uncomment the one you want**. For example, to switch to MiniMax:

```toml
[agents]
# default = { provider = "gemini", model = "gemini-2.5-flash-lite" }
# Alternatives (uncomment and restart to switch):
# default = { provider = "gemini",    model = "gemini-2.5-flash" }
default = { provider = "minimax",   model = "MiniMax-M3",  thinking = "disabled" }
# default = { provider = "groq",      model = "openai/gpt-oss-20b" }
# ...
```

Then make sure `~/wikis/.env` contains the API key for the provider you selected (e.g. `MINIMAX_API_KEY=...` for MiniMax, `ANTHROPIC_API_KEY=...` for Anthropic); see [API Key Setup](#api-key-setup) above. The provider in `config.toml` and the key in `.env` must match. If the expected key is missing, the container exits immediately on startup.

> **CLI providers (`opencode`, `claude-code`) are not supported inside Docker.** These providers work by shelling out to a local binary on the host machine. Inside a container neither binary is available, so Synthadoc will fail to start with `[ERR-PROV-003]`. Use any API-based provider instead (Anthropic, Gemini, OpenAI, etc.). If you want a **no-API-key, locally-run** option, use the Ollama sidecar — see [Ollama sidecar](#ollama-sidecar) below.

### Step 4 — Start the container

Use the port that `synthadoc install` assigned (shown in Step 2) for both sides of `-p`. For the demo wiki that is 7070:

```bash
docker run -d \
  --name history-of-computing \
  -v ~/wikis/history-of-computing:/wiki \
  -p 7070:7070 \
  --env-file ~/wikis/.env \
  chenp/synthadoc:latest
```

<details>
<summary>Windows (Command Prompt)</summary>

```bat
docker run -d --name history-of-computing -v "%USERPROFILE%\wikis\history-of-computing:/wiki" -p 7070:7070 --env-file "%USERPROFILE%\wikis\.env" chenp/synthadoc:latest
```

</details>

Using the same port on both sides means the Obsidian plugin, Web UI, and any scripts that already point at `localhost:7070` work without any changes — whether the wiki is running in Docker or via `synthadoc serve` directly.

### Step 5 — Verify

**Check the container is running:**

```bash
docker ps
```

If it is missing from the list, it exited — check why:

```bash
docker logs history-of-computing
```

**Check the health endpoint:**

```bash
curl http://localhost:7070/health
```

Expected response:

```json
{"status": "ok", ...}
```

**Open the Web UI** in any browser:

```
http://localhost:7070/app
```

**Verify Obsidian:** open the `history-of-computing` vault in Obsidian (the same folder you installed in Step 2) and click the **bookmark icon** in the left navigator. The plugin connects to `localhost:7070` — the same address it used before Docker, so no settings change is needed.

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
docker exec history-of-computing synthadoc query "Who is Turing and his major contributions in the field?"

# Force a fresh LLM call (skip the query cache)
docker exec history-of-computing synthadoc query "What were the key milestones in the development of the internet?" --no-cache
```

### Ingesting content

```bash
# Ingest a single file (relative path resolves from /wiki/)
docker exec history-of-computing synthadoc ingest raw_sources/report.pdf

# Batch-ingest an entire folder
docker exec history-of-computing synthadoc ingest raw_sources/ --batch

# Ingest a URL
docker exec history-of-computing synthadoc ingest https://example.com/article

# Ingest via web search (Tavily) — requires TAVILY_API_KEY in container env
docker exec history-of-computing synthadoc ingest "search for: IFRS 17 insurance contract accounting"

# Watch job progress after queuing (ingest returns immediately)
docker exec history-of-computing synthadoc jobs list --sort created_at --order desc
```

### Linting

```bash
# Enqueue lint and wait for completion (--wait keeps docker exec alive)
docker exec history-of-computing synthadoc lint run --wait

# Show lint report (contradictions, orphan pages, adversarial findings)
docker exec history-of-computing synthadoc lint report

# Lint with URL source availability check
docker exec history-of-computing synthadoc lint run --check-urls --wait
```

### Agentic workflows

```bash
# List all available workflows
docker exec history-of-computing synthadoc workflow list

# Re-ingest all stale pages (agentic loop, streams progress)
docker exec history-of-computing synthadoc workflow run --name ingest-lint

# Run the contradiction resolver (interactive — approves rewrites one by one)
docker exec -it history-of-computing synthadoc workflow run --name contradiction-resolver

# Scan and fix broken wikilinks
docker exec -it history-of-computing synthadoc workflow run --name broken-wikilinks

# Fix broken ^[file:L-L] citation markers
docker exec -it history-of-computing synthadoc workflow run --name broken-citation-resolver

# Content health resolver (v1.4.2) — fix duplicate/thin/empty sections and broken
# markdown structure; side-by-side diff approval per page, snapshot before every write
docker exec -it history-of-computing synthadoc workflow run --name content-health
docker exec -it history-of-computing synthadoc workflow run --name content-health --slug alan-turing

# Review or undo content health fixes
docker exec history-of-computing synthadoc workflow run --name content-health list
docker exec history-of-computing synthadoc workflow run --name content-health roll back alan-turing
```

Use `-it` for any workflow that asks for confirmation; without a TTY the prompts cannot be answered. The same workflows are available in the Web UI at `http://localhost:7070/app`, where the content health resolver is pre-prompted at session start whenever flagged pages exist.

### Scaffold

```bash
# Regenerate index.md, AGENTS.md, and purpose.md using the LLM
# (queues a background job; monitor with jobs list)
docker exec history-of-computing synthadoc scaffold
docker exec history-of-computing synthadoc jobs list --sort created_at --order desc
```

### Lifecycle (promote, archive, restore)

Pages start as `draft`. Use `lifecycle activate` to promote a reviewed page
to `active`, or `lifecycle archive` to retire it.

```bash
# Promote a draft page to active
docker exec history-of-computing synthadoc lifecycle activate quarterly-report-q3 --reason "Reviewed and approved"

# Archive a superseded page
docker exec history-of-computing synthadoc lifecycle archive old-market-analysis --reason "Superseded by 2026 report"

# Restore an archived page back to draft
docker exec history-of-computing synthadoc lifecycle restore old-market-analysis --reason "Needed for comparison"

# Show full lifecycle event log
docker exec history-of-computing synthadoc lifecycle log

# Show lifecycle history for one page
docker exec history-of-computing synthadoc lifecycle history quarterly-report-q3
```

### Scheduled jobs

```bash
# List all registered scheduled jobs
docker exec history-of-computing synthadoc schedule list

# Schedule a nightly lint (cron: 2 AM every day)
docker exec history-of-computing synthadoc schedule add --op "lint run" --cron "0 2 * * *"

# Apply schedules declared in config.toml [schedule] blocks
docker exec history-of-computing synthadoc schedule apply
```

### Monitoring and audit

```bash
# Show all recent jobs (newest first)
docker exec history-of-computing synthadoc jobs list --sort created_at --order desc

# Server health and version
docker exec history-of-computing synthadoc status

# Ingest cost and history
docker exec history-of-computing synthadoc audit history

# Backup the wiki to a zip file (lands in the mounted /wiki folder)
docker exec history-of-computing synthadoc backup
```

---

## Accessing the Web UI and Obsidian

Both interfaces are available automatically the moment the container starts — no extra steps or flags needed.

### Web UI

The HTTP server the container runs also serves the Web UI. Because the port mapping is symmetric (`-p 7070:7070`), the URL is identical to what you would use with a native `synthadoc serve`:

| Client | URL |
|---|---|
| Browser (Web UI) | `http://localhost:7070/app` |
| Obsidian plugin (Server URL) | `http://localhost:7070` |
| MCP client | `http://localhost:7070/mcp` |
| Health check / scripts | `http://localhost:7070/health` |

For a second wiki on port 7071, substitute `7071` throughout.

For a team or remote server, replace `localhost` with the server's IP or hostname:
```
http://192.168.1.50:7070/app        # Web UI
http://192.168.1.50:7070/mcp        # MCP client
```

### Obsidian Plugin

Open the wiki folder (`~/wikis/history-of-computing`) as an Obsidian vault — the volume mount means the wiki files exist on both the host and inside the container, so Obsidian reads them directly with no Docker-specific configuration.

The Synthadoc plugin connects to `http://127.0.0.1:7070` — the same address it uses for a native `synthadoc serve` session. No URL change is needed. Click the **bookmark icon** in the left navigator to verify the connection.

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

## Configuration

Synthadoc reads its configuration from `.synthadoc/config.toml` inside the wiki directory. Because the wiki is mounted as a volume, you edit this file on the host, with no image rebuild. The server reads `config.toml` only at startup, so **restart the container after every change**:

```toml
# ~/wikis/history-of-computing/.synthadoc/config.toml

[server]
port = 7070          # set by install; map it 1:1 to the host (-p 7070:7070)
# host = "0.0.0.0"   # leave commented: the container always binds 0.0.0.0 via --host in its start command

[agents]
default = { provider = "minimax", model = "MiniMax-M3", thinking = "disabled" }
```

```bash
docker restart history-of-computing
```

`docker restart` re-reads `config.toml` but **not** `.env`. The container's environment is fixed when it is created. If you add or change an API key in `.env`, remove and re-create the container instead (see [Troubleshooting](#h-troubleshooting)).

To try another provider without editing `config.toml`, re-create the container with `--provider`, appending the full start command (`synthadoc serve -w /wiki --host 0.0.0.0`) and the override:

```bash
docker rm -f history-of-computing
docker run -d \
  --name history-of-computing \
  -v ~/wikis/history-of-computing:/wiki \
  -p 7070:7070 \
  --env-file ~/wikis/.env \
  chenp/synthadoc:latest \
  synthadoc serve -w /wiki --host 0.0.0.0 --provider openai
```

<details>
<summary>Windows (Command Prompt)</summary>

```bat
docker rm -f history-of-computing
docker run -d --name history-of-computing -v "%USERPROFILE%\wikis\history-of-computing:/wiki" -p 7070:7070 --env-file "%USERPROFILE%\wikis\.env" chenp/synthadoc:latest synthadoc serve -w /wiki --host 0.0.0.0 --provider openai
```

</details>

`.env` must contain that provider's key (here `OPENAI_API_KEY`).

### Semantic search

The image includes [semantic search](design.md#semantic-search) (`fastembed` and the ~65 MB embedding model, built in so containers never download it). It is off by default (the server logs a one-line reminder at startup that it is available); turn it on in `config.toml` and restart:

```toml
[search]
vector = true
```

On the first start the server embeds every page in the background (a few minutes for a couple of thousand pages); search answers with BM25 until it finishes. Embeddings are stored in the wiki's `.synthadoc/embeddings.db`, on the mounted volume, so later restarts only embed pages that changed.

To build a smaller BM25-only image, leave the extra out:

```bash
docker build --build-arg SYNTHADOC_EXTRAS= -t synthadoc:bm25 .
```

---

## Maintenance

Examples below use `history-of-computing` as the container name. Substitute your own container name throughout.

### Health check

The image includes a HEALTHCHECK that polls `/health` every 30 seconds on the port set in the wiki's `.synthadoc/config.toml` (so a wiki installed on 7071 is checked on 7071):

```bash
docker inspect --format='{{.State.Health.Status}}' history-of-computing
# healthy | starting | unhealthy
```

If the status is `unhealthy`, check the logs (see below) and try the health endpoint directly:

```bash
curl http://localhost:7070/health
```

### Pinning a version

`latest` always pulls the newest release, which can introduce breaking changes. For a stable deployment, pin to a specific release tag:

```bash
docker pull chenp/synthadoc:1.4.2
docker run -d \
  --name history-of-computing \
  -v ~/wikis/history-of-computing:/wiki \
  -p 7070:7070 \
  --env-file ~/wikis/.env \
  chenp/synthadoc:1.4.2
```

<details>
<summary>Windows (Command Prompt)</summary>

```bat
docker pull chenp/synthadoc:1.4.2
docker run -d --name history-of-computing -v "%USERPROFILE%\wikis\history-of-computing:/wiki" -p 7070:7070 --env-file "%USERPROFILE%\wikis\.env" chenp/synthadoc:1.4.2
```

</details>

### Viewing logs

```bash
# Live logs (follow)
docker logs -f history-of-computing

# Last 100 lines
docker logs --tail 100 history-of-computing
```

Synthadoc also writes structured logs to `.synthadoc/logs/` inside the wiki directory on the host.

### Updating the image

Pull the latest build, then recreate the container. Wiki data is safe — it lives in the host volume, not inside the container:

```bash
docker pull chenp/synthadoc:latest
docker stop history-of-computing
docker rm history-of-computing
docker run -d \
  --name history-of-computing \
  -v ~/wikis/history-of-computing:/wiki \
  -p 7070:7070 \
  --env-file ~/wikis/.env \
  chenp/synthadoc:latest
```

<details>
<summary>Windows (Command Prompt)</summary>

```bat
docker pull chenp/synthadoc:latest
docker stop history-of-computing
docker rm history-of-computing
docker run -d --name history-of-computing -v "%USERPROFILE%\wikis\history-of-computing:/wiki" -p 7070:7070 --env-file "%USERPROFILE%\wikis\.env" chenp/synthadoc:latest
```

</details>

Then refresh the Obsidian plugin stored in the vault so it matches the new server version:

```bash
docker exec history-of-computing synthadoc plugin install
```

> `synthadoc plugin upgrade` and `synthadoc templates sync`, the upgrade commands for pip installs, read the host wiki registry, which does not exist inside a container. They fail with "No wikis registered" or "is not registered". Use `plugin install` as shown above. Refreshing demo or template content (`templates sync`) is not currently available for container-only setups.

### Stop and restart

```bash
# Stop the container (preserves it; can be restarted)
docker stop history-of-computing

# Start it again
docker start history-of-computing

# Restart in one step (needed after editing config.toml; does not re-read .env)
docker restart history-of-computing
```

### Tear down

Stops and permanently removes the container. The wiki files on the host are untouched:

```bash
docker stop history-of-computing
docker rm history-of-computing
```

### Backup

The built-in backup command is the safest option, because it snapshots the databases consistently while the server runs. It works the same on every platform:

```bash
docker exec history-of-computing synthadoc backup
# The .zip lands in the wiki folder on the host (~/wikis/history-of-computing/)
```

Alternatively, stop the container and archive the wiki folder like any directory:

```bash
docker stop history-of-computing
tar -czf history-of-computing-backup-$(date +%Y%m%d).tar.gz -C ~/wikis history-of-computing
docker start history-of-computing
```

<details>
<summary>Windows (Command Prompt)</summary>

```bat
docker stop history-of-computing
tar -czf history-of-computing-backup.tar.gz -C "%USERPROFILE%\wikis" history-of-computing
docker start history-of-computing
```

</details>

---

## Appendix

### A. Platform-Native Runtimes

#### macOS 26+ (Apple Silicon — M1 or later)

Apple's built-in `container` tool ships with macOS 26 (Tahoe) and runs OCI images without Docker Desktop. Replace `docker` with `container` in every command in this guide, including the one-off install in Step 2 (`container run --rm -v ~/wikis:/wikis chenp/synthadoc:latest synthadoc install …`):

```bash
container run -d \
  --name history-of-computing \
  -v ~/wikis/history-of-computing:/wiki \
  -p 7070:7070 \
  --env-file ~/wikis/.env \
  chenp/synthadoc:latest
```

> **Intel Macs (Mac Pro 2019, MacBook Air/Pro pre-2020):** Apple's `container` tool requires Apple Silicon. Use Docker Desktop on Intel hardware.

#### Windows 11 (WSL 2.9.3+)

WSL Containers (`wslc`) ship with WSL 2.9.3+ on Windows 11. Run these inside a WSL shell, where the Linux / macOS commands of this guide apply, with `wslc` in place of `docker` (including the Step 2 one-off install):

```bash
wslc run -d \
  --name history-of-computing \
  -v ~/wikis/history-of-computing:/wiki \
  -p 7070:7070 \
  --env-file ~/wikis/.env \
  chenp/synthadoc:latest
```

> **Windows performance tip:** keep your wiki folder inside the WSL2 filesystem (e.g. `/home/yourname/wikis/history-of-computing`) rather than on the Windows drive (`/mnt/c/Users/...`). Volume mounts from the Windows drive are significantly slower for file-heavy operations like ingest.

> **Docker Compose** is not yet supported by `wslc`. Use Docker Desktop if you need Compose.

---

### B. Docker Compose

Ready-made Compose files live in [`docker/compose/`](https://github.com/axoviq-ai/synthadoc/tree/main/docker/compose) on GitHub. You don't need to clone the repo: download the one you need into your wikis folder (`~/wikis`), next to your `.env` file. Compose reads `.env` from the same folder, and the examples load your API keys from it with `env_file`. Compose requires Docker Desktop on Windows and macOS (the platform-native tools do not support Compose yet).

Run all `docker compose` commands from `~/wikis`.

#### Single wiki

```bash
cd ~/wikis
curl -fsSL -o docker-compose.yml https://raw.githubusercontent.com/axoviq-ai/synthadoc/main/docker/compose/single-wiki.yml
```

<details>
<summary>Windows (Command Prompt)</summary>

```bat
cd /d "%USERPROFILE%\wikis"
curl -fsSL -o docker-compose.yml https://raw.githubusercontent.com/axoviq-ai/synthadoc/main/docker/compose/single-wiki.yml
```

</details>

Add the wiki path to `~/wikis/.env` (alongside your API key), then start:

```bash
# ~/wikis/.env
# macOS: WIKI_PATH=/Users/yourname/wikis/history-of-computing
WIKI_PATH=/home/yourname/wikis/history-of-computing
MINIMAX_API_KEY=sk-...
```

On Windows, use forward slashes: `WIKI_PATH=C:/Users/yourname/wikis/history-of-computing`. Backslashes break volume mounts.

```bash
docker compose up -d
```

Access at `http://localhost:7070/app`.

Run a CLI command inside the running container:

```bash
docker compose exec sd-server synthadoc ingest raw_sources/report.pdf
```

#### Multiple wikis

Download `multi-wiki.yml` into `~/wikis` (see Step 1 below). It is pre-configured for the two demo wikis used in this guide (`history-of-computing` on 7070, `ai-research` on 7071). If you are using different wikis or ports, do a search-and-replace — the header comment in the file tells you exactly what to change.

**Step 0 — Install both demo wikis** (skip if you already have two wikis). The second wiki needs an explicit `--port`, because a one-off container cannot see which ports earlier installs took:

```bash
mkdir -p ~/wikis
docker run --rm -v ~/wikis:/wikis chenp/synthadoc:latest \
  synthadoc install history-of-computing --target /wikis --demo
docker run --rm -v ~/wikis:/wikis chenp/synthadoc:latest \
  synthadoc install ai-research --target /wikis --demo --port 7071
```

<details>
<summary>Windows (Command Prompt)</summary>

```bat
if not exist "%USERPROFILE%\wikis" mkdir "%USERPROFILE%\wikis"
docker run --rm -v "%USERPROFILE%\wikis:/wikis" chenp/synthadoc:latest synthadoc install history-of-computing --target /wikis --demo
docker run --rm -v "%USERPROFILE%\wikis:/wikis" chenp/synthadoc:latest synthadoc install ai-research --target /wikis --demo --port 7071
```

</details>

**Step 1 — Download the Compose file and set `.env`**

```bash
cd ~/wikis
curl -fsSL -o multi-wiki.yml https://raw.githubusercontent.com/axoviq-ai/synthadoc/main/docker/compose/multi-wiki.yml
```

<details>
<summary>Windows (Command Prompt)</summary>

```bat
cd /d "%USERPROFILE%\wikis"
curl -fsSL -o multi-wiki.yml https://raw.githubusercontent.com/axoviq-ai/synthadoc/main/docker/compose/multi-wiki.yml
```

</details>

```bash
# ~/wikis/.env  (same folder as multi-wiki.yml)
MINIMAX_API_KEY=sk-...
WIKI_A_PATH=/home/yourname/wikis/history-of-computing
WIKI_B_PATH=/home/yourname/wikis/ai-research
```

On Windows: use forward slashes (`C:/Users/yourname/wikis/...`). Backslashes break volume mounts.

**Step 2 — Start**

```bash
docker compose -f multi-wiki.yml up -d
```

Both containers should reach `(healthy)` within 30 seconds:

```bash
docker compose -f multi-wiki.yml ps
```

**Debugging**

```bash
# View logs
docker compose -f multi-wiki.yml logs sd-server-a --tail 50
docker compose -f multi-wiki.yml logs sd-server-b --tail 50

# Recreate one container after editing the yml or a wiki's config.toml
docker compose -f multi-wiki.yml up -d --force-recreate sd-server-a

# Recreate both
docker compose -f multi-wiki.yml up -d --force-recreate
```

See the header comment in `multi-wiki.yml` for a full troubleshooting guide including common cross-wiki error causes.

#### Cross-wiki queries

Cross-wiki queries fan out a single question across multiple wiki containers and return one unified answer. Each container exposes both a `/retrieve` endpoint (responds to other wikis) and a `/cross-wiki/query` endpoint (acts as coordinator). Any running container can coordinate a query.

**How it works — no routing file required**

By default, the coordinator picks which wikis to search automatically: it reads each wiki's domain description from the registry and asks the LLM to select the most relevant ones for your question. You do not need to configure anything beyond starting the containers.

In Docker Compose, containers on the same network reach each other by **service name** rather than `localhost`. `multi-wiki.yml` gives the coordinator (`sd-server-a`) a cross-wiki registry through its `configs:` block, mounted at `/home/synthadoc/.synthadoc/wikis.json`. Each peer entry has a `host` set to its service name (`sd-server-a`, `sd-server-b`), so the coordinator reaches peers without any extra steps. If you rename services, wikis, or ports, update that block to match.

**Step 1 — Start the multi-wiki stack**

```bash
docker compose -f multi-wiki.yml up -d
```

Verify both containers are running:

```bash
docker compose -f multi-wiki.yml ps
```

**Step 2 — Query from the web UI**

Open the coordinator wiki's web UI in your browser (e.g. `http://localhost:7070/app`). In the Chat tab, click the **🌐** globe icon at the right end of the message input bar to enable cross-wiki mode. A context bar appears showing which wikis will be searched:

```
🌐  Querying across: history-of-computing · ai-research
```

Type your question and submit. The coordinator fans out to all running peer containers, merges the results, and returns one synthesised answer. Citations show the source wiki: `[history-of-computing]  Alan Turing`.

If you are using the **history-of-computing** and **ai-research** demo wikis, try this query to see results from both:

> *How did Alan Turing's theoretical work on computation influence the foundations of modern artificial intelligence?*

After the response the bar updates to show what was actually reached:

```
🌐  Searched: history-of-computing · ai-research
```

If a peer was unreachable, it is flagged inline: `⚠ ai-research offline`. The coordinator still returns an answer from the available wikis.

**Step 3 — Handle an offline wiki**

If a peer container is stopped, the coordinator degrades gracefully: it answers from the wikis that responded and notes which were unreachable. Restart a stopped wiki and re-query to include it:

```bash
docker compose -f multi-wiki.yml start sd-server-b
```

**CLI alternative**

You can also run a cross-wiki query from the command line by targeting the coordinator container:

```bash
docker compose -f multi-wiki.yml exec sd-server-a synthadoc query --cross-wiki "How did early computing hardware influence AI research?"
```

**Optional: keyword-based routing override**

For large stacks (three or more wikis) where you want deterministic wiki selection rather than LLM-based routing, you can create `CROSS_WIKI_ROUTING.md` in the coordinator container's config directory. This is a plain-text file that maps keywords to wiki groups:

```bash
docker compose -f multi-wiki.yml exec sd-server-a synthadoc cross-wiki routing init   # scaffold the file, then edit to taste
```

When the file is present, the LLM routing call is skipped and keyword matching is used instead. This is optional — skip it for most setups.

> For full cross-wiki details (citation format, SSE events, routing file syntax) see [Appendix L — Cross-Wiki Queries](user-quick-start-guide.md#appendix-l--cross-wiki-queries) in the Quick-Start Guide.

---

#### Local LLM with Ollama (no cloud API key)

Download the Compose file into `~/wikis` and set `WIKI_PATH` in `~/wikis/.env` as for a single wiki (no API key needed):

```bash
cd ~/wikis
curl -fsSL -o with-ollama.yml https://raw.githubusercontent.com/axoviq-ai/synthadoc/main/docker/compose/with-ollama.yml
```

<details>
<summary>Windows (Command Prompt)</summary>

```bat
cd /d "%USERPROFILE%\wikis"
curl -fsSL -o with-ollama.yml https://raw.githubusercontent.com/axoviq-ai/synthadoc/main/docker/compose/with-ollama.yml
```

</details>

```bash
docker compose -f with-ollama.yml up -d

# Pull a model into Ollama
docker compose -f with-ollama.yml exec ollama ollama pull llama3.2
```

Then point the wiki at Ollama: in `config.toml`, comment out the active `default =` line under `[agents]` and add this one (don't add a separate `[agents.default]` table, which would duplicate `default`). Restart the stack afterwards:

```toml
[agents]
default = { provider = "ollama", model = "llama3.2", base_url = "http://ollama:11434" }
```

```bash
docker compose -f with-ollama.yml restart sd-server
```

---

### C. CI/CD — Scheduled Ingest

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

### D. File Permissions on Linux Hosts

> **macOS / Windows:** Docker Desktop maps file ownership transparently through
> its virtual machine layer. This section does not apply to those platforms.

The container process runs as **uid 1000** (an internal user named `synthadoc`).
Docker maps uids numerically — it does not look up user names — so the container
can write to a host directory only if the directory's owner uid matches the
process uid (1000).

**You do not need to create any user account on your host.** The fix is purely
about which uid owns the directory.

#### Step 1 — Check your host uid

```bash
id -u    # prints your numeric user id, e.g. 1000 or 1001
```

#### Step 2 — Pick the right fix

**Your host uid is already 1000** (the first user on most Linux systems):

No action needed. The container's uid 1000 and your uid 1000 match — Docker
mounts the directory and both sides can read and write it without any changes.

**Your host uid is NOT 1000:**

Option A — tell Docker to run the container as your uid (recommended, no sudo):

```bash
docker run -d \
  --name history-of-computing \
  --user $(id -u):$(id -g) \
  -v ~/wikis/history-of-computing:/wiki \
  -p 7070:7070 \
  --env-file ~/wikis/.env \
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
sudo chown -R 1000:1000 ~/wikis/history-of-computing
```

This permanently assigns the directory to uid 1000. Useful on servers where you
always want containers to own the wiki data and your personal account is a
separate uid for administration only.

---

### E. Export, Backup, and Restore Paths

The container's only persistent storage is the `/wiki` mount. Any file written
**outside** `/wiki` goes into the container's ephemeral overlay filesystem:
it is invisible to your host, and is permanently lost when the container is
removed (`docker rm`). No error is reported — the command appears to succeed.

The image sets `WORKDIR /wiki`, so **relative paths and the default `.` all
resolve inside `/wiki/`** — which means the safe defaults work without extra flags.

#### Backup

```bash
# Default (--output ".") writes the zip to /wiki/ → visible on host
docker exec history-of-computing synthadoc backup

# Explicit subdirectory — also fine
docker exec history-of-computing synthadoc backup --output /wiki/backups/
```

Avoid absolute host-style paths (`--output ~/backups/`): `~` expands to
`/home/synthadoc/` inside the container, not your home directory on the host.

#### Restore

The zip file must be reachable inside the container. The easiest way is to
copy it into the mounted wiki directory first:

```bash
# On the host — copy the zip into the wiki mount
cp ~/Downloads/synthadoc-backup-history-of-computing-20261010.zip ~/wikis/history-of-computing/

# Inside the container — restore from /wiki/ (default target is zip's parent = /wiki/)
docker exec -it history-of-computing synthadoc restore /wiki/synthadoc-backup-history-of-computing-20261010.zip
```

<details>
<summary>Windows (Command Prompt)</summary>

```bat
copy "%USERPROFILE%\Downloads\synthadoc-backup-history-of-computing-20261010.zip" "%USERPROFILE%\wikis\history-of-computing\"
docker exec -it history-of-computing synthadoc restore /wiki/synthadoc-backup-history-of-computing-20261010.zip
```

</details>

Alternatively, use `docker cp` to push the file directly into the container:

```bash
docker cp ~/Downloads/synthadoc-backup-history-of-computing-20261010.zip history-of-computing:/wiki/
docker exec -it history-of-computing synthadoc restore /wiki/synthadoc-backup-history-of-computing-20261010.zip
```

<details>
<summary>Windows (Command Prompt)</summary>

```bat
docker cp "%USERPROFILE%\Downloads\synthadoc-backup-history-of-computing-20261010.zip" history-of-computing:/wiki/
docker exec -it history-of-computing synthadoc restore /wiki/synthadoc-backup-history-of-computing-20261010.zip
```

</details>

#### Export (CLI)

For formats that print to stdout (`json`, `llms.txt`, `llms-full.txt`,
`graphml`), redirect on the host side — no path issue:

```bash
docker exec history-of-computing synthadoc export --format llms.txt > ~/wiki-export.txt
docker exec history-of-computing synthadoc export --format json     > ~/wiki-export.json
```

<details>
<summary>Windows (Command Prompt)</summary>

```bat
docker exec history-of-computing synthadoc export --format llms.txt > "%USERPROFILE%\wiki-export.txt"
docker exec history-of-computing synthadoc export --format json > "%USERPROFILE%\wiki-export.json"
```

</details>

For **OKF**, the CLI writes a directory tree to `--output`. Use a path inside
`/wiki/` so it lands on the host:

```bash
# Writes to /wiki/exports/<wiki>-okf-<date>/ → visible on host
docker exec history-of-computing synthadoc export --format okf --output /wiki/exports/
```

> **Obsidian plugin OKF export does not have this limitation.** When you
> trigger the export from the Obsidian UI, the plugin fetches the manifest
> from the server and then writes files using **Obsidian's own filesystem API
> on your host machine**. The default path (`~/exports/…`) resolves on your
> host, not inside the container. No special Docker configuration is needed.

---

### F. Security

Synthadoc has **no built-in authentication**. For localhost-only use this is fine. For any deployment reachable beyond localhost:

- Put a reverse proxy (nginx, Traefik, Caddy) with TLS and basic auth in front of the container
- Restrict the mapped port to a specific interface: `-p 127.0.0.1:7070:7070` binds only to localhost even if the container listens on `0.0.0.0`
- On team servers, use a VPN or SSH tunnel rather than exposing the port directly

**API keys:** always use `--env-file ~/wikis/.env`, never `-e KEY=value` on the command line. Restrict who can read the `.env` file: `chmod 600 ~/wikis/.env` on Linux/macOS; on Windows, keep it under your user profile, which other standard users cannot read.

---

### G. Local Build and Test (Windows)

Use this when you want to verify the Dockerfile works before publishing a release.
Building images requires **Docker Desktop** — `wslc` is runtime-only and cannot build.

#### Step 1 — Install Docker Desktop

1. Download from [docs.docker.com/desktop/install/windows-install](https://docs.docker.com/desktop/install/windows-install/)
2. Run the installer — it uses your existing WSL2 backend automatically
3. After install, open a new terminal and verify:

```bat
docker --version
docker buildx version
```

#### Step 2 — Build the image from source

The `Dockerfile` lives at the **repo root** — the top-level `synthadoc/` folder,
not the `docker/` subfolder (which only contains Compose files and examples).
Run the build from that directory:

```bat
REM cd to the repo root first (/d also switches drive letters)
cd /d C:\Users\you\Documents\my_workspace\synthadoc

docker build --no-cache -t synthadoc:local .
```

The trailing `.` tells Docker to use the current directory as the build context
(where it reads the `Dockerfile` and packages source files).

`--no-cache` forces Docker to re-copy the source files on every build. Without it, Docker reuses the cached source layer and your local code changes are silently ignored.

The first build takes a few minutes (downloads `python:3.12-slim` and installs synthadoc). Subsequent builds take roughly the same time because `--no-cache` disables layer reuse.

> **Local vs. production builds:** A local `docker build` installs synthadoc directly from your source tree, so it picks up any unreleased changes. The production CI build passes `--build-arg SYNTHADOC_VERSION=X.Y.Z` to install the exact release from PyPI instead, and it runs only after the PyPI publish workflow completes — so there is no race between the two.

Expected output (Docker BuildKit format):
```
[+] Building XX.Xs (13/13) FINISHED
 ...
 => => naming to docker.io/library/synthadoc:local
 => => unpacking to docker.io/library/synthadoc:local
```

If you see `(N/N) FINISHED` at the top and no `ERROR` lines, the image built successfully.

#### Step 3 — Create a test wiki

You need a wiki on disk for the container to mount. If you already have one, skip this. Otherwise install the built-in demo using the image you just built:

```bat
if not exist "%USERPROFILE%\wikis" mkdir "%USERPROFILE%\wikis"
docker run --rm -v "%USERPROFILE%\wikis:/wikis" synthadoc:local synthadoc install history-of-computing --target /wikis --demo
```

This creates `%USERPROFILE%\wikis\history-of-computing\` pre-populated with demo content, so you have real pages to query straight away.

#### Step 4 — Create a .env file

```bat
notepad "%USERPROFILE%\wikis\.env"
```

Add your key and save (see [API Key Setup](#api-key-setup)):

```bash
# %USERPROFILE%\wikis\.env  (keep outside the wiki folder)
MINIMAX_API_KEY=sk-...
# optional — enables web search ingest
TAVILY_API_KEY=tvly-...
```

Comments must be on their own line: `docker run --env-file` does not strip text after `#` on a value line.

Select the matching provider in `history-of-computing\.synthadoc\config.toml` (Quick Start Step 3).

#### Step 5 — Run the container

Single line, because backslash continuation does not work in Command Prompt:

```bat
docker run -d --name synthadoc-test -v "%USERPROFILE%\wikis\history-of-computing:/wiki" -p 7070:7070 --env-file "%USERPROFILE%\wikis\.env" synthadoc:local
```

Stop any locally running `synthadoc serve` instance for that wiki before starting the container — they both bind the same port.

#### Step 6 — Verify it started

```bat
REM Check the container is running
docker ps

REM Check startup logs
docker logs synthadoc-test

REM Hit the health endpoint (curl ships with Windows 10 and later)
curl http://localhost:7070/health
```

Expected response:
```json
{"status": "ok", ...}
```

#### Step 7 — Run a quick ingest test

```bat
REM Drop a small test file into raw_sources on the host
echo Synthadoc Docker test document.> "%USERPROFILE%\wikis\history-of-computing\raw_sources\docker-test.txt"

REM Ingest it from inside the container (no -w needed, SYNTHADOC_WIKI=/wiki is set)
docker exec synthadoc-test synthadoc ingest raw_sources/docker-test.txt

REM Check the job completed
docker exec synthadoc-test synthadoc jobs list --sort created_at --order desc
```

#### Step 8 — Tear down

```bat
docker stop synthadoc-test
docker rm synthadoc-test
```

The wiki files on the host are untouched — only the container is removed.

#### Step 9 — Rebuild after a source change

When you change the Python source and want to test it in Docker, remove the
old container, rebuild the image from the repo root, then re-run Step 5:

```bat
docker rm -f synthadoc-test
cd /d C:\Users\you\Documents\my_workspace\synthadoc
docker build --no-cache -t synthadoc:local .
```

`--no-cache` is required here: without it, Docker reuses the cached source
layer and your code changes are silently ignored.

---

### H. Troubleshooting

**API key change has no effect after `docker restart`**

`docker restart` reuses the environment captured at `docker run` time — it does not re-read `.env`. After updating `.env`, stop and recreate the container:

```bash
docker stop history-of-computing
docker rm history-of-computing
docker run -d \
  --name history-of-computing \
  -v ~/wikis/history-of-computing:/wiki \
  -p 7070:7070 \
  --env-file ~/wikis/.env \
  chenp/synthadoc:latest
```

<details>
<summary>Windows (Command Prompt)</summary>

```bat
docker stop history-of-computing
docker rm history-of-computing
docker run -d --name history-of-computing -v "%USERPROFILE%\wikis\history-of-computing:/wiki" -p 7070:7070 --env-file "%USERPROFILE%\wikis\.env" chenp/synthadoc:latest
```

</details>


**Container exits immediately**

```bash
docker logs history-of-computing
```

Common causes: `.env` lacks the key for the provider selected in `config.toml` (e.g. `MINIMAX_API_KEY` for `provider = "minimax"`), wiki path does not exist at `/wiki`, or host port already in use (stop any running `synthadoc serve` instance for the same wiki first).

**Permission denied on wiki files**

The container user (uid 1000) cannot write to the mounted directory. See [Appendix D: File Permissions on Linux Hosts](#d-file-permissions-on-linux-hosts).

**Port already in use**

Another process (or a running `synthadoc serve` for this wiki) is already on that port. Stop it first, or install a second wiki on a different port and use `-p 7071:7071` for it.

**Health check shows `unhealthy`**

```bash
docker logs history-of-computing        # check for startup errors
curl http://localhost:7070/health
```

If the server started but `/health` does not respond, the wiki may have failed validation (e.g. corrupted database). Check the logs and try `synthadoc status -w /wiki` inside the container.

**`wslc` or `container` command not found**

- `container`: requires macOS 26 (Tahoe) on Apple Silicon. Not available on Intel Macs or macOS < 26.
- `wslc`: requires WSL 2.9.3+ on Windows 11. Update WSL: `wsl --update`.

**Slow file operations on Windows**

Move the wiki folder from the Windows drive into the WSL2 filesystem. See the [Windows performance tip](#windows-11-wsl-293) above.
