"""Tests for ``app.services.log_service``.

Property-based tests (L1–L3) drive the validation, NotFound, and
roundtrip invariants of ``create_voice_command_log``. Each Hypothesis
example uses its own fresh in-memory SQLite database via
``_make_session()`` so state never leaks between examples. A small
happy-path unit test at the bottom covers Task 6.5.
"""
from __future__ import annotations

import json
from uuid import uuid4

import pytest
from hypothesis import HealthCheck, assume, given, settings, strategies as st
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
import app.models  # noqa: F401  registers tables on Base.metadata
from app.models import Device, User, VoiceCommandLog
from app.models.constants import DeviceStatus
from app.services.exceptions import NotFoundError, ValidationError
from app.services.log_service import create_voice_command_log


# ── Test infrastructure ────────────────────────────────────────────


def _make_session() -> tuple[Session, object]:
    """Build a fresh in-memory SQLite engine + session for one example."""
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
    return SessionLocal(), engine


def _make_user(db: Session, suffix: str | None = None) -> User:
    sfx = suffix or uuid4().hex
    user = User(name=f"User {sfx}", email=f"user-{sfx}@taskbot.local")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_device(db: Session, user: User) -> Device:
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


# ── Generators ─────────────────────────────────────────────────────

non_blank_str = st.text(min_size=1, max_size=80).filter(lambda s: s.strip() != "")
blank_str = st.one_of(
    st.just(""),
    st.integers(min_value=1, max_value=10).map(lambda n: " " * n),
    st.integers(min_value=1, max_value=5).map(lambda n: "\t" * n),
    st.just("   \t  \n "),
)

# JSON-serializable values: recursively built from JSON-friendly atoms.
# Floats are constrained with ``allow_subnormal=False`` because subnormal
# IEEE-754 values can drift by 1 ULP across SQLite's TEXT-based JSON
# round-trip (e.g. ``8.427515233054102e-228`` becomes
# ``8.427515233054103e-228``). They are also bounded to ±1e15 because
# very large doubles (>~1e16) lose mantissa precision through Python's
# json.dumps→json.loads cycle even outside subnormal range. LLM tool
# args don't realistically produce such magnitudes.
# Integers are bounded to ±(2**53-1) to avoid JSON precision loss when
# SQLite stores them as TEXT and Python's json.dumps converts large ints
# to scientific notation (floats).
json_serializable = st.recursive(
    st.one_of(
        st.none(),
        st.booleans(),
        st.integers(min_value=-(2**53 - 1), max_value=2**53 - 1),
        st.floats(
            min_value=-1e15,
            max_value=1e15,
            allow_nan=False,
            allow_infinity=False,
            allow_subnormal=False,
        ),
        st.text(max_size=20),
    ),
    lambda children: st.one_of(
        st.lists(children, max_size=4),
        st.dictionaries(st.text(min_size=1, max_size=8), children, max_size=4),
    ),
    max_leaves=10,
)


class _NotJsonSerializable:
    """Plain object with no JSON encoder support."""


# Sampled non-JSON-serializable values. ``st.sampled_from`` requires the
# values up front, so we build a fresh instance per call via ``builds``.
non_json_serializable = st.one_of(
    st.builds(set, st.lists(st.integers(), min_size=1, max_size=3)),
    st.builds(_NotJsonSerializable),
    st.binary(min_size=1, max_size=4),
)


# ── Property L1: valid inputs + parsed_actions roundtrip ───────────
# Feature: service-layer, Property L1: create_voice_command_log valid + roundtrip parsed_actions
# Validates: Requirements 5.1, 5.6
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    input_text=non_blank_str,
    parsed_actions=json_serializable,
    attach_user=st.booleans(),
    attach_device=st.booleans(),
    response_text=st.one_of(st.none(), st.text(max_size=40)),
    status=st.sampled_from(["success", "error", "partial"]),
)
def test_property_l1_create_voice_command_log_valid_and_roundtrip(
    input_text, parsed_actions, attach_user, attach_device, response_text, status
):
    db, engine = _make_session()
    try:
        user = _make_user(db) if attach_user else None
        device = _make_device(db, user or _make_user(db, suffix="for-device")) \
            if attach_device else None

        before = db.query(VoiceCommandLog).count()
        log = create_voice_command_log(
            db,
            user_id=user.id if user else None,
            device_id=device.id if device else None,
            input_text=input_text,
            parsed_actions=parsed_actions,
            response_text=response_text,
            status=status,
        )
        after = db.query(VoiceCommandLog).count()

        # Exactly one new row was inserted.
        assert after == before + 1
        assert log.id is not None
        assert log.input_text == input_text
        assert log.user_id == (user.id if user else None)
        assert log.device_id == (device.id if device else None)
        assert log.response_text == response_text
        assert log.status == status

        # JSON-equivalence roundtrip on parsed_actions: the value read back
        # from the DB serialises to the same JSON as the input.
        persisted = (
            db.query(VoiceCommandLog).filter(VoiceCommandLog.id == log.id).one()
        )
        assert json.loads(json.dumps(persisted.parsed_actions)) == json.loads(
            json.dumps(parsed_actions)
        )
    finally:
        db.close()
        engine.dispose()


# ── Property L2: invalid input raises ValidationError ──────────────
# Feature: service-layer, Property L2: create_voice_command_log ValidationError pada input invalid
# Validates: Requirements 5.2, 5.5
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    failure_mode=st.sampled_from(["blank_input", "non_json_parsed_actions"]),
    input_text_valid=non_blank_str,
    input_text_blank=blank_str,
    parsed_actions_valid=json_serializable,
    parsed_actions_invalid=non_json_serializable,
)
def test_property_l2_create_voice_command_log_validation_error(
    failure_mode,
    input_text_valid,
    input_text_blank,
    parsed_actions_valid,
    parsed_actions_invalid,
):
    db, engine = _make_session()
    try:
        before = db.query(VoiceCommandLog).count()

        if failure_mode == "blank_input":
            with pytest.raises(ValidationError):
                create_voice_command_log(
                    db,
                    user_id=None,
                    device_id=None,
                    input_text=input_text_blank,
                    parsed_actions=parsed_actions_valid,
                )
        else:  # non_json_parsed_actions
            with pytest.raises(ValidationError):
                create_voice_command_log(
                    db,
                    user_id=None,
                    device_id=None,
                    input_text=input_text_valid,
                    parsed_actions=parsed_actions_invalid,
                )

        after = db.query(VoiceCommandLog).count()
        assert after == before
    finally:
        db.close()
        engine.dispose()


# ── Property L3: unknown user/device raises NotFoundError ──────────
# Feature: service-layer, Property L3: create_voice_command_log NotFoundError pada referensi tidak dikenal
# Validates: Requirements 5.3, 5.4
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    branch=st.sampled_from(["unknown_user", "unknown_device"]),
    unknown_id=st.text(min_size=1, max_size=36),
    input_text=non_blank_str,
    parsed_actions=json_serializable,
)
def test_property_l3_create_voice_command_log_not_found(
    branch, unknown_id, input_text, parsed_actions
):
    db, engine = _make_session()
    try:
        # Seed a real user (and device under it) so the unused branch
        # passes its own existence check.
        seeded_user = _make_user(db)
        seeded_device = _make_device(db, seeded_user)

        # Avoid colliding with the seeded ids.
        assume(unknown_id != seeded_user.id)
        assume(unknown_id != seeded_device.id)

        before = db.query(VoiceCommandLog).count()

        if branch == "unknown_user":
            with pytest.raises(NotFoundError):
                create_voice_command_log(
                    db,
                    user_id=unknown_id,
                    device_id=None,
                    input_text=input_text,
                    parsed_actions=parsed_actions,
                )
        else:
            with pytest.raises(NotFoundError):
                create_voice_command_log(
                    db,
                    user_id=None,
                    device_id=unknown_id,
                    input_text=input_text,
                    parsed_actions=parsed_actions,
                )

        after = db.query(VoiceCommandLog).count()
        assert after == before
    finally:
        db.close()
        engine.dispose()


# ── Unit test (Task 6.5): happy-path with both user_id and device_id ─


def test_unit_create_voice_command_log_with_user_and_device(db_session):
    """Persist a log linked to both an existing user and device."""
    user = User(name="Demo Logger", email="logger@taskbot.local")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    device = Device(
        user_id=user.id,
        device_code="UNIT-LOG-001",
        name="Logger bench",
        status=DeviceStatus.OFFLINE,
    )
    db_session.add(device)
    db_session.commit()
    db_session.refresh(device)

    parsed = {"intent": "create_task", "title": "Belajar Hypothesis"}
    log = create_voice_command_log(
        db_session,
        user_id=user.id,
        device_id=device.id,
        input_text="Catat tugas: belajar Hypothesis",
        parsed_actions=parsed,
        response_text="Tugas berhasil dicatat.",
        status="success",
    )

    assert log.id is not None
    assert log.user_id == user.id
    assert log.device_id == device.id
    assert log.input_text == "Catat tugas: belajar Hypothesis"
    assert log.parsed_actions == parsed
    assert log.response_text == "Tugas berhasil dicatat."
    assert log.status == "success"

    persisted = (
        db_session.query(VoiceCommandLog)
        .filter(VoiceCommandLog.id == log.id)
        .one()
    )
    assert persisted.parsed_actions == parsed
    assert persisted.user_id == user.id
    assert persisted.device_id == device.id
