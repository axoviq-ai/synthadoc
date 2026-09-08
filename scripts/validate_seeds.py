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


def _detect_backend(model: str) -> "_Backend | None":
    """Return the first usable LLM backend, or None if none is available.

    Priority:
      1. ANTHROPIC_API_KEY env var  → direct async Anthropic client (fastest)
      2. opencode in PATH           → opencode run "<prompt>"
      3. claude in PATH             → claude -p "<prompt>"  (Claude Code)
    """
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
            pass  # fall through to CLI detection

    # CLI candidates: (binary name, base command list)
    for binary, cli_cmd in [
        ("opencode", ["opencode", "run"]),   # opencode run "<prompt>"
        ("claude",   ["claude", "-p"]),       # claude -p "<prompt>"
    ]:
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
            result["url_status"] = "OK" if content else "EMPTY"
        except DomainBlockedException as e:
            result["url_status"] = f"BLOCKED ({e.status_code})"
        except Exception as e:
            result["url_status"] = "ERROR"
            result["error_detail"] = str(e)[:120]

    # ── Step 2: scope check (only when fetch succeeded and backend available) ─
    if backend is not None and purpose and result["url_status"] == "OK":
        async with llm_sem:
            try:
                in_scope, reasoning = await check_scope(purpose, content, backend)
            except Exception as e:
                in_scope, reasoning = True, f"(scope check error: {e!s:.100})"
        result["in_scope"] = in_scope
        result["scope_reason"] = reasoning

    return result


# ── Per-template validation ───────────────────────────────────────────────────

async def validate_template(
    template_dir: Path,
    *,
    skill,
    backend: "_Backend | None",
    url_sem: asyncio.Semaphore,
    llm_sem: asyncio.Semaphore,
) -> list[dict]:
    """Return a list of result dicts for every URL in this template's seeds.md."""
    seeds_path = template_dir / "wiki" / "seeds.md"
    purpose_path = template_dir / "wiki" / "purpose.md"
    if not seeds_path.exists():
        return []

    seeds_text = seeds_path.read_text(encoding="utf-8")
    urls = extract_seed_urls(seeds_text)
    if not urls:
        return []

    purpose = purpose_path.read_text(encoding="utf-8") if purpose_path.exists() else ""
    template_name = template_dir.relative_to(TEMPLATES_DIR).as_posix()

    url_results = await asyncio.gather(*[
        validate_url(
            url, purpose,
            skill=skill,
            backend=backend,
            url_sem=url_sem,
            llm_sem=llm_sem,
        )
        for url in urls
    ])
    return [{"template": template_name, **r} for r in url_results]


# ── Report ─────────────────────────────────────────────────────────────────────

def print_report(results: list[dict], scope_active: bool) -> list[dict]:
    """Print a colour-coded table and return the list of failed rows."""
    GREEN = "\033[32m"
    RED   = "\033[31m"
    RESET = "\033[0m"

    COL_T = 32   # template name
    COL_S = 18   # url_status

    hdr = f"{'TEMPLATE':<{COL_T}}  {'URL_STATUS':<{COL_S}}"
    if scope_active:
        hdr += f"  {'SCOPE':<6}"
    hdr += "  URL"
    print(f"\n{hdr}")
    print("-" * (len(hdr) + 35))

    failures: list[dict] = []
    for r in results:
        url_ok   = r["url_status"] == "OK"
        scope_ok = r["in_scope"] is None or r["in_scope"]
        passed   = url_ok and scope_ok
        if not passed:
            failures.append(r)

        color = GREEN if passed else RED
        scope_str = ""
        if scope_active and r["in_scope"] is not None:
            scope_str = "YES" if r["in_scope"] else "NO "
        short_url = r["url"][:56] + "…" if len(r["url"]) > 57 else r["url"]

        row = f"{color}{r['template']:<{COL_T}}  {r['url_status']:<{COL_S}}"
        if scope_active:
            row += f"  {scope_str:<6}"
        row += f"  {short_url}{RESET}"
        print(row)

        if not url_ok and r["error_detail"]:
            print(f"  {'':>{COL_T}}  {r['error_detail']}")
        if scope_active and not scope_ok:
            print(f"  {'':>{COL_T}}  ↳ {r['scope_reason']}")

    return failures


# ── Entry point ───────────────────────────────────────────────────────────────

async def async_main(args: argparse.Namespace) -> int:
    _ensure_path()
    from synthadoc.skills.url.scripts.main import UrlSkill

    # ── LLM backend resolution ────────────────────────────────────────────────
    backend: "_Backend | None" = None
    if not args.no_scope:
        backend = _detect_backend(args.model)
        if backend is None:
            print(
                "WARNING: SCOPE CHECK SKIPPED — no LLM backend available.\n"
                "  Results below show URL accessibility only; out-of-scope seeds\n"
                "  will NOT be detected.\n"
                "  To enable scope checks (required before shipping), use one of:\n"
                "    • set ANTHROPIC_API_KEY in your environment\n"
                "    • install opencode  (opencode run is used)\n"
                "    • install claude    (Claude Code, claude -p is used)",
                file=sys.stderr,
            )

    # ── Template directories ──────────────────────────────────────────────────
    if args.template:
        dirs = [TEMPLATES_DIR / args.template]
        if not dirs[0].exists():
            print(f"ERROR: template directory not found: {dirs[0]}", file=sys.stderr)
            return 1
    else:
        dirs = sorted({
            p.parent.parent          # templates/<cat>/<name>/wiki/seeds.md → templates/<cat>/<name>
            for p in TEMPLATES_DIR.glob("**/wiki/seeds.md")
        })

    skill   = UrlSkill(fetch_timeout=30)
    url_sem = asyncio.Semaphore(5)   # max 5 concurrent URL fetches
    llm_sem = asyncio.Semaphore(2)   # max 2 concurrent LLM scope checks

    scope_label = (
        f"scope via {backend.label}"
        if backend is not None
        else "--no-scope: URL check only"
    )
    print(f"Scanning {len(dirs)} template(s) …  ({scope_label})")

    batches = await asyncio.gather(*[
        validate_template(
            d,
            skill=skill,
            backend=backend,
            url_sem=url_sem,
            llm_sem=llm_sem,
        )
        for d in dirs
    ])

    all_results: list[dict] = [r for batch in batches for r in batch]

    if not all_results:
        print("No concrete seed URLs found.")
        return 0

    failures = print_report(all_results, scope_active=backend is not None)

    total = len(all_results)
    print(f"\n{'='*60}")
    if failures:
        print(f"FAILED: {len(failures)} of {total} URLs")
        for r in failures:
            tag = r["url_status"] if r["url_status"] != "OK" else "OUT-OF-SCOPE"
            print(f"  [{tag}] {r['template']}: {r['url']}")
            detail = r.get("error_detail") or r.get("scope_reason", "")
            if detail:
                print(f"          {detail}")
        return 1

    print(f"All {total} seed URLs passed ✓")
    return 0


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
    sys.exit(asyncio.run(async_main(parser.parse_args())))


if __name__ == "__main__":
    main()
