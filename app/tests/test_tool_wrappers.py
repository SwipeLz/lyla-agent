"""Tests for the Tool Wrapper Layer (``app.tools``).

Covers Properties TW1–TW7 from
``.kiro/specs/service-layer/design.md`` (Correctness Properties → Tool
Wrapper Layer). Each Hypothesis test builds its own in-memory SQLite
engine via :func:`_make_session` so every example starts from a clean
schema.

A note on SQLite + timezones: even though datetime columns are declared
with ``DateTime(timezone=True)``, SQLite has no native tz-aware storage
and SQLAlchemy returns naive ``datetime`` instances on read. We
therefore normalise persisted values to aware UTC before comparing
against inputs.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from hypothesis import HealthCheck, assume, given, settings, strategies as st
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base

# Importing the models package registers every table on ``Base.metadata``.
import app.models  # noqa: F401
from app.models.constants import DeviceCommandStatus, DeviceStatus, TaskStatus
from app.models.device import Device
from app.models.device_command import DeviceCommand
from app.models.expense import Expense
from app.models.task import Task
from app.models.user import User
from app.services.exceptions import (
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from app.tools.device_tools import send_device_command_tool
from app.tools.expense_tools import create_expense_tool
from app.tools.reminder_tools import set_reminder_tool
from app.tools.summary_tools import get_today_summary_tool
from app.tools.task_tools import create_task_tool
from app.utils.timezone import jakarta_today_window_utc


# ── helpers ─────────────────────────────────────────────────────────


def _make_session() -> tuple[Session, object]:
    """Create a fresh in-memory SQLite session.

    Returns ``(session, engine)``. The caller is responsible for closing
    the session and disposing the engine.
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
    Session_ = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return Session_(), engine


def _make_user(db: Session, name: str = "u") -> User:
    """Insert a ``User`` with a unique email and return it."""
    user = User(name=name, email=f"{name}-{uuid.uuid4().hex}@example.com")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_device(db: Session, user: User, code: str | None = None) -> Device:
    """Insert a ``Device`` belonging to ``user`` and return it."""
    device = Device(
        user_id=user.id,
        device_code=code or f"dev-{uuid.uuid4().hex}",
        name="Test Device",
        status=DeviceStatus.OFFLINE,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


# ── Hypothesis strategies ───────────────────────────────────────────

# Aware future datetime built as ``now + N seconds`` for integer N in a
# safe future range. Using ``datetime.now(timezone.utc)`` at example
# generation time keeps "future" semantics correct (the captured "now"
# moves with each example), avoiding the stale-bound problem.
future_seconds = st.integers(min_value=60, max_value=30 * 24 * 3600)
past_seconds = st.integers(min_value=-30 * 24 * 3600, max_value=-60)
any_offset_seconds = st.integers(
    min_value=-30 * 24 * 3600, max_value=30 * 24 * 3600
)


@st.composite
def aware_future_dt(draw):
    """Generate a timezone-aware UTC datetime strictly in the future."""
    secs = draw(future_seconds)
    return datetime.now(timezone.utc) + timedelta(seconds=secs)


@st.composite
def aware_any_dt(draw):
    """Generate a timezone-aware UTC datetime around now (past or future)."""
    secs = draw(any_offset_seconds)
    return datetime.now(timezone.utc) + timedelta(seconds=secs)


non_blank_str = st.text(min_size=1, max_size=40).filter(lambda s: s.strip() != "")
optional_short_text = st.one_of(st.none(), st.text(min_size=1, max_size=20))
positive_amount = st.integers(min_value=1, max_value=10**9)
valid_channel = st.sampled_from(["whatsapp", "device", "both"])
optional_payload_field = st.one_of(
    st.none(), st.text(min_size=1, max_size=20)
)


# ─────────────────────────────────────────────────────────────────────
# Property TW1: create_task_tool success → success Tool Result Dict
# ─────────────────────────────────────────────────────────────────────

# Feature: service-layer, Property TW1: create_task_tool mengembalikan Tool Result Dict sukses
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    title=non_blank_str,
    course=optional_short_text,
    deadline_at=st.one_of(st.none(), aware_future_dt()),
    reminder_at=st.one_of(st.none(), aware_future_dt()),
    priority=optional_short_text,
)
def test_TW1_create_task_tool_success(
    title, course, deadline_at, reminder_at, priority
):
    """Validates: Requirements 6.1

    For any input that is valid for ``task_service.create_task``,
    ``create_task_tool`` returns a dict with ``success=True``,
    ``type="task"``, ``id`` matching the persisted ``Task.id``, and a
    non-empty ``message``.
    """
    db, engine = _make_session()
    try:
        user = _make_user(db, name="alice")

        result = create_task_tool(
            db,
            user_id=user.id,
            title=title,
            course=course,
            deadline_at=deadline_at,
            reminder_at=reminder_at,
            priority=priority,
        )

        assert result["success"] is True
        assert result["type"] == "task"
        assert "id" in result and result["id"] is not None
        assert isinstance(result["message"], str) and result["message"]

        # The returned id should match exactly one persisted Task row.
        task = db.query(Task).filter(Task.id == result["id"]).one_or_none()
        assert task is not None
        assert task.user_id == user.id
        assert task.status == TaskStatus.PENDING
    finally:
        db.close()
        engine.dispose()


# ─────────────────────────────────────────────────────────────────────
# Property TW2: create_expense_tool success → success Tool Result Dict
# ─────────────────────────────────────────────────────────────────────

# Feature: service-layer, Property TW2: create_expense_tool mengembalikan Tool Result Dict sukses
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    amount=positive_amount,
    category=optional_short_text,
    note=optional_short_text,
    spent_at=st.one_of(st.none(), aware_any_dt()),
)
def test_TW2_create_expense_tool_success(amount, category, note, spent_at):
    """Validates: Requirements 6.2

    For any input that is valid for ``expense_service.create_expense``,
    ``create_expense_tool`` returns a dict with ``success=True``,
    ``type="expense"``, ``id`` matching the persisted ``Expense.id``,
    and a non-empty ``message``.
    """
    db, engine = _make_session()
    try:
        user = _make_user(db, name="bob")

        result = create_expense_tool(
            db,
            user_id=user.id,
            amount=amount,
            category=category,
            note=note,
            spent_at=spent_at,
        )

        assert result["success"] is True
        assert result["type"] == "expense"
        assert "id" in result and result["id"] is not None
        assert isinstance(result["message"], str) and result["message"]

        expense = (
            db.query(Expense).filter(Expense.id == result["id"]).one_or_none()
        )
        assert expense is not None
        assert expense.user_id == user.id
        assert expense.amount == amount
    finally:
        db.close()
        engine.dispose()


# ─────────────────────────────────────────────────────────────────────
# Property TW3: set_reminder_tool success → success Tool Result Dict
# ─────────────────────────────────────────────────────────────────────

# Feature: service-layer, Property TW3: set_reminder_tool mengembalikan Tool Result Dict sukses
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    title=non_blank_str,
    remind_at=aware_future_dt(),
    channel=valid_channel,
)
def test_TW3_set_reminder_tool_success(title, remind_at, channel):
    """Validates: Requirements 6.3

    For any input that is valid for ``reminder_service.create_reminder``,
    ``set_reminder_tool`` returns a dict with ``success=True``,
    ``type="reminder"``, ``id`` matching the persisted ``Reminder.id``,
    and a non-empty ``message``.
    """
    from app.models.reminder import Reminder

    db, engine = _make_session()
    try:
        user = _make_user(db, name="carol")

        result = set_reminder_tool(
            db,
            user_id=user.id,
            title=title,
            remind_at=remind_at,
            channel=channel,
        )

        assert result["success"] is True
        assert result["type"] == "reminder"
        assert "id" in result and result["id"] is not None
        assert isinstance(result["message"], str) and result["message"]

        reminder = (
            db.query(Reminder).filter(Reminder.id == result["id"]).one_or_none()
        )
        assert reminder is not None
        assert reminder.user_id == user.id
        assert reminder.channel == channel
    finally:
        db.close()
        engine.dispose()


# ─────────────────────────────────────────────────────────────────────
# Property TW4: send_device_command_tool builds consistent payload
# ─────────────────────────────────────────────────────────────────────

# Feature: service-layer, Property TW4: send_device_command_tool membentuk payload yang konsisten
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    face=optional_payload_field,
    sound=optional_payload_field,
    text=optional_payload_field,
)
def test_TW4_send_device_command_tool_payload(face, sound, text):
    """Validates: Requirements 6.4

    For any device that exists and any combination of ``face``,
    ``sound``, ``text`` with at least one non-``None`` value,
    ``send_device_command_tool`` returns a success Tool Result Dict and
    persists a new ``DeviceCommand`` whose ``payload`` contains exactly
    the non-``None`` keys mapped to their input values.
    """
    # Restrict to the "non-empty payload" branch: at least one of the
    # three fields must be non-None.
    assume(face is not None or sound is not None or text is not None)

    db, engine = _make_session()
    try:
        user = _make_user(db, name="dave")
        device = _make_device(db, user)

        before_count = db.query(DeviceCommand).count()

        result = send_device_command_tool(
            db,
            device_id=device.id,
            face=face,
            sound=sound,
            text=text,
        )

        assert result["success"] is True
        assert result["type"] == "device_command"
        assert "id" in result and result["id"] is not None
        assert isinstance(result["message"], str) and result["message"]

        # Exactly one new DeviceCommand row was persisted.
        assert db.query(DeviceCommand).count() == before_count + 1

        command = (
            db.query(DeviceCommand)
            .filter(DeviceCommand.id == result["id"])
            .one()
        )
        assert command.device_id == device.id
        assert command.status == DeviceCommandStatus.PENDING

        # Payload contains exactly the non-None keys with their values.
        expected_payload = {
            k: v
            for k, v in {"face": face, "sound": sound, "text": text}.items()
            if v is not None
        }
        assert command.payload == expected_payload
    finally:
        db.close()
        engine.dispose()


# ─────────────────────────────────────────────────────────────────────
# Property TW5: send_device_command_tool all-None rejected
# ─────────────────────────────────────────────────────────────────────

# Feature: service-layer, Property TW5: send_device_command_tool semua None ditolak
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    # The device id may be a real device or a bogus id — either way the
    # wrapper short-circuits before touching the DB, so no row may be
    # added regardless.
    bogus_device_id=st.text(min_size=1, max_size=40).filter(
        lambda s: s.strip() != ""
    ),
)
def test_TW5_send_device_command_tool_all_none(bogus_device_id):
    """Validates: Requirements 6.5

    When ``face = sound = text = None``, ``send_device_command_tool``
    returns ``{"success": False, "type": "device_command", "error":
    <non-empty>}`` and does not insert any ``DeviceCommand`` row.
    """
    db, engine = _make_session()
    try:
        # Seed with a real device so the table is populated; the
        # wrapper still must not add a new row.
        user = _make_user(db, name="erin")
        _make_device(db, user)

        before_count = db.query(DeviceCommand).count()

        result = send_device_command_tool(
            db,
            device_id=bogus_device_id,
            face=None,
            sound=None,
            text=None,
        )

        assert result["success"] is False
        assert result["type"] == "device_command"
        assert isinstance(result.get("error"), str) and result["error"]
        # Importantly, no DeviceCommand row was added.
        assert db.query(DeviceCommand).count() == before_count
    finally:
        db.close()
        engine.dispose()


# ─────────────────────────────────────────────────────────────────────
# Property TW6: get_today_summary_tool matches Asia/Jakarta window
# ─────────────────────────────────────────────────────────────────────

# Feature: service-layer, Property TW6: get_today_summary_tool cocok dengan window Asia/Jakarta
# Each example seeds the DB with up to ~12 rows, but we still run 100
# examples per the design's testing strategy.
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    # Each tuple = (kind ∈ {"task", "expense"}, seconds offset relative
    # to the Jakarta-day start, expense amount).
    seed=st.lists(
        st.tuples(
            st.sampled_from(["task", "expense"]),
            # Spread offsets across a 4-day band centered on the
            # Jakarta-day start so we exercise both inside and outside
            # the [start, end) window.
            st.integers(
                min_value=-2 * 24 * 3600, max_value=3 * 24 * 3600 - 1
            ),
            positive_amount,
        ),
        min_size=0,
        max_size=12,
    ),
)
def test_TW6_get_today_summary_tool_window(seed):
    """Validates: Requirements 6.6, 8.2

    ``get_today_summary_tool`` returns ``tasks_due_today`` equal to the
    count of ``Task`` rows whose ``deadline_at`` falls in
    ``jakarta_today_window_utc()`` and ``total_expenses_today`` equal
    to the sum of ``Expense.amount`` whose ``spent_at`` falls in the
    same window.
    """
    db, engine = _make_session()
    try:
        user = _make_user(db, name="frank")
        # Pin the window once at the start of the example so both the
        # rows we insert and the wrapper's query interpret "today"
        # consistently within this single example.
        start_utc, end_utc = jakarta_today_window_utc()

        expected_tasks = 0
        expected_total = 0
        for kind, offset, amount in seed:
            ts = start_utc + timedelta(seconds=offset)
            in_window = start_utc <= ts < end_utc
            if kind == "task":
                db.add(
                    Task(
                        user_id=user.id,
                        title=f"task-{uuid.uuid4().hex[:8]}",
                        deadline_at=ts,
                        status=TaskStatus.PENDING,
                    )
                )
                if in_window:
                    expected_tasks += 1
            else:  # expense
                db.add(
                    Expense(
                        user_id=user.id,
                        amount=amount,
                        spent_at=ts,
                    )
                )
                if in_window:
                    expected_total += amount
        db.commit()

        result = get_today_summary_tool(db, user_id=user.id)

        assert result["success"] is True
        assert result["type"] == "summary"
        assert isinstance(result["message"], str) and result["message"]
        assert result["tasks_due_today"] == expected_tasks
        assert result["total_expenses_today"] == expected_total
    finally:
        db.close()
        engine.dispose()


# ─────────────────────────────────────────────────────────────────────
# Property TW7: tool wrappers catch service exceptions
# ─────────────────────────────────────────────────────────────────────

# Feature: service-layer, Property TW7: tool wrapper menangkap exception service
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    exc_class=st.sampled_from(
        [ValidationError, NotFoundError, PermissionDeniedError]
    ),
    err_msg=st.text(min_size=1, max_size=50),
    wrapper_kind=st.sampled_from(["task", "expense", "reminder", "device"]),
)
def test_TW7_wrapper_catches_service_exceptions(
    monkeypatch, exc_class, err_msg, wrapper_kind
):
    """Validates: Requirements 6.7

    For each tool wrapper that wraps a service raising
    ``ValidationError``, ``NotFoundError``, or ``PermissionDeniedError``,
    the wrapper SHALL catch the exception and return a Tool Result Dict
    with ``success=False``, the matching ``type``, and ``error =
    str(exc)`` — without letting the exception propagate.
    """

    def _raise(*_args, **_kwargs):
        raise exc_class(err_msg)

    db, engine = _make_session()
    try:
        if wrapper_kind == "task":
            monkeypatch.setattr(
                "app.services.task_service.create_task", _raise
            )
            result = create_task_tool(
                db, user_id="any", title="anything"
            )
            expected_type = "task"

        elif wrapper_kind == "expense":
            monkeypatch.setattr(
                "app.services.expense_service.create_expense", _raise
            )
            result = create_expense_tool(
                db, user_id="any", amount=1
            )
            expected_type = "expense"

        elif wrapper_kind == "reminder":
            monkeypatch.setattr(
                "app.services.reminder_service.create_reminder", _raise
            )
            result = set_reminder_tool(
                db,
                user_id="any",
                title="anything",
                remind_at=datetime.now(timezone.utc) + timedelta(seconds=60),
            )
            expected_type = "reminder"

        else:  # device
            monkeypatch.setattr(
                "app.services.device_service.queue_device_command", _raise
            )
            # Pass at least one non-None field to bypass the
            # short-circuit and reach the patched service.
            result = send_device_command_tool(
                db, device_id="any", face="happy"
            )
            expected_type = "device_command"

        assert result == {
            "success": False,
            "type": expected_type,
            "error": err_msg,
        }
    finally:
        db.close()
        engine.dispose()
