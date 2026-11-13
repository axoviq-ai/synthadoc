# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Peter White / axoviq.com
"""`synthadoc serve --all`: spawn arguments, sequential start, memory limit.

Process creation is always faked: a real `serve --all` regression would start
server processes without end, so these tests never launch anything.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

runner = CliRunner()


def _registry(tmp_path, names):
    reg = {}
    for i, n in enumerate(names):
        root = tmp_path / n
        (root / ".synthadoc").mkdir(parents=True)
        (root / ".synthadoc" / "config.toml").write_text(
            f"[server]\nport = {7100 + i}\n", encoding="utf-8")
        reg[n] = {"path": str(root), "port": 7100 + i}
    return reg


class _FakePopen:
    """Records the command line; pretends to be a live process."""
    instances: list = []

    def __init__(self, cmd, **kw):
        self.cmd = list(cmd)
        self.pid = 5000 + len(_FakePopen.instances)
        self.returncode = None
        _FakePopen.instances.append(self)

    def poll(self):
        return None


@pytest.fixture(autouse=True)
def _reset_popen():
    _FakePopen.instances = []
    yield


def _run(args, registry, *, total=16000, used=4000, per_wiki_rss=400, extra_patches=()):
    """Invoke `synthadoc <args>` with spawning and memory fully faked.

    Each fake server adds `per_wiki_rss` to the machine's used memory.
    """
    from synthadoc.cli.main import app
    state = {"used": float(used)}

    def fake_spawn_popen(cmd, **kw):
        p = _FakePopen(cmd, **kw)
        state["used"] += per_wiki_rss
        return p

    with patch("synthadoc.cli.serve.read_registry_all", return_value=registry), \
         patch("synthadoc.cli._wiki.probe_port", return_value=False), \
         patch("synthadoc.cli.serve.subprocess.Popen", side_effect=fake_spawn_popen), \
         patch("synthadoc.cli.serve.time.sleep"), \
         patch("synthadoc.cli.serve._wait_for_health", return_value=True), \
         patch("synthadoc.cli.serve.system_memory_mb", side_effect=lambda: (total, state["used"])), \
         patch("synthadoc.cli.serve.process_memory_mb", return_value=per_wiki_rss):
        return runner.invoke(app, args)


# ── the root-cause bug: children must never be `serve --all` again ───────────

def test_spawned_children_serve_one_wiki_not_all(tmp_path):
    reg = _registry(tmp_path, ["alpha", "beta"])
    result = _run(["serve", "--all"], reg)
    assert result.exit_code == 0, result.output
    assert len(_FakePopen.instances) == 2
    for p in _FakePopen.instances:
        assert "--all" not in p.cmd, f"child re-runs --all (fork bomb): {p.cmd}"
        assert "serve" in p.cmd
    spawned_wikis = {p.cmd[p.cmd.index("-w") + 1] for p in _FakePopen.instances}
    assert spawned_wikis == {"alpha", "beta"}


def test_spawned_children_do_not_inherit_max_memory_flag(tmp_path):
    reg = _registry(tmp_path, ["alpha"])
    _run(["serve", "--all", "--max-memory", "6GB"], reg)
    assert all("--max-memory" not in p.cmd for p in _FakePopen.instances)


# ── memory limit: default mode (stay under ~60% of the machine) ──────────────

def test_default_mode_stops_before_machine_crosses_sixty_percent(tmp_path):
    names = [f"w{i}" for i in range(10)]
    reg = _registry(tmp_path, names)
    # total 16000 -> ceiling 9600. used starts 8000, each wiki +400 => room for 4.
    result = _run(["serve", "--all"], reg, total=16000, used=8000, per_wiki_rss=400)
    assert result.exit_code == 0, result.output
    started = len(_FakePopen.instances)
    assert 1 <= started < 10
    assert started == 4, f"expected 4 started, got {started}\n{result.output}"


def test_default_mode_always_starts_at_least_one_on_a_busy_machine(tmp_path):
    reg = _registry(tmp_path, ["alpha", "beta"])
    result = _run(["serve", "--all"], reg, total=16000, used=14000, per_wiki_rss=400)
    assert len(_FakePopen.instances) == 1
    assert result.exit_code == 0


def test_skipped_wikis_are_reported_with_exact_commands_and_override_hint(tmp_path):
    reg = _registry(tmp_path, ["alpha", "beta", "gamma"])
    result = _run(["serve", "--all"], reg, total=16000, used=9000, per_wiki_rss=400)
    out = result.output
    assert "skipped" in out.lower()
    assert "synthadoc serve -w gamma" in out or "synthadoc serve -w beta" in out
    assert "--max-memory" in out and "GB" in out


# ── memory limit: --max-memory budget ────────────────────────────────────────

def test_max_memory_budget_limits_total_of_started_wikis(tmp_path):
    reg = _registry(tmp_path, [f"w{i}" for i in range(6)])
    # machine is busy (irrelevant in budget mode); each wiki ~500 MB; budget 1.5GB=1536MB
    result = _run(["serve", "--all", "--max-memory", "1.5GB"], reg,
                  total=16000, used=15000, per_wiki_rss=500)
    assert result.exit_code == 0, result.output
    assert len(_FakePopen.instances) == 3    # 3 x 500 = 1500 <= 1536; a 4th would be 2000


@pytest.mark.parametrize("bad", ["6000", "6", "6KB", "abc", "-1GB"])
def test_max_memory_without_valid_unit_is_rejected_before_anything_starts(tmp_path, bad):
    reg = _registry(tmp_path, ["alpha"])
    result = _run(["serve", "--all", "--max-memory", bad], reg)
    assert result.exit_code != 0
    assert _FakePopen.instances == []
    assert "GB" in result.output and "MB" in result.output


# ── unchanged behavior ───────────────────────────────────────────────────────

def test_already_running_wikis_are_not_spawned_again(tmp_path):
    from synthadoc.cli.main import app
    reg = _registry(tmp_path, ["alpha"])
    with patch("synthadoc.cli.serve.read_registry_all", return_value=reg), \
         patch("synthadoc.cli._wiki.probe_port", return_value=True), \
         patch("synthadoc.cli.serve.subprocess.Popen") as popen:
        result = runner.invoke(app, ["serve", "--all"])
    popen.assert_not_called()
    assert "already running" in result.output


def test_unreadable_system_memory_requires_explicit_max_memory(tmp_path):
    from synthadoc.cli.main import app
    reg = _registry(tmp_path, ["alpha"])
    with patch("synthadoc.cli.serve.read_registry_all", return_value=reg), \
         patch("synthadoc.cli.serve.system_memory_mb", return_value=None), \
         patch("synthadoc.cli.serve.subprocess.Popen") as popen:
        result = runner.invoke(app, ["serve", "--all"])
    popen.assert_not_called()
    assert result.exit_code != 0
    assert "ERR-SRV-005" in result.output and "--max-memory" in result.output


def test_max_memory_without_all_is_rejected():
    from synthadoc.cli.main import app
    result = runner.invoke(app, ["serve", "--max-memory", "6GB"])
    assert result.exit_code != 0
    assert "--all" in result.output
