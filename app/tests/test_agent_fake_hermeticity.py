"""Property test for AR6: Fake Agent Hermeticity.

This module is deliberately minimal. Beyond the standard library, pytest,
and Hypothesis, the *only* application import is
:func:`app.agent.fake._run_fake`. The Fake Agent transitively pulls in
:mod:`app.agent.result` and :mod:`app.agent.tool_factory` (which itself
imports :mod:`app.tools`), and none of those modules are permitted to
import ``google.adk.*``. The property below holds only when that
isolation is preserved — hence the strict module boundary maintained by
this single-purpose file.

The autouse ``_no_outbound_network`` fixture in
:mod:`app.tests.conftest` is still active here; it patches
``socket.socket`` only and never imports any Google ADK submodule, so it
does not influence the AR6 measurement.

Validates: Requirements 3.2, 3.5, 16.2, 16.3
"""
from __future__ import annotations

import asyncio
import sys
from typing import Any, Callable

from hypothesis import example, given, settings, strategies as st

from app.agent.fake import _run_fake


# ── Property AR6: Fake Agent Hermeticity ───────────────────────────
#
# *For any* execution path of ``_run_fake``, no module reachable from
# the call stack SHALL import ``google.adk.runners``,
# ``google.adk.agents``, or ``google.adk.sessions``.
#
# Strategy: Hypothesis drives ``text`` and ``timezone`` inputs across
# all four keyword branches of the Fake Agent (expense, reminder, task,
# summary) plus the fallback branch. Stub tool callables stand in for
# the per-request Tool Surface so the test never touches the database.
# Before each invocation we purge any ``google.adk.*`` entries that may
# have leaked into ``sys.modules`` from earlier tests in the same
# pytest session (e.g. ``test_agent_runtime.py`` that explicitly imports
# the SDK after ``pytest.importorskip``). This way the post-call
# assertion measures only the modules that ``_run_fake`` itself caused
# to be imported.

_FORBIDDEN_MODULES: tuple[str, ...] = (
    "google.adk.runners",
    "google.adk.agents",
    "google.adk.sessions",
)

# The Tool Surface names — kept in sync with
# :func:`app.agent.tool_factory.build_tools`. The Fake Agent looks up
# tools by ``__name__``, so each stub must carry the corresponding
# attribute (mimicking the real factory's closures).
_TOOL_SURFACE_NAMES: tuple[str, ...] = (
    "create_task",
    "create_expense",
    "set_reminder",
    "get_today_summary",
    "send_device_command",
)


def _purge_google_adk_from_sys_modules() -> None:
    """Drop ``google.adk[.*]`` entries from ``sys.modules``.

    The Fake Agent must not import any Google ADK module. To prove that
    we have to start from a clean slate each run — otherwise modules
    loaded by *other* tests in the same session would mask a real leak.
    """
    for name in list(sys.modules):
        if name == "google.adk" or name.startswith("google.adk."):
            sys.modules.pop(name, None)


def _make_stub_tool(name: str) -> Callable[..., dict]:
    """Return a no-op Tool Surface callable with the given ``__name__``."""

    def stub(*_args: Any, **_kwargs: Any) -> dict:
        # The Tool Result Dict shape is irrelevant for AR6; we only care
        # that ``_run_fake`` never imports a forbidden module while
        # building, dispatching, or summarising the action.
        return {"success": True, "type": name}

    stub.__name__ = name
    return stub


def _make_stub_tools() -> list[Callable[..., dict]]:
    return [_make_stub_tool(n) for n in _TOOL_SURFACE_NAMES]


# Hypothesis strategies. ``text()`` covers the universal-quantifier
# clause of AR6 ("for any execution path"); the ``@example`` decorators
# pin one input per Fake Agent branch so each keyword path is always
# exercised regardless of the random draw.
_TEXT_STRATEGY = st.text(min_size=1, max_size=80)
_TIMEZONE_STRATEGY = st.one_of(
    st.none(),
    st.sampled_from(["UTC", "Asia/Jakarta", "Asia/Tokyo", "America/New_York"]),
)


@settings(max_examples=50, deadline=None)
@given(text=_TEXT_STRATEGY, timezone=_TIMEZONE_STRATEGY)
@example(text="beli kopi 15000", timezone="Asia/Jakarta")  # expense path
@example(text="ingatkan saya minum air", timezone=None)    # reminder path
@example(text="catat tugas matematika", timezone=None)     # task path
@example(text="ringkasan hari ini", timezone="UTC")        # summary path
@example(text="halo apa kabar", timezone=None)             # fallback path
def test_property_ar6_fake_agent_hermeticity(
    text: str, timezone: str | None
) -> None:
    """Property AR6: Fake Agent Hermeticity.

    For any ``(text, timezone)`` input, awaiting ``_run_fake`` MUST NOT
    import ``google.adk.runners``, ``google.adk.agents``, or
    ``google.adk.sessions``.

    Validates: Requirements 3.2, 3.5, 16.2, 16.3
    """
    # Start each run from a clean ``google.adk.*`` slate so we measure
    # only the modules introduced by THIS ``_run_fake`` call.
    _purge_google_adk_from_sys_modules()

    asyncio.run(
        _run_fake(tools=_make_stub_tools(), text=text, timezone=timezone)
    )

    leaked = [m for m in _FORBIDDEN_MODULES if m in sys.modules]
    assert leaked == [], (
        f"_run_fake leaked Google ADK modules into sys.modules: {leaked}. "
        "The Fake Agent must remain hermetic (Property AR6, "
        "Requirements 3.2, 3.5, 16.2, 16.3)."
    )
    # Belt-and-braces: the parent ``google.adk`` namespace package must
    # also stay absent. If any submodule is imported, Python populates
    # the parent automatically — checking it directly catches a leaked
    # ``import google.adk`` even if no specific child was loaded.
    assert "google.adk" not in sys.modules, (
        "_run_fake leaked the google.adk package into sys.modules; "
        "the Fake Agent must not import any Google ADK module."
    )
