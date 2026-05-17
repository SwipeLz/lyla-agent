"""Phase 8.5 backend smoke test CLI (manual gate before Phase 9).

Usage:
    python -m scripts.smoke_test_backend [--real-agent] [--verbose]

This script is a manual end-to-end gate that exercises the wiring of the
Lyla-Taskbot backend (database, Service Layer, Tool Wrapper Layer,
Agent Runtime in fake mode by default, dashboard read path, device
command queue, and the Reminder Scheduler tick) without starting
uvicorn and without making outbound network calls in default mode.

Refer to ``docs/SMOKE_TEST.md`` for prerequisites, exit codes, and the
common-failures table.
"""

from __future__ import annotations

import argparse
import asyncio  # noqa: F401  -- used by Agent Runtime step (added in task 6)
import concurrent.futures  # noqa: F401  -- used by sync timeout helpers (task 8/9/10)
import re  # used by the sys.modules diff helper (Req 9.1)
import socket  # used by the Network Hermeticity Guard (Req 9)
import sys
import textwrap  # noqa: F401  -- used by output formatter (task 11)
import time  # noqa: F401  -- used by step timeout helpers (task 8/9/10)
import traceback  # noqa: F401  -- used by failure helpers (task 4)

from app.config import settings  # noqa: F401  -- consumed by override + main (task 1.2/2)


# --- CLI literals ---------------------------------------------------------

_USAGE_PROG = "python -m scripts.smoke_test_backend"

# --- Exit codes (Req 10, Req 2.2, Req 3.4) -------------------------------

_EXIT_PASS = 0
_EXIT_FAIL = 1
_EXIT_MISSING_KEY = 2
_EXIT_MISSING_FIXTURE = 3

# --- Demo Fixture literals (Req 3.2, Req 3.3) ----------------------------

DEMO_USER_EMAIL = "demo@taskbot.local"
DEMO_DEVICE_CODE = "TASKBOT-DEMO-001"


# --- Smoke Settings Override (Req 1) -------------------------------------


class _SmokeOverrideError(Exception):
    """Raised when the Smoke Settings Override cannot be applied.

    Caught by ``_run_smoke`` so the failure can be surfaced as a
    ``Settings Override`` row in the Smoke Output Contract table while
    the remaining Smoke Steps continue to execute under whatever
    ``settings.agent_mode`` value is currently in effect (Req 1.7).
    """


class _SmokeSettingsOverride:
    """Context manager that mutates ``settings.agent_mode`` in-process.

    Implements Req 1.2, 1.4, and 1.6. The override is a *pure in-memory*
    mutation of the singleton ``app.config.settings`` instance — the
    project-root ``.env`` file is **never** read, written, created, or
    renamed by this class (Req 1.3). On ``__exit__`` the previous
    ``agent_mode`` is restored regardless of whether the wrapped block
    raised, so the process-level invariant in Req 1.6 holds even when
    later Smoke Steps fail.

    ``target_mode`` MUST be either ``"fake"`` (default Smoke Run) or
    ``"real"`` (``--real-agent`` Smoke Run). Any other value is a
    programming error and trips the assertion in ``__init__``.
    """

    def __init__(self, target_mode: str) -> None:
        assert target_mode in ("fake", "real"), (
            f"target_mode must be 'fake' or 'real', got {target_mode!r}"
        )
        self._target_mode = target_mode
        self._previous_mode: str | None = None
        self._applied = False

    def __enter__(self) -> "_SmokeSettingsOverride":
        # Lazy import keeps this class independent of import order in
        # case future callers want to construct it before the rest of
        # the module is imported. ``settings`` is a module-level
        # singleton so the same instance is mutated regardless.
        from app.config import settings as _settings

        self._previous_mode = _settings.agent_mode
        try:
            _settings.agent_mode = self._target_mode
        except Exception as exc:  # pragma: no cover - defensive (Req 1.7)
            raise _SmokeOverrideError(
                f"failed to set settings.agent_mode={self._target_mode!r}: {exc}"
            ) from exc
        self._applied = True
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if not self._applied:
            return
        from app.config import settings as _settings

        _settings.agent_mode = self._previous_mode


def _gemini_key_is_set(value: str | None) -> bool:
    """Return ``True`` iff ``value`` is a non-blank Gemini API key.

    Implements the predicate used by Req 2.1/2.2 to decide whether
    ``--real-agent`` may proceed: ``None``, the empty string, and
    whitespace-only strings all count as *unset*.
    """
    if value is None:
        return False
    if value == "":
        return False
    if value.strip() == "":
        return False
    return True


# --- Network Hermeticity Guard (Req 9) -----------------------------------


class _NetworkHermeticityViolation(RuntimeError):
    """Raised by the patched socket primitives when an outbound non-allowlist
    destination is contacted during a Smoke Run.

    The single positional argument is ``repr(address)`` of whatever the
    caller tried to reach (a ``(host, port[, ...])`` tuple for the
    connect family, a host string for ``getaddrinfo``). Surfaced to the
    Smoke Output Contract as the ``error_message`` of the failing step
    (Req 9.3).
    """


# Loopback hosts always remain reachable during a Smoke Run. The pattern
# mirrors ``app/tests/conftest.py`` deliberately, but Req 9.5 forbids
# importing or depending on that module — so the literal set is restated
# here so the guard works under a plain ``python -m`` invocation.
_LOOPBACK_HOSTS: frozenset[str] = frozenset(
    {"127.0.0.1", "::1", "localhost", "0.0.0.0"}
)

# Hostname suffixes the Gemini real path needs to reach. Only consulted
# when the guard is constructed with ``allow_gemini=True`` (i.e. the
# ``--real-agent`` Smoke Run; Req 9.4).
_GEMINI_HOST_SUFFIXES: tuple[str, ...] = (
    "generativelanguage.googleapis.com",
    "oauth2.googleapis.com",
    "accounts.google.com",
)


def _extract_host(address: object) -> str | None:
    """Return the host string from a connect/getaddrinfo argument or ``None``.

    Accepts either:

    * a ``(host, port[, ...])`` tuple (used by ``socket.socket.connect``,
      ``connect_ex``, and ``socket.create_connection``), or
    * a plain string host (used by ``socket.getaddrinfo``), or
    * ``None`` (passive ``getaddrinfo`` lookup — caller treats as
      allowed).

    Anything else (e.g. ``AF_UNIX`` paths) is reported as ``None`` to
    let the wrapper fall through to its default decision.
    """
    if address is None:
        return None
    if isinstance(address, str):
        return address
    if isinstance(address, tuple) and address and isinstance(address[0], str):
        return address[0]
    return None


class _NetworkHermeticityGuard:
    """Live socket monkeypatch that enforces Smoke Network Hermeticity.

    Implements Req 9.2, 9.3, and 9.5 by patching four primitives on the
    ``socket`` module — ``socket.socket.connect``, ``socket.socket.connect_ex``,
    ``socket.create_connection`` and ``socket.getaddrinfo`` — so that
    every outbound destination is checked against an allowlist before
    the original implementation is invoked.

    The allowlist is constructed once per Smoke Run:

    * Loopback (``127.0.0.1``, ``::1``, ``localhost``, ``0.0.0.0``) is
      *always* allowed so the in-memory FastAPI ASGI transport, SQLite
      file URLs, and ad-hoc localhost connections never trip the guard.
    * The Gemini hostname suffixes are added only when ``allow_gemini``
      is true (i.e. the caller passed ``--real-agent``). This is the
      single permitted egress channel (Req 9.4); the script itself does
      not import ``google.adk`` or ``google.genai``, so the only code
      path that can reach those hostnames is
      ``app.agent.runtime._run_real``.

    Patching is applied via direct ``setattr`` on the ``socket`` module
    so the guard works under a plain ``python -m`` invocation; no
    pytest ``monkeypatch`` fixture and no import of
    ``app.tests.conftest`` is involved (Req 9.5). ``uninstall()`` is
    paired with ``install()`` and restores the originals from
    ``self._originals``; calling ``uninstall()`` without ``install()``
    is a no-op.
    """

    def __init__(self, *, allow_gemini: bool) -> None:
        self._allow_gemini = allow_gemini
        self._originals: dict[str, object] = {}
        self._installed = False

    def _is_allowed(self, address: object) -> bool:
        """Return True iff ``address`` resolves to a host on the allowlist."""
        host = _extract_host(address)
        if host is None:
            # Passive ``getaddrinfo`` (host=None) is harmless — it does
            # not contact the network. AF_UNIX / unknown shapes also
            # land here; treating them as allowed avoids false
            # positives for non-IP socket families. The connect family
            # cannot be triggered with a None host in practice.
            return True
        if host in _LOOPBACK_HOSTS:
            return True
        if self._allow_gemini:
            for suffix in _GEMINI_HOST_SUFFIXES:
                if host == suffix or host.endswith("." + suffix):
                    return True
        return False

    def install(self) -> None:
        """Patch the four ``socket`` primitives in place.

        Safe to call once per guard instance. Subsequent calls without
        an intervening ``uninstall()`` are no-ops so a guard cannot
        accidentally clobber its own snapshot of the originals.
        """
        if self._installed:
            return

        original_connect = socket.socket.connect
        original_connect_ex = socket.socket.connect_ex
        original_create_connection = socket.create_connection
        original_getaddrinfo = socket.getaddrinfo

        self._originals = {
            "socket.connect": original_connect,
            "socket.connect_ex": original_connect_ex,
            "create_connection": original_create_connection,
            "getaddrinfo": original_getaddrinfo,
        }

        guard = self  # bound into the closures below

        def guarded_connect(self_socket, address):  # type: ignore[no-untyped-def]
            if not guard._is_allowed(address):
                raise _NetworkHermeticityViolation(repr(address))
            return original_connect(self_socket, address)

        def guarded_connect_ex(self_socket, address):  # type: ignore[no-untyped-def]
            if not guard._is_allowed(address):
                raise _NetworkHermeticityViolation(repr(address))
            return original_connect_ex(self_socket, address)

        def guarded_create_connection(address, *args, **kwargs):  # type: ignore[no-untyped-def]
            if not guard._is_allowed(address):
                raise _NetworkHermeticityViolation(repr(address))
            return original_create_connection(address, *args, **kwargs)

        def guarded_getaddrinfo(host, *args, **kwargs):  # type: ignore[no-untyped-def]
            if not guard._is_allowed(host):
                raise _NetworkHermeticityViolation(repr(host))
            return original_getaddrinfo(host, *args, **kwargs)

        socket.socket.connect = guarded_connect  # type: ignore[method-assign]
        socket.socket.connect_ex = guarded_connect_ex  # type: ignore[method-assign]
        socket.create_connection = guarded_create_connection  # type: ignore[assignment]
        socket.getaddrinfo = guarded_getaddrinfo  # type: ignore[assignment]

        self._installed = True

    def uninstall(self) -> None:
        """Restore the four ``socket`` primitives from ``self._originals``.

        Idempotent: calling ``uninstall()`` more than once, or before
        ``install()``, does nothing. After a successful ``uninstall()``
        the guard can be re-``install()``-ed to start a fresh window.
        """
        if not self._installed:
            return

        socket.socket.connect = self._originals["socket.connect"]  # type: ignore[method-assign]
        socket.socket.connect_ex = self._originals["socket.connect_ex"]  # type: ignore[method-assign]
        socket.create_connection = self._originals["create_connection"]  # type: ignore[assignment]
        socket.getaddrinfo = self._originals["getaddrinfo"]  # type: ignore[assignment]

        self._originals = {}
        self._installed = False


# Pattern for the Google ADK/GenAI module-namespace diff (Req 9.1).
#
# Matches any of the following ``sys.modules`` keys:
#
# * ``google.adk`` or any submodule (``google.adk.runners``, ...)
# * ``google.genai`` or any submodule (``google.genai.types``, ...)
# * ``google_adk`` or any submodule (defensive — covers the
#   alternative top-level package name some early ADK builds used)
#
# The trailing ``(\.|$)`` group prevents accidental prefix matches such
# as ``google.adkfoo`` or ``google_adkfoo`` from being flagged.
_GOOGLE_MODULE_RE = re.compile(
    r"^google\.(adk|genai)(\.|$)|^google_adk(\.|$)"
)


def _diff_google_modules(
    pre: frozenset[str], post: frozenset[str]
) -> set[str]:
    """Return the Google ADK/GenAI modules newly imported during a Smoke Run.

    Implements the ``sys.modules`` snapshot/diff helper used by the
    default-mode post-run check (Req 9.1, design §3 mechanism B):
    ``pre`` is ``frozenset(sys.modules)`` taken before the first Smoke
    Step runs; ``post`` is the same snapshot taken after the last
    Smoke Step finishes. The returned set contains exactly the module
    names that appeared *during* the Smoke Run and that match the
    Google ADK/GenAI namespace pattern (``google.adk*``,
    ``google.genai*``, or ``google_adk*``).

    The default-mode invariant is that this set is empty: the Fake
    Agent path must not pull the Google SDK into ``sys.modules``. The
    ``--real-agent`` path is permitted to populate this namespace and
    skips this diff entirely (Req 9.4).
    """
    return {name for name in (post - pre) if _GOOGLE_MODULE_RE.match(name)}


def _build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser for the Smoke Test Backend CLI."""
    p = argparse.ArgumentParser(
        prog=_USAGE_PROG,
        description="Phase 8.5 backend smoke test (manual gate).",
    )
    p.add_argument(
        "--real-agent",
        action="store_true",
        help="Force agent_mode=real (requires GOOGLE_API_KEY).",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="On failure, print full Python traceback(s) to stderr.",
    )
    return p


def _run_smoke(*, target_mode: str, verbose: bool) -> int:
    """Stub for the Smoke Run dispatcher.

    Filled in by later tasks (Settings Override, Network Hermeticity Guard,
    DB session, six Smoke Steps, output formatter). For task 1.1 this is a
    no-op that returns ``_EXIT_PASS`` so the CLI is importable and the
    ``--help`` invocation works end-to-end.
    """
    del target_mode, verbose  # unused in skeleton
    return _EXIT_PASS


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns the integer Smoke Exit Code."""
    args = _build_parser().parse_args(argv)
    target_mode = "real" if args.real_agent else "fake"

    # Req 2.1, 2.2, 2.3: when --real-agent is requested but no Gemini key
    # is configured, fail fast with a single-line stderr message and
    # exit code 2. We do this BEFORE _run_smoke so no DB session is
    # opened, no Smoke Step runs, and no Python traceback is printed.
    if args.real_agent and not _gemini_key_is_set(settings.google_api_key):
        print(
            "GOOGLE_API_KEY is required for --real-agent. "
            "Set it in the project-root .env and rerun, or omit --real-agent.",
            file=sys.stderr,
        )
        return _EXIT_MISSING_KEY

    return _run_smoke(target_mode=target_mode, verbose=args.verbose)


if __name__ == "__main__":
    raise SystemExit(main())
