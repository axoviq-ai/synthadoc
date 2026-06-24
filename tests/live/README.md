# Synthadoc Live Tests

Manual integration tests that run against a live server and LLM.  Not run by CI.

## Test suites

| File | What it tests | Checks |
|---|---|---|
| `live_cli_test.py` | 44 CLI commands via `python -m synthadoc` | 59 |
| `live_mcp_test.py` | 12 MCP tools via SSE transport | ~30 |
| `live_plugin_test.py` | 37 REST API endpoints used by the Obsidian plugin | ~40 |

## Prerequisites

1. **Wiki installed**
   ```
   synthadoc install history-of-computing
   ```

2. **Server running**
   ```
   synthadoc serve -w history-of-computing
   ```

3. **LLM API key** — e.g. `ANTHROPIC_API_KEY` in the environment

4. **MCP client library** (MCP test only)
   ```
   pip install mcp
   ```

## Run all suites together

```powershell
# PowerShell
python -X utf8 tests/live/run_all.py

# bash / macOS / Linux
python -X utf8 tests/live/run_all.py
```

### Different wiki or port

```powershell
python -X utf8 tests/live/run_all.py --wiki ai-research --url http://127.0.0.1:7071
```

### One suite only

```powershell
python -X utf8 tests/live/run_all.py --suite cli
python -X utf8 tests/live/run_all.py --suite mcp
python -X utf8 tests/live/run_all.py --suite plugin
```

### Two suites, skip one

```powershell
python -X utf8 tests/live/run_all.py --suite cli --suite plugin
```

## Run suites individually

### CLI test

```powershell
# PowerShell
$env:SYNTHADOC_URL = "http://127.0.0.1:7070/"
python -X utf8 tests/live/live_cli_test.py

# bash
SYNTHADOC_URL=http://127.0.0.1:7070/ python -X utf8 tests/live/live_cli_test.py

# With flags
python -X utf8 tests/live/live_cli_test.py --wiki ai-research --url http://127.0.0.1:7071/
python -X utf8 tests/live/live_cli_test.py --help
```

### MCP test

```powershell
# PowerShell
$env:MCP_URL = "http://127.0.0.1:7070/mcp/sse"
python -X utf8 tests/live/live_mcp_test.py

# bash
MCP_URL=http://127.0.0.1:7070/mcp/sse python -X utf8 tests/live/live_mcp_test.py
```

### Plugin REST API test

```powershell
# PowerShell
$env:SYNTHADOC_URL = "http://127.0.0.1:7070"
python -X utf8 tests/live/live_plugin_test.py

# bash
SYNTHADOC_URL=http://127.0.0.1:7070 python -X utf8 tests/live/live_plugin_test.py

# With flags
python -X utf8 tests/live/live_plugin_test.py --url http://127.0.0.1:7071 --wiki ai-research
python -X utf8 tests/live/live_plugin_test.py --help
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
| Plugin | lifecycle — 1 archived page round-trips | ends back in `archived` state |
| Plugin | staging policy — changed to `off` | restored before test ends |
| MCP | `synthadoc_write_page` — content modified | original content restored |
| MCP | lifecycle — 1 active page marked stale | restored to `active` |