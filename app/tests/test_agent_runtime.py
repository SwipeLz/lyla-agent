"""Property-based tests for the Agent Runtime (Phase 4).

Properties tested in this module are listed in
``.kiro/specs/agent-runtime-and-apis/design.md`` (section "Correctness
Properties").
"""
from __future__ import annotations

import inspect

import pytest
from hypothesis import given, settings, strategies as st

from app.agent.tool_factory import build_tools


# ── Property AR2: Tool Schema Hides Injected Context ───────────────
#
# *For any* tool produced by ``build_tools(db, user_id, device_id)``, the
# function's ``inspect.signature(tool).parameters`` SHALL NOT contain
# ``"db"``, ``"user_id"``, or ``"device_id"`` as a parameter name.
#
# The closures defined in :mod:`app.agent.tool_factory` accept ``**_kwargs``
# to absorb stray keyword arguments from the model. ``inspect.signature``
# reports that variadic catch-all as a parameter with kind
# ``VAR_KEYWORD`` — we deliberately exclude it from the check, since it
# does not appear in the function schema ADK derives from the signature.
# Only named ``POSITIONAL_OR_KEYWORD`` and ``KEYWORD_ONLY`` parameters
# would surface to the model, so those are the kinds we audit.
#
# Validates: Requirements 2.1, 2.2

_INJECTED_CONTEXT_NAMES = frozenset({"db", "user_id", "device_id"})

_MODEL_VISIBLE_KINDS = frozenset(
    {
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.KEYWORD_ONLY,
        inspect.Parameter.POSITIONAL_ONLY,
    }
)


def _model_visible_parameter_names(tool) -> set[str]:
    """Return names of parameters that would appear in the ADK schema.

    Variadic ``*args``/``**kwargs`` are excluded because they collapse
    into the schema's open-ended catch-all rather than a named field.
    """
    return {
        name
        for name, param in inspect.signature(tool).parameters.items()
        if param.kind in _MODEL_VISIBLE_KINDS
    }


@settings(max_examples=50, deadline=None)
@given(
    user_id=st.text(min_size=0, max_size=40),
    device_id=st.one_of(st.none(), st.text(min_size=0, max_size=40)),
)
def test_property_ar2_tool_schema_hides_injected_context(user_id, device_id):
    """Property AR2: Tool Schema Hides Injected Context.

    Validates: Requirements 2.1, 2.2
    """
    db_sentinel = object()  # tool factory never touches ``db`` at build time
    tools = build_tools(db_sentinel, user_id, device_id)

    # Sanity: factory always produces the five Tool Surface callables.
    assert len(tools) == 5

    for tool in tools:
        named_params = _model_visible_parameter_names(tool)
        leaked = named_params & _INJECTED_CONTEXT_NAMES
        assert not leaked, (
            f"Tool {tool.__name__!r} exposes Injected Context parameter(s) "
            f"{sorted(leaked)} to the model schema; expected the "
            f"closure to bind {sorted(_INJECTED_CONTEXT_NAMES)} via the "
            f"factory's lexical scope."
        )


def test_property_ar2_tool_schema_hides_injected_context_example():
    """Concrete example exercising Property AR2 with fixed inputs.

    Validates: Requirements 2.1, 2.2
    """
    tools = build_tools(object(), "user-123", "device-456")
    assert {tool.__name__ for tool in tools} == {
        "create_task",
        "create_expense",
        "set_reminder",
        "get_today_summary",
        "send_device_command",
    }
    for tool in tools:
        named_params = _model_visible_parameter_names(tool)
        assert "db" not in named_params
        assert "user_id" not in named_params
        assert "device_id" not in named_params


# ── Property AR3: Bound Context Forwarded ──────────────────────────
#
# *For any* tool from ``build_tools(db, user_id, device_id)`` invoked with
# valid Model-Visible Arguments, the underlying Phase 3 tool wrapper
# SHALL be called with ``db=db``, ``user_id=user_id`` (or
# ``device_id=device_id`` for ``send_device_command``); model-supplied
# ``db``/``user_id``/``device_id`` smuggled in via ``**kwargs`` SHALL be
# ignored.
#
# Strategy: monkeypatch each Phase 3 wrapper at its module location with a
# stub that records the kwargs it is called with and returns a deterministic
# Tool Result Dict. The factory imports the wrappers as
# ``from app.tools import task_tools, ...`` and calls them via attribute
# access (``task_tools.create_task_tool(...)``), so patching the attribute
# on the module is what the closure actually resolves at call time.
#
# Validates: Requirements 2.3, 2.4, 2.5

from app.tools import (  # noqa: E402  (placed after AR2 helpers above)
    device_tools,
    expense_tools,
    reminder_tools,
    summary_tools,
    task_tools,
)

# A timezone-aware ISO 8601 string in the far future — large enough to keep
# the Phase 3 reminder service happy in case anyone wires this through the
# real wrapper in the future. The factory's closure parses it via
# ``datetime.fromisoformat`` before delegating.
_VALID_REMIND_AT_ISO = "2099-01-01T00:00:00+00:00"


def _make_recorder(type_label: str, calls: list[dict]):
    """Return a stub wrapper that records its kwargs and returns success."""

    def _stub(**kwargs):
        calls.append(kwargs)
        return {"success": True, "type": type_label}

    return _stub


def _patch_all_wrappers(monkeypatch):
    """Monkeypatch every Phase 3 wrapper used by ``build_tools``.

    Returns a dict mapping the tool name to the per-tool recording list, so
    each assertion can read back ``calls[name][-1]`` for the most recent
    invocation in this scope.
    """
    calls: dict[str, list[dict]] = {
        "create_task": [],
        "create_expense": [],
        "set_reminder": [],
        "get_today_summary": [],
        "send_device_command": [],
    }
    monkeypatch.setattr(
        task_tools,
        "create_task_tool",
        _make_recorder("task", calls["create_task"]),
    )
    monkeypatch.setattr(
        expense_tools,
        "create_expense_tool",
        _make_recorder("expense", calls["create_expense"]),
    )
    monkeypatch.setattr(
        reminder_tools,
        "set_reminder_tool",
        _make_recorder("reminder", calls["set_reminder"]),
    )
    monkeypatch.setattr(
        summary_tools,
        "get_today_summary_tool",
        _make_recorder("summary", calls["get_today_summary"]),
    )
    monkeypatch.setattr(
        device_tools,
        "send_device_command_tool",
        _make_recorder("device_command", calls["send_device_command"]),
    )
    return calls


# Adversarial keyword arguments: this is what we expect the model to
# occasionally hallucinate or what a malicious prompt could try to smuggle.
# All three keys MUST be silently absorbed by ``**_kwargs`` in the factory
# closures and replaced by the bound values.
_ADVERSARIAL_INJECTED_CONTEXT = {
    "db": "HACKED",
    "user_id": "EVIL",
    "device_id": "OTHER",
}


def _invoke_each_tool(tools_by_name):
    """Invoke each Tool Surface callable with valid args + adversarial kwargs."""
    tools_by_name["create_task"](
        title="Tugas Kalkulus",
        **_ADVERSARIAL_INJECTED_CONTEXT,
    )
    tools_by_name["create_expense"](
        amount=10_000,
        **_ADVERSARIAL_INJECTED_CONTEXT,
    )
    tools_by_name["set_reminder"](
        title="Reminder Belajar",
        remind_at=_VALID_REMIND_AT_ISO,
        **_ADVERSARIAL_INJECTED_CONTEXT,
    )
    tools_by_name["get_today_summary"](**_ADVERSARIAL_INJECTED_CONTEXT)
    tools_by_name["send_device_command"](
        text="halo",
        **_ADVERSARIAL_INJECTED_CONTEXT,
    )


def _assert_bound_context_forwarded(
    calls, *, db_sentinel, user_id, device_id
):
    """Assert each wrapper was invoked with the bound context, not the spoof."""
    # create_task → wrapper takes db + user_id (no device_id field).
    create_task_call = calls["create_task"][-1]
    assert create_task_call["db"] is db_sentinel, (
        "create_task wrapper received a db that is not the bound sentinel: "
        f"{create_task_call.get('db')!r}"
    )
    assert create_task_call["user_id"] == user_id
    assert "device_id" not in create_task_call
    assert create_task_call["title"] == "Tugas Kalkulus"

    # create_expense → wrapper takes db + user_id (no device_id field).
    create_expense_call = calls["create_expense"][-1]
    assert create_expense_call["db"] is db_sentinel
    assert create_expense_call["user_id"] == user_id
    assert "device_id" not in create_expense_call
    assert create_expense_call["amount"] == 10_000

    # set_reminder → wrapper takes db + user_id; closure parses remind_at.
    set_reminder_call = calls["set_reminder"][-1]
    assert set_reminder_call["db"] is db_sentinel
    assert set_reminder_call["user_id"] == user_id
    assert "device_id" not in set_reminder_call
    assert set_reminder_call["title"] == "Reminder Belajar"

    # get_today_summary → wrapper takes db + user_id only.
    get_summary_call = calls["get_today_summary"][-1]
    assert get_summary_call["db"] is db_sentinel
    assert get_summary_call["user_id"] == user_id
    assert "device_id" not in get_summary_call

    # send_device_command → wrapper takes db + device_id (no user_id field).
    send_device_call = calls["send_device_command"][-1]
    assert send_device_call["db"] is db_sentinel
    assert send_device_call["device_id"] == device_id
    assert "user_id" not in send_device_call
    assert send_device_call["text"] == "halo"


def test_property_ar3_bound_context_forwarded_example(monkeypatch):
    """Concrete example exercising Property AR3 with fixed sentinel inputs.

    Validates: Requirements 2.3, 2.4, 2.5
    """
    db_sentinel = object()
    user_id = "real_user"
    device_id = "real_device"

    calls = _patch_all_wrappers(monkeypatch)

    tools = build_tools(db_sentinel, user_id, device_id)
    tools_by_name = {t.__name__: t for t in tools}
    _invoke_each_tool(tools_by_name)

    _assert_bound_context_forwarded(
        calls,
        db_sentinel=db_sentinel,
        user_id=user_id,
        device_id=device_id,
    )

    # Adversarial injection MUST NOT have appeared anywhere.
    for tool_name, call_list in calls.items():
        for recorded in call_list:
            assert recorded.get("db") is db_sentinel, (
                f"{tool_name} wrapper saw model-supplied db={recorded.get('db')!r} "
                f"instead of the bound sentinel"
            )
            if "user_id" in recorded:
                assert recorded["user_id"] != "EVIL", (
                    f"{tool_name} wrapper accepted spoofed user_id='EVIL'"
                )
            if "device_id" in recorded:
                assert recorded["device_id"] != "OTHER", (
                    f"{tool_name} wrapper accepted spoofed device_id='OTHER'"
                )


@settings(max_examples=25, deadline=None)
@given(
    user_id=st.text(min_size=1, max_size=40).filter(lambda s: s != "EVIL"),
    device_id=st.text(min_size=1, max_size=40).filter(lambda s: s != "OTHER"),
)
def test_property_ar3_bound_context_forwarded(user_id, device_id):
    """Property AR3: Bound Context Forwarded.

    For any ``(user_id, device_id)`` bound at factory time, every Tool
    Surface callable forwards exactly those values to its Phase 3 wrapper
    even when the caller supplies adversarial ``db``/``user_id``/``device_id``
    kwargs that mimic an LLM hallucination.

    Uses :class:`pytest.MonkeyPatch` directly (instead of the
    function-scoped ``monkeypatch`` fixture) so the patches are torn down
    cleanly between each Hypothesis-generated example.

    Validates: Requirements 2.3, 2.4, 2.5
    """
    db_sentinel = object()
    with pytest.MonkeyPatch.context() as monkeypatch:
        calls = _patch_all_wrappers(monkeypatch)

        tools = build_tools(db_sentinel, user_id, device_id)
        tools_by_name = {t.__name__: t for t in tools}
        _invoke_each_tool(tools_by_name)

        _assert_bound_context_forwarded(
            calls,
            db_sentinel=db_sentinel,
            user_id=user_id,
            device_id=device_id,
        )


# ── Property AR4: send_device_command without device_id short-circuits ──
#
# *For any* tool list built with ``device_id is None``, calling the
# ``send_device_command`` tool with any combination of ``face``/``sound``/
# ``text`` SHALL return a Tool Result Dict with ``success=False``,
# ``type="device_command"``, non-empty ``error``, and SHALL NOT call
# ``device_service.queue_device_command``.
#
# Strategy: build the tools with ``device_id=None`` and monkeypatch
# ``app.services.device_service.queue_device_command`` with a recorder
# stub. The Phase 3 wrapper ``send_device_command_tool`` accesses
# ``device_service.queue_device_command`` via attribute lookup at call
# time, so patching the attribute is what the closure-bound short-circuit
# would defeat if it were ever skipped. The recorder must remain empty.
#
# Validates: Requirement 2.6

from app.services import device_service  # noqa: E402

# ``send_device_command`` accepts each field as ``str | None``. We generate
# short ASCII strings to stay within reasonable input space and combine
# them with ``st.none()`` so every field independently flips between
# "missing" and "present". Hypothesis will explore all eight combinations
# (including the all-None case, which the Phase 3 wrapper itself rejects;
# the short-circuit must trigger *before* we ever reach that check).
_AR4_OPT_STR = st.one_of(
    st.none(),
    st.text(
        alphabet=st.characters(min_codepoint=0x20, max_codepoint=0x7E),
        min_size=0,
        max_size=20,
    ),
)


def _find_send_device_command(tools):
    """Return the ``send_device_command`` callable from ``tools``."""
    for tool in tools:
        if tool.__name__ == "send_device_command":
            return tool
    raise AssertionError(
        "build_tools did not produce a 'send_device_command' callable"
    )


@settings(max_examples=50, deadline=None)
@given(face=_AR4_OPT_STR, sound=_AR4_OPT_STR, text=_AR4_OPT_STR)
def test_property_ar4_send_device_command_short_circuits_without_device_id(
    face, sound, text
):
    """Property AR4: send_device_command without device_id short-circuits.

    Validates: Requirement 2.6
    """
    db_sentinel = object()
    user_id = "real_user"

    queue_calls: list[tuple[tuple, dict]] = []

    def _record_queue_call(*args, **kwargs):
        queue_calls.append((args, kwargs))
        # Returning a sentinel here would never be reached if the
        # short-circuit holds — but if the property is violated, we still
        # want the test to fail loudly on the assertions below rather than
        # explode inside the wrapper.
        raise AssertionError(
            "device_service.queue_device_command must not be called when "
            "device_id is None"
        )

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            device_service, "queue_device_command", _record_queue_call
        )

        tools = build_tools(db_sentinel, user_id, None)
        send_device_command = _find_send_device_command(tools)

        result = send_device_command(face=face, sound=sound, text=text)

    # Tool Result Dict shape required by Requirement 2.6 / Property AR4.
    assert isinstance(result, dict), (
        f"send_device_command must return a dict, got {type(result).__name__}"
    )
    assert result.get("success") is False, (
        f"expected success=False on short-circuit, got {result!r}"
    )
    assert result.get("type") == "device_command", (
        f"expected type=='device_command', got {result.get('type')!r}"
    )
    error_message = result.get("error")
    assert isinstance(error_message, str) and error_message.strip(), (
        f"expected non-empty error string, got {error_message!r}"
    )

    # The service-layer entry point must never be reached.
    assert queue_calls == [], (
        "device_service.queue_device_command was called "
        f"{len(queue_calls)} time(s) despite device_id=None: {queue_calls!r}"
    )


def test_property_ar4_short_circuit_example_all_fields_set():
    """Concrete example exercising Property AR4 with every field populated.

    Validates: Requirement 2.6
    """
    db_sentinel = object()
    queue_calls: list[tuple[tuple, dict]] = []

    def _record_queue_call(*args, **kwargs):
        queue_calls.append((args, kwargs))
        raise AssertionError(
            "device_service.queue_device_command must not be called when "
            "device_id is None"
        )

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            device_service, "queue_device_command", _record_queue_call
        )

        tools = build_tools(db_sentinel, "real_user", None)
        send_device_command = _find_send_device_command(tools)

        result = send_device_command(face="happy", sound="chime", text="halo")

    assert result["success"] is False
    assert result["type"] == "device_command"
    assert isinstance(result["error"], str) and result["error"].strip()
    assert queue_calls == []


# ── Property AR5: Mode Selection ───────────────────────────────────
#
# *For any* settings combination, ``select_mode(settings)`` SHALL return:
#
# 1. ``"real"`` if ``settings.agent_mode == "real"``;
# 2. ``"fake"`` if ``settings.agent_mode == "fake"``;
# 3. ``"real"`` if ``settings.agent_mode == ""`` and
#    ``settings.google_api_key != ""``;
# 4. ``"fake"`` otherwise.
#
# Strategy: Hypothesis generates pairs of ``(agent_mode, google_api_key)``
# values and we verify the table mapping. ``agent_mode`` is drawn from a
# small explicit alphabet (``""``, ``"real"``, ``"fake"``, ``"garbage"``)
# unioned with arbitrary text, so the generator covers both the named
# branches and the "unrecognised mode" fallthrough that AR5 collapses
# into "otherwise → fake". ``google_api_key`` mirrors the same shape: an
# explicit alphabet (``""``, ``"valid_key"``) unioned with arbitrary
# text, so empty / non-empty / weird-key cases are all explored.
#
# We construct a ``SimpleNamespace`` stub instead of building a real
# ``Settings`` instance so the test stays decoupled from the
# ``pydantic-settings`` env-loading machinery — ``select_mode`` reads
# only ``agent_mode`` and ``google_api_key`` via ``getattr``.
#
# Validates: Requirements 3.3, 3.4

from types import SimpleNamespace  # noqa: E402

from app.agent.runtime import select_mode  # noqa: E402


def _expected_mode(agent_mode: str, google_api_key: str) -> str:
    """Reference oracle for AR5's mapping table.

    Mirrors the four bullet points of Property AR5 verbatim. Any input
    that does not match the first three bullets falls through to
    ``"fake"`` (the safe, hermetic default), including unrecognised
    ``agent_mode`` strings such as ``"garbage"`` or random text — even
    when ``google_api_key`` is non-empty. AR5 only consults
    ``google_api_key`` as a fallback when ``agent_mode`` is exactly the
    empty string.
    """
    if agent_mode == "real":
        return "real"
    if agent_mode == "fake":
        return "fake"
    if agent_mode == "" and google_api_key != "":
        return "real"
    return "fake"


# Explicit corners from the task hint plus arbitrary text to stress the
# fallthrough branch. ``st.text()`` may produce ``"real"`` or ``"fake"``
# but the oracle handles those correctly because it shares the same
# table, so no filtering is required.
_AR5_AGENT_MODE_STRATEGY = st.one_of(
    st.sampled_from(["", "real", "fake", "garbage"]),
    st.text(max_size=20),
)
_AR5_GOOGLE_KEY_STRATEGY = st.one_of(
    st.sampled_from(["", "valid_key"]),
    st.text(max_size=40),
)


@settings(max_examples=100, deadline=None)
@given(
    agent_mode=_AR5_AGENT_MODE_STRATEGY,
    google_api_key=_AR5_GOOGLE_KEY_STRATEGY,
)
def test_property_ar5_mode_selection(agent_mode, google_api_key):
    """Property AR5: Mode Selection.

    Validates: Requirements 3.3, 3.4
    """
    stub = SimpleNamespace(
        agent_mode=agent_mode,
        google_api_key=google_api_key,
    )
    expected = _expected_mode(agent_mode, google_api_key)
    actual = select_mode(stub)
    assert actual == expected, (
        f"select_mode(agent_mode={agent_mode!r}, "
        f"google_api_key={google_api_key!r}) returned {actual!r}, "
        f"expected {expected!r} per AR5 mapping table"
    )


@pytest.mark.parametrize(
    "agent_mode, google_api_key, expected",
    [
        # Bullet 1: explicit "real" wins regardless of google_api_key.
        ("real", "", "real"),
        ("real", "valid_key", "real"),
        # Bullet 2: explicit "fake" wins regardless of google_api_key.
        ("fake", "", "fake"),
        ("fake", "valid_key", "fake"),
        # Bullet 3: empty mode + non-empty key → "real".
        ("", "valid_key", "real"),
        # Bullet 4 (otherwise): empty mode + empty key → "fake".
        ("", "", "fake"),
        # Bullet 4 (otherwise): unrecognised mode falls through to "fake"
        # even when a key is present — see the docstring on
        # ``select_mode`` for why this is the safe default.
        ("garbage", "valid_key", "fake"),
        ("garbage", "", "fake"),
    ],
)
def test_property_ar5_mode_selection_examples(
    agent_mode, google_api_key, expected
):
    """Concrete examples spanning each branch of AR5's mapping table.

    Validates: Requirements 3.3, 3.4
    """
    stub = SimpleNamespace(
        agent_mode=agent_mode,
        google_api_key=google_api_key,
    )
    assert select_mode(stub) == expected


# ── Property AR7: AgentRunResult device_feedback selection ─────────
#
# *For any* ``actions`` list produced by an agent run,
# ``result.device_feedback`` SHALL equal the most recent (last by
# index) entry of ``actions`` for which
# ``entry.get("type") == "device_command"`` and
# ``entry.get("success") is True``, or ``None`` if no such entry
# exists.
#
# Strategy: Hypothesis generates lists of dicts with ``type`` drawn
# from a small alphabet (``"device_command"`` plus other realistic Tool
# Result Dict types like ``"task"``, ``"expense"``, ``"reminder"``,
# ``"summary"``, plus arbitrary text and absent keys) and ``success``
# drawn from booleans, truthy non-bool values (``1``, ``"yes"``), and
# absence. The reference oracle scans the list from the end and picks
# the first dict whose ``type == "device_command"`` and whose
# ``success is True`` (strict identity check, mirroring the
# implementation's guard against truthy-but-non-bool values).
#
# We also assert the helper is robust to non-dict entries in
# ``actions`` (the implementation skips them via ``isinstance``), and
# to ``None`` / empty-list inputs (both must return ``None``).
#
# Validates: Requirement 6.5

from app.agent.result import _pick_device_feedback  # noqa: E402


def _expected_device_feedback(actions):
    """Reference oracle for AR7.

    Mirrors :func:`_pick_device_feedback` verbatim: scan from the end,
    return the first ``dict`` with ``type == "device_command"`` and
    ``success is True``, else ``None``. Non-dict entries are skipped.
    Empty / ``None`` inputs return ``None``.
    """
    if not actions:
        return None
    for entry in reversed(actions):
        if not isinstance(entry, dict):
            continue
        if (
            entry.get("type") == "device_command"
            and entry.get("success") is True
        ):
            return entry
    return None


# Strategy for the ``type`` field: realistic Tool Result Dict values
# plus arbitrary text so the generator explores both the matching and
# non-matching branches.
_AR7_TYPE_STRATEGY = st.one_of(
    st.sampled_from(
        ["device_command", "task", "expense", "reminder", "summary", ""]
    ),
    st.text(max_size=20),
)

# Strategy for ``success``: booleans plus truthy-but-non-bool values
# (``1``, ``"yes"``, ``"true"``) so the generator stresses the strict
# ``is True`` check in :func:`_pick_device_feedback`.
_AR7_SUCCESS_STRATEGY = st.one_of(
    st.booleans(),
    st.sampled_from([1, 0, "yes", "true", "false", None]),
)


@st.composite
def _ar7_action_dict(draw):
    """Build a single action dict, optionally omitting ``type`` /
    ``success`` keys to exercise the ``.get`` defaults in the helper."""
    type_val = draw(_AR7_TYPE_STRATEGY)
    success_val = draw(_AR7_SUCCESS_STRATEGY)
    include_type = draw(st.booleans())
    include_success = draw(st.booleans())
    entry: dict = {}
    if include_type:
        entry["type"] = type_val
    if include_success:
        entry["success"] = success_val
    return entry


_AR7_ACTIONS_STRATEGY = st.lists(_ar7_action_dict(), max_size=10)


@settings(max_examples=200, deadline=None)
@given(actions=_AR7_ACTIONS_STRATEGY)
def test_property_ar7_pick_device_feedback(actions):
    """Property AR7: AgentRunResult device_feedback selection.

    Validates: Requirement 6.5
    """
    expected = _expected_device_feedback(actions)
    actual = _pick_device_feedback(actions)
    assert actual == expected, (
        f"_pick_device_feedback({actions!r}) returned {actual!r}, "
        f"expected {expected!r} per AR7 selection rule"
    )
    # When a match exists it must be referentially identical to the
    # entry from ``actions`` (no copying / mutation).
    if expected is not None:
        assert actual is expected, (
            "helper must return the original dict reference, not a copy"
        )


@pytest.mark.parametrize(
    "actions, expected",
    [
        # Empty input → None.
        ([], None),
        # ``None`` input → None.
        (None, None),
        # No device_command entries at all → None.
        (
            [
                {"type": "task", "success": True},
                {"type": "expense", "success": True},
            ],
            None,
        ),
        # Single successful device_command → that entry.
        (
            [{"type": "device_command", "success": True, "ack": "ok"}],
            {"type": "device_command", "success": True, "ack": "ok"},
        ),
        # Failed device_command only → None.
        (
            [{"type": "device_command", "success": False, "error": "x"}],
            None,
        ),
        # Multiple successful device_commands → the LAST one wins.
        (
            [
                {"type": "device_command", "success": True, "ack": "first"},
                {"type": "task", "success": True},
                {"type": "device_command", "success": True, "ack": "last"},
            ],
            {"type": "device_command", "success": True, "ack": "last"},
        ),
        # Mixed successes/failures: helper iterates past failed entries
        # from the end, so the earlier successful entry wins.
        (
            [
                {"type": "device_command", "success": True, "ack": "winner"},
                {"type": "device_command", "success": False, "error": "x"},
            ],
            {"type": "device_command", "success": True, "ack": "winner"},
        ),
        # Truthy-but-non-bool ``success`` (``1``) MUST NOT be selected;
        # the helper uses strict ``is True``.
        (
            [{"type": "device_command", "success": 1}],
            None,
        ),
        # Truthy-but-non-bool ``success`` (``"yes"``) MUST NOT be
        # selected.
        (
            [{"type": "device_command", "success": "yes"}],
            None,
        ),
        # Strict ``is True`` falls through to an earlier real ``True``
        # device_command when the latest is truthy-non-bool.
        (
            [
                {"type": "device_command", "success": True, "ack": "real"},
                {"type": "device_command", "success": 1, "ack": "fake"},
            ],
            {"type": "device_command", "success": True, "ack": "real"},
        ),
        # Non-dict entries in ``actions`` are skipped, not crashed on.
        (
            [
                "not a dict",
                None,
                42,
                {"type": "device_command", "success": True, "ack": "ok"},
            ],
            {"type": "device_command", "success": True, "ack": "ok"},
        ),
        # Missing ``type`` / ``success`` keys → entry is not selected.
        (
            [
                {"success": True},
                {"type": "device_command"},
                {"type": "device_command", "success": True, "ack": "ok"},
            ],
            {"type": "device_command", "success": True, "ack": "ok"},
        ),
    ],
)
def test_property_ar7_pick_device_feedback_examples(actions, expected):
    """Concrete examples spanning each branch of AR7's selection rule.

    Validates: Requirement 6.5
    """
    assert _pick_device_feedback(actions) == expected


# ── Property AR1: Tool Surface Identitas ───────────────────────────
#
# *For any* invocation of ``build_taskbot_agent`` produced by the Agent
# Runtime under ``agent_mode == "real"``, the resulting agent SHALL have
# exactly five tools whose ``__name__`` attributes equal the set
# ``{"create_task", "create_expense", "set_reminder",
#    "get_today_summary", "send_device_command"}``.
#
# Strategy: build the per-request Tool Surface via
# :func:`app.agent.tool_factory.build_tools`, hand it to
# :func:`app.agent.adk_agent.build_taskbot_agent` with a stub model
# identifier (no network call is required because the agent is only
# *constructed* — the Gemini endpoint is hit later by the runner), and
# audit ``agent.tools``. Google ADK 1.x stores the tools list as-is
# (the FunctionTool wrappers are produced lazily by
# ``Agent.canonical_tools()``); we check both surfaces so the test stays
# robust against minor SDK changes that might pre-wrap the callables.
#
# The whole test is gated by ``pytest.importorskip`` — environments
# without ``google-adk`` installed (e.g. minimal CI variants) skip this
# check instead of failing module collection.
#
# Validates: Requirements 1.1, 1.3, 1.5

# Skip the entire AR1 block when google-adk is not installed. The import
# is intentionally local to this section so the AR2/AR3/AR4 tests above
# (which never touch ADK) remain runnable without the SDK.
pytest.importorskip("google.adk.agents")

from app.agent.adk_agent import build_taskbot_agent  # noqa: E402

_TOOL_SURFACE_NAMES = frozenset(
    {
        "create_task",
        "create_expense",
        "set_reminder",
        "get_today_summary",
        "send_device_command",
    }
)


def _agent_tool_names(agent) -> set[str]:
    """Return the names of the tools registered on ``agent``.

    ADK 1.x exposes two surfaces:

    - ``agent.tools`` — the raw list of callables/tool objects passed at
      construction time. Each plain Python callable retains its
      ``__name__``; class-based tools expose ``.name``.
    - ``agent.canonical_tools(ctx)`` — the resolved list of ``BaseTool``
      objects (e.g. ``FunctionTool``) that the runner actually invokes.
      Each item has a ``.name`` attribute.

    Property AR1 is phrased over ``agent.tools`` (per the design / task
    description), but we union both surfaces so the test still holds if a
    future ADK release decides to pre-wrap the callables eagerly. The
    union approach also documents that *both* surfaces are expected to
    converge on the same five Tool Surface names.
    """
    names: set[str] = set()
    for tool in agent.tools:
        # Plain callables (Phase 4 factory output) carry ``__name__``.
        if hasattr(tool, "__name__"):
            names.add(tool.__name__)
        # ADK ``BaseTool`` subclasses expose ``.name``.
        elif hasattr(tool, "name"):
            names.add(tool.name)
    return names


def _canonical_tool_names(agent) -> set[str] | None:
    """Return the names from ``agent.canonical_tools()`` if available.

    Google ADK 1.33 exposes ``canonical_tools`` as an *async* method that
    returns ``list[BaseTool]``. Older releases sometimes return the list
    directly. We handle both shapes and return ``None`` if the method is
    missing entirely so the caller can skip this secondary assertion.
    The coroutine is always awaited (or explicitly closed on failure)
    to avoid ``RuntimeWarning: coroutine ... was never awaited``.
    """
    import asyncio
    import inspect as _inspect

    fn = getattr(agent, "canonical_tools", None)
    if fn is None:
        return None
    try:
        result = fn()
    except TypeError:
        # Some versions require a context argument; pass ``None``.
        try:
            result = fn(None)
        except Exception:  # pragma: no cover — defensive only
            return None
    except Exception:  # pragma: no cover — defensive only
        return None
    if _inspect.iscoroutine(result):
        try:
            result = asyncio.run(result)
        except Exception:  # pragma: no cover — defensive only
            result.close()
            return None
    if not isinstance(result, list):
        return None
    return {getattr(t, "name", getattr(t, "__name__", "")) for t in result}


def test_property_ar1_tool_surface_identity_example():
    """Concrete example exercising Property AR1 with fixed inputs.

    Build the per-request tools and the ``taskbot_agent`` using a stub
    model identifier. The agent must register exactly the five Tool
    Surface callables, identified by their ``__name__``.

    Validates: Requirements 1.1, 1.3, 1.5
    """
    tools = build_tools(object(), "user-123", "device-456")
    agent = build_taskbot_agent(model="gemini-stub", tools=tools)

    # Primary check: ``agent.tools`` length and names.
    assert len(agent.tools) == 5, (
        f"taskbot_agent must register exactly 5 tools, got {len(agent.tools)}: "
        f"{[getattr(t, '__name__', type(t).__name__) for t in agent.tools]}"
    )
    assert _agent_tool_names(agent) == _TOOL_SURFACE_NAMES

    # Secondary check: ``canonical_tools`` (if exposed by this SDK
    # version) converges on the same five names.
    canonical = _canonical_tool_names(agent)
    if canonical is not None:
        assert canonical == _TOOL_SURFACE_NAMES, (
            f"canonical_tools must agree with agent.tools; got {canonical}"
        )


@settings(max_examples=25, deadline=None)
@given(
    user_id=st.text(min_size=1, max_size=40),
    device_id=st.one_of(st.none(), st.text(min_size=1, max_size=40)),
)
def test_property_ar1_tool_surface_identity(user_id, device_id):
    """Property AR1: Tool Surface Identitas.

    For any ``(user_id, device_id)`` bound at factory time, the
    ``taskbot_agent`` built from ``build_tools(...)`` must always
    register exactly the five Tool Surface callables — independent of
    the bound context, because the tool *identity* is structural.

    Validates: Requirements 1.1, 1.3, 1.5
    """
    tools = build_tools(object(), user_id, device_id)
    agent = build_taskbot_agent(model="gemini-stub", tools=tools)

    assert len(agent.tools) == 5
    assert _agent_tool_names(agent) == _TOOL_SURFACE_NAMES

    canonical = _canonical_tool_names(agent)
    if canonical is not None:
        assert canonical == _TOOL_SURFACE_NAMES
