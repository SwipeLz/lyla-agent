"""Unit tests for the manual run script ``scripts/run_agent_text.py``.

Validates Requirements 4.3 and 4.4:

- Requirement 4.3: invoking the script without a non-empty ``text`` argument
  must exit with a non-zero status code and write a usage message to stderr.
- Requirement 4.4: under ``agent_mode == "fake"`` the script must run
  successfully without importing the ``google.adk`` SDK (hermeticity for CI
  without ``GOOGLE_API_KEY``).

The empty-text checks run the script in a child Python process so we observe
the real exit status and stderr stream that a developer would see at the
command line. The fake-mode hermeticity check runs in-process: a subprocess
would not let us inspect the parent's ``sys.modules`` table, which is what
makes the assertion meaningful.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path


# ``app/tests/test_run_agent_text.py`` → project root is two parents up.
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _run_script(
    args: list[str], env_extra: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run ``python -m scripts.run_agent_text`` in a child Python process.

    The child inherits the parent's environment except for ``AGENT_MODE`` and
    ``GOOGLE_API_KEY``, which are stripped so behaviour does not depend on a
    developer's local ``.env``. Callers may add or override environment
    variables via ``env_extra``.
    """
    env = os.environ.copy()
    env.pop("AGENT_MODE", None)
    env.pop("GOOGLE_API_KEY", None)
    if env_extra:
        env.update(env_extra)
    # ``stdin=DEVNULL`` keeps the child off pytest's captured stdin handle.
    # On Windows, inheriting that handle raises ``OSError: [WinError 6] The
    # handle is invalid`` when pytest is running with output capture on.
    return subprocess.run(
        [sys.executable, "-m", "scripts.run_agent_text", *args],
        cwd=str(PROJECT_ROOT),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        env=env,
    )


# ---------------------------------------------------------------------------
# Requirement 4.3 — Empty / whitespace text exits non-zero with usage stderr
# ---------------------------------------------------------------------------


def test_whitespace_only_text_exits_nonzero_with_usage_on_stderr() -> None:
    """A ``text`` argument that is only whitespace must trigger the script's
    own usage branch (``sys.exit(2)``) and write a usage line to stderr.

    **Validates: Requirement 4.3**
    """
    result = _run_script(["   "])

    assert result.returncode != 0, (
        f"expected non-zero exit, got {result.returncode}; "
        f"stdout={result.stdout!r}; stderr={result.stderr!r}"
    )
    assert "usage" in result.stderr.lower(), (
        f"expected 'usage' in stderr, got: {result.stderr!r}"
    )
    # The usage branch must NOT print the JSON payload to stdout.
    assert result.stdout == "", (
        f"expected empty stdout on usage branch, got: {result.stdout!r}"
    )


def test_missing_text_argument_exits_nonzero_with_usage_on_stderr() -> None:
    """Omitting the positional ``text`` argument lets argparse emit usage and
    exit with a non-zero status.

    **Validates: Requirement 4.3**
    """
    result = _run_script([])

    assert result.returncode != 0
    assert "usage" in result.stderr.lower()


# ---------------------------------------------------------------------------
# Requirement 4.4 — Fake mode runs without importing google.adk
# ---------------------------------------------------------------------------


def test_fake_mode_runs_without_importing_google_adk(monkeypatch, capsys) -> None:
    """In ``agent_mode == "fake"``, running ``main`` end-to-end must not pull
    any ``google.adk`` submodule into ``sys.modules``.

    ``SessionLocal`` is stubbed so the script never touches the on-disk dev
    SQLite DB, and the user text contains no Fake Agent keyword so the runner
    returns the fallback reply with an empty ``actions`` list — exercising the
    dispatcher and the tool factory while issuing no service-layer calls.

    **Validates: Requirement 4.4**
    """
    # Drop any ``google.adk`` modules that may have leaked from earlier tests
    # in the same session so the assertion measures only this run.
    for name in list(sys.modules):
        if name == "google.adk" or name.startswith("google.adk."):
            sys.modules.pop(name, None)

    # Pin the runtime to fake mode regardless of environment.
    from app import config as config_module

    monkeypatch.setattr(config_module.settings, "agent_mode", "fake")
    monkeypatch.setattr(config_module.settings, "google_api_key", "")

    # Stub SessionLocal so the script does not open the on-disk SQLite DB.
    class _StubSession:
        def close(self) -> None:  # noqa: D401 - simple stub
            return None

    import scripts.run_agent_text as script_module

    monkeypatch.setattr(script_module, "SessionLocal", lambda: _StubSession())

    # CLI argv with a text that does NOT match any Fake Agent keyword, so no
    # tool wrapper is invoked and no DB row is read or written.
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_agent_text", "halo dunia tanpa kata kunci"],
    )

    asyncio.run(script_module.main())

    # The Fake Agent fallback reply must surface in the JSON output and the
    # actions list must be empty (no tool wrapper called).
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["status"] == "success"
    assert payload["actions"] == []
    assert payload["device_feedback"] is None
    assert payload["reply"], "Fake Agent must produce a non-empty fallback reply."

    # Crucially: no part of the ADK SDK was imported during the run.
    leaked = sorted(
        name
        for name in sys.modules
        if name == "google.adk" or name.startswith("google.adk.")
    )
    assert leaked == [], f"google.adk leaked into sys.modules: {leaked}"
