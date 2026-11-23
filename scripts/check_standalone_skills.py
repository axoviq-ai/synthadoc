# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Check that every skill works from an INSTALLED Synthadoc wheel with only the skills' own
dependencies, the way the v0.9.3 "standalone skills" promise says it should.

Intended environment (see the skills-standalone job in .github/workflows/ci.yml):
    pip install <union of synthadoc/skills/*/requirements.txt>
    pip install --no-deps .          # the wheel, WITHOUT Synthadoc's own dependencies
    python scripts/check_standalone_skills.py

It imports and constructs every skill, really runs the ones that need no network or API key
(markdown, xlsx, docx, pptx, and url against a local server), and fails if any non-skill
Synthadoc module (core, agents, config, ...) was imported along the way. Exit code 1 on any
failure, so a regression cannot slip through.
"""
from __future__ import annotations

import asyncio
import http.server
import importlib
import inspect
import sys
import tempfile
import threading
from pathlib import Path


def _skill_class(name: str):
    from synthadoc.skills.base import BaseSkill
    mod = importlib.import_module(f"synthadoc.skills.{name}.scripts.main")
    return [c for c in vars(mod).values() if isinstance(c, type) and issubclass(c, BaseSkill)
            and c is not BaseSkill and c.__module__ == mod.__name__][0]


def _construct(cls):
    kwargs = {p: None for p, v in inspect.signature(cls.__init__).parameters.items()
              if p != "self" and v.default is inspect._empty
              and v.kind in (v.POSITIONAL_OR_KEYWORD, v.KEYWORD_ONLY)}
    return cls(**kwargs)


class _Page(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"<html><body><p>Hello from a local web page</p></body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


def _make_files(work: Path) -> dict:
    import docx
    import openpyxl
    import pptx

    md = work / "note.md"
    md.write_text("# Title\n\nHello standalone skill.\n", encoding="utf-8")
    wb = openpyxl.Workbook()
    wb.active.append(["a", "b"])
    wb.active.append([1, 2])
    wb.save(work / "t.xlsx")
    d = docx.Document()
    d.add_paragraph("Hello from a Word document")
    d.save(work / "t.docx")
    pr = pptx.Presentation()
    pr.slides.add_slide(pr.slide_layouts[5]).shapes.title.text = "Slide title text"
    pr.save(work / "t.pptx")
    return {"markdown": (str(md), "Hello standalone skill"), "xlsx": (str(work / "t.xlsx"), "a, b"),
            "docx": (str(work / "t.docx"), "Hello from a Word document"),
            "pptx": (str(work / "t.pptx"), "Slide title text")}


def main() -> int:
    import synthadoc
    location = str(getattr(synthadoc, "__file__", ""))
    failures: list = []
    if "site-packages" not in location.replace("\\", "/"):
        failures.append(f"synthadoc was imported from {location}, not from an installed wheel; "
                        "run this from an environment where the wheel is installed")

    skills_dir = Path(location).parent / "skills"
    names = sorted(d.name for d in skills_dir.iterdir() if (d / "SKILL.md").exists())
    if len(names) < 9:
        failures.append(f"only {len(names)} skills found in the installed wheel: {names}")

    for name in names:
        try:
            _construct(_skill_class(name))
            print(f"ok    {name}: import and construct")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")

    work = Path(tempfile.mkdtemp())
    server = http.server.HTTPServer(("127.0.0.1", 0), _Page)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    runs = dict(_make_files(work))
    runs["url"] = (f"http://127.0.0.1:{server.server_address[1]}/", "Hello from a local web page")
    try:
        for name, (source, expected) in runs.items():
            try:
                out = asyncio.run(_construct(_skill_class(name)).extract(source))
                if expected not in out.text:
                    raise AssertionError(f"expected {expected!r} in {out.text[:80]!r}")
                print(f"ok    {name}: extracted {len(out.text)} chars")
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{name} extract: {type(exc).__name__}: {exc}")
                print(f"FAIL  {name} extract: {type(exc).__name__}: {exc}")
    finally:
        server.shutdown()

    leaked = sorted(m for m in sys.modules if m.startswith("synthadoc") and m != "synthadoc"
                    and not m.startswith("synthadoc.skills"))
    if leaked:
        failures.append(f"non-skill Synthadoc modules were imported: {leaked}")

    print()
    if failures:
        print("STANDALONE SKILLS CHECK FAILED")
        for line in failures:
            print(" -", line)
        return 1
    print(f"STANDALONE SKILLS CHECK PASSED ({len(names)} skills, no non-skill Synthadoc modules imported)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
