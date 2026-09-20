# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""
validate_seeds.py  — Scan all template seeds.md and verify each concrete
ingest URL is (1) accessible via UrlSkill and (2) in-scope per purpose.md.

Usage:
  python scripts/validate_seeds.py                        # all templates
  python scripts/validate_seeds.py --template real-estate/investment
  python scripts/validate_seeds.py --no-scope             # URL check only

Exit code: 0 = all pass, 1 = any failure.

Why two checks?
  1. URL accessibility  — UrlSkill is the actual fetch path used by synthadoc
     ingest.  A blocked (403/429) or empty response causes a skip just as it
     would in production.
  2. Scope alignment    — replicates the LLM purpose-block prepended to the
     ingest decision prompt.  A page whose text is outside the wiki's stated
     domain receives action='skip' in production; this script catches that
     before a user hits it on a fresh wiki.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import sys
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────

# This script lives in  <repo>/scripts/validate_seeds.py
# Repo root is one level up; synthadoc package is at <repo>/synthadoc/
REPO_ROOT = Path(__file__).parent.parent
TEMPLATES_DIR = REPO_ROOT / "synthadoc" / "templates"

_SYS_PATH_SET = False


def _ensure_path() -> None:
    global _SYS_PATH_SET
    if not _SYS_PATH_SET:
        sys.path.insert(0, str(REPO_ROOT))
        _SYS_PATH_SET = True


# ── Content-quality threshold ─────────────────────────────────────────────────

# URLs that return HTTP 200 but fewer than this many characters are treated as
# THIN (challenge pages, paywall stubs, empty navigation shells).  The ingest
# agent would skip them anyway; we surface them here before users hit the wall.
_MIN_CONTENT_CHARS = 500

# ── Login / paywall wall detection ───────────────────────────────────────────

# Some sites redirect 200 → a login or subscribe page instead of raising 401/403.
# These patterns are matched against the first 3 000 characters of extracted text.
# A match sets url_status = "LOGIN_WALL" and counts as a failure, because the
# ingest agent would receive the same gated content and skip the page.
_LOGIN_WALL_RE = re.compile(
    r"""
    (?:
        please\s+(?:sign|log)\s*(?:-\s*)?in\b                                   # "please sign in"
      | (?:sign|log)\s*(?:-\s*)?in\s+(?:to\s+access|is\s+required|required)     # "sign in required"
      | you\s+(?:must|need\s+to)\s+(?:be\s+)?(?:signed|logged)\s*[-\s]?in      # "you must be logged in"
      | (?:this\s+)?(?:page|content|article|resource)\s+(?:is\s+)?(?:available\s+only|requires?)\s+(?:to\s+)?(?:subscribers?|members?|registered\s+users?)
      | (?:subscribe|subscription)\s+(?:to\s+access|required\s+to)              # "subscribe to access"
      | (?:access\s+denied|not\s+authorized\s+to\s+access)                      # hard auth errors
      | authentication\s+required                                                # "authentication required"
      | \bpaywall\b                                                              # explicit paywall mention
      | restricted\s+to\s+(?:subscribers?|members?|registered\s+users?)         # "restricted to members"
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

# ── URL extraction from seeds.md ──────────────────────────────────────────────

_INGEST_URL_RE = re.compile(r'synthadoc\s+ingest\s+"(https?://[^"]+)"')
_PLACEHOLDER_RE = re.compile(r"<[^>]+>")


def extract_seed_urls(seeds_text: str) -> list[str]:
    """Return concrete https URLs from ``synthadoc ingest`` commands.

    Skips:
    - local file paths (no http scheme)
    - user-placeholder URLs that contain ``<param>`` tokens
    """
    urls: list[str] = []
    for m in _INGEST_URL_RE.finditer(seeds_text):
        url = m.group(1)
        if _PLACEHOLDER_RE.search(url):
            continue
        urls.append(url)
    return urls


# ── Scope check ───────────────────────────────────────────────────────────────

# Mirrors the purpose_block prepended to _DECISION_PROMPT in ingest_agent.py.
# The ingest agent uses action="skip" for out-of-scope content; this prompt
# reduces that to a binary yes/no so we can report it without writing pages.
_SCOPE_PROMPT = """\
You maintain a knowledge wiki. Decide whether a new source document is in scope.

Wiki scope (from purpose.md):
{purpose}

action="skip" means the source is completely OUTSIDE the wiki's domain \
(e.g. spam, medical receipts, unrelated e-commerce).
action="skip" must NEVER be used because a topic is already covered by an \
existing page — that is what action="update" is for.
A broad general resource (e.g. a macro-economic report covering all sectors \
when the wiki is focused on one sub-domain, or raw JSON metadata with no \
readable prose) should be action="skip" because it adds no domain-specific \
value.
A source that is clearly authored for practitioners in this specific domain \
should be action="ingest".

Source text (first 4 000 characters):
{content}

Return ONLY valid JSON (no markdown fences):
{{"action": "ingest or skip", "reasoning": "one concise sentence"}}"""

# ANSI escape sequence pattern used to strip CLI colour output
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[mGKHF]")


def _extract_json_from_text(text: str) -> dict:
    """Extract the last JSON object ``{...}`` from potentially decorated CLI output."""
    clean = _ANSI_RE.sub("", text)
    clean = re.sub(r"^```[a-z]*\s*|\s*```$", "", clean, flags=re.MULTILINE)
    # Find the last {...} block (handles preamble text some CLIs emit)
    matches = list(re.finditer(r"\{[^{}]+\}", clean, re.DOTALL))
    if not matches:
        raise ValueError(f"no JSON object in output: {clean[:200]!r}")
    return json.loads(matches[-1].group())


# ── LLM backend detection ─────────────────────────────────────────────────────

class _Backend:
    """Represents one LLM backend: either a direct async Anthropic client or a
    local CLI tool (opencode / claude).

    CLI invocation by tool:
      opencode  →  opencode run "<prompt>"
      claude    →  claude -p "<prompt>"
    """

    def __init__(
        self,
        label: str,
        client=None,          # anthropic.AsyncAnthropic | None
        cli_cmd: list = None,  # base command list; prompt appended as last arg
        model: str = "",
    ) -> None:
        self.label = label
        self._client = client
        self._cli_cmd: list = cli_cmd or []
        self._model = model

    async def complete(self, prompt: str) -> str:
        """Run the prompt and return raw text output."""
        if self._client is not None:
            resp = await self._client.messages.create(
                model=self._model,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            return (resp.content[0].text if resp.content else "").strip()

        # CLI path — prompt appended as final positional argument:
        #   opencode run "<prompt>"   or   claude -p "<prompt>"
        cmd = [*self._cli_cmd, prompt]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=90)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            raise RuntimeError(f"{self._cli_cmd[0]} timed out after 90 s")
        if proc.returncode not in (0, None):
            raise RuntimeError(
                f"{self._cli_cmd[0]} exited {proc.returncode}"
            )
        return stdout.decode(errors="replace").strip()


def _detect_backend(model: str, prefer: str = "auto") -> "_Backend | None":
    """Return the requested (or first usable) LLM backend.

    prefer values:
      "auto"       — try anthropic-sdk → opencode → claude in order
      "anthropic"  — force ANTHROPIC_API_KEY / anthropic SDK
      "opencode"   — force opencode CLI
      "claude"     — force claude -p (Claude Code CLI)
    """
    if prefer in ("auto", "anthropic"):
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if api_key:
            try:
                import anthropic
                return _Backend(
                    label="anthropic-sdk",
                    client=anthropic.AsyncAnthropic(api_key=api_key),
                    model=model,
                )
            except ImportError:
                if prefer == "anthropic":
                    return None  # explicitly requested but unavailable
        elif prefer == "anthropic":
            return None

    cli_candidates = [
        ("opencode", ["opencode", "run"]),
        ("claude",   ["claude", "-p"]),
    ]
    if prefer in ("opencode", "claude"):
        cli_candidates = [(b, c) for b, c in cli_candidates if b == prefer]

    for binary, cli_cmd in cli_candidates:
        if shutil.which(binary):
            return _Backend(label=binary, cli_cmd=cli_cmd)

    return None


async def check_scope(
    purpose: str,
    content: str,
    backend: "_Backend",
) -> tuple[bool, str]:
    """Return ``(in_scope, reasoning)`` from an LLM scope check.

    Uses action="skip"/"ingest" to mirror the ingest agent's decision prompt
    framing, which is stricter than a binary yes/no about general relevance.
    """
    prompt = _SCOPE_PROMPT.format(
        purpose=purpose.strip()[:4_000],
        content=content[:4_000],
    )
    raw = await backend.complete(prompt)
    try:
        data = _extract_json_from_text(raw)
        action = str(data.get("action", "ingest")).strip().lower()
        in_scope = action != "skip"
        return in_scope, str(data.get("reasoning", ""))
    except (json.JSONDecodeError, ValueError):
        # Treat parse failure as pass so we do not create false negatives
        return True, f"(JSON parse error — treating as pass; raw={raw[:80]!r})"


# ── Per-URL validation ────────────────────────────────────────────────────────

async def validate_url(
    url: str,
    purpose: str,
    *,
    skill: "UrlSkill",
    backend: "_Backend | None",
    url_sem: asyncio.Semaphore,
    llm_sem: asyncio.Semaphore,
) -> dict:
    """Fetch ``url`` and optionally scope-check it.  Returns a result dict."""
    from synthadoc.skills.base import DomainBlockedException

    result: dict = {
        "url": url,
        "url_status": "",
        "chars": 0,
        "in_scope": None,
        "scope_reason": "",
        "error_detail": "",
    }

    # ── Step 1: URL accessibility ────────────────────────────────────────────
    content = ""
    async with url_sem:
        try:
            extracted = await skill.extract(url)
            content = extracted.text.strip()
            result["chars"] = len(content)
            if not content:
                result["url_status"] = "EMPTY"
            elif len(content) < _MIN_CONTENT_CHARS:
                result["url_status"] = "THIN"
            else:
                m = _LOGIN_WALL_RE.search(content[:3_000])
                if m:
                    result["url_status"] = "LOGIN_WALL"
                    result["error_detail"] = f"auth/paywall pattern: {m.group().strip()!r}"
                else:
                    result["url_status"] = "OK"
        except DomainBlockedException as e:
            result["url_status"] = f"BLOCKED ({e.status_code})"
        except Exception as e:
            result["url_status"] = "ERROR"
            result["error_detail"] = str(e)[:120]

    # ── Step 2: scope check (only when content is substantive and backend available) ─
    if backend is not None and purpose and result["url_status"] == "OK":
        async with llm_sem:
            try:
                in_scope, reasoning = await check_scope(purpose, content, backend)
            except Exception as e:
                in_scope, reasoning = True, f"(scope check error: {e!s:.100})"
        result["in_scope"] = in_scope
        result["scope_reason"] = reasoning

    return result


# ── Progress tracker ─────────────────────────────────────────────────────────

class _Progress:
    """Thread-safe-enough (asyncio is single-threaded) URL progress counter."""

    _GREEN = "\033[32m"
    _RED   = "\033[31m"
    _YEL   = "\033[33m"
    _RESET = "\033[0m"

    def __init__(self, total: int) -> None:
        self.done = 0
        self.total = total

    def tick(self, template: str, result: dict) -> None:
        self.done += 1
        url_ok   = result["url_status"] == "OK"
        scope_ok = result["in_scope"] is None or result["in_scope"]
        passed   = url_ok and scope_ok

        if not url_ok:
            status = result["url_status"]
            color  = self._YEL if result["url_status"].startswith("BLOCKED") else self._RED
        elif not scope_ok:
            status = "OUT-OF-SCOPE"
            color  = self._RED
        else:
            status = "OK"
            color  = self._GREEN

        url = result["url"]
        short_url = url[:68] + "…" if len(url) > 69 else url
        print(
            f"  {color}[{self.done:>3}/{self.total}] "
            f"{template:<32} {status:<14} {short_url}{self._RESET}",
            flush=True,
        )


# ── Per-template validation ───────────────────────────────────────────────────

async def validate_template(
    template_dir: Path,
    *,
    skill,
    backend: "_Backend | None",
    url_sem: asyncio.Semaphore,
    llm_sem: asyncio.Semaphore,
    progress: "_Progress | None" = None,
) -> list[dict]:
    """Return a list of result dicts for every URL in this template's seeds.md."""
    seeds_path = template_dir / "seeds.md"
    purpose_path = template_dir / "wiki" / "purpose.md"
    if not seeds_path.exists():
        return []

    seeds_text = seeds_path.read_text(encoding="utf-8")
    urls = extract_seed_urls(seeds_text)
    if not urls:
        return []

    purpose = purpose_path.read_text(encoding="utf-8") if purpose_path.exists() else ""
    template_name = template_dir.relative_to(TEMPLATES_DIR).as_posix()

    async def _run(url: str) -> dict:
        result = await validate_url(
            url, purpose,
            skill=skill,
            backend=backend,
            url_sem=url_sem,
            llm_sem=llm_sem,
        )
        if progress is not None:
            progress.tick(template_name, result)
        return result

    url_results = await asyncio.gather(*[_run(url) for url in urls])
    return [{"template": template_name, **r} for r in url_results]


# ── Report ─────────────────────────────────────────────────────────────────────

def collect_failures(results: list[dict]) -> list[dict]:
    """Return only the failed rows (inaccessible or out-of-scope)."""
    failures = []
    for r in results:
        url_ok   = r["url_status"] == "OK"
        scope_ok = r["in_scope"] is None or r["in_scope"]
        if not (url_ok and scope_ok):
            failures.append(r)
    return failures


def print_summary(all_results: list[dict], failures: list[dict]) -> None:
    """Print a compact failure list and suggested fix commands."""
    RED   = "\033[31m"
    RESET = "\033[0m"

    total   = len(all_results)
    n_fail  = len(failures)
    n_pass  = total - n_fail

    print(f"\n{'='*60}")
    print(f"{n_pass}/{total} URLs passed" + (f", {n_fail} failed" if n_fail else ""))

    if not failures:
        return

    print(f"\nFailed URLs:")
    for r in failures:
        tag = r["url_status"] if r["url_status"] != "OK" else "OUT-OF-SCOPE"
        from urllib.parse import urlparse
        domain = urlparse(r["url"]).netloc or r["url"]
        print(f"  {RED}[{tag}] {r['template']}  {domain}{RESET}")
        print(f"         {r['url']}")
        detail = r.get("error_detail") or r.get("scope_reason", "")
        if detail:
            print(f"         ↳ {detail}")

    # Deduplicate failing templates and emit ready-to-run fix commands.
    failing_templates = sorted({r["template"] for r in failures})
    print(f"\nTo fix, re-run the refresh script for each failing template:")
    for tmpl in failing_templates:
        print(f"  python scripts/refresh_search_seeds.py --template {tmpl}")


# ── Entry point ───────────────────────────────────────────────────────────────

async def async_main(args: argparse.Namespace) -> int:
    _ensure_path()
    from synthadoc.skills.url.scripts.main import UrlSkill

    # ── LLM backend resolution ────────────────────────────────────────────────
    backend: "_Backend | None" = None
    if not args.no_scope:
        backend = _detect_backend(args.model, prefer=args.backend)
        if backend is None:
            print(
                "ERROR: SCOPE CHECK REQUIRED but no LLM backend is available.\n"
                "  Without scope checks, out-of-scope seeds will NOT be detected\n"
                "  (this is how a zoning-board URL ended up in finance/banking).\n"
                "  Fix one of:\n"
                "    • set ANTHROPIC_API_KEY in your environment\n"
                "    • install opencode  (opencode run is used)\n"
                "    • install claude    (Claude Code, claude -p is used)\n"
                "  To skip scope checks explicitly:  --no-scope",
                file=sys.stderr,
            )
            return 1

    # ── Template directories ──────────────────────────────────────────────────
    if args.template:
        dirs = [TEMPLATES_DIR / args.template]
        if not dirs[0].exists():
            print(f"ERROR: template directory not found: {dirs[0]}", file=sys.stderr)
            return 1
    else:
        dirs = sorted({
            p.parent                 # templates/<cat>/<name>/seeds.md → templates/<cat>/<name>
            for p in TEMPLATES_DIR.glob("*/*/seeds.md")
        })

    skill   = UrlSkill(fetch_timeout=30)
    url_sem = asyncio.Semaphore(5)   # max 5 concurrent URL fetches
    llm_sem = asyncio.Semaphore(2)   # max 2 concurrent LLM scope checks

    scope_label = (
        f"scope via {backend.label}"
        if backend is not None
        else "--no-scope: URL check only"
    )

    # Count total URLs upfront so the progress counter shows [n/total].
    total_urls = sum(
        len(extract_seed_urls((d / "seeds.md").read_text(encoding="utf-8")))
        for d in dirs
        if (d / "seeds.md").exists()
    )
    print(
        f"Scanning {total_urls} URL(s) across {len(dirs)} template(s)  ({scope_label})"
    )

    progress = _Progress(total_urls)
    batches = await asyncio.gather(*[
        validate_template(
            d,
            skill=skill,
            backend=backend,
            url_sem=url_sem,
            llm_sem=llm_sem,
            progress=progress,
        )
        for d in dirs
    ])

    all_results: list[dict] = [r for batch in batches for r in batch]

    if not all_results:
        print("No concrete seed URLs found.")
        return 0

    failures = collect_failures(all_results)
    print_summary(all_results, failures)
    return 1 if failures else 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Validate synthadoc template seed URLs — checks URL accessibility "
            "and in-scope alignment with purpose.md."
        )
    )
    parser.add_argument(
        "--template", metavar="NAME",
        help="Validate a single template (e.g. real-estate/investment). "
             "Omit to scan all templates.",
    )
    parser.add_argument(
        "--no-scope", action="store_true",
        help="Skip the LLM scope check (URL accessibility only).",
    )
    parser.add_argument(
        "--model", default="claude-haiku-4-5-20251001",
        metavar="MODEL_ID",
        help="Model used for LLM scope checks (default: claude-haiku-4-5-20251001).",
    )
    parser.add_argument(
        "--backend",
        choices=["auto", "anthropic", "opencode", "claude"],
        default="auto",
        help=(
            "LLM backend for scope checks: "
            "'auto' tries anthropic-sdk → opencode → claude in order (default); "
            "'anthropic' forces ANTHROPIC_API_KEY / SDK; "
            "'opencode' forces opencode CLI; "
            "'claude' forces claude -p (Claude Code CLI)."
        ),
    )
    sys.exit(asyncio.run(async_main(parser.parse_args())))


if __name__ == "__main__":
    main()
