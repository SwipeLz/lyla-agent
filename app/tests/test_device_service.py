"""Tests for ``app.services.device_service``.

This file holds both Hypothesis property tests (D1–D6) and a small
number of happy-path unit tests. Each Hypothesis example needs its own
isolated in-memory SQLite database, so we build a fresh session via
``_make_session()`` rather than relying on the per-test pytest fixture.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.db import Base
import app.models  # noqa: F401  (registers all tables on Base.metadata)
from app.models.constants import DeviceCommandStatus, DeviceStatus
from app.models.device import Device
from app.models.device_command import DeviceCommand
from app.models.user import User
from app.services import device_service
from app.services.exceptions import NotFoundError, ValidationError


# ── Test infrastructure ────────────────────────────────────────────


def _make_session():
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
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return Session(), engine


def _make_user(db, suffix: str | None = None) -> User:
    sfx = suffix or uuid4().hex
    user = User(name=f"User {sfx}", email=f"user-{sfx}@taskbot.local")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_device(db, user: User, device_code: str | None = None) -> Device:
    code = device_code or f"dev-{uuid4()}"
    device = Device(
        user_id=user.id,
        device_code=code,
        name=f"Device {code}",
        status=DeviceStatus.OFFLINE,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


# ── Generators ─────────────────────────────────────────────────────

non_blank_str = st.text(min_size=1, max_size=40).filter(lambda s: s.strip())
blank_str = st.one_of(
    st.just(""),
    st.integers(min_value=1, max_value=8).map(lambda n: " " * n),
    st.integers(min_value=1, max_value=4).map(lambda n: "\t" * n),
    st.just("   \t  \n "),
)
non_dict_payload = st.one_of(
    st.text(),
    st.integers(),
    st.lists(st.integers()),
    st.none(),
    st.booleans(),
)
invalid_status_str = st.text(min_size=1, max_size=20).filter(
    lambda s: s not in {"online", "offline"}
)


# ── Property D1: get_device_by_code roundtrip dan unknown ──────────
# Feature: service-layer, Property D1: get_device_by_code roundtrip dan unknown
# Validates: Requirements 4.1, 4.2
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    existing_code=st.text(
        alphabet=st.characters(min_codepoint=33, max_codepoint=126),
        min_size=1,
        max_size=30,
    ),
    lookup_existing=st.booleans(),
    unknown_code=st.text(min_size=1, max_size=30),
)
def test_property_d1_get_device_by_code_roundtrip_and_unknown(
    existing_code, lookup_existing, unknown_code
):
    db, engine = _make_session()
    try:
        user = _make_user(db)
        # Use a UUID-namespaced code so we never clash with the random
        # ``unknown_code`` Hypothesis generates.
        registered_code = f"dev-{uuid4()}-{existing_code}"
        device = _make_device(db, user, device_code=registered_code)

        if lookup_existing:
            result = device_service.get_device_by_code(db, registered_code)
            assert result.id == device.id
            assert result.device_code == registered_code
        else:
            # Ensure ``unknown_code`` does not accidentally coincide with
            # the registered code we just inserted.
            if unknown_code == registered_code:
                unknown_code = unknown_code + "-x"
            with pytest.raises(NotFoundError):
                device_service.get_device_by_code(db, unknown_code)
    finally:
        db.close()
        engine.dispose()


# ── Property D2: queue_device_command valid invariants ─────────────
# Feature: service-layer, Property D2: queue_device_command valid invariants
# Validates: Requirement 4.3
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    command_type=non_blank_str,
    payload=st.dictionaries(
        keys=st.text(min_size=1, max_size=10),
        values=st.one_of(
            st.text(max_size=20),
            st.integers(),
            st.booleans(),
            st.none(),
        ),
        max_size=5,
    ),
)
def test_property_d2_queue_device_command_valid_invariants(command_type, payload):
    db, engine = _make_session()
    try:
        user = _make_user(db)
        device = _make_device(db, user)

        before = db.query(DeviceCommand).count()
        cmd = device_service.queue_device_command(
            db, device.id, command_type, payload
        )
        after = db.query(DeviceCommand).count()

        assert after == before + 1
        assert cmd.id is not None
        assert cmd.device_id == device.id
        assert cmd.command_type == command_type
        assert cmd.payload == payload
        assert cmd.status == DeviceCommandStatus.PENDING

        # Round-trip via DB to confirm persistence, not just in-memory state.
        persisted = (
            db.query(DeviceCommand).filter(DeviceCommand.id == cmd.id).one()
        )
        assert persisted.command_type == command_type
        assert persisted.payload == payload
        assert persisted.status == DeviceCommandStatus.PENDING
    finally:
        db.close()
        engine.dispose()


# ── Property D3: queue_device_command validasi argumen ─────────────
# Feature: service-layer, Property D3: queue_device_command validasi argumen
# Validates: Requirements 4.4, 4.5, 4.6
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    failure_mode=st.sampled_from(
        ["unknown_device", "blank_command_type", "non_dict_payload"]
    ),
    command_type_valid=non_blank_str,
    command_type_blank=blank_str,
    payload_valid=st.dictionaries(
        keys=st.text(min_size=1, max_size=5),
        values=st.integers(),
        max_size=3,
    ),
    payload_invalid=non_dict_payload,
)
def test_property_d3_queue_device_command_validation(
    failure_mode,
    command_type_valid,
    command_type_blank,
    payload_valid,
    payload_invalid,
):
    db, engine = _make_session()
    try:
        user = _make_user(db)
        device = _make_device(db, user)

        before = db.query(DeviceCommand).count()

        if failure_mode == "unknown_device":
            with pytest.raises(NotFoundError):
                device_service.queue_device_command(
                    db,
                    f"missing-{uuid4()}",
                    command_type_valid,
                    payload_valid,
                )
        elif failure_mode == "blank_command_type":
            with pytest.raises(ValidationError):
                device_service.queue_device_command(
                    db,
                    device.id,
                    command_type_blank,
                    payload_valid,
                )
        else:  # non_dict_payload
            with pytest.raises(ValidationError):
                device_service.queue_device_command(
                    db,
                    device.id,
                    command_type_valid,
                    payload_invalid,
                )

        after = db.query(DeviceCommand).count()
        assert after == before
    finally:
        db.close()
        engine.dispose()


# ── Property D4: list_pending_device_commands filter benar ─────────
# Feature: service-layer, Property D4: list_pending_device_commands filter benar
# Validates: Requirement 4.7
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    rows=st.lists(
        st.tuples(
            st.integers(min_value=0, max_value=2),  # device index (0..2)
            st.sampled_from(
                [
                    DeviceCommandStatus.PENDING,
                    DeviceCommandStatus.SENT,
                    DeviceCommandStatus.ACKNOWLEDGED,
                    DeviceCommandStatus.FAILED,
                ]
            ),
        ),
        min_size=0,
        max_size=15,
    ),
    target_index=st.integers(min_value=0, max_value=2),
)
def test_property_d4_list_pending_device_commands_filter(rows, target_index):
    db, engine = _make_session()
    try:
        user = _make_user(db)
        # Always create three devices so any ``device_index`` is valid.
        devices = [_make_device(db, user) for _ in range(3)]

        # Track the expected pending command ids per device for cross-check.
        expected_pending_ids: dict[int, set[str]] = {0: set(), 1: set(), 2: set()}

        for device_index, status in rows:
            cmd = DeviceCommand(
                device_id=devices[device_index].id,
                command_type="noop",
                payload={"k": "v"},
                status=status,
            )
            db.add(cmd)
            db.flush()
            if status == DeviceCommandStatus.PENDING:
                expected_pending_ids[device_index].add(cmd.id)
        db.commit()

        target_device = devices[target_index]
        result = device_service.list_pending_device_commands(
            db, target_device.device_code
        )

        result_ids = {c.id for c in result}
        assert result_ids == expected_pending_ids[target_index]
        for c in result:
            assert c.device_id == target_device.id
            assert c.status == DeviceCommandStatus.PENDING
    finally:
        db.close()
        engine.dispose()


# ── Property D5: mark_device_command_sent / ack_device_command ─────
# Feature: service-layer, Property D5: transisi status mark_device_command_sent dan ack_device_command
# Validates: Requirements 4.8, 4.9, 8.1
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    transition=st.sampled_from(["sent", "ack"]),
    initial_status=st.sampled_from(
        [
            DeviceCommandStatus.PENDING,
            DeviceCommandStatus.SENT,
            DeviceCommandStatus.ACKNOWLEDGED,
        ]
    ),
)
def test_property_d5_device_command_transitions(transition, initial_status):
    db, engine = _make_session()
    try:
        user = _make_user(db)
        device = _make_device(db, user)

        cmd = DeviceCommand(
            device_id=device.id,
            command_type="ping",
            payload={"x": 1},
            status=initial_status,
        )
        db.add(cmd)
        db.commit()
        db.refresh(cmd)

        before = datetime.now(timezone.utc) - timedelta(seconds=1)

        if transition == "sent":
            updated = device_service.mark_device_command_sent(db, cmd.id)
            after = datetime.now(timezone.utc) + timedelta(seconds=1)

            assert updated.id == cmd.id
            assert updated.status == DeviceCommandStatus.SENT
            assert updated.sent_at is not None
            sent_at = updated.sent_at
            if sent_at.tzinfo is None:
                sent_at = sent_at.replace(tzinfo=timezone.utc)
            assert before <= sent_at <= after
        else:
            updated = device_service.ack_device_command(db, cmd.id)
            after = datetime.now(timezone.utc) + timedelta(seconds=1)

            assert updated.id == cmd.id
            assert updated.status == DeviceCommandStatus.ACKNOWLEDGED
            assert updated.acknowledged_at is not None
            ack_at = updated.acknowledged_at
            if ack_at.tzinfo is None:
                ack_at = ack_at.replace(tzinfo=timezone.utc)
            assert before <= ack_at <= after
    finally:
        db.close()
        engine.dispose()


# ── Property D6: update_device_status valid dan invalid ────────────
# Feature: service-layer, Property D6: update_device_status valid dan invalid
# Validates: Requirements 4.10, 4.11, 8.1
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    valid_path=st.booleans(),
    new_status=st.sampled_from([DeviceStatus.ONLINE, DeviceStatus.OFFLINE]),
    bad_status=invalid_status_str,
    initial_status=st.sampled_from([DeviceStatus.ONLINE, DeviceStatus.OFFLINE]),
)
def test_property_d6_update_device_status(
    valid_path, new_status, bad_status, initial_status
):
    db, engine = _make_session()
    try:
        user = _make_user(db)
        device = Device(
            user_id=user.id,
            device_code=f"dev-{uuid4()}",
            name="Bench",
            status=initial_status,
            last_seen_at=None,
        )
        db.add(device)
        db.commit()
        db.refresh(device)

        original_status = device.status
        original_seen = device.last_seen_at

        if valid_path:
            before = datetime.now(timezone.utc) - timedelta(seconds=1)
            updated = device_service.update_device_status(
                db, device.device_code, new_status
            )
            after = datetime.now(timezone.utc) + timedelta(seconds=1)

            assert updated.id == device.id
            assert updated.status == new_status
            assert updated.last_seen_at is not None
            seen = updated.last_seen_at
            if seen.tzinfo is None:
                seen = seen.replace(tzinfo=timezone.utc)
            assert before <= seen <= after
        else:
            with pytest.raises(ValidationError):
                device_service.update_device_status(
                    db, device.device_code, bad_status
                )

            db.expire(device)
            reloaded = (
                db.query(Device).filter(Device.id == device.id).one()
            )
            assert reloaded.status == original_status
            assert reloaded.last_seen_at == original_seen
    finally:
        db.close()
        engine.dispose()


# ── Unit tests (Task 5.8): happy-path examples ─────────────────────


def test_unit_queue_and_list_pending_device_command(db_session):
    """Queueing a command makes it visible via list_pending_device_commands."""
    user = User(name="Demo", email="demo@taskbot.local")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    device = Device(
        user_id=user.id,
        device_code="UNIT-DEV-001",
        name="Bench device",
        status=DeviceStatus.OFFLINE,
    )
    db_session.add(device)
    db_session.commit()
    db_session.refresh(device)

    cmd = device_service.queue_device_command(
        db_session,
        device.id,
        "update_face",
        {"face": "happy"},
    )

    assert cmd.status == DeviceCommandStatus.PENDING
    assert cmd.command_type == "update_face"
    assert cmd.payload == {"face": "happy"}

    pending = device_service.list_pending_device_commands(
        db_session, device.device_code
    )
    assert [p.id for p in pending] == [cmd.id]


def test_unit_update_device_status_sets_last_seen(db_session):
    """Updating status to ONLINE flips status and refreshes last_seen_at."""
    user = User(name="Demo2", email="demo2@taskbot.local")
    db_session.add(user)
    db_session.commit()

    device = Device(
        user_id=user.id,
        device_code="UNIT-DEV-002",
        name="Other bench",
        status=DeviceStatus.OFFLINE,
        last_seen_at=None,
    )
    db_session.add(device)
    db_session.commit()
    db_session.refresh(device)

    before = datetime.now(timezone.utc) - timedelta(seconds=1)
    updated = device_service.update_device_status(
        db_session, "UNIT-DEV-002", DeviceStatus.ONLINE
    )
    after = datetime.now(timezone.utc) + timedelta(seconds=1)

    assert updated.status == DeviceStatus.ONLINE
    assert updated.last_seen_at is not None
    seen = updated.last_seen_at
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=timezone.utc)
    assert before <= seen <= after

    # Invalid status leaves state alone.
    with pytest.raises(ValidationError):
        device_service.update_device_status(db_session, "UNIT-DEV-002", "weird")
