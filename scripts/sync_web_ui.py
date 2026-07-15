"""Sync built web UI dist files into the Python package data directory.

Run this after rebuilding the web UI:

    cd web-ui && npm run build
    python scripts/sync_web_ui.py

The compiled files are committed to synthadoc/data/web-ui/dist/ so that
pip-installed synthadoc includes the web UI without needing a separate build step.
"""
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "web-ui" / "dist"
DST = REPO_ROOT / "synthadoc" / "data" / "web-ui" / "dist"


def main() -> int:
    if not SRC.exists() or not (SRC / "index.html").is_file():
        print(
            f"Error: {SRC} not found or incomplete. "
            "Build the web UI first: cd web-ui && npm run build",
            file=sys.stderr,
        )
        return 1
    if DST.exists():
        shutil.rmtree(DST)
    shutil.copytree(SRC, DST)
    file_count = sum(1 for _ in DST.rglob("*") if _.is_file())
    print(f"  synced {file_count} files  ->  synthadoc/data/web-ui/dist/")
    print("\nDone. Commit synthadoc/data/web-ui/ to include in the next release.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
