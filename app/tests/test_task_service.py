"""Tests for ``app.services.task_service``.

Covers Properties T1–T5 from
``.kiro/specs/service-layer/design.md`` (Correctness Properties → Task
Service) plus a handful of human-readable happy-path unit tests.

Each Hypothesis test builds its own in-memory SQLite engine via the
``_make_session`` helper because Hypothesis runs many examples per test
function and we want every example to start from a clean schema. The
``db_session`` fixture from ``conftest.py`` is still used for the unit
tests, where one DB per test function is enough.
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
from app.models.constants import ReminderStatus, TaskStatus
from app.models.reminder import Reminder
from app.models.task import Task
from app.models.user import User
from app.services import task_service
from app.services.exceptions import (
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)


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


def _normalize(dt):
    """Coerce a (possibly naive) datetime read back from SQLite into UTC.

    SQLite stores timestamps as ISO strings and SQLAlchemy returns them
    as naive datetimes even when the column is declared with
    ``timezone=True``. To compare an input datetime with a value read
    back from the DB we normalise both to aware UTC.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ── Hypothesis strategies ───────────────────────────────────────────

# Bounds are computed once at module load. By the time tests run (a few
# seconds later) the future bound is still firmly in the future and the
# past bound is still firmly in the past, so reminder_at validation is
# deterministic. We keep these as naive datetimes because Hypothesis'
# ``min_value`` / ``max_value`` for ``st.datetimes`` must be naive.
_NOW_NAIVE = datetime.now(timezone.utc).replace(tzinfo=None)

aware_future_dt = st.datetimes(
    min_value=_NOW_NAIVE + timedelta(hours=1),
    max_value=_NOW_NAIVE + timedelta(days=30),
    timezones=st.just(timezone.utc),
)

aware_past_dt = st.datetimes(
    min_value=_NOW_NAIVE - timedelta(days=30),
    max_value=_NOW_NAIVE - timedelta(hours=1),
    timezones=st.just(timezone.utc),
)

# ``st.datetimes()`` without a ``timezones`` argument always yields naive
# datetimes — exactly what we want for negative validation cases.
naive_dt = st.datetimes(
    min_value=_NOW_NAIVE - timedelta(days=30),
    max_value=_NOW_NAIVE + timedelta(days=30),
)

non_blank_str = st.text(min_size=1, max_size=50).filter(lambda s: s.strip() != "")
blank_str = st.sampled_from(["", " ", "\t", "\n", "   "])

optional_aware_future_dt = st.one_of(st.none(), aware_future_dt)
optional_short_text = st.one_of(st.none(), st.text(min_size=1, max_size=20))


# ── Property T1: create_task valid invariants ───────────────────────

# Feature: service-layer, Property T1: create_task valid invariants
@settings(max_examples=100, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    title=non_blank_str,
    course=optional_short_text,
    deadline_at=st.one_of(st.none(), aware_future_dt),
    reminder_at=optional_aware_future_dt,
    priority=optional_short_text,
)
def test_create_task_valid_invariants(title, course, deadline_at, reminder_at, priority):
    """Validates: Requirements 1.1, 1.2

    Valid input → exactly one Task row created with matching fields and
    status PENDING. When ``reminder_at`` is non-None, exactly one linked
    Reminder row is also created.
    """
    db, engine = _make_session()
    try:
        user = _make_user(db, name="alice")

        before_tasks = db.query(Task).count()
        before_reminders = db.query(Reminder).count()

        task = task_service.create_task(
            db,
            user_id=user.id,
            title=title,
            course=course,
            deadline_at=deadline_at,
            reminder_at=reminder_at,
            priority=priority,
        )

        # exactly one Task created
        assert db.query(Task).count() == before_tasks + 1
        assert task.id is not None
        assert task.user_id == user.id
        assert task.title == title
        assert task.course == course
        assert task.priority == priority
        assert task.status == TaskStatus.PENDING
        assert _normalize(task.deadline_at) == _normalize(deadline_at)
        assert _normalize(task.reminder_at) == _normalize(reminder_at)

        if reminder_at is None:
            assert db.query(Reminder).count() == before_reminders
        else:
            assert db.query(Reminder).count() == before_reminders + 1
            reminder = (
                db.query(Reminder).filter(Reminder.task_id == task.id).one()
            )
            assert reminder.user_id == user.id
            assert reminder.task_id == task.id
            assert reminder.status == ReminderStatus.SCHEDULED
            assert _normalize(reminder.remind_at) == _normalize(reminder_at)
    finally:
        db.close()
        engine.dispose()


# ── Property T2: create_task ValidationError on invalid input ───────

# Feature: service-layer, Property T2: create_task ValidationError on invalid input
@settings(max_examples=100, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    title=st.one_of(non_blank_str, blank_str),
    deadline_at=st.one_of(st.none(), aware_future_dt, naive_dt),
    reminder_at=st.one_of(st.none(), aware_future_dt, aware_past_dt, naive_dt),
)
def test_create_task_validation_error(title, deadline_at, reminder_at):
    """Validates: Requirements 1.3, 1.5, 1.6

    Any input with at least one of (blank title, naive deadline, naive
    reminder, past reminder) → ValidationError, no row changes.
    """
    title_blank = not (isinstance(title, str) and title.strip())
    deadline_naive = deadline_at is not None and deadline_at.tzinfo is None
    reminder_naive = reminder_at is not None and reminder_at.tzinfo is None
    reminder_past = (
        reminder_at is not None
        and reminder_at.tzinfo is not None
        and reminder_at < datetime.now(timezone.utc)
    )
    assume(title_blank or deadline_naive or reminder_naive or reminder_past)

    db, engine = _make_session()
    try:
        user = _make_user(db, name="bob")

        before_tasks = db.query(Task).count()
        before_reminders = db.query(Reminder).count()

        with pytest.raises(ValidationError):
            task_service.create_task(
                db,
                user_id=user.id,
                title=title,
                deadline_at=deadline_at,
                reminder_at=reminder_at,
            )

        assert db.query(Task).count() == before_tasks
        assert db.query(Reminder).count() == before_reminders
    finally:
        db.close()
        engine.dispose()


# ── Property T3: create_task NotFoundError on unknown user ──────────

# Feature: service-layer, Property T3: create_task NotFoundError on unknown user
@settings(max_examples=100, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    user_id=st.text(min_size=1, max_size=40).filter(lambda s: s.strip() != ""),
    title=non_blank_str,
    reminder_at=optional_aware_future_dt,
)
def test_create_task_unknown_user(user_id, title, reminder_at):
    """Validates: Requirement 1.4

    Any user_id that does not match an existing User → NotFoundError.
    Row counts (Task and Reminder) unchanged.
    """
    db, engine = _make_session()
    try:
        # Sanity check: the generated user_id should not exist (we never
        # insert any User in this test, so this always holds).
        assume(db.query(User).filter(User.id == user_id).one_or_none() is None)

        before_tasks = db.query(Task).count()
        before_reminders = db.query(Reminder).count()

        with pytest.raises(NotFoundError):
            task_service.create_task(
                db,
                user_id=user_id,
                title=title,
                reminder_at=reminder_at,
            )

        assert db.query(Task).count() == before_tasks
        assert db.query(Reminder).count() == before_reminders
    finally:
        db.close()
        engine.dispose()


# ── Property T4: list_tasks user isolation + status filter ──────────

# Feature: service-layer, Property T4: list_tasks user isolation + status filter
@settings(max_examples=100, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    seed=st.lists(
        st.tuples(
            st.integers(min_value=0, max_value=2),  # user index 0..2
            st.sampled_from([TaskStatus.PENDING, TaskStatus.DONE]),
            non_blank_str,
        ),
        min_size=0,
        max_size=10,
    ),
    target_user_idx=st.integers(min_value=0, max_value=2),
    status_filter=st.one_of(
        st.none(),
        st.sampled_from([TaskStatus.PENDING, TaskStatus.DONE]),
    ),
)
def test_list_tasks_user_isolation_and_status_filter(
    seed, target_user_idx, status_filter
):
    """Validates: Requirements 1.7, 1.8

    list_tasks(db, u) returns exactly tasks with user_id=u. With an
    additional status filter, also restricts by that status.
    """
    db, engine = _make_session()
    try:
        users = [_make_user(db, name=f"u{i}") for i in range(3)]

        for user_idx, status, title in seed:
            db.add(
                Task(
                    user_id=users[user_idx].id,
                    title=title,
                    status=status,
                )
            )
        db.commit()

        target_user = users[target_user_idx]
        result = task_service.list_tasks(db, target_user.id, status=status_filter)

        # Every returned row belongs to the target user (and matches
        # status when supplied).
        for t in result:
            assert t.user_id == target_user.id
            if status_filter is not None:
                assert t.status == status_filter

        # And the set of ids returned equals the set we expect from a
        # direct query.
        expected_query = db.query(Task).filter(Task.user_id == target_user.id)
        if status_filter is not None:
            expected_query = expected_query.filter(Task.status == status_filter)
        expected_ids = {t.id for t in expected_query.all()}
        actual_ids = {t.id for t in result}
        assert actual_ids == expected_ids
    finally:
        db.close()
        engine.dispose()


# ── Property T5: mark_task_done transitions per authorization ───────

# Feature: service-layer, Property T5: mark_task_done transitions per authorization
@settings(max_examples=100, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    scenario=st.sampled_from(["unknown", "other_user", "owner"]),
    title=non_blank_str,
    initial_status=st.sampled_from([TaskStatus.PENDING, TaskStatus.DONE]),
)
def test_mark_task_done_authorization(scenario, title, initial_status):
    """Validates: Requirements 1.9, 1.10, 1.11

    - Unknown task_id → NotFoundError, no state change.
    - Task belonging to another user → PermissionDeniedError, no state change.
    - Owner → status set to DONE.
    """
    db, engine = _make_session()
    try:
        owner = _make_user(db, name="owner")
        other = _make_user(db, name="other")

        task = Task(user_id=owner.id, title=title, status=initial_status)
        db.add(task)
        db.commit()
        db.refresh(task)

        if scenario == "unknown":
            unknown_id = "missing-" + uuid.uuid4().hex
            with pytest.raises(NotFoundError):
                task_service.mark_task_done(db, owner.id, unknown_id)
            db.refresh(task)
            assert task.status == initial_status
        elif scenario == "other_user":
            with pytest.raises(PermissionDeniedError):
                task_service.mark_task_done(db, other.id, task.id)
            db.refresh(task)
            assert task.status == initial_status
        else:  # owner
            result = task_service.mark_task_done(db, owner.id, task.id)
            assert result.id == task.id
            assert result.status == TaskStatus.DONE
            db.refresh(task)
            assert task.status == TaskStatus.DONE
    finally:
        db.close()
        engine.dispose()


# ── Unit tests (happy path) ─────────────────────────────────────────


def test_create_task_basic_happy_path(db_session):
    """A typical task with a deadline and a future reminder is persisted
    along with a linked SCHEDULED reminder."""
    user = User(name="Alice", email=f"alice-{uuid.uuid4().hex}@example.com")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    deadline = datetime.now(timezone.utc) + timedelta(days=2)
    reminder = datetime.now(timezone.utc) + timedelta(days=1)

    task = task_service.create_task(
        db_session,
        user_id=user.id,
        title="Tugas Jaringan",
        course="Jaringan Komputer",
        deadline_at=deadline,
        reminder_at=reminder,
        priority="high",
    )

    assert task.id is not None
    assert task.user_id == user.id
    assert task.title == "Tugas Jaringan"
    assert task.course == "Jaringan Komputer"
    assert task.priority == "high"
    assert task.status == TaskStatus.PENDING

    reminders = (
        db_session.query(Reminder).filter(Reminder.task_id == task.id).all()
    )
    assert len(reminders) == 1
    assert reminders[0].user_id == user.id
    assert reminders[0].status == ReminderStatus.SCHEDULED


def test_mark_task_done_basic(db_session):
    """Marking an owned task as done flips its status to DONE."""
    user = User(name="Bob", email=f"bob-{uuid.uuid4().hex}@example.com")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    task = Task(user_id=user.id, title="Belajar", status=TaskStatus.PENDING)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    result = task_service.mark_task_done(db_session, user.id, task.id)

    assert result.id == task.id
    assert result.status == TaskStatus.DONE


# ── update_task / delete_task unit tests ────────────────────────────


def _make_task_for(db_session, user, **overrides) -> Task:
    """Insert a minimal ``Task`` for ``user`` and return it."""
    fields = {
        "user_id": user.id,
        "title": "Original",
        "status": TaskStatus.PENDING,
    }
    fields.update(overrides)
    task = Task(**fields)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


def test_update_task_patch_single_field(db_session):
    """Updating a single field leaves all other fields untouched."""
    user = _make_user(db_session, name="upd-single")
    task = _make_task_for(
        db_session,
        user,
        title="Awal",
        course="Mat",
        priority="low",
    )

    result = task_service.update_task(db_session, task.id, status=TaskStatus.DONE)

    assert result.id == task.id
    assert result.status == TaskStatus.DONE
    # Untouched fields
    assert result.title == "Awal"
    assert result.course == "Mat"
    assert result.priority == "low"

    db_session.refresh(task)
    assert task.status == TaskStatus.DONE
    assert task.title == "Awal"


def test_update_task_patch_multiple_fields(db_session):
    """Multiple non-None fields are applied; None-valued kwargs are skipped."""
    user = _make_user(db_session, name="upd-multi")
    task = _make_task_for(
        db_session,
        user,
        title="Lama",
        course="Algo",
        priority="low",
    )
    new_deadline = datetime.now(timezone.utc) + timedelta(days=3)
    new_reminder = datetime.now(timezone.utc) + timedelta(days=1)

    result = task_service.update_task(
        db_session,
        task.id,
        title="Baru",
        course=None,  # None must be ignored, not nullify the field
        deadline_at=new_deadline,
        reminder_at=new_reminder,
        priority="high",
    )

    assert result.title == "Baru"
    assert result.course == "Algo"  # untouched because patch was None
    assert result.priority == "high"
    assert _normalize(result.deadline_at) == _normalize(new_deadline)
    assert _normalize(result.reminder_at) == _normalize(new_reminder)


def test_update_task_ignores_user_id_change(db_session):
    """``user_id`` is not in the updatable allow-list and must be ignored."""
    owner = _make_user(db_session, name="owner-upd")
    other = _make_user(db_session, name="other-upd")
    task = _make_task_for(db_session, owner, title="Tidak pindah")

    result = task_service.update_task(
        db_session,
        task.id,
        user_id=other.id,
        title="Tetap milik owner",
    )

    assert result.user_id == owner.id
    assert result.title == "Tetap milik owner"


def test_update_task_blank_title_raises_validation_error(db_session):
    """Supplying a blank/whitespace title must raise ValidationError without mutating the row."""
    user = _make_user(db_session, name="upd-blank")
    task = _make_task_for(db_session, user, title="Tetap")

    with pytest.raises(ValidationError):
        task_service.update_task(db_session, task.id, title="   ")

    db_session.refresh(task)
    assert task.title == "Tetap"


def test_update_task_naive_deadline_raises_validation_error(db_session):
    """Naive datetime in patch must raise ValidationError without mutating the row."""
    user = _make_user(db_session, name="upd-naive")
    task = _make_task_for(db_session, user, title="Asli")

    # A naive datetime (no tzinfo) — taken from a UTC point but stripped.
    naive = (datetime.now(timezone.utc) + timedelta(days=2)).replace(tzinfo=None)

    with pytest.raises(ValidationError):
        task_service.update_task(db_session, task.id, deadline_at=naive)

    db_session.refresh(task)
    assert task.title == "Asli"
    assert task.deadline_at is None


def test_update_task_past_reminder_raises_validation_error(db_session):
    """Reminder in the past must raise ValidationError."""
    user = _make_user(db_session, name="upd-past")
    task = _make_task_for(db_session, user, title="Asli")

    past = datetime.now(timezone.utc) - timedelta(hours=1)

    with pytest.raises(ValidationError):
        task_service.update_task(db_session, task.id, reminder_at=past)


def test_update_task_unknown_id_raises_not_found(db_session):
    """Unknown ``task_id`` raises NotFoundError, no Task row is created or modified."""
    before = db_session.query(Task).count()

    with pytest.raises(NotFoundError):
        task_service.update_task(
            db_session,
            "missing-" + uuid.uuid4().hex,
            title="apa pun",
        )

    assert db_session.query(Task).count() == before


def test_delete_task_removes_row(db_session):
    """Deleting an existing task removes the row from the table."""
    user = _make_user(db_session, name="del-ok")
    task = _make_task_for(db_session, user, title="Hapus aku")
    task_id = task.id

    result = task_service.delete_task(db_session, task_id)

    assert result is None
    assert (
        db_session.query(Task).filter(Task.id == task_id).one_or_none()
        is None
    )


def test_delete_task_unknown_id_raises_not_found(db_session):
    """Deleting an unknown id raises NotFoundError and removes no rows."""
    user = _make_user(db_session, name="del-missing")
    other_task = _make_task_for(db_session, user, title="Tetap")
    before = db_session.query(Task).count()

    with pytest.raises(NotFoundError):
        task_service.delete_task(db_session, "missing-" + uuid.uuid4().hex)

    assert db_session.query(Task).count() == before
    # The unrelated task is still there.
    assert (
        db_session.query(Task).filter(Task.id == other_task.id).one_or_none()
        is not None
    )
