"""Sync compiled Obsidian plugin files into the Python package data directory.

Run this after rebuilding the plugin TypeScript source:

    cd obsidian-plugin && npm run build
    python scripts/sync_plugin.py

The compiled files are committed to synthadoc/data/obsidian-plugin/ so that
pip-installed synthadoc includes the plugin without needing a separate build step.
"""
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "obsidian-plugin"
DST = REPO_ROOT / "synthadoc" / "data" / "obsidian-plugin"
FILES = ("main.js", "manifest.json", "styles.css")

# Bundlers (esbuild/rollup/Babel) inject Function("return this")() as a
# universal global-scope accessor for pre-ES2020 targets.  Electron/Obsidian
# runs Chromium and supports globalThis natively, so the fallback is dead
# code.  Replacing it removes a false-positive eval/exec scanner finding
# without changing runtime behaviour.
_PATCHES = [
    ('Function("return this")()', "globalThis"),
]


def _patch_main_js(path: Path) -> bool:
    """Apply safe post-build patches to main.js. Returns True if any change was made."""
    text = path.read_text(encoding="utf-8")
    patched = text
    for old, new in _PATCHES:
        patched = patched.replace(old, new)
    if patched == text:
        return False
    path.write_text(patched, encoding="utf-8", newline="\n")
    return True


def main() -> int:
    if not SRC.exists():
        print(f"Error: {SRC} not found.", file=sys.stderr)
        return 1
    DST.mkdir(parents=True, exist_ok=True)
    copied = []
    for name in FILES:
        src_file = SRC / name
        if src_file.exists():
            shutil.copy2(src_file, DST / name)
            copied.append(name)
    if not copied:
        print(f"Nothing to copy — build the plugin first: cd obsidian-plugin && npm run build", file=sys.stderr)
        return 1
    for name in copied:
        print(f"  copied {name}  ->  synthadoc/data/obsidian-plugin/{name}")

    main_js = DST / "main.js"
    if main_js.exists() and _patch_main_js(main_js):
        print(f"  patched main.js  (Function(\"return this\") → globalThis)")

    print(f"\nDone. Commit synthadoc/data/obsidian-plugin/ to include in the next release.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
