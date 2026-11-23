# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Skills must not depend on the rest of Synthadoc.

The project promises (v0.9.3 notes) that every skill works without a Synthadoc wiki or
server. The old in-process check hid imports with a meta-path hook that Python 3.12+ no
longer calls, so it silently passed. These checks do not rely on import hooks:

1. Static: every import in every skill (lazy ones too, relative ones resolved, literal
   dynamic imports included) may only reach ``synthadoc.skills.base`` or the skill's own
   package.
2. Filesystem: each skill runs in a fresh interpreter whose ``synthadoc`` package is a
   stub containing ONLY ``skills/base.py`` and that one skill folder. Any import of core,
   agents, config, providers, storage, another skill, ... cannot resolve and fails.

Dynamic imports built from non-literal strings cannot be seen statically; check 2 covers
those whenever the code path runs at import or construction time.
"""
from __future__ import annotations

import ast
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = REPO_ROOT / "synthadoc" / "skills"
SKILL_NAMES = sorted(d.name for d in SKILLS_DIR.iterdir() if (d / "SKILL.md").exists())

# Guard against a vacuous pass if discovery ever returns nothing.
_KNOWN = {"docx", "image", "markdown", "pdf", "pptx", "url", "web_search", "xlsx", "youtube"}


def test_all_known_skills_are_discovered():
    assert _KNOWN <= set(SKILL_NAMES), f"missing skills: {_KNOWN - set(SKILL_NAMES)}"


# ---- 1. static scan ----------------------------------------------------------

def _allowed(dotted: str, own: str | None) -> bool:
    if not (dotted == "synthadoc" or dotted.startswith("synthadoc.")):
        return True                                   # stdlib / third party
    if dotted in ("synthadoc", "synthadoc.skills"):
        return True                                   # the packages themselves
    if dotted == "synthadoc.skills.base" or dotted.startswith("synthadoc.skills.base."):
        return True
    if own and (dotted == f"synthadoc.skills.{own}" or dotted.startswith(f"synthadoc.skills.{own}.")):
        return True
    return False


def _violations(path: Path, own: str | None) -> list:
    parts = path.relative_to(REPO_ROOT).with_suffix("").parts
    package = list(parts[:-1])
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        names: list = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package[: len(package) - (node.level - 1)]
                module = ".".join(base + ([node.module] if node.module else []))
            else:
                module = node.module or ""
            names = [module] + [f"{module}.{a.name}" for a in node.names if a.name != "*"]
        elif isinstance(node, ast.Call):
            func = node.func
            callee = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if callee in ("import_module", "__import__", "find_spec") and node.args \
                    and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                names = [node.args[0].value]
        for dotted in names:
            if not _allowed(dotted, own):
                found.append((node.lineno, dotted))
    return found


def _skill_files():
    for name in SKILL_NAMES:
        for path in sorted((SKILLS_DIR / name).rglob("*.py")):
            yield pytest.param(path, name, id=path.relative_to(SKILLS_DIR).as_posix())
    yield pytest.param(SKILLS_DIR / "base.py", None, id="base.py")


@pytest.mark.parametrize("path, own", list(_skill_files()))
def test_skill_imports_only_its_own_package_and_the_shared_base(path, own):
    bad = _violations(path, own)
    assert not bad, (
        f"{path.relative_to(REPO_ROOT)} imports Synthadoc code outside its skill: {bad}. "
        "Skills must stay usable without the rest of Synthadoc; inject the dependency "
        "(see the URL skill's fetcher argument) instead of importing it.")


def test_the_scanner_catches_each_kind_of_violation(tmp_path):
    cases = {
        "from synthadoc.core.cache import CacheManager": True,
        "import synthadoc.config": True,
        "from synthadoc import config": True,
        "from synthadoc.skills import registry": True,
        "from synthadoc.skills.url.scripts.main import UrlSkill": True,   # another skill
        "def f():\n    from synthadoc.storage.wiki import WikiPage": True,   # lazy import
        "import importlib\nimportlib.import_module('synthadoc.agents.x')": True,
        "__import__('synthadoc.core')": True,
        "from synthadoc.skills.base import BaseSkill": False,
        "from synthadoc.skills import base": False,
        "import os, json\nfrom pathlib import Path": False,
    }
    for source, should_flag in cases.items():
        target = REPO_ROOT / "synthadoc" / "skills" / "markdown" / "scripts" / "_probe.py"
        tree = ast.parse(source)          # the source itself must be valid
        probe = tmp_path / "probe.py"
        probe.write_text(source, encoding="utf-8")
        flagged = _violations_for_source(source, "markdown")
        assert bool(flagged) is should_flag, (source, flagged)
        assert tree is not None and target.name == "_probe.py"


def _violations_for_source(source: str, own: str) -> list:
    """Same rules as _violations, for an in-memory source placed in skills/<own>/scripts/."""
    fake = SKILLS_DIR / own / "scripts" / "_probe.py"
    original = Path.read_text
    try:
        Path.read_text = lambda self, *a, **k: source if self == fake else original(self, *a, **k)  # type: ignore
        return _violations(fake, own)
    finally:
        Path.read_text = original  # type: ignore


# ---- 2. filesystem isolation -------------------------------------------------

_RUNNER = r'''
import importlib, inspect, json, sys
tmp, name = sys.argv[1], sys.argv[2]
sys.path.insert(0, tmp)
import synthadoc
assert synthadoc.__file__.startswith(tmp), "real synthadoc package was importable"
try:
    mod = importlib.import_module(f"synthadoc.skills.{name}.scripts.main")
    from synthadoc.skills.base import BaseSkill
    classes = [c for c in vars(mod).values() if isinstance(c, type)
               and issubclass(c, BaseSkill) and c is not BaseSkill and c.__module__ == mod.__name__]
    assert classes, "no BaseSkill subclass found"
    cls = classes[0]
    kwargs = {p: None for p, v in inspect.signature(cls.__init__).parameters.items()
              if p != "self" and v.default is inspect._empty
              and v.kind in (v.POSITIONAL_OR_KEYWORD, v.KEYWORD_ONLY)}
    cls(**kwargs)
except ModuleNotFoundError as exc:
    print(json.dumps({"missing": exc.name or str(exc)}))
    sys.exit(0)
leaked = sorted(m for m in sys.modules if m.startswith("synthadoc")
                and m != "synthadoc" and not m.startswith("synthadoc.skills"))
print(json.dumps({"cls": cls.__name__, "leaked": leaked}))
'''


def _build_stub_tree(root: Path, name: str) -> None:
    pkg = root / "synthadoc"
    skills = pkg / "skills"
    skills.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")          # stub: no version lookup
    shutil.copy2(SKILLS_DIR / "__init__.py", skills / "__init__.py")
    shutil.copy2(SKILLS_DIR / "base.py", skills / "base.py")
    shutil.copytree(SKILLS_DIR / name, skills / name, ignore=shutil.ignore_patterns("__pycache__"))


def _run_in_stub(tmp_path: Path, name: str) -> dict:
    _build_stub_tree(tmp_path, name)
    proc = subprocess.run(
        # -E ignores PYTHON* variables and -P keeps the cwd off sys.path (so the repo is not
        # importable), while user-level site-packages stay visible for third-party skill deps.
        [sys.executable, "-E", "-P", "-c", _RUNNER, str(tmp_path), name],
        capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, (
        f"skill '{name}' failed to import or construct with only skills/base.py and its own "
        f"folder available:\n{proc.stderr[-1500:]}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("name", SKILL_NAMES)
def test_skill_runs_with_only_the_shared_base_and_its_own_folder(tmp_path, name):
    result = _run_in_stub(tmp_path, name)
    missing = result.get("missing")
    if missing:
        if missing == "synthadoc" or missing.startswith("synthadoc"):
            pytest.fail(f"skill '{name}' needs Synthadoc module '{missing}', which is not part of the skill")
        pytest.skip(f"third-party dependency '{missing}' is not installed here")
    assert result["leaked"] == [], f"skill '{name}' pulled in Synthadoc modules: {result['leaked']}"
