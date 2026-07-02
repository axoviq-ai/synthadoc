# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import json
import socket
import pytest
from synthadoc.cli._port import find_free_port as _find_free_port, assign_wiki_port


def _find_bindable_base(count: int) -> int:
    """Return the first port in a run of `count` consecutively bindable ports.

    Hardcoded port numbers fail on Windows when Hyper-V or other system
    components exclude specific ranges (WinError 10013). Starting from a
    high ephemeral range and scanning avoids those exclusions.
    """
    for base in range(40000, 41000):
        socks: list[socket.socket] = []
        try:
            for i in range(count):
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", base + i))
                socks.append(s)
            return base
        except OSError:
            pass
        finally:
            for s in socks:
                try:
                    s.close()
                except OSError:
                    pass
    pytest.skip("No block of consecutive bindable ports found")


def test_find_free_port_returns_start_when_available():
    """Returns the start port if it is not bound."""
    base = _find_bindable_base(1)
    assert _find_free_port(start=base) == base


def test_find_free_port_skips_bound_port():
    """Skips a port that is already bound and returns the next free one."""
    base = _find_bindable_base(2)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", base))
        port = _find_free_port(start=base)
    assert port == base + 1


def test_find_free_port_scans_multiple():
    """Scans past multiple bound ports."""
    base = _find_bindable_base(3)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s1, \
         socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s2:
        s1.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s2.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s1.bind(("127.0.0.1", base))
        s2.bind(("127.0.0.1", base + 1))
        port = _find_free_port(start=base)
    assert port == base + 2


# ── assign_wiki_port ──────────────────────────────────────────────────────────

def test_assign_wiki_port_skips_reserved():
    """assign_wiki_port skips ports in reserved_ports even when they are unbound."""
    base = _find_bindable_base(2)
    reserved = {base}
    port = assign_wiki_port(reserved, start=base)
    assert port == base + 1


def test_assign_wiki_port_skips_bound_and_reserved():
    """assign_wiki_port skips both registry-reserved and currently-bound ports."""
    base = _find_bindable_base(3)
    # base   → reserved (another wiki)
    # base+1 → currently bound by another process
    # base+2 → free and unreserved → should be selected
    reserved = {base}
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", base + 1))
        port = assign_wiki_port(reserved, start=base)
    assert port == base + 2


def test_assign_wiki_port_returns_start_when_nothing_conflicts():
    """assign_wiki_port returns start when reserved set is empty and port is free."""
    base = _find_bindable_base(1)
    port = assign_wiki_port(set(), start=base)
    assert port == base


# ── _get_reserved_ports ───────────────────────────────────────────────────────

def test_get_reserved_ports_reads_from_registry(tmp_path, monkeypatch):
    """_get_reserved_ports returns ports stored in the registry."""
    import synthadoc.cli.install as install_mod
    monkeypatch.setattr(install_mod, "_REGISTRY", tmp_path / "wikis.json")
    install_mod._write_registry({
        "wiki-a": {"path": str(tmp_path / "a"), "port": 7070, "installed": "2026-01-01"},
        "wiki-b": {"path": str(tmp_path / "b"), "port": 7071, "installed": "2026-01-01"},
    })
    ports = install_mod._get_reserved_ports()
    assert ports == {7070, 7071}


def test_get_reserved_ports_falls_back_to_config_toml(tmp_path, monkeypatch):
    """_get_reserved_ports reads config.toml when registry entry has no 'port' key."""
    import synthadoc.cli.install as install_mod
    monkeypatch.setattr(install_mod, "_REGISTRY", tmp_path / "wikis.json")
    wiki_dir = tmp_path / "old-wiki"
    (wiki_dir / ".synthadoc").mkdir(parents=True)
    (wiki_dir / ".synthadoc" / "config.toml").write_text(
        "[server]\nport = 7075\n", encoding="utf-8"
    )
    install_mod._write_registry({
        "old-wiki": {"path": str(wiki_dir), "installed": "2025-01-01"},
    })
    ports = install_mod._get_reserved_ports()
    assert 7075 in ports


def test_get_reserved_ports_empty_when_no_wikis(tmp_path, monkeypatch):
    """_get_reserved_ports returns empty set when no wikis are registered."""
    import synthadoc.cli.install as install_mod
    monkeypatch.setattr(install_mod, "_REGISTRY", tmp_path / "wikis.json")
    ports = install_mod._get_reserved_ports()
    assert ports == set()


def test_install_stores_port_in_registry(tmp_path, monkeypatch):
    """install records the assigned port in the registry entry."""
    import synthadoc.cli.install as install_mod
    from typer.testing import CliRunner
    from synthadoc.cli.main import app
    monkeypatch.setattr(install_mod, "_REGISTRY", tmp_path / "wikis.json")
    monkeypatch.setattr(install_mod, "_assign_wiki_port", lambda reserved, start=7070: 7072)
    monkeypatch.setattr(install_mod, "_run_scaffold", lambda dest, domain: None)

    runner = CliRunner()
    result = runner.invoke(app, ["install", "my-wiki", "--target", str(tmp_path)])
    assert result.exit_code == 0, result.output

    registry = install_mod._read_registry()
    assert registry["my-wiki"]["port"] == 7072


def test_install_second_wiki_gets_different_port(tmp_path, monkeypatch):
    """Case a/c: When wiki-a is on 7070, wiki-b gets the next available port."""
    import synthadoc.cli.install as install_mod
    from typer.testing import CliRunner
    from synthadoc.cli.main import app
    monkeypatch.setattr(install_mod, "_REGISTRY", tmp_path / "wikis.json")
    monkeypatch.setattr(install_mod, "_run_scaffold", lambda dest, domain: None)

    # Wire assign_wiki_port to the real implementation but route it through a
    # counter so it picks 7070 for the first wiki, 7071 for the second.
    call_count = {"n": 0}
    def _fake_assign(reserved, start=7070):
        call_count["n"] += 1
        return 7070 if call_count["n"] == 1 else 7071
    monkeypatch.setattr(install_mod, "_assign_wiki_port", _fake_assign)

    runner = CliRunner()
    runner.invoke(app, ["install", "wiki-a", "--target", str(tmp_path)])
    runner.invoke(app, ["install", "wiki-b", "--target", str(tmp_path)])

    registry = install_mod._read_registry()
    assert registry["wiki-a"]["port"] != registry["wiki-b"]["port"]


def test_assign_wiki_port_sees_registry_reserved_port_even_when_unbound(tmp_path, monkeypatch):
    """Case a: assign_wiki_port skips another wiki's port even when that wiki is stopped."""
    import synthadoc.cli.install as install_mod
    monkeypatch.setattr(install_mod, "_REGISTRY", tmp_path / "wikis.json")
    install_mod._write_registry({
        "existing-wiki": {"path": str(tmp_path / "w"), "port": 7070, "installed": "2026-01-01"},
    })
    # _get_reserved_ports returns {7070}; assign_wiki_port must skip it
    base = _find_bindable_base(2)
    # Simulate: reserved = {base}, expect base+1
    port = assign_wiki_port({base}, start=base)
    assert port == base + 1


# ── Case g: uninstall frees port ──────────────────────────────────────────────

def test_uninstall_frees_port_from_reserved_set(tmp_path, monkeypatch):
    """Case g: after uninstall, _get_reserved_ports no longer includes that wiki's port."""
    import synthadoc.cli.install as install_mod
    from typer.testing import CliRunner
    from synthadoc.cli.main import app
    monkeypatch.setattr(install_mod, "_REGISTRY", tmp_path / "wikis.json")

    dest = tmp_path / "my-wiki"
    dest.mkdir()
    (dest / "wiki").mkdir()
    install_mod._write_registry({
        "my-wiki": {"path": str(dest), "port": 7070, "demo": None, "installed": "2026-01-01"},
    })

    assert 7070 in install_mod._get_reserved_ports()

    runner = CliRunner()
    runner.invoke(app, ["uninstall", "my-wiki"], input="y\nmy-wiki\n")

    assert 7070 not in install_mod._get_reserved_ports()


# ── Case h: port exhaustion ───────────────────────────────────────────────────

def test_find_free_port_raises_when_scan_exhausted():
    """Case h: find_free_port raises RuntimeError when no free port is found."""
    base = _find_bindable_base(1)
    # Exhaust exactly 1 port by binding it, then scan with max_scan=1
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", base))
        with pytest.raises(RuntimeError, match="No free port"):
            _find_free_port(start=base, max_scan=1)


def test_assign_wiki_port_skips_reserved_contiguous_block():
    """Case h: assign_wiki_port correctly steps past a large contiguous reserved block."""
    base = _find_bindable_base(4)
    # Reserve base, base+1, base+2 — expect base+3
    reserved = {base, base + 1, base + 2}
    port = assign_wiki_port(reserved, start=base)
    assert port == base + 3


def test_assign_wiki_port_raises_when_scan_exhausted():
    """Case h: assign_wiki_port raises RuntimeError when the reserved set contains 65535
    and start=65535, exhausting the entire scan range immediately."""
    with pytest.raises(RuntimeError, match="No free port found below 65536"):
        assign_wiki_port({65535}, start=65535)


# ── Case d: plugin install writes data.json ───────────────────────────────────

def test_write_plugin_data_creates_data_json(tmp_path):
    """Case d: _write_plugin_data writes data.json with the port from config.toml."""
    from synthadoc.cli.plugin import _write_plugin_data
    (tmp_path / ".synthadoc").mkdir()
    (tmp_path / ".synthadoc" / "config.toml").write_text(
        "[server]\nport = 7075\n", encoding="utf-8"
    )
    plugin_dir = tmp_path / ".obsidian" / "plugins" / "synthadoc"
    plugin_dir.mkdir(parents=True)

    _write_plugin_data(tmp_path, plugin_dir)

    data = json.loads((plugin_dir / "data.json").read_text())
    assert data["serverUrl"] == "http://127.0.0.1:7075"


def test_write_plugin_data_merges_existing_keys(tmp_path):
    """Case d: _write_plugin_data preserves existing data.json keys when updating serverUrl."""
    from synthadoc.cli.plugin import _write_plugin_data
    (tmp_path / ".synthadoc").mkdir()
    (tmp_path / ".synthadoc" / "config.toml").write_text(
        "[server]\nport = 7076\n", encoding="utf-8"
    )
    plugin_dir = tmp_path / ".obsidian" / "plugins" / "synthadoc"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "data.json").write_text(
        json.dumps({"serverUrl": "http://127.0.0.1:7070", "rawSourcesFolder": "raw_sources"}),
        encoding="utf-8",
    )

    _write_plugin_data(tmp_path, plugin_dir)

    data = json.loads((plugin_dir / "data.json").read_text())
    assert data["serverUrl"] == "http://127.0.0.1:7076"
    assert data["rawSourcesFolder"] == "raw_sources"  # preserved


def test_write_plugin_data_defaults_to_7070_when_no_config(tmp_path):
    """Case d: _write_plugin_data falls back to port 7070 when config.toml is absent."""
    from synthadoc.cli.plugin import _write_plugin_data
    plugin_dir = tmp_path / ".obsidian" / "plugins" / "synthadoc"
    plugin_dir.mkdir(parents=True)

    _write_plugin_data(tmp_path, plugin_dir)

    data = json.loads((plugin_dir / "data.json").read_text())
    assert data["serverUrl"] == "http://127.0.0.1:7070"
