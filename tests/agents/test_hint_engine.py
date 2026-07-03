# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import json
import pytest
from pathlib import Path
from synthadoc.agents.hint_engine import HintEngine, _dynamic_followup, _slug_to_title


@pytest.fixture(autouse=True)
def reset_hints():
    """Reset HintEngine to built-in defaults before each test."""
    HintEngine.configure(None)
    yield
    HintEngine.configure(None)


# ── build_pool ────────────────────────────────────────────────────────────────

def test_build_pool_mode_hints_first():
    pool = HintEngine.build_pool("EXPLORER")
    explorer_hints = ["What topics does this wiki cover?",
                      "What are the key topics in this wiki?",
                      "Show wiki status"]
    assert pool[:3] == explorer_hints


def test_build_pool_includes_other_mode_hints():
    pool = HintEngine.build_pool("EXPLORER")
    # POWER_USER hints must appear somewhere after the EXPLORER hints
    assert "Export my wiki as llms.txt" in pool
    assert "Which pages are marked stale?" in pool


def test_build_pool_no_duplicates():
    pool = HintEngine.build_pool("POWER_USER")
    assert len(pool) == len(set(pool))


def test_build_pool_is_cached():
    p1 = HintEngine.build_pool("POWER_USER")
    p2 = HintEngine.build_pool("POWER_USER")
    assert p1 is p2


# ── initial_hints ─────────────────────────────────────────────────────────────

def test_initial_hints_returns_three():
    for mode in ("NEW_WIKI", "EXPLORER", "HEALTH_CHECK", "POWER_USER"):
        assert len(HintEngine.initial_hints(mode)) == 3


def test_initial_hints_are_mode_first():
    hints = HintEngine.initial_hints("NEW_WIKI")
    assert hints[0] == "How do I ingest my first document?"


# ── after_response_windowed ───────────────────────────────────────────────────

def test_windowed_advances_cursor():
    pool = HintEngine.build_pool("POWER_USER")
    _, c1 = HintEngine.after_response_windowed("some answer", "POWER_USER", 0)
    assert c1 == 3 % len(pool)


def test_windowed_wraps_around():
    pool = HintEngine.build_pool("POWER_USER")
    last = len(pool) - 1
    hints, next_c = HintEngine.after_response_windowed("answer", "POWER_USER", last)
    assert len(hints) == 3
    assert next_c < len(pool)


def test_windowed_topic_match_advances_cursor():
    pool = HintEngine.build_pool("POWER_USER")
    _, cursor_before = HintEngine.after_response_windowed("answer", "POWER_USER", 0)
    _, cursor_after = HintEngine.after_response_windowed("the page is stale", "POWER_USER", cursor_before)
    # topic match must still advance the cursor so rotation continues
    assert cursor_after == (cursor_before + 3) % len(pool)


def test_windowed_topic_match_returns_relevant_hints():
    # answer-body match (no question supplied)
    hints, _ = HintEngine.after_response_windowed("your page is stale and outdated", "POWER_USER", 0)
    assert "How do I run a lint check?" in hints


def test_windowed_no_topic_match_returns_pool_window():
    pool = HintEngine.build_pool("POWER_USER")
    hints, _ = HintEngine.after_response_windowed("generic answer with no keywords", "POWER_USER", 0)
    assert hints == pool[:3]


def test_windowed_skips_repeated_topic_hints():
    # Same topic match on consecutive calls should not return the same hints twice.
    stale_answer = "your page is stale and outdated"
    hints1, c1 = HintEngine.after_response_windowed(stale_answer, "POWER_USER", 0)
    # Second call passes previous_hints — same topic match should be skipped.
    hints2, _ = HintEngine.after_response_windowed(stale_answer, "POWER_USER", c1,
                                                    previous_hints=hints1)
    assert hints2 != hints1, "repeated topic hints must be suppressed"


def test_windowed_allows_topic_hints_after_different_previous():
    stale_answer = "your page is stale and outdated"
    hints1, _ = HintEngine.after_response_windowed(stale_answer, "POWER_USER", 0,
                                                   previous_hints=["some", "other", "hints"])
    assert "How do I run a lint check?" in hints1


# ── question-intent vs answer-body topic matching ─────────────────────────────

def test_windowed_question_intent_fires_lifecycle_hints():
    # "Activate a draft page" → question contains "draft" and "activate"
    # → lifecycle hints, NOT domain content from the answer
    hints, _ = HintEngine.after_response_windowed(
        "The September draft proposed a 5-year methodology.",  # domain answer with "draft"
        "POWER_USER", 0,
        question="Activate a draft page",
    )
    assert "Activate a draft page" in hints or "Show me recently updated wiki pages" in hints


def test_windowed_domain_answer_with_draft_does_not_fire_when_question_clean():
    # "draft" in a financial analysis answer must NOT trigger lifecycle hints
    # when the question itself contains no lifecycle keywords
    pool = HintEngine.build_pool("POWER_USER")
    answer = "The September draft proposed a 5-year averaging window for the sales-to-capital ratio."
    question = "维护性资本支出的计算方法是什么？"  # no lifecycle keywords
    hints, _ = HintEngine.after_response_windowed(answer, "POWER_USER", 0, question=question)
    # Must not return lifecycle pattern hints
    assert "Activate a draft page" not in hints
    # Should be 2 pool + 1 dynamic (answer has no [[links]], so 3 pool)
    assert hints == pool[:3]


def test_windowed_answer_body_catches_emergent_stale_signal():
    # Question is neutral; answer reveals "stale" — answer-body match should fire
    hints, _ = HintEngine.after_response_windowed(
        "This page is stale and has not been updated in 6 months.",
        "POWER_USER", 0,
        question="Tell me about the portfolio overview",
    )
    assert "How do I run a lint check?" in hints


def test_windowed_stale_keyword_does_not_match_inside_threshold():
    # "old" appears inside "threshold" — must NOT trigger stale topic hints
    pool = HintEngine.build_pool("POWER_USER")
    answer = "The minimum threshold is 10%. Exceed it to qualify."
    question = "What does capex policy analysis cover?"
    hints, _ = HintEngine.after_response_windowed(answer, "POWER_USER", 0, question=question)
    # stale hints should NOT fire — "old" is only a substring of "threshold"
    assert "How do I run a lint check?" not in hints
    assert hints == pool[:3] or hints[2] not in pool  # pool window or dynamic hint


def test_windowed_outdated_in_domain_answer_does_not_fire_stale_hints():
    # "outdated" as a whole word inside a financial answer (e.g. "outdated build-out phases")
    # must NOT trigger stale hints; only "stale" is in answer_keywords for the stale pattern
    pool = HintEngine.build_pool("POWER_USER")
    answer = (
        "The September draft was withdrawn because years 4–5 captured "
        "outdated build-out phases no longer reflecting current operations. "
        "The final 3-year method corrects this. See [[capex-policy-analysis]]."
    )
    question = "What does capex policy analysis cover?"
    hints, _ = HintEngine.after_response_windowed(answer, "POWER_USER", 0, question=question)
    assert "How do I run a lint check?" not in hints


def test_windowed_stale_as_whole_word_still_fires():
    # "stale" as a standalone word must still trigger the stale topic hints
    hints, _ = HintEngine.after_response_windowed(
        "This page is stale and has not been updated.",
        "POWER_USER", 0,
        question="What are the stale pages?",
    )
    assert "How do I run a lint check?" in hints


def test_windowed_pdf_url_in_domain_answer_does_not_fire_ingest_hints():
    # "pdf" and "url" in a financial answer (e.g. "the PDF report", "the filing URL")
    # must NOT trigger ingest hints; only "ingest" is in answer_keywords.
    pool = HintEngine.build_pool("POWER_USER")
    answer = "The source PDF document and the URL to the SEC filing are referenced here."
    question = "What does the annual report cover?"
    hints, _ = HintEngine.after_response_windowed(answer, "POWER_USER", 0, question=question)
    assert "What file types can I ingest?" not in hints
    assert "How do I bulk ingest?" not in hints


def test_windowed_isolated_in_domain_answer_does_not_fire_orphan_hints():
    # "isolated" in a financial risk context must NOT trigger orphan hints.
    answer = "GreenField's project debt is structured as isolated non-recourse financing."
    question = "What are the main risks?"
    hints, _ = HintEngine.after_response_windowed(answer, "POWER_USER", 0, question=question)
    assert "What pages are orphan pages?" not in hints
    assert "Run lint on orphans only" not in hints


def test_windowed_orphan_in_dashboard_description_does_not_fire_orphan_hints():
    # "orphan" mentioned as a dashboard feature ("surfacing contradicted, orphan,
    # and recently updated pages") must NOT trigger orphan hints.
    # answer_keywords is now ["no inbound"] — "orphan" alone is too common.
    answer = (
        "Dashboard (dashboard) — surfacing contradicted, orphan, and recently updated pages. "
        "See [[dashboard]] for details."
    )
    question = "What raw funding sources does this wiki contain?"
    hints, _ = HintEngine.after_response_windowed(answer, "POWER_USER", 0, question=question)
    assert "What pages are orphan pages?" not in hints
    assert "Run lint on orphans only" not in hints


def test_windowed_contradiction_in_domain_answer_does_not_fire_lint_hints():
    # "contradiction" in financial analysis must NOT trigger lint hints;
    # only "lint" and "dangling" are in answer_keywords for the lint pattern.
    pool = HintEngine.build_pool("POWER_USER")
    answer = "There is a contradiction between the Q3 and Q4 revenue figures in the report."
    question = "What does the revenue growth analysis cover?"
    hints, _ = HintEngine.after_response_windowed(answer, "POWER_USER", 0, question=question)
    assert "List contradicted pages" not in hints
    assert "Run lint on contradictions only" not in hints


def test_windowed_recurring_revenue_does_not_fire_schedule_hints():
    # "recurring" and "schedule" in financial domain text must NOT trigger schedule hints;
    # only "cron" is in answer_keywords for the schedule pattern.
    pool = HintEngine.build_pool("POWER_USER")
    answer = "TechNova's recurring SaaS revenue grew 24%. The payment schedule is quarterly."
    question = "What does the revenue analysis show?"
    hints, _ = HintEngine.after_response_windowed(answer, "POWER_USER", 0, question=question)
    assert "Show my scheduled tasks" not in hints
    assert "Schedule a daily ingest at 6 AM" not in hints


def test_windowed_job_losses_in_domain_answer_does_not_fire_job_hints():
    # "job" and "jobs" in an economic context must NOT trigger wiki job-status hints;
    # only "ingest status" and "lint status" are in answer_keywords.
    pool = HintEngine.build_pool("POWER_USER")
    answer = "RetailPulse's restructuring resulted in 200 job losses across its distribution jobs."
    question = "What are the operational risks?"
    hints, _ = HintEngine.after_response_windowed(answer, "POWER_USER", 0, question=question)
    assert "Show me job status" not in hints
    assert "List all jobs" not in hints


def test_windowed_updated_figures_do_not_fire_changed_hints():
    # "updated", "recently", and "added" in a financial answer must NOT trigger
    # the changed topic-pattern hints; only "re-ingested" is in answer_keywords.
    # The changed pattern's 3rd hint is "Show me recently updated wiki pages";
    # if the pattern fired it would appear at hints[2]. Pool[:3] has
    # "What pages were added this year?" at [2] instead.
    answer = (
        "The updated figures show recently added capacity. "
        "Management recently revised its guidance for this year."
    )
    question = "What is the 2026 outlook?"
    hints, _ = HintEngine.after_response_windowed(answer, "POWER_USER", 0, question=question)
    # Pattern-fire would produce "Show me recently updated wiki pages" at slot 2
    assert "Show me recently updated wiki pages" not in hints


def test_windowed_graph_in_domain_answer_does_not_fire_export_hints():
    # "graph" in "navigation graph" / "knowledge graph" must NOT trigger export hints;
    # only "export" and "llms" are in answer_keywords for the export pattern.
    pool = HintEngine.build_pool("POWER_USER")
    answer = (
        "Cross-references available in the wiki's navigation graph link these pages. "
        "See [[portfolio-valuation-report-fy2025]] for full details."
    )
    question = "What does portfolio valuation report cover?"
    hints, _ = HintEngine.after_response_windowed(answer, "POWER_USER", 0, question=question)
    assert "Export as llms.txt for AI tools" not in hints
    assert "Export as GraphML" not in hints


def test_windowed_export_in_question_fires_export_hints():
    # "export" in the QUESTION must still trigger export hints
    hints, _ = HintEngine.after_response_windowed(
        "You can export the wiki in several formats.",
        "POWER_USER", 0,
        question="How do I export my wiki as a graph?",
    )
    assert "Export as llms.txt for AI tools" in hints or "Export as GraphML" in hints


def test_windowed_structure_in_domain_answer_does_not_fire_scaffold_hints():
    # "structure" in a financial context (e.g. "project finance structure") must NOT
    # trigger scaffold hints; only "scaffold" is in answer_keywords for that pattern.
    pool = HintEngine.build_pool("POWER_USER")
    answer = (
        "GreenField has the highest leverage due to its project finance structure. "
        "Each asset is independently financed. See [[portfolio-risk-metrics-report-fy2025]]."
    )
    question = "What does portfolio risk metrics report cover?"
    hints, _ = HintEngine.after_response_windowed(answer, "POWER_USER", 0, question=question)
    assert "Rebuild the wiki scaffold" not in hints
    assert "What does scaffold generate?" not in hints


def test_windowed_scaffold_in_question_fires_scaffold_hints():
    # "scaffold" in the QUESTION must still trigger scaffold hints
    hints, _ = HintEngine.after_response_windowed(
        "The scaffold creates starter pages for your wiki.",
        "POWER_USER", 0,
        question="How do I rebuild the wiki scaffold structure?",
    )
    assert "Rebuild the wiki scaffold" in hints or "What does scaffold generate?" in hints


def test_windowed_flagged_in_domain_answer_does_not_fire_adversarial_hints():
    # "flagged" in a financial context must NOT trigger adversarial hints;
    # only "adversarial" and "claim concern" are in answer_keywords for that pattern.
    pool = HintEngine.build_pool("POWER_USER")
    answer = (
        "TechNova was flagged for overestimation under the 5-year methodology. "
        "See [[capex-policy-analysis]] for details."
    )
    question = "How does capex policy analysis connect to technova inc?"
    hints, _ = HintEngine.after_response_windowed(answer, "POWER_USER", 0, question=question)
    assert "Which pages have adversarial warnings?" not in hints
    assert "Run the adversarial lint pass" not in hints


def test_windowed_adversarial_in_question_fires_adversarial_hints():
    # "flagged" in the QUESTION (user intent, no other pattern matches) triggers adversarial hints
    hints, _ = HintEngine.after_response_windowed(
        "Page X has no issues.",
        "POWER_USER", 0,
        question="Which pages are flagged for overstated claims?",
    )
    assert "Which pages have adversarial warnings?" in hints or "Run the adversarial lint pass" in hints


def test_windowed_outdated_in_question_fires_stale_hints():
    # "outdated" in the QUESTION (user intent) must still trigger stale hints
    hints, _ = HintEngine.after_response_windowed(
        "Several pages have not been updated recently.",
        "POWER_USER", 0,
        question="Which pages are outdated?",
    )
    assert "How do I run a lint check?" in hints


def test_windowed_question_intent_takes_priority_over_answer_body():
    # Question matches lifecycle; answer matches ingest — question wins
    hints, _ = HintEngine.after_response_windowed(
        "You can ingest a PDF or URL into the wiki.",  # ingest keywords
        "POWER_USER", 0,
        question="Activate a draft page",  # lifecycle keywords
    )
    # Should return lifecycle hints (question match), not ingest hints
    lifecycle_hints = {"Show me recently updated wiki pages", "Activate a draft page",
                       "Show me recently archived wiki pages"}
    assert any(h in lifecycle_hints for h in hints)


# ── _slug_to_title ────────────────────────────────────────────────────────────

def test_slug_to_title_replaces_hyphens():
    assert _slug_to_title("technova-inc") == "technova inc"


def test_slug_to_title_strips_fy_year():
    assert _slug_to_title("portfolio-valuation-report-fy2025") == "portfolio valuation report"


def test_slug_to_title_strips_bare_year():
    assert _slug_to_title("market-outlook-2026") == "market outlook"


def test_slug_to_title_no_year():
    assert _slug_to_title("capex-policy-analysis") == "capex policy analysis"


# ── _dynamic_followup ─────────────────────────────────────────────────────────

def test_dynamic_followup_none_when_no_links():
    assert _dynamic_followup("What is X?", "Plain answer with no wiki links.") is None


def test_dynamic_followup_none_when_only_scaffold_links():
    answer = "See [[overview]] and [[index]] for orientation."
    assert _dynamic_followup("What is X?", answer) is None


def test_dynamic_followup_picks_first_non_scaffold_slug():
    answer = "See [[overview]] then check [[technova-inc]] for details."
    result = _dynamic_followup("What is the revenue growth?", answer)
    assert result is not None
    assert "technova inc" in result


def test_dynamic_followup_compound_question_strips_second_clause():
    # "What is X and what are Y?" — after prefix strip the 5-word slice ends in
    # "and what".  Both "and" and "what" are trailing stop words so subject
    # must be trimmed to just the first clause.
    answer = "See [[capex-policy-analysis]] for details."
    question = (
        "What is the maintenance CAPEX methodology and what are the final "
        "maintenance CAPEX estimates for each portfolio company?"
    )
    result = _dynamic_followup(question, answer)
    assert result is not None
    assert "and what" not in result.lower()
    assert "methodology" in result.lower()


def test_dynamic_followup_generated_hint_as_question_no_duplicate_connect():
    # When the user re-asks a generated "How does X connect to Y?" hint,
    # "connect" lands at position 4 in the words[:5] slice.  It must be
    # stripped as a trailing stop word so the next hint reads
    # "How does X connect to Z?" not "How does X connect connect to Z?".
    answer = (
        "See [[portfolio-valuation-report-fy2025]] and [[technova-inc]]."
    )
    question = "How does maintenance CAPEX methodology connect to Capex Policy Analysis?"
    result = _dynamic_followup(question, answer)
    assert result is not None
    assert "connect connect" not in result.lower()
    assert "methodology" in result.lower()


def test_dynamic_followup_which_has_truncates_at_aux_verb():
    # "Which X has Y?" — prefix regex strips "Which " but "has" lands at
    # position 2 in the 5-word slice.  Aux-verb truncation must stop there
    # so the subject is just "portfolio company", not "portfolio company has…".
    answer = "See [[portfolio-risk-metrics-report-fy2025]] and [[greenfield-energy-annual-report-2025]]."
    question = "Which portfolio company has the highest leverage risk?"
    result = _dynamic_followup(question, answer)
    assert result is not None
    assert "has" not in result.lower()
    assert "highest" not in result.lower()


def test_dynamic_followup_strips_question_prefix():
    answer = "Revenue grew 16%. See [[technova-inc]]."
    result = _dynamic_followup("What is the revenue growth outlook?", answer)
    # Subject extracted should not start with "what is"
    assert result is not None
    assert "what is" not in result.lower()


def test_dynamic_followup_strips_bare_what_before_noun():
    # "What raw funding sources…" — prefix regex misses "what [noun]".
    # _LEADING_QUESTION_WORD_RE must strip the bare "What" as a second pass.
    answer = "See [[market-outlook-2026-sector-analysis]] for details."
    question = "What raw funding sources does this wiki contain?"
    result = _dynamic_followup(question, answer)
    assert result is not None
    assert not result.lower().startswith("what "), (
        f"Subject still starts with 'What': {result}"
    )


def test_dynamic_followup_empty_question_uses_fallback_template():
    answer = "See [[capex-policy-analysis]] for details."
    result = _dynamic_followup("", answer)
    assert result == "What does capex policy analysis cover?"


def test_dynamic_followup_circular_single_link_is_none():
    # When the generated hint would be identical to the question asked and no
    # other non-scaffold links exist, _dynamic_followup returns None.
    answer = "Refer to [[capex-policy-analysis]]."
    result = _dynamic_followup("What does capex policy analysis cover?", answer)
    assert result is None


def test_dynamic_followup_overlap_uses_second_link():
    # When the first link is circular (overlaps the question subject),
    # _dynamic_followup should fall through to the second link.
    answer = "See [[capex-policy-analysis]] for policy. Also see [[technova-inc]] for an example."
    result = _dynamic_followup("What does capex policy analysis cover?", answer)
    assert result is not None
    assert "technova inc" in result


def test_dynamic_followup_skips_pipe_alias():
    # [[slug|Display text]] — should extract slug, not alias
    answer = "Refer to [[technova-inc|TechNova]] for numbers."
    result = _dynamic_followup("What is the revenue outlook?", answer)
    assert result is not None
    assert "technova inc" in result


def test_dynamic_followup_cjk_question_uses_simple_template():
    answer = "Revenue grew 18.2%. See [[technova-inc]] for details."
    result = _dynamic_followup("TechNova 在 2025 财年的收入增长率和 EBITDA 利润率是多少？", answer)
    assert result == "What does technova inc cover?"


def test_dynamic_followup_strips_fy_year_in_output():
    answer = "See [[portfolio-valuation-report-fy2025]]."
    result = _dynamic_followup("What are valuations?", answer)
    assert "fy2025" not in result.lower()
    assert "2025" not in result


# ── after_response_windowed — 2+1 composition ────────────────────────────────

def test_windowed_with_question_returns_dynamic_as_third():
    answer = "TechNova grew 16%. See [[technova-inc]] for details."
    question = "What is the 2026 revenue growth outlook?"
    hints, _ = HintEngine.after_response_windowed(answer, "POWER_USER", 0, question=question)
    assert len(hints) == 3
    pool = HintEngine.build_pool("POWER_USER")
    # First two come from pool, third is dynamic (not in pool)
    assert hints[:2] == pool[:2]
    assert hints[2] not in pool


def test_windowed_without_question_returns_3_pool_hints():
    answer = "TechNova grew 16%. See [[technova-inc]] for details."
    hints, _ = HintEngine.after_response_windowed(answer, "POWER_USER", 0)
    pool = HintEngine.build_pool("POWER_USER")
    assert hints == pool[:3]


def test_windowed_no_links_in_answer_falls_back_to_pool():
    answer = "The wiki does not cover this topic."
    question = "What is the revenue growth?"
    hints, _ = HintEngine.after_response_windowed(answer, "POWER_USER", 0, question=question)
    pool = HintEngine.build_pool("POWER_USER")
    assert hints == pool[:3]


def test_windowed_topic_match_takes_priority_over_dynamic():
    answer = "Your page is stale and outdated. See [[technova-inc]]."
    question = "What pages are stale?"
    hints, _ = HintEngine.after_response_windowed(answer, "POWER_USER", 0, question=question)
    # Topic match fires; lint hint must be present regardless of dynamic
    assert "How do I run a lint check?" in hints


def test_windowed_dynamic_falls_back_to_pool_when_only_circular_link():
    # Answer has only one non-scaffold link and it's the same page the question
    # asks about — no valid dynamic hint exists → fall back to 3 pool hints.
    pool = HintEngine.build_pool("POWER_USER")
    answer = "See [[capex-policy-analysis]] for the full methodology. " * 3
    question = "What does capex policy analysis cover?"
    hints, _ = HintEngine.after_response_windowed(answer, "POWER_USER", 0, question=question)
    assert hints == pool[:3], "circular dynamic hint must be dropped in favour of pool window"


def test_windowed_dynamic_uses_second_link_when_first_is_circular():
    # Answer cites the same-page first, then another page — second link used.
    answer = (
        "See [[capex-policy-analysis]] for the framework. "
        "[[technova-inc]] is an example company."
    )
    question = "What does capex policy analysis cover?"
    hints, _ = HintEngine.after_response_windowed(answer, "POWER_USER", 0, question=question)
    assert len(hints) == 3
    assert any("technova inc" in h for h in hints), "second link should supply the dynamic hint"


def test_windowed_dynamic_not_duplicated_in_pool_window():
    # If _dynamic_followup returns a string already in the window, fall back to 3 pool hints
    pool = HintEngine.build_pool("POWER_USER")
    # Construct answer whose dynamic followup would clash with pool[2]
    # (hard to force deterministically, so just verify length stays 3)
    answer = "See [[technova-inc]]."
    hints, _ = HintEngine.after_response_windowed(answer, "POWER_USER", 0, question="What is revenue?")
    assert len(hints) == 3


# ── after_response (backward compat) ─────────────────────────────────────────

def test_after_response_returns_list():
    result = HintEngine.after_response("some answer", "POWER_USER")
    assert isinstance(result, list)
    assert len(result) == 3


# ── configure() — external hints.json ────────────────────────────────────────

def test_configure_extends_mode_hints(tmp_path):
    hints_file = tmp_path / "hints.json"
    hints_file.write_text(json.dumps({
        "by_mode": {
            "POWER_USER": ["My custom power hint"]
        }
    }), encoding="utf-8")
    HintEngine.configure(hints_file)
    pool = HintEngine.build_pool("POWER_USER")
    assert "My custom power hint" in pool
    assert "Export my wiki as llms.txt" in pool  # built-in preserved


def test_configure_adds_new_mode(tmp_path):
    hints_file = tmp_path / "hints.json"
    hints_file.write_text(json.dumps({
        "by_mode": {
            "CUSTOM_ROLE": ["Custom role hint 1", "Custom role hint 2"]
        }
    }), encoding="utf-8")
    HintEngine.configure(hints_file)
    pool = HintEngine.build_pool("CUSTOM_ROLE")
    assert "Custom role hint 1" in pool


def test_configure_no_duplicates_from_file(tmp_path):
    hints_file = tmp_path / "hints.json"
    hints_file.write_text(json.dumps({
        "by_mode": {
            "POWER_USER": ["Export my wiki as llms.txt"]  # already a built-in
        }
    }), encoding="utf-8")
    HintEngine.configure(hints_file)
    pool = HintEngine.build_pool("POWER_USER")
    assert pool.count("Export my wiki as llms.txt") == 1


def test_configure_custom_topic_pattern_takes_priority(tmp_path):
    hints_file = tmp_path / "hints.json"
    hints_file.write_text(json.dumps({
        "topic_patterns": [
            {"keywords": ["kubernetes"], "hints": ["K8s hint 1", "K8s hint 2", "K8s hint 3"]}
        ]
    }), encoding="utf-8")
    HintEngine.configure(hints_file)
    hints, _ = HintEngine.after_response_windowed("kubernetes deployment failed", "POWER_USER", 0)
    assert hints == ["K8s hint 1", "K8s hint 2", "K8s hint 3"]


def test_configure_missing_file_uses_builtins():
    HintEngine.configure(Path("/nonexistent/hints.json"))
    hints = HintEngine.initial_hints("POWER_USER")
    # Falls back to _FALLBACK_BY_MODE — just verify the core time-range hint is present
    assert "What changed in the wiki this week?" in hints


def test_configure_malformed_file_uses_builtins(tmp_path):
    hints_file = tmp_path / "hints.json"
    hints_file.write_text("not valid json", encoding="utf-8")
    HintEngine.configure(hints_file)  # must not raise
    assert len(HintEngine.initial_hints("POWER_USER")) > 0


def test_configure_resets_on_second_call(tmp_path):
    hints_file = tmp_path / "hints.json"
    hints_file.write_text(json.dumps({
        "by_mode": {"POWER_USER": ["Temp hint"]}
    }), encoding="utf-8")
    HintEngine.configure(hints_file)
    assert "Temp hint" in HintEngine.build_pool("POWER_USER")

    HintEngine.configure(None)  # reset
    assert "Temp hint" not in HintEngine.build_pool("POWER_USER")
