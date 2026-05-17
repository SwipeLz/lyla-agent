"""Tests for ``app.scheduler.tick.reminder_tick``.

Covers Property RS2 from
``.kiro/specs/agent-runtime-and-apis/design.md`` (Correctness Properties →
Reminder Scheduler).

Each Hypothesis example builds its own in-memory SQLite engine via the
``_make_engine_session`` helper so state is fully isolated per example.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from hypothesis import HealthCheck, given, settings, strategies as st
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base

# Importing the models package registers every table on ``Base.metadata``.
import app.models  # noqa: F401
from app.models.constants import ReminderStatus
from app.models.device import Device
from app.models.reminder import Reminder
from app.models.user import User
from app.scheduler.tick import reminder_tick
from app.services import device_service, reminder_service


# ── helpers ─────────────────────────────────────────────────────────


def _make_engine_session():
    """Return ``(engine, SessionLocal)`` for a fresh in-memory SQLite DB.

    The caller is responsible for disposing the engine at the end of the
    test example. ``SessionLocal`` can be passed straight to
    ``reminder_tick(db_factory=...)`` so the function-under-test receives
    a brand-new session, just like it would in production.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return engine, SessionLocal


def _make_user(db: Session) -> User:
    """Insert a unique ``User`` and return it."""
    user = User(
        name="Sched User",
        email=f"u-{uuid.uuid4().hex}@taskbot.local",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ── Property RS2: Tick processes all due reminders ─────────────────
#
# *For any* DB state with ``n`` Due Reminders, one call to
# ``reminder_tick`` SHALL invoke ``reminder_service.list_due_reminders``
# exactly once and SHALL attempt dispatch for each Due Reminder before
# returning.
#
# Strategy: generate a list of 0..N Due Reminders (channel="whatsapp" so
# the dispatch leg is exactly one ``whatsapp_send`` call per reminder),
# wrap ``reminder_service.list_due_reminders`` with a counting shim, and
# inject a fake ``whatsapp_send`` that records each reminder it receives.
#
# Validates: Requirements 8.1, 8.5


@settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(n_due=st.integers(min_value=0, max_value=8))
def test_reminder_tick_processes_all_due_reminders(monkeypatch, n_due):
    """Property RS2: ``list_due_reminders`` is called exactly once and one
    dispatch is attempted for every Due Reminder it returns.

    Validates: Requirements 8.1, 8.5
    """
    engine, SessionLocal = _make_engine_session()
    try:
        # ── Seed: one user + ``n_due`` whatsapp-channel due reminders ──
        seed_db = SessionLocal()
        try:
            user = _make_user(seed_db)
            past = datetime.now(timezone.utc) - timedelta(minutes=1)
            seeded_ids: list[str] = []
            for idx in range(n_due):
                reminder = Reminder(
                    user_id=user.id,
                    title=f"R{idx}",
                    remind_at=past,
                    channel="whatsapp",
                    status=ReminderStatus.SCHEDULED,
                )
                seed_db.add(reminder)
                seed_db.commit()
                seed_db.refresh(reminder)
                seeded_ids.append(reminder.id)
        finally:
            seed_db.close()

        # ── Counter wrappers for the two collaborators we measure ──
        list_due_calls: list[Session] = []
        real_list_due = reminder_service.list_due_reminders

        def counting_list_due(db, *args, **kwargs):
            list_due_calls.append(db)
            return real_list_due(db, *args, **kwargs)

        monkeypatch.setattr(
            reminder_service, "list_due_reminders", counting_list_due
        )

        whatsapp_calls: list[str] = []

        def fake_whatsapp_send(reminder):
            whatsapp_calls.append(reminder.id)
            return {"sent": True, "stub": True}

        # ── Run the tick once ──
        result = reminder_tick(
            db_factory=SessionLocal,
            whatsapp_send=fake_whatsapp_send,
        )

        # ── Invariants ──
        # 1. ``list_due_reminders`` is invoked exactly once per tick.
        assert len(list_due_calls) == 1, (
            f"expected exactly one list_due_reminders call, "
            f"got {len(list_due_calls)}"
        )
        # 2. Dispatch is attempted for every Due Reminder returned.
        assert len(whatsapp_calls) == n_due
        # 3. Each seeded reminder id was dispatched exactly once.
        assert sorted(whatsapp_calls) == sorted(seeded_ids)
        # 4. Counter dict reflects all reminders as successfully sent.
        assert result == {"sent": n_due, "failed": 0, "skipped": 0}
    finally:
        engine.dispose()


# ── Property RS3: Channel routing ──────────────────────────────────
#
# *For any* Due Reminder with ``channel in {"device","both"}`` and a
# user that has at least one Device, the tick SHALL invoke
# ``device_service.queue_device_command`` exactly once for that
# reminder. *For any* with ``channel in {"whatsapp","both"}``, the tick
# SHALL invoke ``whatsapp_send`` exactly once for that reminder.
#
# Strategy: hypothesise over ``channel ∈ {device, whatsapp, both}``;
# seed one Due Reminder of that channel attached to a user that owns a
# Device; record both dispatchers; assert call counts exactly match the
# expected routing table.
#
# Validates: Requirements 8.2, 8.3


@settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(channel=st.sampled_from(["device", "whatsapp", "both"]))
def test_reminder_tick_routes_by_channel(monkeypatch, channel):
    """Property RS3: Channel routing.

    For one seeded Due Reminder with the given ``channel``:
    - ``device`` → ``queue_device_command`` 1×, ``whatsapp_send`` 0×.
    - ``whatsapp`` → ``queue_device_command`` 0×, ``whatsapp_send`` 1×.
    - ``both`` → ``queue_device_command`` 1×, ``whatsapp_send`` 1×.

    Validates: Requirements 8.2, 8.3
    """
    engine, SessionLocal = _make_engine_session()
    try:
        # ── Seed: user + device + one Due Reminder with the given channel ──
        seed_db = SessionLocal()
        try:
            user = _make_user(seed_db)
            device = Device(
                user_id=user.id,
                device_code=f"dev-{uuid.uuid4().hex[:8]}",
                name="Test Device",
            )
            seed_db.add(device)
            seed_db.commit()
            seed_db.refresh(device)
            device_id = device.id

            past = datetime.now(timezone.utc) - timedelta(minutes=1)
            reminder = Reminder(
                user_id=user.id,
                title="Routing test",
                remind_at=past,
                channel=channel,
                status=ReminderStatus.SCHEDULED,
            )
            seed_db.add(reminder)
            seed_db.commit()
            seed_db.refresh(reminder)
            reminder_id = reminder.id
        finally:
            seed_db.close()

        # ── Recording stubs for both dispatch legs ──
        device_calls: list[tuple] = []

        def recording_queue_device_command(db, device_id, command_type, payload):
            device_calls.append((device_id, command_type, payload))
            # Return a sentinel — the tick ignores the return value.
            return None

        monkeypatch.setattr(
            device_service,
            "queue_device_command",
            recording_queue_device_command,
        )

        whatsapp_calls: list[str] = []

        def recording_whatsapp_send(rem):
            whatsapp_calls.append(rem.id)
            return {"sent": True, "stub": True}

        # ── Run the tick once ──
        result = reminder_tick(
            db_factory=SessionLocal,
            whatsapp_send=recording_whatsapp_send,
        )

        # ── Expected call counts per channel ──
        expected_device = 1 if channel in ("device", "both") else 0
        expected_whatsapp = 1 if channel in ("whatsapp", "both") else 0

        assert len(device_calls) == expected_device, (
            f"channel={channel!r}: expected {expected_device} "
            f"queue_device_command call(s), got {len(device_calls)}"
        )
        assert len(whatsapp_calls) == expected_whatsapp, (
            f"channel={channel!r}: expected {expected_whatsapp} "
            f"whatsapp_send call(s), got {len(whatsapp_calls)}"
        )

        # When the WhatsApp leg is invoked, it must receive *this* reminder.
        if expected_whatsapp:
            assert whatsapp_calls == [reminder_id]

        # When the device leg is invoked, it must target the seeded device.
        if expected_device:
            assert device_calls[0][0] == device_id

        # The reminder dispatched successfully on every leg, so the tick
        # counter should reflect a single ``sent`` reminder.
        assert result == {"sent": 1, "failed": 0, "skipped": 0}
    finally:
        engine.dispose()


# ── Property RS4: Status transition ────────────────────────────────
#
# *For any* Due Reminder where all dispatch calls succeed, after the
# tick its status SHALL equal ``ReminderStatus.SENT``. *For any* where
# any dispatch raises, its status SHALL equal ``ReminderStatus.FAILED``.
# Either way, processing of remaining Due Reminders SHALL continue
# within the same tick.
#
# Strategy: hypothesise a list of booleans (size 0..6) where each entry
# is True iff the corresponding seeded reminder's WhatsApp dispatch
# should raise. Seed N whatsapp-channel Due Reminders, inject a
# `whatsapp_send` that raises ``RuntimeError`` for the flagged ones and
# returns OK otherwise. After running the tick, re-query the DB and
# assert each seeded reminder's status matches its flag, and that the
# returned counter dict reflects the success/failure split exactly.
#
# Validates: Requirements 8.4, 8.5


@settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(fail_flags=st.lists(st.booleans(), min_size=0, max_size=6))
def test_reminder_tick_status_transition(monkeypatch, fail_flags):
    """Property RS4: Status transition.

    Successful dispatches transition the reminder to ``SENT``; raising
    dispatches transition to ``FAILED``; remaining reminders in the same
    tick continue to be processed.

    Validates: Requirements 8.4, 8.5
    """
    engine, SessionLocal = _make_engine_session()
    try:
        # ── Seed: one user + N whatsapp-channel Due Reminders ──
        seed_db = SessionLocal()
        try:
            user = _make_user(seed_db)
            past = datetime.now(timezone.utc) - timedelta(minutes=1)
            reminder_ids: list[str] = []
            for idx, _ in enumerate(fail_flags):
                reminder = Reminder(
                    user_id=user.id,
                    title=f"R{idx}",
                    remind_at=past,
                    channel="whatsapp",
                    status=ReminderStatus.SCHEDULED,
                )
                seed_db.add(reminder)
                seed_db.commit()
                seed_db.refresh(reminder)
                reminder_ids.append(reminder.id)
        finally:
            seed_db.close()

        # Build a lookup mapping reminder id → "should this dispatch raise?"
        should_fail: dict[str, bool] = {
            rid: flag for rid, flag in zip(reminder_ids, fail_flags)
        }

        # ── Inject whatsapp_send that raises for flagged reminders ──
        whatsapp_calls: list[str] = []

        def selectively_failing_whatsapp_send(reminder):
            whatsapp_calls.append(reminder.id)
            if should_fail.get(reminder.id, False):
                raise RuntimeError(f"simulated whatsapp failure for {reminder.id}")
            return {"sent": True, "stub": True}

        # ── Run the tick once ──
        result = reminder_tick(
            db_factory=SessionLocal,
            whatsapp_send=selectively_failing_whatsapp_send,
        )

        # ── Invariants ──
        # 1. Every seeded reminder had its dispatch attempted (Req 8.5:
        #    failures do not stop processing of remaining reminders).
        assert sorted(whatsapp_calls) == sorted(reminder_ids)

        # 2. Re-query each seeded reminder and check its final status.
        verify_db = SessionLocal()
        try:
            for rid, flag in should_fail.items():
                row = (
                    verify_db.query(Reminder)
                    .filter(Reminder.id == rid)
                    .one_or_none()
                )
                assert row is not None, f"reminder {rid} disappeared"
                expected = (
                    ReminderStatus.FAILED if flag else ReminderStatus.SENT
                )
                assert row.status == expected, (
                    f"reminder {rid}: expected status {expected!r} "
                    f"(should_fail={flag}), got {row.status!r}"
                )
        finally:
            verify_db.close()

        # 3. Counter dict matches the success/failure split exactly.
        expected_failed = sum(1 for f in fail_flags if f)
        expected_sent = len(fail_flags) - expected_failed
        assert result == {
            "sent": expected_sent,
            "failed": expected_failed,
            "skipped": 0,
        }
    finally:
        engine.dispose()


# ── Property RS5: No real WhatsApp call ────────────────────────────
#
# *For any* tick run with the default WhatsApp Stub, the dispatch leg
# SHALL NOT touch a real WhatsApp Cloud API endpoint or any HTTP client
# library that would enable one. Specifically:
#
# 1. The module ``app.integrations.whatsapp`` SHALL NOT import
#    ``httpx``, ``requests``, or ``urllib`` at the source level. This
#    is checked by reading the module source via ``inspect.getsource``.
# 2. With the autouse network kill-switch in ``conftest.py`` blocking
#    any outbound connection (e.g. to ``graph.facebook.com`` or
#    ``*.whatsapp.com``), one tick over a mix of ``whatsapp``/``both``
#    channel reminders SHALL complete without raising. That proves the
#    stub actually returns synchronously without attempting any socket
#    operation outside loopback.
#
# Strategy: Hypothesise a list of channel choices restricted to
# ``{"whatsapp", "both"}`` so the WhatsApp dispatch leg is exercised on
# every seeded reminder. For ``"both"``, also seed a Device for the
# user so the device leg short-circuits cleanly without raising. Run
# ``reminder_tick`` with the *default* ``whatsapp_send`` (i.e. the real
# ``whatsapp_send_stub``) and assert it completes and that the source
# of ``app/integrations/whatsapp.py`` contains no forbidden imports.
#
# Validates: Requirements 8.6, 15.2


@settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    channels=st.lists(
        st.sampled_from(["whatsapp", "both"]),
        min_size=0,
        max_size=5,
    )
)
def test_reminder_tick_makes_no_real_whatsapp_call(channels):
    """Property RS5: No real WhatsApp call.

    The default WhatsApp Stub does not import any HTTP client, and a
    full tick over reminders that exercise the WhatsApp leg completes
    without raising while the autouse network kill-switch blocks every
    non-loopback connection (including ``graph.facebook.com`` and
    ``*.whatsapp.com``).

    Validates: Requirements 8.6, 15.2
    """
    import inspect

    import app.integrations.whatsapp as whatsapp_module

    # ── 1. Source-level invariant: the WhatsApp Stub module must not
    #       import any HTTP client that could reach a real endpoint. ──
    source = inspect.getsource(whatsapp_module)
    forbidden_imports = (
        "import httpx",
        "from httpx",
        "import requests",
        "from requests",
        "import urllib",
        "from urllib",
    )
    for needle in forbidden_imports:
        assert needle not in source, (
            f"app/integrations/whatsapp.py must not contain {needle!r} "
            f"(would enable real WhatsApp Cloud API calls)"
        )

    # ── 2. Behavioural invariant: tick completes with the default
    #       stub even when the kill-switch blocks non-loopback I/O. ──
    engine, SessionLocal = _make_engine_session()
    try:
        seed_db = SessionLocal()
        try:
            user = _make_user(seed_db)
            # If any reminder has channel="both", the device leg also
            # runs; seed one Device so that path doesn't get skipped
            # (Req 8.7) and we genuinely exercise the whatsapp leg too.
            if any(c == "both" for c in channels):
                device = Device(
                    user_id=user.id,
                    device_code=f"dev-{uuid.uuid4().hex[:8]}",
                    name="Test Device",
                )
                seed_db.add(device)
                seed_db.commit()

            past = datetime.now(timezone.utc) - timedelta(minutes=1)
            for idx, channel in enumerate(channels):
                seed_db.add(
                    Reminder(
                        user_id=user.id,
                        title=f"R{idx}",
                        remind_at=past,
                        channel=channel,
                        status=ReminderStatus.SCHEDULED,
                    )
                )
            seed_db.commit()
        finally:
            seed_db.close()

        # ── Run the tick with the *default* whatsapp_send. Any attempt
        #     to reach graph.facebook.com / *.whatsapp.com would be
        #     blocked by the autouse kill-switch and bubble up as a
        #     RuntimeError that mark_reminder_failed catches — which
        #     would manifest as ``failed > 0``. We assert the tick is
        #     fully successful and skipped == 0. ──
        result = reminder_tick(db_factory=SessionLocal)

        assert result["failed"] == 0, (
            f"tick reported {result['failed']} failed dispatch(es); "
            f"the default WhatsApp Stub must not attempt any real "
            f"network call. Full result: {result!r}"
        )
        assert result["sent"] == len(channels)
        assert result["skipped"] == 0
    finally:
        engine.dispose()


# ── Property RS6: Skip device-only when user has no device ─────────
#
# *For any* Due Reminder with ``channel == "device"`` whose user has
# no Device, the tick SHALL NOT call
# ``device_service.queue_device_command`` for that reminder, SHALL NOT
# call WhatsApp, and SHALL leave the reminder's status equal to
# ``ReminderStatus.SCHEDULED`` (no transition).
#
# Strategy: hypothesise the number ``n`` of seeded
# ``channel="device"`` reminders attached to a user that owns *no*
# Device. Monkeypatch ``device_service.queue_device_command`` and
# inject a recording ``whatsapp_send``. Run one tick and assert:
# - ``queue_device_command`` was not called.
# - ``whatsapp_send`` was not called.
# - Every seeded reminder still has ``status == SCHEDULED`` in DB.
# - The returned counter dict is ``{"sent": 0, "failed": 0,
#   "skipped": n}``.
#
# Validates: Requirement 8.7


@settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(n_reminders=st.integers(min_value=1, max_value=5))
def test_reminder_tick_skips_device_only_when_no_device(monkeypatch, n_reminders):
    """Property RS6: Skip device-only when user has no device.

    A device-channel reminder belonging to a user that has no Device
    must produce no dispatch calls and must leave the reminder's
    status untouched.

    Validates: Requirement 8.7
    """
    engine, SessionLocal = _make_engine_session()
    try:
        # ── Seed: one user with NO Device + N device-channel reminders ──
        seed_db = SessionLocal()
        try:
            user = _make_user(seed_db)
            # Sanity check: the seeded user really has no Device.
            assert (
                seed_db.query(Device)
                .filter(Device.user_id == user.id)
                .count()
                == 0
            )

            past = datetime.now(timezone.utc) - timedelta(minutes=1)
            reminder_ids: list[str] = []
            for idx in range(n_reminders):
                reminder = Reminder(
                    user_id=user.id,
                    title=f"R{idx}",
                    remind_at=past,
                    channel="device",
                    status=ReminderStatus.SCHEDULED,
                )
                seed_db.add(reminder)
                seed_db.commit()
                seed_db.refresh(reminder)
                reminder_ids.append(reminder.id)
        finally:
            seed_db.close()

        # ── Recording stub for ``queue_device_command`` ──
        device_calls: list[tuple] = []

        def recording_queue_device_command(db, device_id, command_type, payload):
            device_calls.append((device_id, command_type, payload))
            return None

        monkeypatch.setattr(
            device_service,
            "queue_device_command",
            recording_queue_device_command,
        )

        # ── Recording ``whatsapp_send`` (must never be called) ──
        whatsapp_calls: list[str] = []

        def recording_whatsapp_send(reminder):
            whatsapp_calls.append(reminder.id)
            return {"sent": True, "stub": True}

        # ── Run the tick once ──
        result = reminder_tick(
            db_factory=SessionLocal,
            whatsapp_send=recording_whatsapp_send,
        )

        # ── Invariants ──
        # 1. ``queue_device_command`` was never called: the user owns
        #    no Device, so device-only routing must short-circuit.
        assert device_calls == [], (
            f"queue_device_command must not be called when the user "
            f"has no Device, got {len(device_calls)} call(s)"
        )

        # 2. WhatsApp must never be called for ``channel="device"``.
        assert whatsapp_calls == [], (
            f"whatsapp_send must not be called for channel='device', "
            f"got {len(whatsapp_calls)} call(s)"
        )

        # 3. Every seeded reminder must still be SCHEDULED in DB.
        verify_db = SessionLocal()
        try:
            for rid in reminder_ids:
                row = (
                    verify_db.query(Reminder)
                    .filter(Reminder.id == rid)
                    .one_or_none()
                )
                assert row is not None, f"reminder {rid} disappeared"
                assert row.status == ReminderStatus.SCHEDULED, (
                    f"reminder {rid}: expected status SCHEDULED "
                    f"(no transition), got {row.status!r}"
                )
        finally:
            verify_db.close()

        # 4. Counter dict reflects every reminder as skipped.
        assert result == {
            "sent": 0,
            "failed": 0,
            "skipped": n_reminders,
        }, (
            f"expected counter {{'sent': 0, 'failed': 0, "
            f"'skipped': {n_reminders}}}, got {result!r}"
        )
    finally:
        engine.dispose()
