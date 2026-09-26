#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""
OKF Consumer Agent — standalone demo.

Reads an OKF v0.2 bundle directory and answers domain questions using only
the OKF contract. Zero Synthadoc imports — proves any OKF-aware agent
works against a Synthadoc-exported bundle without modification.

Usage:
    python tests/integration/okf_consumer_agent.py \\
        --bundle exports/history-okf \\
        --question "Who pioneered compiler development and what did they build?"

    python tests/integration/okf_consumer_agent.py \\
        --bundle exports/history-okf \\
        --question "List all computing pioneers" \\
        --type person
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: pip install pyyaml")

try:
    import anthropic
except ImportError:
    anthropic = None  # type: ignore[assignment]


def parse_okf_file(path: Path) -> tuple[dict, str]:
    """Parse an OKF markdown file into (frontmatter_dict, body_str)."""
    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            fm = yaml.safe_load(parts[1]) or {}
            body = parts[2].strip()
            return fm, body
    return {}, text.strip()


def load_bundle(bundle_dir: Path, type_filter: str | None = None) -> list[dict]:
    """Load all concept files from an OKF bundle, optionally filtered by type."""
    concepts = []
    wiki_dir = bundle_dir / "wiki"
    if not wiki_dir.exists():
        sys.exit(f"Bundle has no 'wiki/' directory: {bundle_dir}")

    for md_file in sorted(wiki_dir.glob("*.md")):
        fm, body = parse_okf_file(md_file)
        if not fm.get("type"):
            continue
        if type_filter and fm["type"] != type_filter:
            continue
        concepts.append({
            "path": str(md_file.relative_to(bundle_dir)),
            "frontmatter": fm,
            "body": body,
        })
    return concepts


def discover_types(bundle_dir: Path) -> list[str]:
    """Read index.md and return all type headings found."""
    index_path = bundle_dir / "index.md"
    if not index_path.exists():
        return []
    _, body = parse_okf_file(index_path)
    types = []
    for line in body.splitlines():
        if line.startswith("## ") and not line.startswith("## #"):
            types.append(line[3:].strip())
    return types


# ~4 chars per token; reserve ~10k tokens for system prompt + question + response
_MAX_CONTEXT_CHARS = (200_000 - 10_000) * 4


def build_context(concepts: list[dict], max_chars: int = _MAX_CONTEXT_CHARS) -> str:
    """Format OKF concepts as a grounded context block, trimmed to fit the token limit."""
    sections = []
    total_chars = 0
    included = 0
    for c in concepts:
        fm = c["frontmatter"]
        header = (
            f"### {fm.get('title', c['path'])} "
            f"(type: {fm.get('type', '?')}, source: {c['path']})"
        )
        body = c["body"]
        if fm.get("description"):
            body = fm["description"] + "\n\n" + body
        section = f"{header}\n\n{body}"
        if total_chars + len(section) > max_chars:
            omitted = len(concepts) - included
            print(
                f"[consumer-agent] Context budget reached — included {included}/{len(concepts)} pages "
                f"({omitted} omitted). Use --type to narrow the scope.",
                file=sys.stderr,
            )
            break
        sections.append(section)
        total_chars += len(section)
        included += 1
    return "\n\n---\n\n".join(sections)


_DEFAULT_MODEL_ANTHROPIC = "claude-haiku-4-5-20251001"
_DEFAULT_MODEL_OPENAI    = "gpt-4o-mini"


def _call_anthropic(system_prompt: str, user_prompt: str, model: str) -> str:
    if anthropic is None:
        sys.exit("anthropic SDK is required: pip install anthropic")
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit(
            "Error: ANTHROPIC_API_KEY environment variable is not set.\n"
            "Set it with:\n"
            "  Windows:     set ANTHROPIC_API_KEY=your-key\n"
            "  macOS/Linux: export ANTHROPIC_API_KEY='your-key'"
        )
    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return message.content[0].text


def _call_openai_compat(
    system_prompt: str, user_prompt: str, model: str, base_url: str
) -> str:
    try:
        import openai
    except ImportError:
        sys.exit("openai SDK is required for --base-url: pip install openai")
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("API_KEY") or "placeholder"
    client = openai.OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=model,
        max_tokens=1024,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
    )
    return response.choices[0].message.content or ""


def run(
    bundle_dir: Path,
    question: str,
    type_filter: str | None,
    *,
    base_url: str | None = None,
    model: str | None = None,
) -> str:
    """Run the OKF consumer agent and return the answer."""
    available_types = discover_types(bundle_dir)
    type_info = (
        f"Available knowledge types: {', '.join(available_types)}"
        if available_types else ""
    )
    if type_filter:
        type_info += f"\nFiltering to type: {type_filter}"

    concepts = load_bundle(bundle_dir, type_filter)
    if not concepts:
        return f"No concepts found in bundle (type filter: {type_filter!r})."

    context = build_context(concepts)

    system_prompt = (
        "You are a knowledge assistant. Answer questions using ONLY the provided OKF "
        "knowledge bundle. Cite the source file path for every claim you make. "
        "Do not use any external knowledge.\n\n"
        f"{type_info}"
    )
    user_prompt = (
        f"Knowledge bundle context:\n\n{context}\n\n"
        f"---\n\nQuestion: {question}"
    )

    if base_url:
        resolved_model = model or _DEFAULT_MODEL_OPENAI
        print(f"[consumer-agent] OpenAI-compatible endpoint: {base_url} | model: {resolved_model}", file=sys.stderr)
        return _call_openai_compat(system_prompt, user_prompt, resolved_model, base_url)

    resolved_model = model or _DEFAULT_MODEL_ANTHROPIC
    print(f"[consumer-agent] Anthropic | model: {resolved_model}", file=sys.stderr)
    return _call_anthropic(system_prompt, user_prompt, resolved_model)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="OKF Consumer Agent — reads an OKF bundle and answers questions."
    )
    parser.add_argument("--bundle",   required=True, help="Path to OKF bundle directory")
    parser.add_argument("--question", required=True, help="Question to answer from the bundle")
    parser.add_argument(
        "--type", dest="type_filter", default=None,
        help="Filter to pages of this OKF type (e.g. person, technology)",
    )
    parser.add_argument(
        "--base-url", dest="base_url", default=None,
        help=(
            "OpenAI-compatible base URL (e.g. https://api.minimax.chat/v1). "
            "When set, uses the openai SDK instead of anthropic. "
            "Set OPENAI_API_KEY (or API_KEY) in the environment for the key."
        ),
    )
    parser.add_argument(
        "--model", default=None,
        help=(
            f"Model name to use. Defaults to {_DEFAULT_MODEL_ANTHROPIC!r} for Anthropic "
            f"and {_DEFAULT_MODEL_OPENAI!r} for OpenAI-compatible endpoints."
        ),
    )
    args = parser.parse_args()

    bundle_dir = Path(args.bundle)
    if not bundle_dir.exists():
        sys.exit(f"Bundle directory not found: {bundle_dir}")

    answer = run(
        bundle_dir, args.question, args.type_filter,
        base_url=args.base_url, model=args.model,
    )
    print(answer)


if __name__ == "__main__":
    main()
