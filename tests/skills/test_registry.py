# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import json, time, pytest
from pathlib import Path


def _make_skill_dir(base: Path, name: str, extensions=None, intents=None) -> Path:
    """Create a minimal valid skill folder with SKILL.md."""
    import yaml
    skill_dir = base / name
    (skill_dir / "scripts").mkdir(parents=True)
    (skill_dir / "scripts" / "main.py").write_text(
        f"from synthadoc.skills.base import BaseSkill, ExtractedContent\n"
        f"class {name.title()}Skill(BaseSkill):\n"
        f"    async def extract(self, s): return ExtractedContent('', s, {{}})\n",
        encoding="utf-8",
    )
    fm = {
        "name": name, "version": "1.0", "description": f"Test {name}",
        "entry": {"script": "scripts/main.py", "class": f"{name.title()}Skill"},
        "triggers": {"extensions": extensions or [], "intents": intents or []},
        "requires": [],
    }
    (skill_dir / "SKILL.md").write_text(
        f"---\n{yaml.dump(fm)}---\n\n# {name}\n", encoding="utf-8"
    )
    return skill_dir


def test_parse_skill_md_returns_meta(tmp_path):
    from synthadoc.skills.registry import parse_skill_md
    skill_dir = _make_skill_dir(tmp_path, "mypdf", extensions=[".pdf"], intents=["document"])
    meta = parse_skill_md(skill_dir)
    assert meta.name == "mypdf"
    assert ".pdf" in meta.triggers.extensions
    assert "document" in meta.triggers.intents
    assert meta.entry_script == "scripts/main.py"
    assert meta.skill_dir == skill_dir


def test_parse_skill_md_missing_file_raises(tmp_path):
    from synthadoc.skills.registry import parse_skill_md, SkillManifestError
    with pytest.raises(SkillManifestError, match="SKILL.md not found"):
        parse_skill_md(tmp_path / "nonexistent")


def test_parse_skill_md_missing_required_field_raises(tmp_path):
    from synthadoc.skills.registry import parse_skill_md, SkillManifestError
    d = tmp_path / "bad"
    d.mkdir()
    (d / "SKILL.md").write_text("---\nname: bad\n---\n", encoding="utf-8")
    with pytest.raises(SkillManifestError, match="missing required"):
        parse_skill_md(d)


def test_cold_start_writes_cache(tmp_path):
    from synthadoc.skills.registry import build_registry_cache
    _make_skill_dir(tmp_path / "skills", "alpha", extensions=[".alp"])
    cache_path = tmp_path / "skill_registry.json"
    registry = build_registry_cache([tmp_path / "skills"], cache_path)
    assert "alpha" in registry
    assert cache_path.exists()
    assert "alpha" in json.loads(cache_path.read_text())["entries"]


def test_warm_start_skips_reparse(tmp_path):
    from synthadoc.skills.registry import build_registry_cache
    _make_skill_dir(tmp_path / "skills", "beta", extensions=[".bet"])
    cache_path = tmp_path / "skill_registry.json"
    build_registry_cache([tmp_path / "skills"], cache_path)
    mtime_before = cache_path.stat().st_mtime
    time.sleep(0.05)
    build_registry_cache([tmp_path / "skills"], cache_path)
    assert cache_path.stat().st_mtime == mtime_before


def test_invalidation_on_mtime_change(tmp_path):
    from synthadoc.skills.registry import build_registry_cache
    skill_dir = _make_skill_dir(tmp_path / "skills", "gamma", extensions=[".gam"])
    cache_path = tmp_path / "skill_registry.json"
    build_registry_cache([tmp_path / "skills"], cache_path)
    time.sleep(0.05)
    md = skill_dir / "SKILL.md"
    md.write_text(md.read_text() + "\n<!-- edited -->", encoding="utf-8")
    registry = build_registry_cache([tmp_path / "skills"], cache_path)
    assert "gamma" in registry


def test_new_skill_folder_detected(tmp_path):
    from synthadoc.skills.registry import build_registry_cache
    _make_skill_dir(tmp_path / "skills", "delta", extensions=[".del"])
    cache_path = tmp_path / "skill_registry.json"
    build_registry_cache([tmp_path / "skills"], cache_path)
    _make_skill_dir(tmp_path / "skills", "epsilon", extensions=[".eps"])
    registry = build_registry_cache([tmp_path / "skills"], cache_path)
    assert "delta" in registry and "epsilon" in registry


def test_deleted_skill_removed(tmp_path):
    import shutil
    from synthadoc.skills.registry import build_registry_cache
    _make_skill_dir(tmp_path / "skills", "zeta", extensions=[".zet"])
    _make_skill_dir(tmp_path / "skills", "eta", extensions=[".eta"])
    cache_path = tmp_path / "skill_registry.json"
    build_registry_cache([tmp_path / "skills"], cache_path)
    shutil.rmtree(tmp_path / "skills" / "zeta")
    registry = build_registry_cache([tmp_path / "skills"], cache_path)
    assert "zeta" not in registry and "eta" in registry


# ── parse_skill_md error paths ────────────────────────────────────────────────

def test_parse_skill_md_raises_on_unterminated_frontmatter(tmp_path):
    """SKILL.md with only one --- delimiter raises SkillManifestError."""
    from synthadoc.skills.registry import parse_skill_md, SkillManifestError
    skill_dir = tmp_path / "broken"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: broken\n", encoding="utf-8")
    with pytest.raises(SkillManifestError, match="unterminated"):
        parse_skill_md(skill_dir)


def test_parse_skill_md_raises_on_invalid_yaml(tmp_path):
    """SKILL.md with malformed YAML in frontmatter raises SkillManifestError."""
    from synthadoc.skills.registry import parse_skill_md, SkillManifestError
    skill_dir = tmp_path / "bad_yaml"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\n: invalid: yaml: {[\n---\n", encoding="utf-8"
    )
    with pytest.raises(SkillManifestError, match="invalid YAML"):
        parse_skill_md(skill_dir)


# ── _load_cache error paths ───────────────────────────────────────────────────

def test_load_cache_returns_empty_on_version_mismatch(tmp_path):
    """Cache file with wrong version number is ignored and returns empty dict."""
    import json
    from synthadoc.skills.registry import _load_cache
    cache_path = tmp_path / "skill_registry.json"
    cache_path.write_text(
        json.dumps({"version": 9999, "entries": {"pdf": {"name": "pdf"}}}),
        encoding="utf-8",
    )
    assert _load_cache(cache_path) == {}


def test_load_cache_returns_empty_on_invalid_json(tmp_path):
    """Cache file with invalid JSON is silently ignored and returns empty dict."""
    from synthadoc.skills.registry import _load_cache
    cache_path = tmp_path / "skill_registry.json"
    cache_path.write_text("this is not json {{", encoding="utf-8")
    assert _load_cache(cache_path) == {}


# ── build_registry_cache deserialisation fallback ────────────────────────────

def test_build_registry_cache_falls_back_on_corrupt_cache_entry(tmp_path):
    """When a cached entry cannot be deserialised, the skill is re-parsed fresh."""
    import json
    from synthadoc.skills.registry import build_registry_cache, _CACHE_VERSION
    skill_dir = _make_skill_dir(tmp_path / "skills", "theta", extensions=[".tht"])
    cache_path = tmp_path / "skill_registry.json"
    # Write a cache entry that matches the skill_dir and mtime but is missing required fields
    mtime = (skill_dir / "SKILL.md").stat().st_mtime
    cache_path.write_text(json.dumps({
        "version": _CACHE_VERSION,
        "entries": {
            "theta": {"skill_dir": str(skill_dir), "skill_md_mtime": mtime}
            # "name", "entry", "triggers" etc. intentionally missing
        }
    }), encoding="utf-8")
    registry = build_registry_cache([tmp_path / "skills"], cache_path)
    assert "theta" in registry
