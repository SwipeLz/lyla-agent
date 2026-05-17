"""Property-based tests for ``app.utils`` helpers.

Covers Properties U1 and U2 from the service-layer design document.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from hypothesis import given, settings, strategies as st
from sqlalchemy import inspect

from app.models.constants import TaskStatus
from app.models.expense import Expense
from app.models.task import Task
from app.models.user import User
from app.utils.serialization import model_to_dict
from app.utils.timezone import JAKARTA, jakarta_today_window_utc


# ── Strategy helpers ──────────────────────────────────────────────

# Aware datetimes restricted to a sane range so ``isoformat``/``fromisoformat``
# round-trips never run into year-out-of-range issues.
_aware_utc = st.datetimes(
    min_value=datetime(2000, 1, 1),
    max_value=datetime(2100, 1, 1),
    timezones=st.just(timezone.utc),
)


# ── Property U1: model_to_dict serialisasi konsisten ───────────────

def _assert_model_to_dict_consistent(instance) -> None:
    """Shared invariants for Property U1 across model classes."""
    result = model_to_dict(instance)

    # Result is a dict whose keys are exactly the mapped column names.
    expected_keys = {column.key for column in inspect(type(instance)).mapper.columns}
    assert isinstance(result, dict)
    assert set(result.keys()) == expected_keys

    for key, serialised in result.items():
        original = getattr(instance, key)
        if isinstance(original, datetime):
            # Datetime values are ISO 8601 strings round-trippable to the
            # same instant.
            assert isinstance(serialised, str)
            parsed = datetime.fromisoformat(serialised)
            assert parsed == original
        else:
            # Non-datetime values are returned verbatim.
            assert serialised == original


# Feature: service-layer, Property U1: model_to_dict serialisasi konsisten
# Validates: Requirements 7.2, 7.3
@settings(max_examples=100, deadline=None)
@given(
    name=st.text(min_size=1, max_size=50),
    email_local=st.text(
        alphabet=st.characters(min_codepoint=97, max_codepoint=122),
        min_size=1,
        max_size=20,
    ),
    whatsapp=st.one_of(st.none(), st.text(min_size=1, max_size=20)),
    has_dt=st.booleans(),
    dt=_aware_utc,
)
def test_property_u1_model_to_dict_user(name, email_local, whatsapp, has_dt, dt):
    user = User(
        id=str(uuid4()),
        name=name,
        email=f"{email_local}@example.com",
        whatsapp_number=whatsapp,
        created_at=dt if has_dt else None,
    )
    _assert_model_to_dict_consistent(user)


# Feature: service-layer, Property U1: model_to_dict serialisasi konsisten
# Validates: Requirements 7.2, 7.3
@settings(max_examples=100, deadline=None)
@given(
    title=st.text(min_size=1, max_size=80),
    course=st.one_of(st.none(), st.text(min_size=1, max_size=40)),
    priority=st.one_of(st.none(), st.sampled_from(["low", "medium", "high"])),
    status=st.sampled_from([TaskStatus.PENDING, TaskStatus.DONE, TaskStatus.CANCELLED]),
    has_deadline=st.booleans(),
    deadline_at=_aware_utc,
    has_reminder=st.booleans(),
    reminder_at=_aware_utc,
    has_created=st.booleans(),
    created_at=_aware_utc,
)
def test_property_u1_model_to_dict_task(
    title,
    course,
    priority,
    status,
    has_deadline,
    deadline_at,
    has_reminder,
    reminder_at,
    has_created,
    created_at,
):
    task = Task(
        id=str(uuid4()),
        user_id=str(uuid4()),
        title=title,
        course=course,
        deadline_at=deadline_at if has_deadline else None,
        reminder_at=reminder_at if has_reminder else None,
        status=status,
        priority=priority,
        created_at=created_at if has_created else None,
    )
    _assert_model_to_dict_consistent(task)


# Feature: service-layer, Property U1: model_to_dict serialisasi konsisten
# Validates: Requirements 7.2, 7.3
@settings(max_examples=100, deadline=None)
@given(
    amount=st.integers(min_value=1, max_value=10**9),
    category=st.one_of(st.none(), st.text(min_size=1, max_size=30)),
    note=st.one_of(st.none(), st.text(max_size=80)),
    has_spent=st.booleans(),
    spent_at=_aware_utc,
    has_created=st.booleans(),
    created_at=_aware_utc,
)
def test_property_u1_model_to_dict_expense(
    amount, category, note, has_spent, spent_at, has_created, created_at
):
    expense = Expense(
        id=str(uuid4()),
        user_id=str(uuid4()),
        amount=amount,
        category=category,
        note=note,
        spent_at=spent_at if has_spent else None,
        created_at=created_at if has_created else None,
    )
    _assert_model_to_dict_consistent(expense)


def test_property_u1_model_to_dict_none_returns_none():
    # Feature: service-layer, Property U1: model_to_dict serialisasi konsisten
    # Validates: Requirements 7.3
    assert model_to_dict(None) is None


# ── Property U2: jakarta_today_window_utc invariants ───────────────

# Feature: service-layer, Property U2: jakarta_today_window_utc invariants
# Validates: Requirements 8.2
@settings(max_examples=100, deadline=None)
@given(
    now=st.datetimes(
        min_value=datetime(2000, 1, 1),
        max_value=datetime(2100, 1, 1),
        timezones=st.timezones(),
    )
)
def test_property_u2_jakarta_today_window_invariants(now):
    start, end = jakarta_today_window_utc(now)

    # Both bounds are timezone-aware UTC.
    assert start.tzinfo is not None
    assert start.utcoffset() == timedelta(0)
    assert end.tzinfo is not None
    assert end.utcoffset() == timedelta(0)

    # The window spans exactly 24 hours.
    assert end - start == timedelta(hours=24)

    # ``start`` corresponds to midnight in Asia/Jakarta.
    start_jkt = start.astimezone(JAKARTA)
    assert start_jkt.hour == 0
    assert start_jkt.minute == 0
    assert start_jkt.second == 0
    assert start_jkt.microsecond == 0

    # ``now`` falls inside the window of its own Jakarta calendar day.
    assert start <= now < end
