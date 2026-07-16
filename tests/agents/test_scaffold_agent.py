# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import json
import pytest
from unittest.mock import AsyncMock
from synthadoc.agents.scaffold_agent import ScaffoldAgent, ScaffoldResult
from synthadoc.providers.base import CompletionResponse, Message


def _make_provider(json_payload: dict) -> AsyncMock:
    """Return a mock provider that returns the given dict as JSON text."""
    provider = AsyncMock()
    provider.complete = AsyncMock(return_value=CompletionResponse(
        text=json.dumps(json_payload),
        input_tokens=100,
        output_tokens=200,
    ))
    return provider


_VALID_RESPONSE = {
    "categories": [
        {"heading": "Key Concepts", "description": "Fundamental ideas in the domain", "slugs": ["neural-networks", "backpropagation"]},
        {"heading": "People", "description": "Notable figures", "slugs": []},
    ],
    "agents_guidelines": "Summarize claims. Use [[wikilinks]].",
    "purpose_include": "Topics directly related to Machine Learning.",
    "purpose_exclude": "Unrelated domains such as cooking.",
    "dashboard_intro": "A wiki tracking Machine Learning knowledge.",
}


@pytest.mark.asyncio
async def test_scaffold_returns_result():
    """ScaffoldAgent.scaffold() returns a ScaffoldResult with all fields populated."""
    provider = _make_provider(_VALID_RESPONSE)
    agent = ScaffoldAgent(provider=provider)
    result = await agent.scaffold(domain="Machine Learning")
    assert isinstance(result, ScaffoldResult)
    assert "Key Concepts" in result.index_md
    assert "People" in result.index_md
    assert "Machine Learning" in result.agents_md
    assert "Machine Learning" in result.purpose_md
    assert "Machine Learning" in result.dashboard_intro


@pytest.mark.asyncio
async def test_scaffold_index_md_has_frontmatter():
    """index.md must include YAML frontmatter."""
    provider = _make_provider(_VALID_RESPONSE)
    agent = ScaffoldAgent(provider=provider)
    result = await agent.scaffold(domain="Machine Learning")
    assert result.index_md.startswith("---")
    assert "title: Index" in result.index_md


@pytest.mark.asyncio
async def test_scaffold_protected_slugs_appear_in_prompt():
    """Protected slugs must be included in the LLM prompt."""
    provider = _make_provider(_VALID_RESPONSE)
    agent = ScaffoldAgent(provider=provider)
    await agent.scaffold(domain="ML", protected_slugs=["neural-networks", "transformers"])
    call_kwargs = provider.complete.call_args.kwargs
    call_messages = call_kwargs.get("messages") or provider.complete.call_args[0][0]
    prompt_text = " ".join(m.content for m in call_messages)
    assert "neural-networks" in prompt_text
    assert "transformers" in prompt_text


@pytest.mark.asyncio
async def test_scaffold_index_md_has_wikilinks():
    """index.md must include [[slug]] wikilinks for slugs returned by the LLM."""
    provider = _make_provider(_VALID_RESPONSE)
    agent = ScaffoldAgent(provider=provider)
    result = await agent.scaffold(domain="Machine Learning")
    assert "- [[neural-networks]]" in result.index_md
    assert "- [[backpropagation]]" in result.index_md


@pytest.mark.asyncio
async def test_scaffold_protected_slugs_instruction_in_prompt():
    """Protected slugs must trigger assignment instruction in the LLM prompt."""
    provider = _make_provider(_VALID_RESPONSE)
    agent = ScaffoldAgent(provider=provider)
    await agent.scaffold(domain="ML", protected_slugs=["neural-networks", "transformers"])
    call_kwargs = provider.complete.call_args.kwargs
    call_messages = call_kwargs.get("messages") or provider.complete.call_args[0][0]
    prompt_text = " ".join(m.content for m in call_messages)
    assert "every protected slug must appear in exactly one category" in prompt_text.lower()


@pytest.mark.asyncio
async def test_scaffold_handles_json_with_markdown_fences():
    """Parser must strip ```json fences if the LLM wraps the response."""
    fenced = f"```json\n{json.dumps(_VALID_RESPONSE)}\n```"
    provider = AsyncMock()
    provider.complete = AsyncMock(return_value=CompletionResponse(
        text=fenced, input_tokens=10, output_tokens=20
    ))
    agent = ScaffoldAgent(provider=provider)
    result = await agent.scaffold(domain="ML")
    assert "Key Concepts" in result.index_md


@pytest.mark.asyncio
async def test_scaffold_raises_on_invalid_json():
    """ScaffoldAgent must raise ValueError if the LLM returns unparseable text."""
    provider = AsyncMock()
    provider.complete = AsyncMock(return_value=CompletionResponse(
        text="not json at all", input_tokens=10, output_tokens=5
    ))
    agent = ScaffoldAgent(provider=provider)
    with pytest.raises(ValueError, match="scaffold"):
        await agent.scaffold(domain="ML")


# ── CJK (Chinese / Japanese / Korean) coverage ───────────────────────────────

_CJK_VALID_RESPONSE = {
    "categories": [
        {"heading": "核心概念", "description": "人工智能的基本原理", "slugs": ["神经网络", "机器学习"]},
        {"heading": "应用领域", "description": "实际应用场景", "slugs": ["自然语言处理"]},
    ],
    "agents_guidelines": "总结关键主张。使用[[维基链接]]交叉引用相关页面。",
    "purpose_include": "与人工智能直接相关的主题。",
    "purpose_exclude": "与人工智能无关的领域，例如烹饪。",
    "dashboard_intro": "跟踪人工智能知识库领域知识的维基百科。",
}


@pytest.mark.asyncio
async def test_scaffold_cjk_domain_name_in_all_outputs():
    """Scaffold with a CJK domain name → all output documents contain the CJK domain string."""
    provider = _make_provider(_CJK_VALID_RESPONSE)
    agent = ScaffoldAgent(provider=provider)
    result = await agent.scaffold(domain="人工智能知识库")

    assert isinstance(result, ScaffoldResult)
    assert "人工智能知识库" in result.agents_md
    assert "人工智能知识库" in result.purpose_md
    assert "人工智能知识库" in result.dashboard_intro


@pytest.mark.asyncio
async def test_scaffold_cjk_categories_produce_wikilinks():
    """LLM returns CJK category headings and CJK slugs → index.md contains CJK [[wikilinks]]."""
    provider = _make_provider(_CJK_VALID_RESPONSE)
    agent = ScaffoldAgent(provider=provider)
    result = await agent.scaffold(domain="人工智能知识库")

    assert "核心概念" in result.index_md
    assert "应用领域" in result.index_md
    assert "- [[神经网络]]" in result.index_md
    assert "- [[机器学习]]" in result.index_md
    assert "- [[自然语言处理]]" in result.index_md


# ── Protected scaffold zone ───────────────────────────────────────────────────

def test_scaffold_preserves_user_content_above_marker():
    from synthadoc.agents.scaffold_agent import SCAFFOLD_MARKER, preserve_user_zone

    existing = "My custom intro.\n\n<!-- synthadoc:scaffold -->\n\n## Old Section\n- [[old]]\n"
    new_scaffold = "## People\n- [[alan-turing]]\n"
    result = preserve_user_zone(existing, new_scaffold)
    assert "My custom intro." in result
    assert "## People" in result
    assert "## Old Section" not in result
    assert SCAFFOLD_MARKER in result


def test_scaffold_no_marker_returns_new_content():
    from synthadoc.agents.scaffold_agent import preserve_user_zone
    result = preserve_user_zone("", "## People\n- [[alan-turing]]\n")
    assert result == "## People\n- [[alan-turing]]\n"


def test_scaffold_marker_without_user_zone():
    from synthadoc.agents.scaffold_agent import SCAFFOLD_MARKER, preserve_user_zone
    existing = f"{SCAFFOLD_MARKER}\n\n## Old Section\n"
    new_scaffold = "## New Section\n"
    result = preserve_user_zone(existing, new_scaffold)
    assert SCAFFOLD_MARKER in result
    assert "## New Section" in result
    assert "## Old Section" not in result


# ── _coerce_scaffold_dict ─────────────────────────────────────────────────────

def test_coerce_scaffold_dict_with_wrapped_list():
    """[{...categories...}] — single wrapped dict is unwrapped."""
    from synthadoc.agents.scaffold_agent import _coerce_scaffold_dict
    inner = {"categories": [{"heading": "A", "slugs": []}], "dashboard_intro": "x"}
    assert _coerce_scaffold_dict([inner]) == inner


def test_coerce_scaffold_dict_with_categories_array():
    """[{heading, slugs}, ...] — bare categories array is wrapped in a dict."""
    from synthadoc.agents.scaffold_agent import _coerce_scaffold_dict
    cats = [{"heading": "A", "slugs": []}, {"heading": "B", "slugs": ["foo"]}]
    result = _coerce_scaffold_dict(cats)
    assert result == {"categories": cats}


def test_coerce_scaffold_dict_returns_none_for_unrecognised_list():
    from synthadoc.agents.scaffold_agent import _coerce_scaffold_dict
    assert _coerce_scaffold_dict([1, 2, 3]) is None


def test_coerce_scaffold_dict_returns_none_for_string():
    from synthadoc.agents.scaffold_agent import _coerce_scaffold_dict
    assert _coerce_scaffold_dict("just a string") is None


# ── _parse_scaffold_json tiers ────────────────────────────────────────────────

def test_extract_first_json_object_ignores_trailing_braces():
    """Brace-balanced extractor stops at the closing } of the first object,
    ignoring trailing prose that contains its own {braces}."""
    from synthadoc.agents.scaffold_agent import _extract_first_json_object
    payload = '{"key": "value"}'
    raw = f'{payload}\nSee {{field}} for details.'
    extracted = _extract_first_json_object(raw)
    assert extracted == payload


def test_extract_first_json_object_handles_braces_in_strings():
    """String values that contain { or } must not confuse the depth counter."""
    from synthadoc.agents.scaffold_agent import _extract_first_json_object
    payload = '{"note": "see {example} here", "ok": true}'
    assert _extract_first_json_object(payload) == payload


def test_extract_first_json_object_handles_escaped_quote_in_string():
    """Backslash-escaped quote inside a JSON string must not end the string early.

    This exercises the escape-flag path (lines that set/clear escape) so that
    the \" sequence does not toggle in_str and break depth tracking.
    """
    from synthadoc.agents.scaffold_agent import _extract_first_json_object
    # JSON: {"key": "val\"ue"} — escaped quote inside the string value
    payload = '{"key": "val\\"ue"}'
    result = _extract_first_json_object(payload)
    assert result == payload


def test_extract_first_json_object_returns_none_for_unclosed_brace():
    """Input that opens a brace but never closes it must return None."""
    from synthadoc.agents.scaffold_agent import _extract_first_json_object
    assert _extract_first_json_object("{ never closed") is None


def test_parse_scaffold_json_tier2_extracts_embedded_object():
    """Tier 2 (brace-balanced): valid JSON object buried in surrounding text."""
    from synthadoc.agents.scaffold_agent import _parse_scaffold_json
    payload = '{"categories": [{"heading": "A", "slugs": []}]}'
    raw = f"Here is the scaffold:\n{payload}\nDone."
    result = _parse_scaffold_json(raw)
    assert result is not None
    assert result["categories"][0]["heading"] == "A"


def test_parse_scaffold_json_tier2_trailing_prose_with_braces():
    """Tier 2 must succeed even when trailing prose has its own {brace} patterns."""
    from synthadoc.agents.scaffold_agent import _parse_scaffold_json
    payload = '{"categories": [{"heading": "A", "slugs": []}], "dashboard_intro": "x"}'
    raw = f"{payload}\nNote: use {{field}} syntax for placeholders."
    result = _parse_scaffold_json(raw)
    assert result is not None
    assert result["categories"][0]["heading"] == "A"


def test_parse_scaffold_json_tier2_and_4_invalid_embedded_returns_none():
    """All tiers find a {…} block but it is not valid JSON → return None."""
    from synthadoc.agents.scaffold_agent import _parse_scaffold_json
    raw = "Some preamble {not valid json here} trailing text"
    assert _parse_scaffold_json(raw) is None


def test_parse_scaffold_json_tier3_fixes_minimax_comma_drop():
    """Tier 3: missing comma between adjacent array objects is inserted and parsed."""
    from synthadoc.agents.scaffold_agent import _parse_scaffold_json
    raw = '{"categories": [{"heading": "A", "slugs": []}\n{"heading": "B", "slugs": []}]}'
    result = _parse_scaffold_json(raw)
    assert result is not None
    assert len(result["categories"]) == 2


# ── _build_purpose_md with list fields ───────────────────────────────────────

@pytest.mark.asyncio
async def test_scaffold_purpose_md_with_list_fields():
    """purpose_include / purpose_exclude returned as lists are rendered as bullets."""
    response_with_lists = {
        **_VALID_RESPONSE,
        "purpose_include": ["Core algorithms", "Benchmark datasets"],
        "purpose_exclude": ["Unrelated biology topics"],
    }
    provider = _make_provider(response_with_lists)
    agent = ScaffoldAgent(provider=provider)
    result = await agent.scaffold(domain="ML")
    assert "Core algorithms" in result.purpose_md
    assert "Benchmark datasets" in result.purpose_md
    assert "Unrelated biology topics" in result.purpose_md


@pytest.mark.asyncio
async def test_scaffold_purpose_md_has_frontmatter():
    """purpose.md must include YAML frontmatter with status: active and a created date."""
    provider = _make_provider(_VALID_RESPONSE)
    agent = ScaffoldAgent(provider=provider)
    result = await agent.scaffold(domain="Machine Learning")
    assert result.purpose_md.startswith("---"), "purpose.md must start with YAML frontmatter"
    assert "status: active" in result.purpose_md
    assert "created:" in result.purpose_md


# ── Self-correction retry ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scaffold_self_corrects_on_second_attempt():
    """If attempt 1 returns invalid JSON, the agent sends a correction prompt and retries."""
    valid_json = json.dumps(_VALID_RESPONSE)
    provider = AsyncMock()
    provider.complete = AsyncMock(side_effect=[
        CompletionResponse(text="not json at all", input_tokens=10, output_tokens=5),
        CompletionResponse(text=valid_json, input_tokens=20, output_tokens=100),
    ])
    agent = ScaffoldAgent(provider=provider)
    result = await agent.scaffold(domain="ML")
    assert provider.complete.call_count == 2
    assert "Key Concepts" in result.index_md


@pytest.mark.asyncio
async def test_scaffold_raises_after_two_failed_attempts():
    """If both attempts return invalid JSON, ValueError is raised."""
    provider = AsyncMock()
    provider.complete = AsyncMock(return_value=CompletionResponse(
        text="still not json", input_tokens=10, output_tokens=5
    ))
    agent = ScaffoldAgent(provider=provider)
    with pytest.raises(ValueError, match="scaffold"):
        await agent.scaffold(domain="ML")


# ── _validate_scaffold_result ─────────────────────────────────────────────────

def _make_agents_md(domain: str = "Machine Learning") -> str:
    return (
        f"# AGENTS.md — {domain} Wiki\n\n"
        f"## Domain Guidelines\n- Summarize key claims.\n\n"
        f"## Quick Reference\n| Action | Command |\n|---|---|\n"
        f"| Start server | `synthadoc serve -w <wiki>` |\n\n"
        f"## Ingest\nIngest sources here.\n\n"
        f"## Query\nQuery wiki here.\n"
    )


def _make_result(
    index_md: str | None = None,
    agents_md: str | None = None,
    purpose_md: str | None = None,
    dashboard_intro: str = "x",
    domain: str = "Machine Learning",
) -> "ScaffoldResult":
    from synthadoc.agents.scaffold_agent import ScaffoldResult
    _agents = agents_md if agents_md is not None else _make_agents_md(domain)
    return ScaffoldResult(
        index_md=index_md if index_md is not None else (
            f"---\ntitle: Index\ncreated: '2026-01-01'\n---\n\n# {domain} — Index\n\n"
            f"## Core Concepts\n*key ideas*\n\n- [[neural-networks]]\n"
        ),
        agents_md=_agents,
        claude_md=_agents.replace("# AGENTS.md", "# CLAUDE.md", 1),
        gemini_md=_agents.replace("# AGENTS.md", "# GEMINI.md", 1),
        purpose_md=purpose_md if purpose_md is not None else (
            f"# Wiki Purpose — {domain}\n\n## Overview\n\nSome overview.\n"
        ),
        dashboard_intro=dashboard_intro,
    )


# ── _validate_routing_md ─────────────────────────────────────────────────────

def test_validate_routing_md_passes_on_valid_content():
    from synthadoc.agents.scaffold_agent import _validate_routing_md
    content = "## Due Diligence\n- [[lbo-model]]\n- [[covenant-analysis]]\n\n## Market\n- [[water-market]]\n"
    _validate_routing_md(content)  # must not raise


def test_validate_routing_md_fails_missing_headings():
    from synthadoc.agents.scaffold_agent import _validate_routing_md
    with pytest.raises(ValueError, match="branch headings"):
        _validate_routing_md("- [[slug-one]]\n- [[slug-two]]\n")


def test_validate_routing_md_fails_no_slugs():
    from synthadoc.agents.scaffold_agent import _validate_routing_md
    with pytest.raises(ValueError, match="\\[\\[slug\\]\\] entries"):
        _validate_routing_md("## Due Diligence\n## Market\n")


def test_validate_routing_md_reports_both_issues():
    from synthadoc.agents.scaffold_agent import _validate_routing_md
    with pytest.raises(ValueError) as exc_info:
        _validate_routing_md("no structure at all")
    msg = str(exc_info.value)
    assert "branch headings" in msg
    assert "[[slug]]" in msg


def test_validate_scaffold_result_passes_on_valid_output():
    from synthadoc.agents.scaffold_agent import _validate_scaffold_result
    result = _make_result()
    _validate_scaffold_result(result, "Machine Learning")  # must not raise


def test_validate_scaffold_result_fails_missing_frontmatter():
    from synthadoc.agents.scaffold_agent import _validate_scaffold_result
    result = _make_result(index_md="# Machine Learning — Index\n\n- [[page]]\n")
    with pytest.raises(ValueError, match="YAML frontmatter"):
        _validate_scaffold_result(result, "Machine Learning")


def test_validate_scaffold_result_fails_missing_domain_in_index():
    from synthadoc.agents.scaffold_agent import _validate_scaffold_result
    result = _make_result(index_md="---\ntitle: Index\n---\n\n# Something Else — Index\n\n- [[page]]\n")
    with pytest.raises(ValueError, match="H1 title"):
        _validate_scaffold_result(result, "Machine Learning")


def test_validate_scaffold_result_fails_no_wikilinks():
    from synthadoc.agents.scaffold_agent import _validate_scaffold_result
    result = _make_result(
        index_md="---\ntitle: Index\n---\n\n# Machine Learning — Index\n\n## Core\n"
    )
    with pytest.raises(ValueError, match="no \\[\\[wikilinks\\]\\]"):
        _validate_scaffold_result(result, "Machine Learning")


def test_validate_scaffold_result_fails_missing_domain_guidelines():
    from synthadoc.agents.scaffold_agent import _validate_scaffold_result
    result = _make_result(agents_md="# AGENTS.md\n\n## Quick Reference\n## Ingest\n## Query\n")
    with pytest.raises(ValueError, match="Domain Guidelines"):
        _validate_scaffold_result(result, "Machine Learning")


def test_validate_scaffold_result_fails_missing_quick_reference():
    from synthadoc.agents.scaffold_agent import _validate_scaffold_result
    result = _make_result(agents_md="# AGENTS.md\n\n## Domain Guidelines\n## Ingest\n## Query\n")
    with pytest.raises(ValueError, match="Quick Reference"):
        _validate_scaffold_result(result, "Machine Learning")


def test_validate_scaffold_result_fails_missing_overview():
    from synthadoc.agents.scaffold_agent import _validate_scaffold_result
    result = _make_result(purpose_md="# Wiki Purpose — Machine Learning\n\n## Something Else\n")
    with pytest.raises(ValueError, match="Overview"):
        _validate_scaffold_result(result, "Machine Learning")


def test_validate_scaffold_result_fails_domain_not_in_purpose():
    from synthadoc.agents.scaffold_agent import _validate_scaffold_result
    result = _make_result(purpose_md="# Wiki Purpose\n\n## Overview\n\nSome generic text.\n")
    with pytest.raises(ValueError, match="domain name"):
        _validate_scaffold_result(result, "Machine Learning")


def test_validate_scaffold_result_reports_all_issues_at_once():
    """All issues are collected and reported together, not one at a time."""
    from synthadoc.agents.scaffold_agent import _validate_scaffold_result, ScaffoldResult
    bad = ScaffoldResult(
        index_md="no frontmatter here",
        agents_md="no sections",
        claude_md="no sections",
        gemini_md="no sections",
        purpose_md="no sections",
        dashboard_intro="x",
    )
    with pytest.raises(ValueError) as exc_info:
        _validate_scaffold_result(bad, "ML")
    msg = str(exc_info.value)
    assert "index.md" in msg
    assert "AGENTS.md" in msg
    assert "purpose.md" in msg


@pytest.mark.asyncio
async def test_scaffold_raises_on_validation_failure():
    """scaffold() raises ValueError if built output fails format validation."""
    # Return a response where LLM gives categories with no slugs at all
    sparse = {
        "categories": [],   # no slugs → index will have no [[wikilinks]]
        "agents_guidelines": "Summarize.",
        "purpose_overview": "A wiki.",
        "purpose_include": "Topics.",
        "purpose_exclude": "Unrelated.",
        "dashboard_intro": "Tracks ML.",
    }
    provider = _make_provider(sparse)
    agent = ScaffoldAgent(provider=provider)
    with pytest.raises(ValueError, match="no \\[\\[wikilinks\\]\\]"):
        await agent.scaffold(domain="Machine Learning")


@pytest.mark.asyncio
async def test_scaffold_returns_claude_and_gemini_md():
    """scaffold() must populate claude_md and gemini_md alongside agents_md."""
    provider = _make_provider(_VALID_RESPONSE)
    agent = ScaffoldAgent(provider=provider)
    result = await agent.scaffold(domain="Machine Learning")
    assert result.claude_md.startswith("# CLAUDE.md")
    assert result.gemini_md.startswith("# GEMINI.md")
    assert "Machine Learning" in result.claude_md
    assert "Machine Learning" in result.gemini_md


@pytest.mark.asyncio
async def test_scaffold_skill_files_share_body():
    """AGENTS.md, CLAUDE.md, GEMINI.md must share identical body (differ only in H1)."""
    provider = _make_provider(_VALID_RESPONSE)
    agent = ScaffoldAgent(provider=provider)
    result = await agent.scaffold(domain="Machine Learning")
    agents_lines = result.agents_md.splitlines()
    claude_lines = result.claude_md.splitlines()
    gemini_lines = result.gemini_md.splitlines()
    assert agents_lines[1:] == claude_lines[1:] == gemini_lines[1:]


@pytest.mark.asyncio
async def test_scaffold_port_embedded_in_skill_files():
    """scaffold(port=9090) must embed 9090 in all three skill files."""
    provider = _make_provider(_VALID_RESPONSE)
    agent = ScaffoldAgent(provider=provider)
    result = await agent.scaffold(domain="Machine Learning", port=9090)
    for content in (result.agents_md, result.claude_md, result.gemini_md):
        assert "9090" in content


def test_build_index_md_strips_meta_slugs():
    """_build_index_md must never emit [[index]], [[overview]], [[purpose]], etc."""
    from synthadoc.agents.scaffold_agent import ScaffoldAgent, _META_SLUGS
    from unittest.mock import AsyncMock

    agent = ScaffoldAgent(provider=AsyncMock())
    data = {
        "categories": [
            {
                "heading": "Wiki Meta",
                "description": "System pages",
                "slugs": list(_META_SLUGS) + ["real-topic"],
            },
            {
                "heading": "Research",
                "description": "Content",
                "slugs": ["index", "overview", "another-real-page"],
            },
        ],
    }
    result = agent._build_index_md("Test Domain", data)

    for slug in _META_SLUGS:
        assert f"[[{slug}]]" not in result, f"meta slug [[{slug}]] must not appear in index.md"
    assert "[[real-topic]]" in result
    assert "[[another-real-page]]" in result


# ── domain_label overrides config domain ─────────────────────────────────────

@pytest.mark.asyncio
async def test_domain_label_overrides_config_domain():
    """When the LLM returns domain_label, it replaces the config domain in all titles."""
    response = {**_VALID_RESPONSE, "domain_label": "History of Computing"}
    provider = _make_provider(response)
    agent = ScaffoldAgent(provider=provider)
    result = await agent.scaffold(domain="General")
    assert "History of Computing" in result.agents_md
    assert "History of Computing" in result.claude_md
    assert "History of Computing" in result.gemini_md
    assert "# History of Computing — Index" in result.index_md
    assert "General" not in result.agents_md.splitlines()[0]


@pytest.mark.asyncio
async def test_domain_label_empty_falls_back_to_config_domain():
    """An empty or missing domain_label falls back to the config domain name."""
    response = {**_VALID_RESPONSE, "domain_label": ""}
    provider = _make_provider(response)
    agent = ScaffoldAgent(provider=provider)
    result = await agent.scaffold(domain="Machine Learning")
    assert "Machine Learning" in result.agents_md


# ── ⚠ contradiction bullet always present ────────────────────────────────────

@pytest.mark.asyncio
async def test_contradiction_bullet_appended_when_absent():
    """⚠ contradiction-marker bullet is always present even if the LLM omits it."""
    response = {**_VALID_RESPONSE, "agents_guidelines": "Summarize key claims.\nCross-link related concepts."}
    provider = _make_provider(response)
    agent = ScaffoldAgent(provider=provider)
    result = await agent.scaffold(domain="Machine Learning")
    assert "⚠" in result.agents_md
    assert "⚠" in result.claude_md
    assert "⚠" in result.gemini_md


@pytest.mark.asyncio
async def test_contradiction_bullet_not_duplicated_when_present():
    """If the LLM already includes ⚠ the bullet is not added a second time."""
    response = {**_VALID_RESPONSE, "agents_guidelines": "Summarize claims.\nFlag contradictions with ⚠ markers."}
    provider = _make_provider(response)
    agent = ScaffoldAgent(provider=provider)
    result = await agent.scaffold(domain="Machine Learning")
    assert result.agents_md.count("⚠") == 1


@pytest.mark.asyncio
async def test_condensed_guidelines_paragraph_becomes_bullets():
    """A single-paragraph guidelines response is wrapped in one bullet + ⚠ appended."""
    response = {**_VALID_RESPONSE, "agents_guidelines": "Summarize claims and cross-link related topics."}
    provider = _make_provider(response)
    agent = ScaffoldAgent(provider=provider)
    result = await agent.scaffold(domain="Machine Learning")
    guidelines_section = result.agents_md.split("## Domain Guidelines")[1].split("##")[0]
    bullets = [ln for ln in guidelines_section.splitlines() if ln.strip().startswith("- ")]
    assert len(bullets) >= 2  # original sentence + ⚠ bullet
    assert any("⚠" in b for b in bullets)


# ── purpose.md per-section scaffold markers ───────────────────────────────────

@pytest.mark.asyncio
async def test_purpose_md_has_scaffold_marker():
    """Generated purpose.md must contain one scaffold marker inside each of the 5 sections."""
    provider = _make_provider(_VALID_RESPONSE)
    agent = ScaffoldAgent(provider=provider)
    result = await agent.scaffold(domain="Machine Learning")
    assert result.purpose_md.count("<!-- synthadoc:scaffold -->") == 5
    # Marker sits inside each section (after the ## heading, not before it)
    assert "## Overview\n\n<!-- synthadoc:scaffold -->" in result.purpose_md
    assert "## What Belongs in This Wiki\n\n<!-- synthadoc:scaffold -->" in result.purpose_md
    assert "## What Is Out of Scope\n\n<!-- synthadoc:scaffold -->" in result.purpose_md
    assert "## Intended Audience\n\n<!-- synthadoc:scaffold -->" in result.purpose_md
    assert "## Primary Use Cases\n\n<!-- synthadoc:scaffold -->" in result.purpose_md


def test_preserve_user_zone_multi_marker_basic():
    """Multi-marker mode: user content above each section marker is preserved;
    scaffold content below each marker is replaced with fresh LLM output."""
    from synthadoc.agents.scaffold_agent import SCAFFOLD_MARKER, preserve_user_zone
    M = SCAFFOLD_MARKER
    existing = (
        "---\ntitle: Wiki Purpose\nstatus: active\n---\n\n"
        "# Wiki Purpose — ML\n\n"
        f"## Overview\n\n{M}\n\nOld overview.\n\n"
        f"## What Belongs in This Wiki\n\nUser added line.\n\n{M}\n\n- Old bullet\n\n"
        f"## What Is Out of Scope\n\n{M}\n\n- Old scope\n\n"
    )
    new_scaffold = (
        "---\ntitle: Wiki Purpose — ML\n---\n\n"
        "# Wiki Purpose — ML\n\n"
        f"## Overview\n\n{M}\n\nNew overview.\n\n"
        f"## What Belongs in This Wiki\n\n{M}\n\n- New bullet\n\n"
        f"## What Is Out of Scope\n\n{M}\n\n- New scope\n\n"
        f"## Intended Audience\n\n{M}\n\nNew audience.\n\n"
    )
    result = preserve_user_zone(existing, new_scaffold)

    # User zone preserved
    assert "User added line." in result
    # Scaffold zones replaced
    assert "New overview." in result
    assert "Old overview." not in result
    assert "New bullet" in result
    assert "Old bullet" not in result
    # New section from scaffold appended
    assert "## Intended Audience" in result
    assert "New audience." in result
    # Marker count = 4 (3 existing + 1 appended)
    assert result.count(SCAFFOLD_MARKER) == 4


def test_preserve_user_zone_section_without_marker_not_in_template_kept():
    """A section without a marker that is NOT in the template is user-added — kept as-is."""
    from synthadoc.agents.scaffold_agent import SCAFFOLD_MARKER, preserve_user_zone
    M = SCAFFOLD_MARKER
    existing = (
        "# Wiki Purpose — ML\n\n"
        f"## Overview\n\n{M}\n\nOld overview.\n\n"
        "## My Custom Section\n\nFull user content here.\nMore lines.\n\n"
        f"## What Is Out of Scope\n\n{M}\n\n- Old scope\n\n"
    )
    new_scaffold = (
        "# Wiki Purpose — ML\n\n"
        f"## Overview\n\n{M}\n\nNew overview.\n\n"
        f"## What Is Out of Scope\n\n{M}\n\n- New scope\n\n"
    )
    result = preserve_user_zone(existing, new_scaffold)

    # User-added section (not in template) untouched
    assert "## My Custom Section" in result
    assert "Full user content here." in result
    # Other sections updated
    assert "New overview." in result
    assert "Old overview." not in result


def test_preserve_user_zone_section_without_marker_in_template_overwritten():
    """A section without a marker that IS in the template is replaced by template content."""
    from synthadoc.agents.scaffold_agent import SCAFFOLD_MARKER, preserve_user_zone
    M = SCAFFOLD_MARKER
    existing = (
        "# Wiki Purpose — ML\n\n"
        f"## Overview\n\n{M}\n\nOld overview.\n\n"
        # Intended Audience has NO marker — user removed it
        "## Intended Audience\n\nOld audience content. No marker here.\n\n"
        f"## What Is Out of Scope\n\n{M}\n\n- Old scope\n\n"
    )
    new_scaffold = (
        "# Wiki Purpose — ML\n\n"
        f"## Overview\n\n{M}\n\nNew overview.\n\n"
        f"## Intended Audience\n\n{M}\n\nNew audience content.\n\n"
        f"## What Is Out of Scope\n\n{M}\n\n- New scope\n\n"
    )
    result = preserve_user_zone(existing, new_scaffold)

    # Section without marker that IS in template → replaced with template content
    assert "New audience content." in result
    assert "Old audience content. No marker here." not in result
    # Marker added to the replaced section
    assert result.count(M) == 3
    # Other sections updated normally
    assert "New overview." in result
    assert "- New scope" in result


def test_preserve_user_zone_no_markers_returns_new_content():
    """Existing file with no markers at all is fully replaced — first scaffold on an existing wiki."""
    from synthadoc.agents.scaffold_agent import SCAFFOLD_MARKER, preserve_user_zone
    M = SCAFFOLD_MARKER
    existing = "# Wiki Purpose\n\nSome old content with no markers.\n"
    new_scaffold = (
        "---\ntitle: Wiki Purpose — ML\n---\n\n"
        "# Wiki Purpose — ML\n\n"
        f"## Overview\n\n{M}\n\nNew overview.\n\n"
    )
    result = preserve_user_zone(existing, new_scaffold)
    assert result == new_scaffold
    assert "New overview." in result
    assert "old content" not in result


def test_preserve_user_zone_single_marker_legacy_backward_compat():
    """Single-marker files (index.md / legacy purpose.md) use the original
    file-level split: everything above the marker is preserved, everything below
    is replaced. The H1 and frontmatter of the new scaffold are stripped."""
    from synthadoc.agents.scaffold_agent import SCAFFOLD_MARKER, preserve_user_zone
    M = SCAFFOLD_MARKER
    existing = (
        "---\ntitle: Wiki Purpose\nstatus: active\n---\n\n"
        "# Wiki Purpose — ML\n\n"
        f"{M}\n\n"
        "## Overview\n\nOld overview.\n\n"
        "## What Belongs in This Wiki\n\n- Old bullet\n"
    )
    new_scaffold = (
        "---\ntitle: Wiki Purpose — ML\n---\n\n"
        "# Wiki Purpose — ML\n\n"
        f"{M}\n\n"
        "## Overview\n\nNew overview.\n\n"
        "## What Belongs in This Wiki\n\n- New bullet\n"
    )
    result = preserve_user_zone(existing, new_scaffold)

    assert result.count(SCAFFOLD_MARKER) == 1
    assert "# Wiki Purpose — ML" in result
    assert "New overview." in result
    assert "Old overview." not in result
    assert "New bullet" in result
    assert "Old bullet" not in result
