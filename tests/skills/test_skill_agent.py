# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import pytest, yaml, sys
from pathlib import Path


def _local_skill(wiki: Path, name: str, extensions=None, intents=None,
                 description="local") -> Path:
    skill_dir = wiki / "skills" / name
    (skill_dir / "scripts").mkdir(parents=True)
    fm = {
        "name": name, "version": "1.0", "description": description,
        "entry": {"script": "scripts/main.py", "class": f"{name.title()}Skill"},
        "triggers": {"extensions": extensions or [], "intents": intents or []},
        "requires": [],
    }
    (skill_dir / "SKILL.md").write_text(f"---\n{yaml.dump(fm)}---\n", encoding="utf-8")
    (skill_dir / "scripts" / "main.py").write_text(
        f"from synthadoc.skills.base import BaseSkill, ExtractedContent\n"
        f"class {name.title()}Skill(BaseSkill):\n"
        f"    async def extract(self, s): return ExtractedContent('{name}', s, {{}})\n",
        encoding="utf-8",
    )
    return skill_dir


def test_all_builtin_skills_registered(tmp_wiki):
    from synthadoc.agents.skill_agent import SkillAgent
    agent = SkillAgent(wiki_root=tmp_wiki)
    names = [s.name for s in agent.list_skills()]
    for expected in ("pdf", "url", "markdown", "docx", "xlsx", "image", "web_search"):
        assert expected in names, f"'{expected}' missing from {names}"


def test_intent_dispatch_by_extension(tmp_wiki):
    from synthadoc.agents.skill_agent import SkillAgent
    agent = SkillAgent(wiki_root=tmp_wiki)
    assert agent.detect_skill("paper.pdf").name == "pdf"
    assert agent.detect_skill("notes.md").name == "markdown"
    assert agent.detect_skill("report.docx").name == "docx"
    assert agent.detect_skill("data.xlsx").name == "xlsx"
    assert agent.detect_skill("photo.png").name == "image"
    assert agent.detect_skill("https://example.com").name == "url"
    assert agent.detect_skill("http://example.com").name == "url"


def test_intent_dispatch_by_phrase(tmp_wiki):
    from synthadoc.agents.skill_agent import SkillAgent
    agent = SkillAgent(wiki_root=tmp_wiki)
    assert agent.detect_skill("search for recent AI papers").name == "web_search"
    assert agent.detect_skill("find on the web: quantum computing").name == "web_search"
    assert agent.detect_skill("web search quantum physics").name == "web_search"


def test_intent_dispatch_no_match_raises(tmp_wiki):
    from synthadoc.agents.skill_agent import SkillAgent, SkillNotFoundError
    agent = SkillAgent(wiki_root=tmp_wiki)
    with pytest.raises(SkillNotFoundError):
        agent.detect_skill("file.xyz_unknown_format")


def test_local_skill_overrides_builtin(tmp_wiki):
    _local_skill(tmp_wiki, "pdf", extensions=[".pdf"], description="local override")
    from synthadoc.agents.skill_agent import SkillAgent
    agent = SkillAgent(wiki_root=tmp_wiki)
    assert agent.detect_skill("doc.pdf").description == "local override"


def test_tier1_list_no_python_import(tmp_wiki):
    before = set(sys.modules.keys())
    from synthadoc.agents.skill_agent import SkillAgent
    agent = SkillAgent(wiki_root=tmp_wiki)
    agent.list_skills()
    new_mods = set(sys.modules.keys()) - before
    assert not any("skills.pdf.scripts" in m for m in new_mods)


def test_tier2_lazy_load(tmp_wiki):
    from synthadoc.agents.skill_agent import SkillAgent
    agent = SkillAgent(wiki_root=tmp_wiki)
    # PDF scripts not imported yet
    skill = agent.get_skill("pdf")
    assert skill is not None


def test_tier3_get_resource(tmp_wiki):
    from synthadoc.agents.skill_agent import SkillAgent
    agent = SkillAgent(wiki_root=tmp_wiki)
    skill = agent.get_skill("pdf")
    content = skill.get_resource("cjk-notes.md")
    assert len(content) > 0


def test_missing_requires_raises_clear_error(tmp_wiki):
    _local_skill(tmp_wiki, "needs_fake_pkg", extensions=[".fake"])
    # Add a bogus requires to the SKILL.md
    skill_dir = tmp_wiki / "skills" / "needs_fake_pkg"
    md = skill_dir / "SKILL.md"
    parts = md.read_text().split("---", 2)
    fm = yaml.safe_load(parts[1])
    fm["requires"] = ["this-package-does-not-exist-xyz"]
    md.write_text(f"---\n{yaml.dump(fm)}---\n", encoding="utf-8")
    from synthadoc.agents.skill_agent import SkillAgent
    agent = SkillAgent(wiki_root=tmp_wiki)
    with pytest.raises(ImportError, match="needs_fake_pkg"):
        agent.get_skill("needs_fake_pkg")


def test_registry_cache_written(tmp_wiki):
    from synthadoc.agents.skill_agent import SkillAgent
    SkillAgent(wiki_root=tmp_wiki)
    cache = tmp_wiki / ".synthadoc" / "skill_registry.json"
    assert cache.exists()


def test_pip_entry_point_skill_loaded(tmp_wiki):
    from unittest.mock import patch
    # _local_skill creates: tmp_wiki / "skills" / "_pip_skill_standalone"
    skill_dir = _local_skill(tmp_wiki, "_pip_skill_standalone", extensions=[".psk"],
                             description="pip installed")
    from synthadoc.agents.skill_agent import SkillAgent
    with patch("synthadoc.agents.skill_agent._entry_point_skill_dirs",
               return_value=[skill_dir]):
        agent = SkillAgent(wiki_root=tmp_wiki)
    assert "_pip_skill_standalone" in [s.name for s in agent.list_skills()]


# ── Backslash URL handling ────────────────────────────────────────────────────
# Windows users sometimes paste URLs with backslashes (https:\example.com\path).
# Both detect_skill and needs_path_resolution must handle these correctly so the
# source is routed to the URL skill, not mistakenly treated as a local file path.

def test_detect_skill_handles_backslash_urls(tmp_wiki):
    """URLs with backslashes must be routed to the url skill, not treated as files."""
    from synthadoc.agents.skill_agent import SkillAgent
    agent = SkillAgent(wiki_root=tmp_wiki)
    assert agent.detect_skill(r"https:\example.com\page").name == "url"
    assert agent.detect_skill(r"http:\example.com\page").name == "url"
    assert agent.detect_skill(r"https:\example.com\path\to\article").name == "url"


def test_needs_path_resolution_returns_false_for_backslash_urls(tmp_wiki):
    """URLs with backslashes must not be resolved as local filesystem paths."""
    from synthadoc.agents.skill_agent import SkillAgent
    agent = SkillAgent(wiki_root=tmp_wiki)
    assert agent.needs_path_resolution(r"https:\example.com\page") is False
    assert agent.needs_path_resolution(r"http:\example.com\path") is False


def test_needs_path_resolution_returns_true_for_relative_paths(tmp_wiki):
    """Relative paths with no URL prefix must be flagged for path resolution."""
    from synthadoc.agents.skill_agent import SkillAgent
    agent = SkillAgent(wiki_root=tmp_wiki)
    # Use paths with no extension and no skill intent keywords in the string.
    assert agent.needs_path_resolution("raw_sources/my-transcript") is True
    assert agent.needs_path_resolution("uploads/batch-001") is True


def test_needs_path_resolution_returns_false_for_web_search_intent(tmp_wiki):
    """Web search intent strings must never be resolved as local file paths."""
    from synthadoc.agents.skill_agent import SkillAgent
    agent = SkillAgent(wiki_root=tmp_wiki)
    assert agent.needs_path_resolution("search for: quantum computing qubits") is False
    assert agent.needs_path_resolution("search for: photonic quantum computing qubits") is False
    assert agent.needs_path_resolution("browse: latest AI papers") is False


def test_needs_path_resolution_fallback_when_detect_skill_raises(tmp_wiki):
    """If detect_skill raises, the intent fallback scan must still return False
    for intent-driven sources so they are never treated as file paths."""
    from unittest.mock import patch
    from synthadoc.agents.skill_agent import SkillAgent, SkillNotFoundError
    agent = SkillAgent(wiki_root=tmp_wiki)
    with patch.object(agent, "detect_skill", side_effect=SkillNotFoundError("search for: q")):
        assert agent.needs_path_resolution("search for: quantum computing qubits") is False
    with patch.object(agent, "detect_skill", side_effect=RuntimeError("registry error")):
        assert agent.needs_path_resolution("search for: photonic qubits") is False


# ── YouTube URL routing ───────────────────────────────────────────────────────

def test_youtube_url_routes_to_youtube_skill(tmp_wiki):
    """https://www.youtube.com/... must route to youtube, not url."""
    from synthadoc.agents.skill_agent import SkillAgent
    agent = SkillAgent(wiki_root=tmp_wiki)
    assert agent.detect_skill("https://www.youtube.com/watch?v=dQw4w9WgXcQ").name == "youtube"


def test_youtu_be_url_routes_to_youtube_skill(tmp_wiki):
    """Short youtu.be URLs must route to youtube skill."""
    from synthadoc.agents.skill_agent import SkillAgent
    agent = SkillAgent(wiki_root=tmp_wiki)
    assert agent.detect_skill("https://youtu.be/dQw4w9WgXcQ").name == "youtube"


def test_youtube_beats_url_skill_longest_prefix(tmp_wiki):
    """Longest-prefix rule: youtube (28 chars) must beat url (8 chars)."""
    from synthadoc.agents.skill_agent import SkillAgent
    agent = SkillAgent(wiki_root=tmp_wiki)
    skill = agent.detect_skill("https://www.youtube.com/watch?v=abc123")
    assert skill.name == "youtube"
    assert agent.detect_skill("https://example.com/article").name == "url"


def test_generic_https_still_routes_to_url_skill(tmp_wiki):
    """Non-YouTube https:// URLs must still go to the url skill."""
    from synthadoc.agents.skill_agent import SkillAgent
    agent = SkillAgent(wiki_root=tmp_wiki)
    assert agent.detect_skill("https://en.wikipedia.org/wiki/Turing").name == "url"
    assert agent.detect_skill("https://arxiv.org/abs/1234.5678").name == "url"


def test_youtube_in_builtin_skills(tmp_wiki):
    """youtube must appear in the built-in skill registry."""
    from synthadoc.agents.skill_agent import SkillAgent
    agent = SkillAgent(wiki_root=tmp_wiki)
    names = [s.name for s in agent.list_skills()]
    assert "youtube" in names


def test_youtube_kids_url_routes_to_youtube_skill(tmp_wiki):
    """YouTube Kids URLs must route to the youtube skill, not the url skill."""
    from synthadoc.agents.skill_agent import SkillAgent
    agent = SkillAgent(wiki_root=tmp_wiki)
    assert agent.detect_skill("https://www.youtubekids.com/watch?v=abc123").name == "youtube"


# ── YouTube intent → web_search routing ──────────────────────────────────────

@pytest.mark.parametrize("source", [
    "youtube Moore's Law",
    "youtube video on transistors",
    "youtube kids: Sesame Street",
    "search for youtube: history of computing",
    "search youtube: Alan Turing",
    "search youtube for: Grace Hopper",
    "youtube search: ENIAC",
    "youtube lecture on deep learning",
    "youtube talk: Linus Torvalds",
])
def test_youtube_intent_routes_to_web_search(source, tmp_wiki):
    """Any 'youtube <topic>' phrase (not a URL) must route to the web_search skill."""
    from synthadoc.agents.skill_agent import SkillAgent
    agent = SkillAgent(wiki_root=tmp_wiki)
    assert agent.detect_skill(source).name == "web_search", (
        f"Expected web_search for {source!r}"
    )


def test_youtube_url_still_routes_to_youtube_skill_not_web_search(tmp_wiki):
    """Actual YouTube URLs must still go to the youtube skill (URL prefix wins over intent)."""
    from synthadoc.agents.skill_agent import SkillAgent
    agent = SkillAgent(wiki_root=tmp_wiki)
    assert agent.detect_skill("https://www.youtube.com/watch?v=O5nskjZ_GoI").name == "youtube"
    assert agent.detect_skill("https://youtu.be/O5nskjZ_GoI").name == "youtube"
    assert agent.detect_skill("https://www.youtubekids.com/watch?v=abc").name == "youtube"
