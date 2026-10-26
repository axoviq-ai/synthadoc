#!/usr/bin/env python3
"""Generate README-pypi.md for PyPI publishing.

Transforms README.md by:
  - Stripping <!-- pypi-strip-start --> ... <!-- pypi-strip-end --> blocks
  - Rewriting relative doc links to absolute GitHub blob URLs
  - Rewriting relative image paths to raw.githubusercontent.com URLs

Run before `python -m build`:
    python scripts/prepare_pypi_readme.py
"""
import re
from pathlib import Path

GITHUB_BLOB = "https://github.com/axoviq-ai/synthadoc/blob/main/"
GITHUB_RAW = "https://raw.githubusercontent.com/axoviq-ai/synthadoc/main/"
# A link target inside the repo: not a URL, an in-page anchor or a mail link.
_RELATIVE = r"(?!https?://|#|mailto:)([^)\s]+)"


def transform(content: str) -> str:
    # Strip <!-- pypi-strip-start --> ... <!-- pypi-strip-end --> blocks
    content = re.sub(
        r"\n?<!-- pypi-strip-start -->.*?<!-- pypi-strip-end -->\n?",
        "\n",
        content,
        flags=re.DOTALL,
    )

    # Rewrite inline images with relative paths → raw.githubusercontent.com
    # Must run before the link rewrite to avoid double-replacing image hrefs
    content = re.sub(
        rf"!\[([^\]]*)\]\({_RELATIVE}\)",
        lambda m: f"![{m.group(1)}]({GITHUB_RAW}{m.group(2)})",
        content,
    )

    # Rewrite relative repo links (docs/, benchmarks/, synthadoc/templates/,
    # CONTRIBUTING.md, ...) → github.com blob URLs; PyPI cannot resolve them
    content = re.sub(
        rf"(?<!!)(\[[^\]]*\])\({_RELATIVE}\)",
        lambda m: f"{m.group(1)}({GITHUB_BLOB}{m.group(2)})",
        content,
    )

    # Collapse excess blank lines left by stripped blocks
    content = re.sub(r"\n{3,}", "\n\n", content)

    return content


if __name__ == "__main__":
    src = Path("README.md").read_text(encoding="utf-8")
    out = transform(src)
    Path("README-pypi.md").write_text(out, encoding="utf-8")
    print("README-pypi.md generated successfully.")
