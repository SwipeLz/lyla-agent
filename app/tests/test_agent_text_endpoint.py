"""Property tests for ``POST /agent/text`` (Phase 5).

Properties tested in this module are listed in
``.kiro/specs/agent-runtime-and-apis/design.md`` (section "Correctness
Properties"):

**Property AT1: Request validation table**
*For any* payload, the response SHALL conform to:

| Condition                    | HTTP | Side effect                                |
|------------------------------|------|--------------------------------------------|
| empty/whitespace text        | 422  | no agent call, no log                      |
| unknown user_id              | 404  | no agent call, no log                      |
| unknown device_id (non-null) | 404  | no agent call, no log                      |
| valid input                  | 200  | agent called once, exactly one log row     |

**Validates: Requirements 5.1, 5.2, 5.3, 5.4, 6.1, 6.2, 6.3**

**Property AT2: Log mirrors response**
*For any* successful 200 response, the persisted ``VoiceCommandLog``
row SHALL satisfy:

* ``input_text == request.text``
* ``parsed_actions == response.actions``
* ``response_text == response.reply``
* ``status == "success"``

**Validates: Requirements 6.2, 6.4**

Test infrastructure
-------------------

The handler depends on a SQLAlchemy session via ``Depends(get_db)``. We
override that dependency to yield a session bound to a process-shared
in-memory SQLite engine (``StaticPool``) so the FastAPI handler — which
``TestClient`` runs on a separate worker thread — observes the same
database rows the test seeded on the main thread. The conftest's
``db_session`` fixture builds a per-test engine *without* ``StaticPool``,
so it cannot be reused directly across the TestClient thread boundary;
this module therefore declares its own ``shared_db_session`` fixture
that solves the cross-thread visibility issue while keeping the
in-memory hermetic behaviour.

The Agent Runtime is monkeypatched at ``app.api.agent.run_text`` to a
deterministic ``async`` stub that records each invocation. This:

  * keeps the test hermetic (no real agent dispatch, no Google ADK
    import path triggered),
  * lets us assert the agent is called exactly once on the success path,
  * lets us assert the agent is NOT called on any of the failure paths.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings as hyp_settings, strategies as st
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.agent.result import AgentRunResult
from app.db import Base, get_db
from app.main import app as fastapi_app
import app.models  # noqa: F401  ensures all model tables are registered
from app.models import Device, User, VoiceCommandLog
from app.models.constants import DeviceStatus


# ── Test infrastructure ────────────────────────────────────────────


@pytest.fixture
def shared_db_session():
    """Build a thread-shareable in-memory SQLite session for one test.

    The endpoint runs on the TestClient's worker thread while the test
    body runs on the main thread. A regular ``sqlite:///:memory:``
    engine cannot be shared across threads with separate connections,
    so we use ``StaticPool`` (single shared connection) and disable
    ``check_same_thread``. This still gives us full per-test isolation
    because the engine is disposed at fixture teardown.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _make_user(db) -> User:
    sfx = uuid4().hex
    user = User(name=f"User {sfx}", email=f"user-{sfx}@taskbot.local")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_device(db, user: User) -> Device:
    device = Device(
        user_id=user.id,
        device_code=f"dev-{uuid4()}",
        name="Bench device",
        status=DeviceStatus.OFFLINE,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


@pytest.fixture
def client(shared_db_session):
    """TestClient wired to the per-test ``shared_db_session``.

    Overrides ``get_db`` so the handler and the test share the same
    session (and thus the same SQLite memory database). Cleans up the
    override on teardown so other tests are not affected.
    """

    def _override_get_db():
        yield shared_db_session

    fastapi_app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(fastapi_app) as test_client:
            yield test_client
    finally:
        fastapi_app.dependency_overrides.pop(get_db, None)


class _RunTextRecorder:
    """Records calls to the monkeypatched ``run_text``.

    Each call appends the kwargs it received to ``calls`` and returns
    a deterministic :class:`AgentRunResult`. The recorder is a
    callable so it can be used as a drop-in replacement.
    """

    def __init__(self, result: AgentRunResult | None = None) -> None:
        self.calls: list[dict] = []
        self._result = result or AgentRunResult(
            reply="hello",
            actions=[],
            device_feedback=None,
            status="success",
        )

    async def __call__(self, db, *, user_id, device_id, text, timezone):
        self.calls.append(
            {
                "db": db,
                "user_id": user_id,
                "device_id": device_id,
                "text": text,
                "timezone": timezone,
            }
        )
        return self._result


@pytest.fixture
def recorder(monkeypatch):
    """Monkeypatch ``app.api.agent.run_text`` with a recording stub."""
    rec = _RunTextRecorder()
    monkeypatch.setattr("app.api.agent.run_text", rec)
    return rec


def _log_count(db) -> int:
    """Total ``VoiceCommandLog`` rows currently in the session's DB."""
    # Expire so the count reflects rows committed by the API handler
    # against the same in-memory engine.
    db.expire_all()
    return db.query(VoiceCommandLog).count()


# ── Generators for Property AT1 ────────────────────────────────────

# Whitespace-only / empty text — expected to fail Pydantic validation
# with HTTP 422 before the handler runs.
blank_text_strategy = st.one_of(
    st.just(""),
    st.integers(min_value=1, max_value=8).map(lambda n: " " * n),
    st.integers(min_value=1, max_value=4).map(lambda n: "\t" * n),
    st.integers(min_value=1, max_value=3).map(lambda n: "\n" * n),
    st.just("   \t  \n "),
)

# Non-blank text that always survives the ``_text_not_blank`` validator.
non_blank_text_strategy = (
    st.text(min_size=1, max_size=60)
    .filter(lambda s: s.strip() != "")
)

# Random UUID-shaped strings unlikely to collide with seeded users/devices.
unknown_id_strategy = st.uuids().map(lambda u: f"missing-{u}")


# ── Property AT1: empty / whitespace text → 422 ────────────────────


@hyp_settings(
    max_examples=25,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(text=blank_text_strategy)
def test_at1_blank_text_returns_422_no_side_effect(
    text, client, shared_db_session, recorder
):
    """Property AT1, row 1: blank/whitespace text → 422, no agent, no log.

    Validates: Requirements 5.1, 5.2, 6.1, 6.2, 6.3
    """
    user = _make_user(shared_db_session)

    log_before = _log_count(shared_db_session)
    response = client.post(
        "/agent/text",
        json={"user_id": user.id, "text": text},
    )

    assert response.status_code == 422, (
        f"Expected 422 for blank text {text!r}, got {response.status_code}: "
        f"{response.text}"
    )
    assert recorder.calls == [], (
        "run_text must NOT be invoked when the request body fails "
        "validation (Req 5.2)."
    )
    assert _log_count(shared_db_session) == log_before, (
        "No VoiceCommandLog row may be persisted on a 422 (Req 6.2)."
    )


# ── Property AT1: unknown user_id → 404 ────────────────────────────


@hyp_settings(
    max_examples=25,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(missing_user_id=unknown_id_strategy, text=non_blank_text_strategy)
def test_at1_unknown_user_returns_404_no_side_effect(
    missing_user_id, text, client, shared_db_session, recorder
):
    """Property AT1, row 2: unknown user_id → 404, no agent, no log.

    Validates: Requirements 5.1, 5.3, 6.1, 6.2
    """
    log_before = _log_count(shared_db_session)
    response = client.post(
        "/agent/text",
        json={"user_id": missing_user_id, "text": text},
    )

    assert response.status_code == 404, (
        f"Expected 404 for unknown user_id={missing_user_id!r}, "
        f"got {response.status_code}: {response.text}"
    )
    assert recorder.calls == [], (
        "run_text must NOT be invoked when the user does not exist "
        "(Req 5.3)."
    )
    assert _log_count(shared_db_session) == log_before, (
        "No VoiceCommandLog row may be persisted on a 404 (Req 6.2)."
    )


# ── Property AT1: unknown device_id → 404 ──────────────────────────


@hyp_settings(
    max_examples=25,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(missing_device_id=unknown_id_strategy, text=non_blank_text_strategy)
def test_at1_unknown_device_returns_404_no_side_effect(
    missing_device_id, text, client, shared_db_session, recorder
):
    """Property AT1, row 3: unknown device_id → 404, no agent, no log.

    Validates: Requirements 5.1, 5.4, 6.1, 6.2
    """
    user = _make_user(shared_db_session)

    log_before = _log_count(shared_db_session)
    response = client.post(
        "/agent/text",
        json={
            "user_id": user.id,
            "device_id": missing_device_id,
            "text": text,
        },
    )

    assert response.status_code == 404, (
        f"Expected 404 for unknown device_id={missing_device_id!r}, "
        f"got {response.status_code}: {response.text}"
    )
    assert recorder.calls == [], (
        "run_text must NOT be invoked when the device does not exist "
        "(Req 5.4)."
    )
    assert _log_count(shared_db_session) == log_before, (
        "No VoiceCommandLog row may be persisted on a 404 (Req 6.2)."
    )


# ── Property AT1: valid input → 200 + 1 agent call + 1 log row ─────


@hyp_settings(
    max_examples=15,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(text=non_blank_text_strategy, with_device=st.booleans())
def test_at1_valid_input_returns_200_one_call_one_log(
    text, with_device, client, shared_db_session, recorder
):
    """Property AT1, row 4: valid input → 200, exactly one agent call,
    exactly one VoiceCommandLog row.

    Validates: Requirements 5.1, 6.1, 6.2, 6.3
    """
    user = _make_user(shared_db_session)
    device = _make_device(shared_db_session, user) if with_device else None

    # Snapshot state before the call so we can assert "exactly one"
    # without depending on Hypothesis example ordering.
    log_before = _log_count(shared_db_session)
    calls_before = len(recorder.calls)

    payload: dict = {"user_id": user.id, "text": text}
    if device is not None:
        payload["device_id"] = device.id

    response = client.post("/agent/text", json=payload)

    assert response.status_code == 200, (
        f"Expected 200 for valid input, got {response.status_code}: "
        f"{response.text}"
    )

    body = response.json()
    assert body["reply"] == "hello"
    assert body["actions"] == []
    assert body["device_feedback"] is None

    # Req 6.1: agent invoked exactly once.
    assert len(recorder.calls) - calls_before == 1, (
        f"Expected exactly one run_text call, got "
        f"{len(recorder.calls) - calls_before}."
    )
    last_call = recorder.calls[-1]
    assert last_call["user_id"] == user.id
    assert last_call["device_id"] == (device.id if device is not None else None)
    assert last_call["text"] == text

    # Req 6.2: exactly one VoiceCommandLog row persisted.
    assert _log_count(shared_db_session) - log_before == 1, (
        "Expected exactly one VoiceCommandLog row to be persisted on "
        "the success path (Req 6.2)."
    )


# ── Concrete unit-style example for the validation table ──────────


@pytest.mark.parametrize(
    "case",
    ["blank_text", "whitespace_text", "unknown_user", "unknown_device", "valid"],
)
def test_at1_validation_table_concrete_examples(
    case, client, shared_db_session, recorder
):
    """Concrete table-driven example exercising every Property AT1 row.

    Provides a deterministic supplement to the Hypothesis-driven tests
    above — useful when triaging a failure example and easier to read
    than a shrinker output.

    Validates: Requirements 5.1, 5.2, 5.3, 5.4, 6.1, 6.2, 6.3
    """
    user = _make_user(shared_db_session)
    device = _make_device(shared_db_session, user)
    log_before = _log_count(shared_db_session)
    calls_before = len(recorder.calls)

    if case == "blank_text":
        resp = client.post(
            "/agent/text", json={"user_id": user.id, "text": ""}
        )
        assert resp.status_code == 422
        assert len(recorder.calls) == calls_before
        assert _log_count(shared_db_session) == log_before
    elif case == "whitespace_text":
        resp = client.post(
            "/agent/text", json={"user_id": user.id, "text": "   \t\n "}
        )
        assert resp.status_code == 422
        assert len(recorder.calls) == calls_before
        assert _log_count(shared_db_session) == log_before
    elif case == "unknown_user":
        resp = client.post(
            "/agent/text",
            json={"user_id": f"missing-{uuid4()}", "text": "hi"},
        )
        assert resp.status_code == 404
        assert len(recorder.calls) == calls_before
        assert _log_count(shared_db_session) == log_before
    elif case == "unknown_device":
        resp = client.post(
            "/agent/text",
            json={
                "user_id": user.id,
                "device_id": f"missing-{uuid4()}",
                "text": "hi",
            },
        )
        assert resp.status_code == 404
        assert len(recorder.calls) == calls_before
        assert _log_count(shared_db_session) == log_before
    elif case == "valid":
        resp = client.post(
            "/agent/text",
            json={"user_id": user.id, "device_id": device.id, "text": "hi"},
        )
        assert resp.status_code == 200
        assert len(recorder.calls) - calls_before == 1
        assert _log_count(shared_db_session) - log_before == 1
    else:  # pragma: no cover — defensive branch
        pytest.fail(f"unknown case {case!r}")


# ── Property AT2: Log mirrors response ─────────────────────────────
#
# The recorder fixture from AT1 always returns a fixed
# ``AgentRunResult(reply="hello", actions=[], ...)``. To exercise
# Property AT2 we need to *vary* the runtime's reply and actions per
# Hypothesis example and then verify the persisted ``VoiceCommandLog``
# row mirrors them. We do that by mutating ``recorder._result`` before
# each request, which is the same hook ``_RunTextRecorder`` already
# uses internally (see the ``_RunTextRecorder.__call__`` implementation
# above — it returns ``self._result``).
#
# We use ``device_feedback=None`` for these tests because Property AT2
# only constrains the four log columns listed above; ``device_feedback``
# selection is covered by Property AT4 in a separate task.


# JSON-friendly leaves for Tool Result Dict fields (extras like ``id``,
# ``amount``, ``message``). We bound the tree depth/width to keep
# Hypothesis runs fast — the property is universal in shape, not size.
_action_extra_value = st.recursive(
    st.one_of(
        st.none(),
        st.booleans(),
        st.integers(min_value=-1_000, max_value=1_000),
        st.text(max_size=20),
    ),
    lambda children: st.one_of(
        st.lists(children, max_size=3),
        st.dictionaries(st.text(min_size=1, max_size=8), children, max_size=3),
    ),
    max_leaves=5,
)


def _action_strategy() -> st.SearchStrategy[dict]:
    """Generate a single Tool Result Dict resembling Phase 3 output.

    Each action has the canonical ``type``/``success`` pair plus a
    handful of optional extras under non-reserved keys, mirroring what
    the Phase 3 tool wrappers actually return (e.g. ``{"type":
    "task_created", "success": True, "id": "...", "title": "..."}``).
    """
    type_strategy = st.sampled_from(
        [
            "task_created",
            "expense_created",
            "reminder_set",
            "today_summary",
            "device_command",
        ]
    )
    extras_strategy = st.dictionaries(
        # Avoid colliding with the canonical keys so the assertion on
        # ``type``/``success`` stays unambiguous.
        st.text(
            alphabet=st.characters(
                whitelist_categories=("Ll", "Lu", "Nd"),
                whitelist_characters="_",
            ),
            min_size=1,
            max_size=8,
        ).filter(lambda k: k not in {"type", "success"}),
        _action_extra_value,
        max_size=3,
    )
    return st.builds(
        lambda t, ok, extras: {"type": t, "success": ok, **extras},
        type_strategy,
        st.booleans(),
        extras_strategy,
    )


# Reply strings the agent might emit. Keep them non-empty so the
# request-side validator (which the response side does not share) does
# not interfere with comparisons; allow Indonesian-ish punctuation.
_reply_strategy = st.text(min_size=1, max_size=80).filter(lambda s: s.strip() != "")


@hyp_settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    text=non_blank_text_strategy,
    reply=_reply_strategy,
    actions=st.lists(_action_strategy(), max_size=4),
    with_device=st.booleans(),
)
def test_at2_log_mirrors_response(
    text, reply, actions, with_device, client, shared_db_session, recorder
):
    """Property AT2: persisted log row mirrors the 200 response.

    For any successful invocation the new ``VoiceCommandLog`` row SHALL
    satisfy:

    * ``input_text == request.text``
    * ``parsed_actions == response.actions``
    * ``response_text == response.reply``
    * ``status == "success"``

    Validates: Requirements 6.2, 6.4
    """
    user = _make_user(shared_db_session)
    device = _make_device(shared_db_session, user) if with_device else None

    # Install a per-example AgentRunResult on the existing recorder so
    # the handler returns the reply/actions we want to verify against
    # the log row. ``device_feedback`` is intentionally fixed to None
    # — Property AT2 does not constrain it.
    recorder._result = AgentRunResult(
        reply=reply,
        actions=list(actions),
        device_feedback=None,
        status="success",
    )

    payload: dict = {"user_id": user.id, "text": text}
    if device is not None:
        payload["device_id"] = device.id

    response = client.post("/agent/text", json=payload)
    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text}"
    )
    body = response.json()

    # Sanity check: the response itself should reflect the configured
    # AgentRunResult. If this fails the whole property is moot.
    assert body["reply"] == reply
    assert body["actions"] == list(actions)

    # Fetch the most recent VoiceCommandLog row for this user. We
    # filter by user_id (rather than just ordering globally) so a
    # parallel/Hypothesis-leftover row from another example cannot be
    # picked up. ``expire_all`` ensures we observe rows committed by
    # the handler on the TestClient worker thread.
    shared_db_session.expire_all()
    log_row = (
        shared_db_session.query(VoiceCommandLog)
        .filter(VoiceCommandLog.user_id == user.id)
        .order_by(VoiceCommandLog.created_at.desc())
        .first()
    )
    assert log_row is not None, "No VoiceCommandLog row was persisted (Req 6.2)."

    # Req 6.2 + 6.4: the log row mirrors the response exactly.
    assert log_row.input_text == text, (
        "Req 6.2: VoiceCommandLog.input_text must equal request.text. "
        f"Got {log_row.input_text!r}, expected {text!r}."
    )
    assert log_row.parsed_actions == list(actions), (
        "Req 6.4: VoiceCommandLog.parsed_actions must equal "
        "response.actions in invocation order. "
        f"Got {log_row.parsed_actions!r}, expected {list(actions)!r}."
    )
    assert log_row.response_text == reply, (
        "Req 6.2: VoiceCommandLog.response_text must equal "
        f"response.reply. Got {log_row.response_text!r}, expected {reply!r}."
    )
    assert log_row.status == "success", (
        "Req 6.2: VoiceCommandLog.status must equal 'success' on the "
        f"happy path. Got {log_row.status!r}."
    )


# ── Property AT3: Error path persists log without leaking trace ────
#
# **Property AT3** (from `.kiro/specs/agent-runtime-and-apis/design.md`):
# *For any* invocation in which ``run_text`` raises, the response SHALL
# be HTTP 500, the response body SHALL NOT contain a stack trace, and
# a ``VoiceCommandLog`` row SHALL exist with ``status == "error"`` and
# ``response_text == str(exc)``.
#
# **Validates: Requirement 6.6**
#
# Test approach
# -------------
# We bypass the ``recorder`` fixture (which installs a non-raising stub)
# and instead use the test's ``monkeypatch`` directly to replace
# ``app.api.agent.run_text`` with a small ``async`` function that
# raises ``RuntimeError(message)``. The Hypothesis strategy generates
# *non-blank* exception messages so every example exercises both halves
# of the property: (a) the response body must not contain the message
# (only the generic ``"Agent runtime error"`` detail), and (b) the
# persisted ``VoiceCommandLog.response_text`` MUST contain the message.
#
# Note on stack-trace leakage assertions:
#   * ``"Traceback"`` is the canonical Python traceback header — any
#     leaked ``traceback.format_exc`` output starts with this token.
#   * The handler module path (``app/api/agent.py`` on POSIX,
#     ``app\\api\\agent.py`` on Windows) is what would appear in a
#     leaked frame summary; we assert neither separator-style appears.


# Non-blank exception messages. We exclude pure-whitespace strings so
# the membership/equality assertion stays meaningful (a message of
# ``"   "`` is technically allowed by ``RuntimeError`` but useless to
# verify against ``response_text``).
exception_message_strategy = (
    st.text(min_size=1, max_size=120).filter(lambda s: s.strip() != "")
)


@hyp_settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    text=non_blank_text_strategy,
    exc_message=exception_message_strategy,
    with_device=st.booleans(),
)
def test_at3_error_path_persists_log_without_leaking_trace(
    text, exc_message, with_device, client, shared_db_session, monkeypatch
):
    """Property AT3: ``run_text`` raise → 500 + error log + no trace leak.

    For *any* ``RuntimeError(message)`` raised by ``run_text``:

    * the HTTP response SHALL be 500 with body ``{"detail": "Agent runtime error"}``;
    * the response body SHALL NOT contain a Python traceback or the
      handler module's file path;
    * a new ``VoiceCommandLog`` row SHALL exist for ``request.user_id``
      with ``status == "error"`` and ``response_text == str(exc)``
      (which equals ``message`` for ``RuntimeError``).

    Validates: Requirement 6.6
    """
    user = _make_user(shared_db_session)
    device = _make_device(shared_db_session, user) if with_device else None

    # Replace the runtime hook with a coroutine that always raises.
    # Defining it inside the test closes over the per-example
    # ``exc_message`` so every Hypothesis example checks a different
    # exception payload against the persisted log row.
    async def raising_run_text(db, *, user_id, device_id, text, timezone):
        raise RuntimeError(exc_message)

    monkeypatch.setattr("app.api.agent.run_text", raising_run_text)

    log_before = _log_count(shared_db_session)

    payload: dict = {"user_id": user.id, "text": text}
    if device is not None:
        payload["device_id"] = device.id

    response = client.post("/agent/text", json=payload)

    # ── Req 6.6, clause 1: HTTP 500 ──
    assert response.status_code == 500, (
        f"Expected 500 when run_text raises, got {response.status_code}: "
        f"{response.text}"
    )

    # ── Req 6.6, clause 2: body is the generic detail, no trace ──
    body = response.json()
    assert body == {"detail": "Agent runtime error"}, (
        "Response body MUST be the generic detail and nothing more. "
        f"Got {body!r}."
    )

    raw_text = response.text
    # No Python traceback header should ever appear in the body.
    assert "Traceback" not in raw_text, (
        f"Response body leaked a Python traceback: {raw_text!r}"
    )
    # No filesystem path of the handler module should leak (POSIX or Windows).
    assert "app/api/agent.py" not in raw_text, (
        f"Response body leaked a POSIX-style handler path: {raw_text!r}"
    )
    assert "app\\api\\agent.py" not in raw_text, (
        f"Response body leaked a Windows-style handler path: {raw_text!r}"
    )
    # Note: a substring check ``exc_message not in raw_text`` would be
    # brittle here — Hypothesis can shrink ``exc_message`` to a single
    # character (e.g. ``'{'``) that legitimately appears inside the
    # generic JSON envelope ``{"detail":"Agent runtime error"}`` without
    # representing a leak. The body-equality assertion above already
    # proves the response contains *only* the generic detail, so any
    # incidental character overlap with ``exc_message`` is by definition
    # not a leak of the exception payload.

    # ── Req 6.6, clause 3: exactly one error log row mirrors str(exc) ──
    shared_db_session.expire_all()
    assert _log_count(shared_db_session) - log_before == 1, (
        "Expected exactly one VoiceCommandLog row to be persisted on the "
        "error path (Req 6.6)."
    )

    log_row = (
        shared_db_session.query(VoiceCommandLog)
        .filter(VoiceCommandLog.user_id == user.id)
        .order_by(VoiceCommandLog.created_at.desc())
        .first()
    )
    assert log_row is not None, (
        "No VoiceCommandLog row was persisted on the error path (Req 6.6)."
    )
    assert log_row.status == "error", (
        "Req 6.6: VoiceCommandLog.status must equal 'error' when run_text "
        f"raised. Got {log_row.status!r}."
    )
    # ``str(RuntimeError(msg)) == msg`` so equality is well-defined here;
    # the task brief asks for containment ("response_text mengandung
    # pesan exception"), which equality satisfies.
    assert log_row.response_text == exc_message, (
        "Req 6.6: VoiceCommandLog.response_text must equal str(exc). "
        f"Got {log_row.response_text!r}, expected {exc_message!r}."
    )
    # Sanity: the input is mirrored as well, so the row is debuggable.
    assert log_row.input_text == text


# Concrete example exercising AT3 — useful for triaging shrinker output.
def test_at3_error_path_concrete_example(
    client, shared_db_session, monkeypatch
):
    """Concrete AT3 example: deterministic raise → 500 + error log row.

    Validates: Requirement 6.6
    """
    user = _make_user(shared_db_session)
    message = "fake runtime exploded: division by zero"

    async def boom(db, *, user_id, device_id, text, timezone):
        raise RuntimeError(message)

    monkeypatch.setattr("app.api.agent.run_text", boom)

    log_before = _log_count(shared_db_session)
    response = client.post(
        "/agent/text",
        json={"user_id": user.id, "text": "halo agent"},
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "Agent runtime error"}
    assert "Traceback" not in response.text
    # The body-equality assertion above proves the response is exactly
    # the generic detail envelope, which already implies the raw
    # exception message is not echoed as content. A direct substring
    # check would be brittle on tiny messages whose characters happen
    # to overlap with the JSON envelope.

    shared_db_session.expire_all()
    assert _log_count(shared_db_session) - log_before == 1
    log_row = (
        shared_db_session.query(VoiceCommandLog)
        .filter(VoiceCommandLog.user_id == user.id)
        .order_by(VoiceCommandLog.created_at.desc())
        .first()
    )
    assert log_row is not None
    assert log_row.status == "error"
    assert log_row.response_text == message
    assert log_row.input_text == "halo agent"


# ── Property AT4: device_feedback equals last successful device command ──
#
# **Property AT4** (from `.kiro/specs/agent-runtime-and-apis/design.md`):
# *For any* successful 200 response, ``response.device_feedback`` SHALL
# equal the last entry of ``response.actions`` with ``type ==
# "device_command"`` and ``success is True``, or ``null`` if none.
#
# **Validates: Requirement 6.5**
#
# Test approach
# -------------
# The handler returns ``device_feedback`` straight from
# ``AgentRunResult.device_feedback``; the runtime is what picks the
# value via ``_pick_device_feedback(actions)``. To exercise AT4 at the
# *endpoint* level we mimic the runtime's contract on the recorder:
# generate a Hypothesis-shaped ``actions`` list, compute the expected
# ``device_feedback`` with the same helper used by the real runtime,
# and stuff both into ``recorder._result``. The handler is then
# expected to forward that value verbatim to the response, which in
# turn validates that:
#
#   * ``response.device_feedback`` equals the **last** entry in
#     ``actions`` whose ``type == "device_command"`` and
#     ``success is True``;
#   * ``response.device_feedback`` is ``null`` when no such entry
#     exists (mixed lists with only failures, non-device entries, or
#     an empty list).
#
# We deliberately reuse ``_pick_device_feedback`` (rather than
# reimplementing the selection in the test) so the property is anchored
# to the same semantics the runtime promises. AT7 in
# ``test_agent_runtime.py`` is the unit-level companion that pins
# ``_pick_device_feedback`` itself.


def _at4_action_strategy() -> st.SearchStrategy[dict]:
    """Generate a Tool Result Dict whose ``type``/``success`` we control.

    We bias the ``type`` distribution so ``device_command`` is well
    represented — otherwise most Hypothesis examples would degenerate
    to ``device_feedback is None`` and the "last successful" branch
    would rarely be exercised. Extras under non-canonical keys mimic
    the optional payload Phase 3 wrappers attach (``id``, ``message``,
    ``payload``, ...) without colliding with ``type``/``success``.
    """
    type_strategy = st.sampled_from(
        [
            "device_command",
            "device_command",  # weighted to exercise the success branch
            "task_created",
            "expense_created",
            "reminder_set",
            "today_summary",
        ]
    )
    extras_strategy = st.dictionaries(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("Ll", "Lu", "Nd"),
                whitelist_characters="_",
            ),
            min_size=1,
            max_size=8,
        ).filter(lambda k: k not in {"type", "success"}),
        _action_extra_value,
        max_size=2,
    )
    return st.builds(
        lambda t, ok, extras: {"type": t, "success": ok, **extras},
        type_strategy,
        st.booleans(),
        extras_strategy,
    )


@hyp_settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    text=non_blank_text_strategy,
    actions=st.lists(_at4_action_strategy(), max_size=6),
    with_device=st.booleans(),
)
def test_at4_device_feedback_is_last_successful_device_command(
    text, actions, with_device, client, shared_db_session, recorder
):
    """Property AT4: ``response.device_feedback`` follows
    ``_pick_device_feedback(actions)`` for the entry it picks (or None).

    For *any* mixed ``actions`` list, the response field
    ``device_feedback`` SHALL be:

    * the **last** entry whose ``type == "device_command"`` and
      ``success is True``; or
    * ``null`` if no such entry exists.

    Validates: Requirement 6.5
    """
    # Import locally so the property test is self-evidently anchored to
    # the same selection helper the runtime uses.
    from app.agent.result import _pick_device_feedback

    user = _make_user(shared_db_session)
    device = _make_device(shared_db_session, user) if with_device else None

    # Mirror the runtime's contract: device_feedback is whatever
    # _pick_device_feedback chooses for this actions list. Setting both
    # fields on the recorder lets us prove the *handler* forwards the
    # runtime's choice (Req 6.5) without re-testing the selection
    # logic in two places.
    expected_feedback = _pick_device_feedback(list(actions))
    recorder._result = AgentRunResult(
        reply="ok",
        actions=list(actions),
        device_feedback=expected_feedback,
        status="success",
    )

    payload: dict = {"user_id": user.id, "text": text}
    if device is not None:
        payload["device_id"] = device.id

    response = client.post("/agent/text", json=payload)

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text}"
    )
    body = response.json()

    # Sanity: the actions list is forwarded verbatim so the
    # device_feedback assertion is meaningful.
    assert body["actions"] == list(actions)

    # Core AT4 assertion: device_feedback equals the runtime's pick.
    assert body["device_feedback"] == expected_feedback, (
        "Req 6.5: response.device_feedback must equal the last "
        "successful 'device_command' action (or null). "
        f"Got {body['device_feedback']!r}, expected {expected_feedback!r}."
    )

    # Independent re-derivation: scan response.actions ourselves and
    # confirm the same entry was selected. This catches a regression
    # where the runtime and helper disagree, even if both happen to
    # match the recorder's pre-computed value.
    rederived = None
    for entry in reversed(body["actions"]):
        if (
            isinstance(entry, dict)
            and entry.get("type") == "device_command"
            and entry.get("success") is True
        ):
            rederived = entry
            break
    assert body["device_feedback"] == rederived, (
        "Req 6.5: response.device_feedback must equal the last entry "
        "of response.actions with type=='device_command' and "
        f"success is True (or null). Got {body['device_feedback']!r}, "
        f"expected {rederived!r}."
    )


# Concrete examples for AT4 — covers the three structural cases:
#   (a) no device_command entries at all → null,
#   (b) device_command entries all unsuccessful → null,
#   (c) mixed entries with multiple successful device_commands → the
#       *last* one is selected (not the first).
@pytest.mark.parametrize(
    ("actions", "expected"),
    [
        # (a) empty actions list → null
        ([], None),
        # (a) only non-device entries → null
        (
            [
                {"type": "task_created", "success": True, "id": "t1"},
                {"type": "expense_created", "success": True, "id": "e1"},
            ],
            None,
        ),
        # (b) device_command present but all failed → null
        (
            [
                {"type": "device_command", "success": False, "error": "no device"},
                {"type": "task_created", "success": True, "id": "t2"},
                {"type": "device_command", "success": False, "error": "timeout"},
            ],
            None,
        ),
        # (c) one successful device_command → that entry
        (
            [
                {"type": "task_created", "success": True, "id": "t3"},
                {
                    "type": "device_command",
                    "success": True,
                    "payload": {"face": "happy"},
                },
            ],
            {
                "type": "device_command",
                "success": True,
                "payload": {"face": "happy"},
            },
        ),
        # (c) multiple successful device_commands → the LAST one wins
        (
            [
                {
                    "type": "device_command",
                    "success": True,
                    "payload": {"face": "neutral"},
                },
                {"type": "task_created", "success": True, "id": "t4"},
                {
                    "type": "device_command",
                    "success": True,
                    "payload": {"face": "smile"},
                },
            ],
            {
                "type": "device_command",
                "success": True,
                "payload": {"face": "smile"},
            },
        ),
        # Truthy-but-not-True success values must NOT be treated as
        # successful (the helper uses ``is True``). Last entry is the
        # only "real" success → it wins.
        (
            [
                {"type": "device_command", "success": 1, "payload": {"face": "x"}},
                {
                    "type": "device_command",
                    "success": "yes",
                    "payload": {"face": "y"},
                },
                {
                    "type": "device_command",
                    "success": True,
                    "payload": {"face": "z"},
                },
            ],
            {
                "type": "device_command",
                "success": True,
                "payload": {"face": "z"},
            },
        ),
    ],
)
def test_at4_device_feedback_concrete_examples(
    actions, expected, client, shared_db_session, recorder
):
    """Concrete AT4 cases: empty, no-device, all-failed, single, multi.

    Validates: Requirement 6.5
    """
    from app.agent.result import _pick_device_feedback

    # The recorder's device_feedback mirrors what the runtime would
    # produce; the parametrize ``expected`` is the externally-derived
    # truth. They MUST agree — otherwise the test fixture itself is
    # wrong and the assertion below would be meaningless.
    assert _pick_device_feedback(actions) == expected, (
        "Test fixture is inconsistent: _pick_device_feedback disagrees "
        "with the parametrized expected value."
    )

    user = _make_user(shared_db_session)
    recorder._result = AgentRunResult(
        reply="ok",
        actions=list(actions),
        device_feedback=expected,
        status="success",
    )

    response = client.post(
        "/agent/text",
        json={"user_id": user.id, "text": "halo"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["actions"] == list(actions)
    assert body["device_feedback"] == expected
