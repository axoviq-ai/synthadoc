# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import re
import yaml
from pathlib import Path
from typing import Optional

import typer

from synthadoc.cli.main import app
from synthadoc.cli._http import post

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
from synthadoc.agents.lint_agent import LINT_SKIP_SLUGS


def _is_reingestable(file: str) -> bool:
    """True only for sources the CLI can actually re-ingest: absolute paths or URLs.

    Relative paths are placeholder entries (e.g. in demo wiki pages) and cannot
    be resolved without knowing the wiki's raw_sources directory.
    """
    if not file:
        return False
    if file.startswith(("http://", "https://")):
        return True
    return Path(file).is_absolute()


def _parse_frontmatter(text: str) -> dict:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}
    try:
        return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}


def _index_suggestion(slug: str, fm: dict) -> str:
    title = fm.get("title") or slug.replace("-", " ").title()
    tags = fm.get("tags") or []
    if isinstance(tags, list) and tags:
        hint = ", ".join(str(t) for t in tags[:4])
    else:
        hint = title
    return f"- [[{slug}]] — {hint}"

def _sync_orphan_frontmatter(
    wiki_dir: Path,
    page_texts: dict[str, str],
    orphan_set: set[str],
) -> None:
    """Write orphan: true/false into page frontmatter so the Obsidian dashboard
    (WHERE orphan = true) stays in sync with what lint report just computed."""
    from synthadoc.agents.lint_agent import LINT_SKIP_SLUGS
    for slug, text in page_texts.items():
        if slug in LINT_SKIP_SLUGS:
            continue
        fm = _parse_frontmatter(text)
        desired = slug in orphan_set
        if fm.get("orphan", False) == desired:
            continue  # already correct — skip to avoid unnecessary disk write
        # Rewrite only the orphan key in the frontmatter block
        path = wiki_dir / f"{slug}.md"
        m = _FRONTMATTER_RE.match(text)
        if not m:
            continue
        try:
            fm_data = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            continue
        fm_data["orphan"] = desired
        new_fm = yaml.dump(fm_data, default_flow_style=False, allow_unicode=True).rstrip()
        new_text = f"---\n{new_fm}\n---" + text[m.end():]
        path.write_text(new_text, encoding="utf-8")


lint_app = typer.Typer(help="Lint the wiki for contradictions and orphans.")
app.add_typer(lint_app, name="lint")


@lint_app.command("run")
def lint_cmd(
    scope: str = typer.Option("all", "--scope", help="all/contradictions/orphans/stale"),
    auto_resolve: bool = typer.Option(False, "--auto-resolve"),
    no_adversarial: bool = typer.Option(False, "--no-adversarial",
                                         help="Skip adversarial review and clear existing lint_warnings"),
    no_lifecycle: bool = typer.Option(False, "--no-lifecycle",
                                      help="Skip lifecycle checks (draft promotion, stale detection)."),
    check_urls: bool = typer.Option(False, "--check-urls",
                                    help="Check URL source availability via HTTP HEAD (adds network calls)"),
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
):
    """Enqueue a lint job. Requires synthadoc serve to be running."""
    from synthadoc.cli._wiki import resolve_wiki
    wiki = resolve_wiki(wiki)
    payload: dict = {
        "scope": scope,
        "auto_resolve": auto_resolve,
        "adversarial": not no_adversarial,
        "lifecycle": not no_lifecycle,
    }
    if check_urls:
        payload["check_url_availability"] = True
    result = post(wiki, "/jobs/lint", payload)
    typer.echo(f"Lint enqueued -> job {result['job_id']}")
    w_flag = f" -w {wiki}" if wiki != "." else ""
    typer.echo(f"Check status: synthadoc jobs status {result['job_id']}{w_flag}")
    typer.echo(f"View results: synthadoc lint report{w_flag}")
    if no_adversarial:
        typer.echo("ℹ️  Adversarial pass skipped — lint_warnings cleared from all pages.")


@lint_app.command("report")
def lint_report(
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
):
    """Show current contradictions and orphan pages — no server required.

    Reads wiki files directly. Run after 'synthadoc lint' completes to see
    what needs your attention.
    """
    from synthadoc.cli._wiki import resolve_wiki
    from synthadoc.cli.install import resolve_wiki_path
    wiki = resolve_wiki(wiki)

    wiki_dir = resolve_wiki_path(wiki) / "wiki"
    if not wiki_dir.exists():
        from synthadoc import errors as E
        E.cli_error(E.WIKI_NOT_FOUND, f"Wiki directory not found: {wiki_dir}")

    pages = list(wiki_dir.glob("*.md"))
    page_texts: dict[str, str] = {p.stem: p.read_text(encoding="utf-8") for p in pages}

    from synthadoc.storage.wiki import WikiStorage
    from synthadoc.agents.lint_agent import read_current_lint_state
    _state = read_current_lint_state(WikiStorage(wiki_dir))
    contradicted = _state.contradicted
    orphans = _state.orphans

    # Augment adv_pages with re-ingest suggestions (CLI-only)
    adv_pages = []
    for entry in _state.adv_pages:
        slug = entry["slug"]
        fm = _parse_frontmatter(page_texts.get(slug, ""))
        sources = fm.get("sources", []) or []
        suggested_reingests = [
            f'synthadoc ingest "{s["file"]}" -w {wiki}'
            for s in sources
            if isinstance(s, dict) and _is_reingestable(s.get("file", ""))
        ]
        adv_pages.append({**entry, "suggested_reingests": suggested_reingests})

    # --- Citation Issues ---
    from synthadoc.agents.lint_agent import _check_page_citations
    from synthadoc.cli.install import resolve_wiki_path
    from synthadoc.storage.wiki import WikiPage as _WP, SourceRef as _SR
    extracted_dir = resolve_wiki_path(wiki) / ".synthadoc" / "extracted"
    citation_issues: list[dict] = []
    for stem, text in page_texts.items():
        if stem in LINT_SKIP_SLUGS:
            continue
        fm = _parse_frontmatter(text)
        m = _FRONTMATTER_RE.match(text)
        body = text[m.end():] if m else text
        sources = [
            _SR(file=s.get("file", ""), hash=s.get("hash", ""),
                size=s.get("size", 0), ingested=s.get("ingested", ""))
            for s in (fm.get("sources") or [])
            if isinstance(s, dict)
        ]
        fake_page = _WP(
            title=stem, tags=[], content=body,
            status=fm.get("status", ""), confidence=fm.get("confidence", "medium"),
            sources=sources,
        )
        citation_issues.extend(_check_page_citations(stem, fake_page, extracted_dir))

    truncated_pages = _state.truncated_pages  # [{slug, file, size}]

    # --- Report ---
    has_issues = contradicted or orphans or adv_pages or citation_issues or truncated_pages
    if not has_issues:
        # Still sync frontmatter to clear stale orphan: true flags from previous runs.
        _sync_orphan_frontmatter(wiki_dir, page_texts, set())
        typer.echo("All clear — no contradictions, orphan pages, adversarial warnings, or truncated sources found.")
        return

    if contradicted:
        typer.echo(f"\nContradicted pages ({len(contradicted)}) - need review:\n")
        for slug in contradicted:
            fm = _parse_frontmatter(page_texts.get(slug, ""))
            typer.echo(f"  {slug}")
            if fm.get("contradiction_note"):
                typer.echo(f"    Why flagged: {fm['contradiction_note']}")
            if fm.get("unresolved_note"):
                typer.echo(f"    Auto-resolve failed: {fm['unresolved_note']}")
            typer.echo(f"    -> Open wiki/{slug}.md, resolve the conflict, then set status: active")
            typer.echo(f"    -> Or re-run: synthadoc lint -w {wiki} --auto-resolve")

    if orphans:
        typer.echo(f"\nOrphan pages ({len(orphans)}) - no inbound links:\n")
        for slug in orphans:
            fm = _parse_frontmatter(page_texts.get(slug, ""))
            suggestion = _index_suggestion(slug, fm)
            typer.echo(f"  {slug}")
            typer.echo(f"    -> Add [[{slug}]] to a related content page, e.g.:")
            typer.echo(f"         {suggestion}")

    if adv_pages:
        total_warnings = sum(len(p["warnings"]) for p in adv_pages)
        typer.echo(f"\nAdversarial Warnings ({total_warnings} across {len(adv_pages)} pages):\n")
        for entry in adv_pages:
            typer.echo(f"  {entry['slug']} ({len(entry['warnings'])} warning(s))")
            for w in entry["warnings"]:
                if w.get("claim"):
                    typer.echo(f"    [!] \"{w['claim']}\"")
                concern = w.get("concern") or "(no concern text)"
                typer.echo(f"       Concern: {concern}")
            if entry["suggested_reingests"]:
                typer.echo("    Tip: If the source has updated content, re-ingest with --force to refresh:")
                for cmd in entry["suggested_reingests"]:
                    typer.echo(f"       {cmd} --force")

    if citation_issues:
        by_slug: dict = {}
        for issue in citation_issues:
            by_slug.setdefault(issue["slug"], []).append(issue)
        total = len(citation_issues)
        typer.echo(f"\nCitation Issues ({total} across {len(by_slug)} pages):\n")
        for slug, issues in by_slug.items():
            typer.echo(f"  {slug}")
            for iss in issues:
                typer.echo(f"    {iss['citation']} — {iss['reason']}")

    if truncated_pages:
        try:
            from synthadoc.config import load_config as _load_cfg
            _default_max = getattr(getattr(_load_cfg(), "ingest", None), "max_source_chars", 32000)
        except Exception:
            _default_max = 32000
        typer.echo(f"\nTruncated Sources ({len(truncated_pages)}) - source exceeded ingest limit:\n")
        for entry in truncated_pages:
            size = entry.get("size") or 0
            suggested = size * 2 if size else _default_max * 2
            typer.echo(f"  {entry['slug']} — source exceeded limit ({size:,} chars)")
            typer.echo(f"    Source: {entry['file']}")
            typer.echo(f"    💡 Re-ingest with a higher limit:")
            typer.echo(f"       synthadoc ingest \"{entry['file']}\" -w {wiki} --max-source-chars {suggested}")

    # Sync orphan: true/false frontmatter so the Obsidian dashboard Dataview
    # query (WHERE orphan = true) reflects the same result as this report.
    _sync_orphan_frontmatter(wiki_dir, page_texts, set(orphans))

    adv_count = sum(len(p["warnings"]) for p in adv_pages)
    typer.echo(
        f"\n{len(contradicted)} contradiction(s), {len(orphans)} orphan(s), "
        f"{adv_count} adversarial warning(s), {len(citation_issues)} citation issue(s), "
        f"{len(truncated_pages)} truncated source(s)."
        f"\nDashboard: open wiki/dashboard.md in Obsidian for a live view."
    )
