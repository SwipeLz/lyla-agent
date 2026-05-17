"""Tests for ``app.services.reminder_service``.

Property-based tests use Hypothesis with ``max_examples=100`` and a fresh
in-memory SQLite database per example to keep state isolated. Unit tests at
the bottom cover one or two human-readable happy paths.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from hypothesis import HealthCheck, assume, given, settings, strategies as st
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
import app.models  # noqa: F401  registers tables on Base.metadata
from app.models.constants import ReminderStatus, TaskStatus
from app.models.reminder import Reminder
from app.models.task import Task
from app.models.user import User
from app.services import reminder_service
from app.services.exceptions import (
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from app.services.reminder_service import (
    ALLOWED_CHANNELS,
    create_reminder,
    list_due_reminders,
    mark_reminder_failed,
    mark_reminder_sent,
)
from app.utils.timezone import now_utc


# ── Test infrastructure ────────────────────────────────────────────


def _make_session() -> Session:
    """Return a fresh in-memory SQLite session with foreign keys enabled.

    Hypothesis runs many examples per test, so we need a brand-new database
    per example rather than relying on the shared ``db_session`` fixture.
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
    return SessionLocal()


def _make_user(db: Session, email_suffix: str = "u") -> User:
    user = User(name="Test User", email=f"{email_suffix}@taskbot.local")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_task(db: Session, user_id: str, title: str = "Some task") -> Task:
    task = Task(user_id=user_id, title=title, status=TaskStatus.PENDING)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _as_utc(dt: datetime) -> datetime:
    """Normalise a datetime to timezone-aware UTC.

    SQLite drops ``tzinfo`` on round-trip even when the column is declared
    ``DateTime(timezone=True)``. The persisted value still represents the
    UTC instant we passed in, so we re-attach ``timezone.utc`` for naive
    inputs and convert otherwise.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ── Generators ─────────────────────────────────────────────────────

valid_channel = st.sampled_from(list(ALLOWED_CHANNELS))
invalid_channel = st.text(min_size=1, max_size=20).filter(
    lambda s: s not in set(ALLOWED_CHANNELS)
)

aware_future_dt = st.datetimes(
    min_value=datetime(2100, 1, 1),
    max_value=datetime(2200, 1, 1),
    timezones=st.just(timezone.utc),
)
aware_past_dt = st.datetimes(
    min_value=datetime(1970, 1, 1),
    max_value=datetime(2000, 1, 1),
    timezones=st.just(timezone.utc),
)
naive_dt = st.datetimes(
    min_value=datetime(2100, 1, 1),
    max_value=datetime(2200, 1, 1),
    timezones=st.none(),
)
non_blank_str = st.text(min_size=1, max_size=80).filter(lambda s: s.strip() != "")
blank_str = st.one_of(
    st.just(""),
    st.integers(min_value=1, max_value=10).map(lambda n: " " * n),
    st.integers(min_value=1, max_value=5).map(lambda n: "\t" * n),
)


# ── Property R1: create_reminder valid invariants ──────────────────
# Feature: service-layer, Property R1: create_reminder valid invariants
# Validates: Requirement 3.1
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    title=non_blank_str,
    remind_at=aware_future_dt,
    channel=valid_channel,
    link_task=st.booleans(),
)
def test_property_r1_create_reminder_valid_invariants(
    title, remind_at, channel, link_task
):
    db = _make_session()
    try:
        user = _make_user(db)
        task = _make_task(db, user.id) if link_task else None

        before = db.query(Reminder).count()
        reminder = create_reminder(
            db,
            user_id=user.id,
            title=title,
            remind_at=remind_at,
            channel=channel,
            task_id=task.id if task else None,
        )
        after = db.query(Reminder).count()

        # Exactly one row was inserted.
        assert after == before + 1

        # Returned object reflects every supplied field.
        assert reminder.user_id == user.id
        assert reminder.title == title
        assert reminder.channel == channel
        assert reminder.status == ReminderStatus.SCHEDULED
        if task is None:
            assert reminder.task_id is None
        else:
            assert reminder.task_id == task.id

        # ``remind_at`` represents the same absolute instant.
        assert _as_utc(reminder.remind_at) == remind_at

        # The persisted row matches what the service returned.
        persisted = db.query(Reminder).filter(Reminder.id == reminder.id).one()
        assert persisted.status == ReminderStatus.SCHEDULED
        assert persisted.title == title
        assert persisted.channel == channel
    finally:
        db.close()


# ── Property R2: create_reminder ValidationError on invalid input ──
# Feature: service-layer, Property R2: create_reminder ValidationError menolak input invalid
# Validates: Requirements 3.2, 3.4, 3.5, 3.6
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    title=st.one_of(non_blank_str, blank_str),
    remind_at=st.one_of(aware_future_dt, aware_past_dt, naive_dt),
    channel=st.one_of(valid_channel, invalid_channel),
)
def test_property_r2_create_reminder_validation_error(title, remind_at, channel):
    title_invalid = not title.strip()
    naive_invalid = remind_at.tzinfo is None
    past_invalid = (not naive_invalid) and remind_at < now_utc()
    channel_invalid = channel not in ALLOWED_CHANNELS

    # Restrict to inputs with at least one validation issue.
    assume(title_invalid or naive_invalid or past_invalid or channel_invalid)

    db = _make_session()
    try:
        user = _make_user(db)
        before = db.query(Reminder).count()

        with pytest.raises(ValidationError):
            create_reminder(
                db,
                user_id=user.id,
                title=title,
                remind_at=remind_at,
                channel=channel,
            )

        after = db.query(Reminder).count()
        assert after == before
    finally:
        db.close()


# ── Property R3: create_reminder NotFoundError on unknown reference ─
# Feature: service-layer, Property R3: create_reminder NotFoundError pada referensi tidak dikenal
# Validates: Requirement 3.3, 3.7 (sub-case task missing)
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    unknown_user_id=st.text(min_size=1, max_size=36),
    unknown_task_id=st.text(min_size=1, max_size=36),
    title=non_blank_str,
    remind_at=aware_future_dt,
    channel=valid_channel,
    branch=st.sampled_from(["unknown_user", "unknown_task"]),
)
def test_property_r3_create_reminder_not_found(
    unknown_user_id, unknown_task_id, title, remind_at, channel, branch
):
    db = _make_session()
    try:
        # Seed a real user so the "unknown_task" branch passes the user check.
        user = _make_user(db)
        # Avoid colliding with the seeded user's id.
        assume(unknown_user_id != user.id)

        before = db.query(Reminder).count()

        if branch == "unknown_user":
            with pytest.raises(NotFoundError):
                create_reminder(
                    db,
                    user_id=unknown_user_id,
                    title=title,
                    remind_at=remind_at,
                    channel=channel,
                )
        else:
            # task_id refers to a non-existent task.
            with pytest.raises(NotFoundError):
                create_reminder(
                    db,
                    user_id=user.id,
                    title=title,
                    remind_at=remind_at,
                    channel=channel,
                    task_id=unknown_task_id,
                )

        after = db.query(Reminder).count()
        assert after == before
    finally:
        db.close()


# ── Property R4: create_reminder PermissionDeniedError on other-user task ─
# Feature: service-layer, Property R4: create_reminder PermissionDeniedError saat task milik user lain
# Validates: Requirement 3.7 (sub-case task owned by other user)
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    title=non_blank_str,
    remind_at=aware_future_dt,
    channel=valid_channel,
)
def test_property_r4_create_reminder_permission_denied(title, remind_at, channel):
    db = _make_session()
    try:
        owner = _make_user(db, email_suffix="owner")
        other = _make_user(db, email_suffix="other")
        task = _make_task(db, owner.id, title="Owner's task")

        before = db.query(Reminder).count()
        with pytest.raises(PermissionDeniedError):
            create_reminder(
                db,
                user_id=other.id,
                title=title,
                remind_at=remind_at,
                channel=channel,
                task_id=task.id,
            )
        after = db.query(Reminder).count()
        assert after == before
    finally:
        db.close()


# ── Property R5: list_due_reminders filter ─────────────────────────
# Feature: service-layer, Property R5: list_due_reminders filter benar
# Validates: Requirement 3.8
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    rows=st.lists(
        st.tuples(
            # remind_at: anywhere between far past and far future
            st.datetimes(
                min_value=datetime(2000, 1, 1),
                max_value=datetime(2200, 1, 1),
                timezones=st.just(timezone.utc),
            ),
            st.sampled_from(
                [
                    ReminderStatus.SCHEDULED,
                    ReminderStatus.SENT,
                    ReminderStatus.FAILED,
                    ReminderStatus.CANCELLED,
                ]
            ),
        ),
        min_size=0,
        max_size=12,
    ),
    cutoff=st.datetimes(
        min_value=datetime(2000, 1, 1),
        max_value=datetime(2200, 1, 1),
        timezones=st.just(timezone.utc),
    ),
    use_default_now=st.booleans(),
)
def test_property_r5_list_due_reminders_filter(
    monkeypatch, rows, cutoff, use_default_now
):
    db = _make_session()
    try:
        user = _make_user(db)
        seeded = []
        for remind_at, status in rows:
            r = Reminder(
                user_id=user.id,
                title="r",
                remind_at=remind_at,
                channel="both",
                status=status,
            )
            db.add(r)
            seeded.append((r, remind_at, status))
        db.commit()
        for r, _, _ in seeded:
            db.refresh(r)

        # Pin ``now_utc`` so the default-``now`` branch uses ``cutoff``.
        monkeypatch.setattr(reminder_service, "now_utc", lambda: cutoff)

        if use_default_now:
            result = list_due_reminders(db)
        else:
            result = list_due_reminders(db, now=cutoff)

        expected_ids = {
            r.id
            for r, rdt, rstatus in seeded
            if rstatus == ReminderStatus.SCHEDULED and rdt <= cutoff
        }
        actual_ids = {r.id for r in result}

        # Predicate holds for every returned row.
        for r in result:
            assert r.status == ReminderStatus.SCHEDULED
            assert _as_utc(r.remind_at) <= cutoff

        # Set membership matches the predicate.
        assert actual_ids == expected_ids
    finally:
        db.close()


# ── Property R6: mark_reminder_sent / mark_reminder_failed ─────────
# Feature: service-layer, Property R6: mark_reminder_sent dan mark_reminder_failed transitions
# Validates: Requirements 3.9, 3.10, 3.11
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    operation=st.sampled_from(["sent", "failed"]),
    branch=st.sampled_from(["existing", "missing"]),
    unknown_id=st.text(min_size=1, max_size=36),
    initial_status=st.sampled_from(
        [
            ReminderStatus.SCHEDULED,
            ReminderStatus.SENT,
            ReminderStatus.FAILED,
        ]
    ),
)
def test_property_r6_mark_transitions(operation, branch, unknown_id, initial_status):
    db = _make_session()
    try:
        user = _make_user(db)
        reminder = Reminder(
            user_id=user.id,
            title="r",
            remind_at=datetime(2100, 1, 1, tzinfo=timezone.utc),
            channel="both",
            status=initial_status,
        )
        db.add(reminder)
        db.commit()
        db.refresh(reminder)

        # Avoid the unknown_id accidentally hitting an existing reminder.
        assume(unknown_id != reminder.id)

        target_status = (
            ReminderStatus.SENT if operation == "sent" else ReminderStatus.FAILED
        )
        fn = mark_reminder_sent if operation == "sent" else mark_reminder_failed

        if branch == "existing":
            updated = fn(db, reminder.id)
            assert updated.id == reminder.id
            assert updated.status == target_status
            persisted = db.query(Reminder).filter(Reminder.id == reminder.id).one()
            assert persisted.status == target_status
        else:
            with pytest.raises(NotFoundError):
                fn(db, unknown_id)
            persisted = db.query(Reminder).filter(Reminder.id == reminder.id).one()
            assert persisted.status == initial_status
    finally:
        db.close()


# ── Unit tests (happy path) ────────────────────────────────────────


def test_create_reminder_happy_path(db_session):
    user = User(name="Alice", email="alice@example.com")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    remind_at = now_utc() + timedelta(hours=2)
    reminder = create_reminder(
        db_session,
        user_id=user.id,
        title="Bayar kos",
        remind_at=remind_at,
        channel="whatsapp",
    )

    assert reminder.id is not None
    assert reminder.user_id == user.id
    assert reminder.title == "Bayar kos"
    assert reminder.channel == "whatsapp"
    assert reminder.status == ReminderStatus.SCHEDULED
    assert _as_utc(reminder.remind_at) == remind_at


def test_mark_reminder_sent_then_list_due_excludes_it(db_session):
    user = User(name="Bob", email="bob@example.com")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    past_due = now_utc() - timedelta(minutes=5)
    reminder = Reminder(
        user_id=user.id,
        title="Already due",
        remind_at=past_due,
        channel="both",
        status=ReminderStatus.SCHEDULED,
    )
    db_session.add(reminder)
    db_session.commit()
    db_session.refresh(reminder)

    # Initially the reminder shows up in ``list_due_reminders``.
    due_before = list_due_reminders(db_session)
    assert reminder.id in {r.id for r in due_before}

    # Marking it sent excludes it.
    updated = mark_reminder_sent(db_session, reminder.id)
    assert updated.status == ReminderStatus.SENT

    due_after = list_due_reminders(db_session)
    assert reminder.id not in {r.id for r in due_after}
