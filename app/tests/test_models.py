"""Tests for database models using a temporary in-memory SQLite database."""
import json
from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models.user import User
from app.models.device import Device
from app.models.task import Task
from app.models.expense import Expense
from app.models.reminder import Reminder
from app.models.voice_command_log import VoiceCommandLog
from app.models.device_command import DeviceCommand
from app.models.constants import (
    TaskStatus,
    DeviceStatus,
    ReminderStatus,
    DeviceCommandStatus,
)


@pytest.fixture
def db_session():
    """Create a fresh in-memory SQLite database for each test."""
    engine = create_engine("sqlite:///:memory:")

    # Enable foreign keys for the test database
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def demo_user(db_session):
    """Create and return a demo user."""
    user = User(name="Test User", email="test@taskbot.local")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def demo_device(db_session, demo_user):
    """Create and return a demo device linked to demo_user."""
    device = Device(
        user_id=demo_user.id,
        device_code="TEST-DEVICE-001",
        name="Test Device",
        status=DeviceStatus.OFFLINE,
    )
    db_session.add(device)
    db_session.commit()
    db_session.refresh(device)
    return device


# ── User ────────────────────────────────────────────────────────────

def test_create_user(db_session):
    user = User(name="Alice", email="alice@example.com")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    assert user.id is not None
    assert user.name == "Alice"
    assert user.email == "alice@example.com"
    assert user.created_at is not None


# ── Device ──────────────────────────────────────────────────────────

def test_create_device_linked_to_user(db_session, demo_user):
    device = Device(
        user_id=demo_user.id,
        device_code="DEV-001",
        name="My Taskbot",
    )
    db_session.add(device)
    db_session.commit()
    db_session.refresh(device)

    assert device.id is not None
    assert device.user_id == demo_user.id
    assert device.status == DeviceStatus.OFFLINE
    assert device.user.name == demo_user.name


# ── Task ────────────────────────────────────────────────────────────

def test_create_task_linked_to_user(db_session, demo_user):
    task = Task(
        user_id=demo_user.id,
        title="Tugas Jaringan Komputer",
        course="Jaringan Komputer",
        deadline_at=datetime.now(timezone.utc) + timedelta(days=3),
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    assert task.id is not None
    assert task.user_id == demo_user.id
    assert task.status == TaskStatus.PENDING
    assert task.course == "Jaringan Komputer"
    assert task.user.name == demo_user.name


# ── Expense ─────────────────────────────────────────────────────────

def test_create_expense_linked_to_user(db_session, demo_user):
    expense = Expense(
        user_id=demo_user.id,
        amount=25000,
        category="Makan",
        note="Makan siang",
    )
    db_session.add(expense)
    db_session.commit()
    db_session.refresh(expense)

    assert expense.id is not None
    assert expense.amount == 25000
    assert expense.category == "Makan"
    assert expense.user.name == demo_user.name


# ── Reminder ────────────────────────────────────────────────────────

def test_create_reminder_linked_to_user(db_session, demo_user):
    reminder = Reminder(
        user_id=demo_user.id,
        title="Bayar kos",
        remind_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    db_session.add(reminder)
    db_session.commit()
    db_session.refresh(reminder)

    assert reminder.id is not None
    assert reminder.status == ReminderStatus.SCHEDULED
    assert reminder.task_id is None
    assert reminder.user.name == demo_user.name


def test_create_reminder_linked_to_task(db_session, demo_user):
    task = Task(
        user_id=demo_user.id,
        title="Baca Bab 1",
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    reminder = Reminder(
        user_id=demo_user.id,
        task_id=task.id,
        title="Reminder: Baca Bab 1",
        remind_at=datetime.now(timezone.utc) + timedelta(hours=6),
    )
    db_session.add(reminder)
    db_session.commit()
    db_session.refresh(reminder)

    assert reminder.task_id == task.id
    assert reminder.task.title == "Baca Bab 1"
    assert len(task.reminders) == 1


# ── VoiceCommandLog ────────────────────────────────────────────────

def test_create_voice_command_log_with_json(db_session, demo_user, demo_device):
    parsed = [{"tool": "create_task", "args": {"title": "Test"}}]
    log = VoiceCommandLog(
        user_id=demo_user.id,
        device_id=demo_device.id,
        input_text="Buat tugas test",
        parsed_actions=parsed,
        response_text="Tugas test telah dicatat.",
        status="success",
    )
    db_session.add(log)
    db_session.commit()
    db_session.refresh(log)

    assert log.id is not None
    assert log.parsed_actions == parsed
    assert log.parsed_actions[0]["tool"] == "create_task"
    assert log.user.name == demo_user.name
    assert log.device.device_code == demo_device.device_code


# ── DeviceCommand ──────────────────────────────────────────────────

def test_create_device_command_with_json_payload(db_session, demo_device):
    payload = {"face": "happy", "sound": "chime"}
    cmd = DeviceCommand(
        device_id=demo_device.id,
        command_type="update_face",
        payload=payload,
    )
    db_session.add(cmd)
    db_session.commit()
    db_session.refresh(cmd)

    assert cmd.id is not None
    assert cmd.status == DeviceCommandStatus.PENDING
    assert cmd.payload["face"] == "happy"
    assert cmd.device.device_code == demo_device.device_code
