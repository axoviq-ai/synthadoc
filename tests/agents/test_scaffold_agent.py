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

def _make_result(
    index_md: str | None = None,
    agents_md: str | None = None,
    purpose_md: str | None = None,
    dashboard_intro: str = "x",
    domain: str = "Machine Learning",
) -> "ScaffoldResult":
    from synthadoc.agents.scaffold_agent import ScaffoldResult
    return ScaffoldResult(
        index_md=index_md if index_md is not None else (
            f"---\ntitle: Index\ncreated: '2026-01-01'\n---\n\n# {domain} — Index\n\n"
            f"## Core Concepts\n*key ideas*\n\n- [[neural-networks]]\n"
        ),
        agents_md=agents_md if agents_md is not None else (
            f"# AGENTS.md — {domain} Wiki\n\n## Purpose\nCaptures knowledge.\n\n"
            f"## Ingest Guidelines\n- Summarize.\n\n## Query Guidelines\n- Cite sources.\n"
        ),
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


def test_validate_scaffold_result_fails_missing_ingest_guidelines():
    from synthadoc.agents.scaffold_agent import _validate_scaffold_result
    result = _make_result(agents_md="# AGENTS.md\n\n## Query Guidelines\n- Cite.\n")
    with pytest.raises(ValueError, match="Ingest Guidelines"):
        _validate_scaffold_result(result, "Machine Learning")


def test_validate_scaffold_result_fails_missing_query_guidelines():
    from synthadoc.agents.scaffold_agent import _validate_scaffold_result
    result = _make_result(agents_md="# AGENTS.md\n\n## Ingest Guidelines\n- Summarize.\n")
    with pytest.raises(ValueError, match="Query Guidelines"):
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
