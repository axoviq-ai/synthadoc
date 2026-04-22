#!/usr/bin/env python3
"""
Bump the project version across all derived files from the single source of truth.

Usage:
    python scripts/bump_version.py 0.3.0

Updates:
    VERSION                              ← source of truth
    obsidian-plugin/manifest.json
    obsidian-plugin/package.json

The Python package version (synthadoc/__init__.py) reads VERSION at runtime,
so no edit is needed there. pyproject.toml uses dynamic versioning from __init__.py.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _set_json_version(path: Path, new_version: str) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    data["version"] = new_version
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"  updated {path.relative_to(ROOT)}")


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python scripts/bump_version.py <new_version>", file=sys.stderr)
        sys.exit(1)

    new_version = sys.argv[1].strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+.*", new_version):
        print(f"Version must be semver (e.g. 0.3.0), got: {new_version!r}", file=sys.stderr)
        sys.exit(1)

    print(f"Bumping version to {new_version}")

    # 1. VERSION file (source of truth)
    version_file = ROOT / "VERSION"
    version_file.write_text(new_version + "\n", encoding="utf-8")
    print(f"  updated {version_file.relative_to(ROOT)}")

    # 2. Obsidian plugin manifest + package
    _set_json_version(ROOT / "obsidian-plugin" / "manifest.json", new_version)
    _set_json_version(ROOT / "obsidian-plugin" / "package.json", new_version)

    print("Done. Remember to:")
    print("  git add VERSION obsidian-plugin/manifest.json obsidian-plugin/package.json")
    print(f"  git commit -m 'chore: bump version to {new_version}'")
    print("  git tag v" + new_version)


if __name__ == "__main__":
    main()
