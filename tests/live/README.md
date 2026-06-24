# Synthadoc Live Tests

Manual integration tests that run against a live server and LLM.  Not run by CI.

## Test suites

| File | What it tests | Checks |
|---|---|---|
| `live_cli_test.py` | 44 CLI commands via `python -m synthadoc` | 59 |
| `live_mcp_test.py` | 12 MCP tools via SSE transport | ~30 |
| `live_plugin_test.py` | 37 REST API endpoints used by the Obsidian plugin | ~40 |

## Prerequisites

1. **Python** — the command name differs by platform:

   | Platform | Command | One-time fix to use `python` everywhere |
   |---|---|---|
   | **Windows** | `python` | _(already works)_ |
   | **macOS** | `python3` | Add `alias python=python3` to `~/.zshrc`, then `source ~/.zshrc` |
   | **Linux** | `python3` | `sudo apt install python-is-python3` (Debian/Ubuntu) |

   All examples below use `python` — apply the one-time fix above on macOS/Linux
   and every example will work as written.

2. **Wiki installed**
   ```
   synthadoc install history-of-computing
   ```

3. **Server running** (the server needs the LLM API key, not the test client)
   ```
   synthadoc serve -w history-of-computing
   ```

4. **MCP client library** — required only for the MCP suite (`live_mcp_test.py`)
   ```
   pip install mcp
   ```

## Run all suites together

The simplest invocation uses whichever wiki is set as your default
(`synthadoc use`).  No flags required:

```
python -X utf8 tests/live/run_all.py
```

The default wiki is `history-of-computing` and the default port is 7070.
If your setup differs, override with `--wiki` and `--url` — but **the wiki
name must match what the running server is actually serving**.  The runner
validates this at startup and exits with a clear error if they don't match.

```
# Server on a non-default port
python -X utf8 tests/live/run_all.py --url http://127.0.0.1:7071

# Different wiki (server must be running for that wiki)
python -X utf8 tests/live/run_all.py --wiki my-other-wiki --url http://127.0.0.1:7072
```

### One suite only

```
python -X utf8 tests/live/run_all.py --suite cli
python -X utf8 tests/live/run_all.py --suite mcp
python -X utf8 tests/live/run_all.py --suite plugin
```

### Two suites, skip one

```
python -X utf8 tests/live/run_all.py --suite cli --suite plugin
```

## Run suites individually

### CLI test

```
python -X utf8 tests/live/live_cli_test.py
python -X utf8 tests/live/live_cli_test.py --help
```

PowerShell / bash — set via environment variable instead of flags:

```powershell
# PowerShell
$env:SYNTHADOC_URL = "http://127.0.0.1:7070/"
python -X utf8 tests/live/live_cli_test.py
```

```bash
# bash
SYNTHADOC_URL=http://127.0.0.1:7070/ python -X utf8 tests/live/live_cli_test.py
```

### MCP test

```
python -X utf8 tests/live/live_mcp_test.py
```

```powershell
# PowerShell
$env:MCP_URL = "http://127.0.0.1:7070/mcp/sse"
python -X utf8 tests/live/live_mcp_test.py
```

```bash
# bash
MCP_URL=http://127.0.0.1:7070/mcp/sse python -X utf8 tests/live/live_mcp_test.py
```

### Plugin REST API test

```
python -X utf8 tests/live/live_plugin_test.py
python -X utf8 tests/live/live_plugin_test.py --help
```

```powershell
# PowerShell
$env:SYNTHADOC_URL = "http://127.0.0.1:7070"
python -X utf8 tests/live/live_plugin_test.py
```

```bash
# bash
SYNTHADOC_URL=http://127.0.0.1:7070 python -X utf8 tests/live/live_plugin_test.py
```

## Environment variables

| Variable | Default | Used by |
|---|---|---|
| `SYNTHADOC_URL` | `http://127.0.0.1:7070/` | CLI test, plugin test |
| `WIKI_NAME` | `history-of-computing` | CLI test, plugin test |
| `MCP_URL` | `http://127.0.0.1:7070/mcp/sse` | MCP test |

CLI flags (`--url`, `--wiki`) override environment variables.

## Output format

Each check prints one of:
- `[PASS]` — assertion met
- `[WARN]` — soft quality issue; does not fail the run
- `[FAIL]` — assertion failed; exits non-zero

A results summary is printed at the end of each suite.

## Side effects and rollback

All tests are designed to leave the wiki in its original state:

| Test | Side effect | Rollback |
|---|---|---|
| CLI | `candidates/` — 2 temp pages created | deleted in `finally` block |
| CLI | lifecycle — 1 archived page round-trips | ends back in `archived` state |
| CLI | `ingest` — uses `--analyse-only` | no wiki page written |
| CLI | `schedule` — temp entry added | removed after test |
| Plugin | `candidates/` — 2 temp pages created | deleted in `finally` block |
| Plugin | lifecycle — 1 archived page round-trips (creates one temporarily if none exist) | ends back in original state |
| Plugin | staging policy — changed to `off` | restored before test ends |
| MCP | `synthadoc_write_page` — content modified | original content restored |
| MCP | lifecycle — 1 active page marked stale | restored to `active` |