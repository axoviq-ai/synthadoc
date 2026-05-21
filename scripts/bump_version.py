#!/usr/bin/env python3
"""
Bump the project version across all derived files from the single source of truth.

Usage:
    python scripts/bump_version.py 0.5.0

Updates:
    VERSION                              ← source of truth
    obsidian-plugin/manifest.json
    obsidian-plugin/package.json
    README.md                            ← ASCII art header, version badge, document version

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


def _patch_text(path: Path, old_str: str, new_str: str) -> None:
    text = path.read_text(encoding="utf-8")
    updated = text.replace(old_str, new_str, 1)
    if updated == text:
        print(f"  WARNING: string not found in {path.relative_to(ROOT)}: {old_str!r}")
    else:
        path.write_text(updated, encoding="utf-8")
        print(f"  updated {path.relative_to(ROOT)}")


def _patch_readme(path: Path, old_version: str, new_version: str) -> None:
    text = path.read_text(encoding="utf-8")
    # Replace all three occurrences: ASCII art, badge URL, document version line
    updated = text.replace(
        f"Community Edition  v{old_version}",
        f"Community Edition  v{new_version}",
    ).replace(
        f"Community%20Edition-v{old_version}-brightgreen",
        f"Community%20Edition-v{new_version}-brightgreen",
    ).replace(
        f"**Document version: v{old_version}**",
        f"**Document version: v{new_version}**",
    )
    if updated == text:
        print(f"  WARNING: no version strings replaced in {path.relative_to(ROOT)} "
              f"(expected v{old_version})")
    else:
        path.write_text(updated, encoding="utf-8")
        print(f"  updated {path.relative_to(ROOT)}")


def main() -> None:
    if len(sys.argv) not in (2, 3):
        print("Usage: python scripts/bump_version.py <new_version> [old_version]",
              file=sys.stderr)
        sys.exit(1)

    new_version = sys.argv[1].strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+.*", new_version):
        print(f"Version must be semver (e.g. 0.5.0), got: {new_version!r}", file=sys.stderr)
        sys.exit(1)

    version_file = ROOT / "VERSION"
    old_version = sys.argv[2].strip() if len(sys.argv) == 3 else version_file.read_text(encoding="utf-8").strip()

    print(f"Bumping version {old_version} -> {new_version}")

    # 1. VERSION file (source of truth)
    version_file.write_text(new_version + "\n", encoding="utf-8")
    print(f"  updated {version_file.relative_to(ROOT)}")

    # 2. Obsidian plugin manifest + package
    _set_json_version(ROOT / "obsidian-plugin" / "manifest.json", new_version)
    _set_json_version(ROOT / "obsidian-plugin" / "package.json", new_version)

    # 3. README.md badges and document version
    _patch_readme(ROOT / "README.md", old_version, new_version)

    # 4. User quick-start guide version header
    _patch_text(
        ROOT / "docs" / "user-quick-start-guide.md",
        f"**Version: v{old_version} (Community Edition)**",
        f"**Version: v{new_version} (Community Edition)**",
    )

    print("Done. Remember to:")
    print("  git add VERSION obsidian-plugin/manifest.json obsidian-plugin/package.json README.md docs/user-quick-start-guide.md")
    print(f"  git commit -m 'chore: bump version to {new_version}'")
    print("  git tag v" + new_version)


if __name__ == "__main__":
    main()
