# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
"""Shared helpers for Synthadoc live test scripts."""
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Live-test provider selection
# ---------------------------------------------------------------------------
# Live tests use coding-tool CLI providers (no API key required).
# Set SYNTHADOC_LIVE_PROVIDER to switch; default is "claude-code".
#
#   set SYNTHADOC_LIVE_PROVIDER=opencode     (Windows)
#   export SYNTHADOC_LIVE_PROVIDER=opencode  (Unix/macOS)
#
# Allowed values: "claude-code" (default), "opencode"
# ---------------------------------------------------------------------------

_LIVE_PROVIDER_ENV = "SYNTHADOC_LIVE_PROVIDER"
_ALLOWED_PROVIDERS = ("claude-code", "opencode")

# Providers known to need longer timeouts than the config.toml defaults.
SLOW_PROVIDER_TIMEOUTS: dict[str, dict[str, int]] = {
    "opencode":    {"job_timeout_seconds": 1200, "client_llm_timeout_seconds": 600},
    "claude-code": {"job_timeout_seconds":  900, "client_llm_timeout_seconds": 360},
}


def get_live_provider() -> str:
    """Return the coding-tool provider for live tests.

    Reads SYNTHADOC_LIVE_PROVIDER; falls back to 'claude-code'.
    Raises ValueError for unsupported values so misconfiguration is caught early.
    """
    name = os.environ.get(_LIVE_PROVIDER_ENV, "claude-code").strip()
    if name not in _ALLOWED_PROVIDERS:
        raise ValueError(
            f"SYNTHADOC_LIVE_PROVIDER={name!r} is not supported. "
            f"Choose one of: {', '.join(_ALLOWED_PROVIDERS)}"
        )
    return name


def patch_provider(wiki_root: Path, provider_name: str | None = None) -> str:
    """Replace the [agents] default provider line in config.toml.

    Uses *provider_name* when given, otherwise reads SYNTHADOC_LIVE_PROVIDER.
    Returns the provider name that was written.
    """
    if provider_name is None:
        provider_name = get_live_provider()
    config_path = wiki_root / ".synthadoc" / "config.toml"
    text = config_path.read_text(encoding="utf-8")
    text = re.sub(
        r"^(default\s*=\s*\{)[^}]*(})",
        f'default = {{ provider = "{provider_name}" }}',
        text,
        flags=re.MULTILINE,
    )
    config_path.write_text(text, encoding="utf-8")
    return provider_name


def patch_slow_provider_timeouts(wiki_root: Path, provider_name: str | None = None) -> int:
    """Raise job/LLM timeouts in config.toml for providers slower than defaults.

    Returns the effective job_timeout_seconds so callers can set their poll
    deadline to match.
    """
    if provider_name is None:
        provider_name = get_live_provider()
    overrides = SLOW_PROVIDER_TIMEOUTS.get(provider_name, {})
    if not overrides:
        return 600  # server default — no patch needed
    config_path = wiki_root / ".synthadoc" / "config.toml"
    text = config_path.read_text(encoding="utf-8")
    for key, value in overrides.items():
        text = re.sub(
            rf"^({re.escape(key)}\s*=\s*)\d+",
            rf"\g<1>{value}",
            text,
            flags=re.MULTILINE,
        )
    config_path.write_text(text, encoding="utf-8")
    return overrides.get("job_timeout_seconds", 600)


def register_sigterm_handler() -> None:
    """Route SIGTERM → sys.exit(1) so that atexit handlers (e.g. wiki restore) fire.

    Python's default SIGTERM disposition terminates the process immediately,
    bypassing atexit.  Replacing it with sys.exit() lets the normal shutdown
    sequence run.  Call this once, early in main(), after any atexit.register()
    calls have been set up.
    """
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(1))


def kill_server_on_port(port: int) -> bool:
    """Terminate the synthadoc server process listening on *port*.

    Returns True if a process was found and terminated, False otherwise.
    Waits up to 5 seconds for the process to fully release file handles before
    returning so that a subsequent shutil.rmtree() succeeds on Windows.
    """
    if sys.platform == "win32":
        try:
            out = subprocess.check_output(
                ["netstat", "-ano", "-p", "TCP"],
                text=True, stderr=subprocess.DEVNULL,
            )
            pid = None
            for line in out.splitlines():
                parts = line.split()
                # netstat -ano output: Proto  LocalAddr  ForeignAddr  State  PID
                if (len(parts) >= 5
                        and parts[0].upper() == "TCP"
                        and f":{port}" in parts[1]
                        and parts[3] == "LISTENING"):
                    try:
                        pid = int(parts[4])
                    except ValueError:
                        pass
                    break
            if pid is None:
                return False
            subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            # Wait for the process to fully exit and release all file handles.
            time.sleep(3)
            return True
        except Exception:
            return False
    else:
        # macOS / Linux
        pid = _find_pid_on_port_unix(port)
        if pid is None:
            return False
        # Graceful shutdown first, escalate to SIGKILL if still alive after 5s.
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return True  # already gone
        except PermissionError:
            return False
        for _ in range(10):          # wait up to 5s (10 × 0.5s)
            time.sleep(0.5)
            try:
                os.kill(pid, 0)      # 0 = just check existence
            except ProcessLookupError:
                return True          # process exited cleanly
        # Still alive — force-kill
        try:
            os.kill(pid, signal.SIGKILL)
            time.sleep(1)
        except ProcessLookupError:
            pass
        return True


def _find_pid_on_port_unix(port: int) -> int | None:
    """Return the PID of the process LISTENING on *port*, or None if not found.

    Tries lsof first (available on macOS and most Linux distros).
    Falls back to ss (iproute2, always present on modern Linux).
    """
    # lsof: -t = PIDs only, -i = network filter, -sTCP:LISTEN = listening only
    try:
        out = subprocess.check_output(
            ["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
        for line in out.splitlines():
            try:
                return int(line.strip())
            except ValueError:
                pass
    except FileNotFoundError:
        pass  # lsof not installed — try ss
    except subprocess.CalledProcessError:
        pass  # no process on that port

    # ss fallback (Linux iproute2)
    try:
        out = subprocess.check_output(
            ["ss", "-tlnp", f"sport = :{port}"],
            text=True, stderr=subprocess.DEVNULL,
        )
        # ss output contains pid=<N> in the last column
        for line in out.splitlines():
            if f":{port}" in line and "pid=" in line:
                for token in line.split(","):
                    if token.strip().startswith("pid="):
                        try:
                            return int(token.strip()[4:])
                        except ValueError:
                            pass
    except Exception:
        pass

    return None


def backup_wiki(wiki_root: Path) -> Path | None:
    """Snapshot wiki/ and .synthadoc/ into a temp directory.

    Returns the snapshot path on success, or None if the copy fails (a warning
    is printed but the caller's test run continues).
    """
    snap = Path(tempfile.mkdtemp(prefix="synthadoc-live-backup-"))
    try:
        shutil.copytree(wiki_root / "wiki", snap / "wiki")
        if (wiki_root / ".synthadoc").exists():
            shutil.copytree(wiki_root / ".synthadoc", snap / ".synthadoc")
        return snap
    except Exception as exc:
        print(f"  [WARN] snapshot failed ({exc}) — wiki will not be auto-restored")
        shutil.rmtree(snap, ignore_errors=True)
        return None


def restore_wiki(snap: Path, wiki_root: Path, wiki_name: str, port: int = 0) -> None:
    """Restore wiki/ and .synthadoc/ from a snapshot created by backup_wiki().

    If *port* is given, the server listening on that port is terminated first so
    that file handles (audit.db, synthadoc.log) are released before the restore
    copies files over them — required on Windows where open handles block rmtree.

    Deletes the snapshot directory on success.  Preserves it on failure so the
    developer can restore manually.
    """
    if port:
        killed = kill_server_on_port(port)
        if killed:
            print(f"\n  Server on port {port} stopped for restore.")
        else:
            print(f"\n  [WARN] Could not stop server on port {port}.")
            print(  "         Restore may fail on Windows if file handles are still open.")

    try:
        if (wiki_root / "wiki").exists():
            shutil.rmtree(wiki_root / "wiki")
        shutil.copytree(snap / "wiki", wiki_root / "wiki")
        if (snap / ".synthadoc").exists():
            if (wiki_root / ".synthadoc").exists():
                shutil.rmtree(wiki_root / ".synthadoc")
            shutil.copytree(snap / ".synthadoc", wiki_root / ".synthadoc")
        shutil.rmtree(snap, ignore_errors=True)
        print()
        print("=" * 64)
        print("  Wiki restored to pre-test state.")
        print("  Restart the server to pick up the restored DB:")
        print(f"    synthadoc serve -w {wiki_name}")
        print("=" * 64)
    except Exception as exc:
        print()
        print("=" * 64)
        print(f"  Restore failed: {exc}")
        print(f"  Snapshot preserved at: {snap}")
        print(f"  Restore manually, then: synthadoc serve -w {wiki_name}")
        print("=" * 64)
