"""Tests for ``app.services.expense_service``.

Covers Properties E1–E5 from
``.kiro/specs/service-layer/design.md`` (Correctness Properties → Expense
Service) plus a couple of human-readable happy-path unit tests at the
end.

Each Hypothesis test builds its own in-memory SQLite engine via the
``_make_session`` helper so every example starts from a clean schema.
The ``db_session`` fixture from ``conftest.py`` is still used for the
unit tests, where one DB per test function is enough.

A note on SQLite + timezones: even though ``Expense.spent_at`` is
declared with ``DateTime(timezone=True)``, SQLite has no native
tz-aware storage and SQLAlchemy returns naive ``datetime`` instances on
read. We therefore normalise persisted values to aware UTC before
comparing against inputs ("same absolute instant"). All aware datetime
generators in this file produce UTC values, so naive→UTC normalisation
preserves the absolute instant.
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
from app.models.expense import Expense
from app.models.user import User
from app.services import expense_service
from app.services.exceptions import NotFoundError, ValidationError


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

# Aware UTC datetimes are built by offsetting "now" so their absolute
# instant is well-defined. ``spent_at`` may legitimately be in the past
# (an expense logged after the fact) or in the (near) future, so we
# allow both directions.
aware_dt_offset_seconds = st.integers(min_value=-30 * 24 * 3600,
                                      max_value=30 * 24 * 3600)


@st.composite
def aware_utc_dt(draw):
    """Generate a timezone-aware UTC datetime as ``now ± offset``."""
    offset = draw(aware_dt_offset_seconds)
    return datetime.now(timezone.utc) + timedelta(seconds=offset)


# Naive datetime strategy — ``st.datetimes()`` without ``timezones``
# always yields naive values, which is exactly what we need to trigger
# the validation error in E2.
naive_dt = st.datetimes(
    min_value=datetime(2020, 1, 1),
    max_value=datetime(2030, 1, 1),
)

positive_amount = st.integers(min_value=1, max_value=10**9)
non_positive_amount = st.integers(min_value=-10**6, max_value=0)

optional_short_text = st.one_of(st.none(), st.text(min_size=1, max_size=20))


# ── Property E1: create_expense valid invariants & default spent_at ─

# Feature: service-layer, Property E1: create_expense valid invariants & default spent_at
@settings(max_examples=100, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    amount=positive_amount,
    category=optional_short_text,
    note=optional_short_text,
    # Either default (None) or aware UTC datetime; both branches are
    # explicitly asserted below so we exercise each case.
    spent_at=st.one_of(st.none(), aware_utc_dt()),
)
def test_create_expense_valid_invariants(amount, category, note, spent_at):
    """Validates: Requirements 2.1, 2.5, 8.1, 8.3

    For valid input, ``create_expense`` adds exactly one ``Expense`` row
    with fields matching the arguments. When ``spent_at is None`` the
    persisted ``spent_at`` falls in ``[now_before, now_after]`` and is
    semantically UTC. When ``spent_at`` is aware, the persisted value
    represents the same absolute instant.
    """
    db, engine = _make_session()
    try:
        user = _make_user(db, name="alice")

        before = db.query(Expense).count()

        now_before = datetime.now(timezone.utc)
        expense = expense_service.create_expense(
            db,
            user_id=user.id,
            amount=amount,
            category=category,
            note=note,
            spent_at=spent_at,
        )
        now_after = datetime.now(timezone.utc)

        # exactly one new Expense row
        assert db.query(Expense).count() == before + 1
        assert expense.id is not None
        assert expense.user_id == user.id
        assert expense.amount == amount
        assert expense.category == category
        assert expense.note == note

        persisted = _normalize(expense.spent_at)
        # Every persisted value must be tz-aware UTC after normalisation
        # (SQLite returns naive datetimes; we treat them as UTC because
        # the service always writes UTC values).
        assert persisted.tzinfo == timezone.utc

        if spent_at is None:
            # default branch: spent_at ∈ [now_before, now_after]
            assert now_before <= persisted <= now_after
        else:
            # aware branch: persisted instant == input instant
            assert persisted == _normalize(spent_at)
    finally:
        db.close()
        engine.dispose()


# ── Property E2: create_expense ValidationError on invalid input ────

# Feature: service-layer, Property E2: create_expense ValidationError on invalid input
@settings(max_examples=100, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    # Amount may be a non-positive int OR a bool (bool is rejected
    # explicitly because ``isinstance(True, int) is True`` in Python).
    # We also include valid positive ints so that the only triggering
    # condition can be a naive ``spent_at``.
    amount=st.one_of(non_positive_amount, st.booleans(), positive_amount),
    spent_at=st.one_of(st.none(), aware_utc_dt(), naive_dt),
)
def test_create_expense_validation_error(amount, spent_at):
    """Validates: Requirements 2.2, 2.4

    Any input where ``amount <= 0`` (including ``bool``) OR ``spent_at``
    is naive must raise ``ValidationError`` and leave the row count
    unchanged.
    """
    amount_invalid = isinstance(amount, bool) or amount <= 0
    spent_at_invalid = spent_at is not None and spent_at.tzinfo is None
    assume(amount_invalid or spent_at_invalid)

    db, engine = _make_session()
    try:
        user = _make_user(db, name="bob")

        before = db.query(Expense).count()

        with pytest.raises(ValidationError):
            expense_service.create_expense(
                db,
                user_id=user.id,
                amount=amount,
                spent_at=spent_at,
            )

        assert db.query(Expense).count() == before
    finally:
        db.close()
        engine.dispose()


# ── Property E3: create_expense NotFoundError on unknown user ───────

# Feature: service-layer, Property E3: create_expense NotFoundError on unknown user
@settings(max_examples=100, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    user_id=st.text(min_size=1, max_size=40).filter(lambda s: s.strip() != ""),
    amount=positive_amount,
    spent_at=st.one_of(st.none(), aware_utc_dt()),
)
def test_create_expense_unknown_user(user_id, amount, spent_at):
    """Validates: Requirement 2.3

    Any ``user_id`` that does not match an existing ``User`` row →
    ``NotFoundError``. No ``Expense`` row is inserted.
    """
    db, engine = _make_session()
    try:
        # Sanity: we never insert any User in this test, so any
        # generated id is necessarily unknown.
        assume(db.query(User).filter(User.id == user_id).one_or_none() is None)

        before = db.query(Expense).count()

        with pytest.raises(NotFoundError):
            expense_service.create_expense(
                db,
                user_id=user_id,
                amount=amount,
                spent_at=spent_at,
            )

        assert db.query(Expense).count() == before
    finally:
        db.close()
        engine.dispose()


# ── Property E4: list_expenses window filter ────────────────────────

# Feature: service-layer, Property E4: list_expenses window filter
# Lower max_examples (50) because this property seeds the DB with up to
# ~10 rows per example, which is heavier than the other properties.
@settings(max_examples=50, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    # Each tuple = (user index 0..2, amount, spent_at offset in seconds)
    seed=st.lists(
        st.tuples(
            st.integers(min_value=0, max_value=2),
            positive_amount,
            aware_dt_offset_seconds,
        ),
        min_size=0,
        max_size=10,
    ),
    target_user_idx=st.integers(min_value=0, max_value=2),
    # The window may be unbounded on either side (or both).
    start_offset=st.one_of(st.none(), aware_dt_offset_seconds),
    end_offset=st.one_of(st.none(), aware_dt_offset_seconds),
)
def test_list_expenses_window_filter(seed, target_user_idx, start_offset, end_offset):
    """Validates: Requirement 2.6

    For a dataset with various users and ``spent_at`` values,
    ``list_expenses(db, u, start, end)`` returns exactly the rows with
    ``user_id == u`` and ``spent_at`` in ``[start, end]`` when the
    bounds are supplied. Without a window, all rows for ``u``.
    """
    db, engine = _make_session()
    try:
        users = [_make_user(db, name=f"u{i}") for i in range(3)]
        anchor = datetime.now(timezone.utc)

        for user_idx, amount, offset in seed:
            db.add(
                Expense(
                    user_id=users[user_idx].id,
                    amount=amount,
                    spent_at=anchor + timedelta(seconds=offset),
                )
            )
        db.commit()

        target_user = users[target_user_idx]
        start_at = (anchor + timedelta(seconds=start_offset)
                    if start_offset is not None else None)
        end_at = (anchor + timedelta(seconds=end_offset)
                  if end_offset is not None else None)

        result = expense_service.list_expenses(
            db, target_user.id, start_at=start_at, end_at=end_at,
        )

        # Compute the expected ID set directly from the persisted rows.
        all_target_rows = (
            db.query(Expense).filter(Expense.user_id == target_user.id).all()
        )
        expected_ids = set()
        for row in all_target_rows:
            ts = _normalize(row.spent_at)
            if start_at is not None and ts < start_at:
                continue
            if end_at is not None and ts > end_at:
                continue
            expected_ids.add(row.id)

        actual_ids = {r.id for r in result}
        assert actual_ids == expected_ids

        # Belt-and-braces: every returned row belongs to the target user
        # and respects the window when supplied.
        for r in result:
            assert r.user_id == target_user.id
            ts = _normalize(r.spent_at)
            if start_at is not None:
                assert ts >= start_at
            if end_at is not None:
                assert ts <= end_at
    finally:
        db.close()
        engine.dispose()


# ── Property E5: get_expense_summary consistent with list_expenses ──

# Feature: service-layer, Property E5: get_expense_summary consistent with list_expenses
# Lower max_examples (50) for the same DB-seeding reason as E4.
@settings(max_examples=50, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    seed=st.lists(
        st.tuples(
            st.integers(min_value=0, max_value=2),
            positive_amount,
            aware_dt_offset_seconds,
        ),
        min_size=0,
        max_size=10,
    ),
    target_user_idx=st.integers(min_value=0, max_value=2),
    start_offset=st.one_of(st.none(), aware_dt_offset_seconds),
    end_offset=st.one_of(st.none(), aware_dt_offset_seconds),
)
def test_get_expense_summary_consistent(seed, target_user_idx, start_offset, end_offset):
    """Validates: Requirements 2.7, 2.8

    ``get_expense_summary`` returns ``{"total": sum(amounts), "count":
    len(L)}`` where ``L = list_expenses(db, ...)`` for the same args.
    Empty result → ``{"total": 0, "count": 0}``.
    """
    db, engine = _make_session()
    try:
        users = [_make_user(db, name=f"u{i}") for i in range(3)]
        anchor = datetime.now(timezone.utc)

        for user_idx, amount, offset in seed:
            db.add(
                Expense(
                    user_id=users[user_idx].id,
                    amount=amount,
                    spent_at=anchor + timedelta(seconds=offset),
                )
            )
        db.commit()

        target_user = users[target_user_idx]
        start_at = (anchor + timedelta(seconds=start_offset)
                    if start_offset is not None else None)
        end_at = (anchor + timedelta(seconds=end_offset)
                  if end_offset is not None else None)

        listed = expense_service.list_expenses(
            db, target_user.id, start_at=start_at, end_at=end_at,
        )
        summary = expense_service.get_expense_summary(
            db, target_user.id, start_at=start_at, end_at=end_at,
        )

        expected_total = sum(e.amount for e in listed)
        expected_count = len(listed)
        assert summary == {"total": expected_total, "count": expected_count}

        # Empty-list case explicitly named by Requirement 2.8.
        if expected_count == 0:
            assert summary == {"total": 0, "count": 0}
    finally:
        db.close()
        engine.dispose()


# ── Unit tests (happy path) ─────────────────────────────────────────


def test_create_expense_basic_happy_path(db_session):
    """A typical expense with explicit ``spent_at`` is persisted with all
    fields preserved."""
    user = User(name="Alice", email=f"alice-{uuid.uuid4().hex}@example.com")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    spent_at = datetime.now(timezone.utc) - timedelta(hours=3)
    expense = expense_service.create_expense(
        db_session,
        user_id=user.id,
        amount=15_000,
        category="makanan",
        note="ayam geprek",
        spent_at=spent_at,
    )

    assert expense.id is not None
    assert expense.user_id == user.id
    assert expense.amount == 15_000
    assert expense.category == "makanan"
    assert expense.note == "ayam geprek"
    assert _normalize(expense.spent_at) == _normalize(spent_at)


def test_get_expense_summary_basic(db_session):
    """Summary aggregates total and count over the user's expenses."""
    user = User(name="Bob", email=f"bob-{uuid.uuid4().hex}@example.com")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    expense_service.create_expense(db_session, user_id=user.id, amount=10_000)
    expense_service.create_expense(db_session, user_id=user.id, amount=20_000)
    expense_service.create_expense(db_session, user_id=user.id, amount=5_000)

    summary = expense_service.get_expense_summary(db_session, user_id=user.id)
    assert summary == {"total": 35_000, "count": 3}

    # And an unknown-user id yields an empty summary, not an error
    # (``get_expense_summary`` does not validate the user — it simply
    # filters; consistent with ``list_expenses``).
    empty = expense_service.get_expense_summary(db_session, user_id="missing")
    assert empty == {"total": 0, "count": 0}
