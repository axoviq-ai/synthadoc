# Copyright (C) 2026 Paul Chen / axoviq.com
# SPDX-License-Identifier: AGPL-3.0-or-later
from synthadoc.agents.hint_engine import HEALTH_CHECK, HintEngine


def test_content_health_chip_when_issues_present():
    hints = HintEngine.initial_hints(
        HEALTH_CHECK,
        context={"content_health": 3},
    )
    assert "Run content health resolver" in hints


def test_content_health_chip_absent_when_zero():
    hints = HintEngine.initial_hints(
        HEALTH_CHECK,
        context={"content_health": 0},
    )
    assert "Run content health resolver" not in hints


def test_content_health_priority_after_broken_citations():
    # Use a sparse context so both chips fit within _INITIAL_HINT_COUNT (3).
    hints = HintEngine.initial_hints(
        HEALTH_CHECK,
        context={
            "broken_citations": 1,
            "content_health": 1,
        },
    )
    assert "Fix broken citations" in hints
    assert "Run content health resolver" in hints
    # content health must come after broken_citations in the priority list
    ci = hints.index("Run content health resolver")
    bc = hints.index("Fix broken citations")
    assert ci > bc


def test_content_health_chip_in_hints_pool():
    """'Run content health resolver' must be in HEALTH_CHECK pool so it can appear without priority."""
    pool = HintEngine.build_pool(HEALTH_CHECK)
    assert "Run content health resolver" in pool
