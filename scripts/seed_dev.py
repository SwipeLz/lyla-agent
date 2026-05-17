"""Idempotent seed script for development data.

Usage:
    python -m scripts.seed_dev

Creates a demo user and demo device if they do not already exist.
"""
import sys
import os

# Ensure the project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db import SessionLocal, engine, Base
from app.models.user import User
from app.models.device import Device
from app.models.constants import DeviceStatus


DEMO_EMAIL = "demo@taskbot.local"
DEMO_DEVICE_CODE = "TASKBOT-DEMO-001"


def seed():
    db = SessionLocal()
    try:
        # Idempotent: check if demo user already exists
        user = db.query(User).filter(User.email == DEMO_EMAIL).first()
        if user is None:
            user = User(name="Demo User", email=DEMO_EMAIL, whatsapp_number=None)
            db.add(user)
            db.commit()
            db.refresh(user)
            print(f"[seed] Created demo user: {user.name} ({user.email})")
        else:
            print(f"[seed] Demo user already exists: {user.name} ({user.email})")

        # Idempotent: check if demo device already exists
        device = db.query(Device).filter(Device.device_code == DEMO_DEVICE_CODE).first()
        if device is None:
            device = Device(
                user_id=user.id,
                device_code=DEMO_DEVICE_CODE,
                name="Demo Taskbot",
                status=DeviceStatus.OFFLINE,
            )
            db.add(device)
            db.commit()
            db.refresh(device)
            print(f"[seed] Created demo device: {device.name} ({device.device_code})")
        else:
            print(f"[seed] Demo device already exists: {device.name} ({device.device_code})")

        # Print IDs so you can copy them into curl/HTTPie/your dashboard.
        print()
        print("=" * 60)
        print("Use these IDs when calling POST /agent/text:")
        print(f"  user_id   = {user.id}")
        print(f"  device_id = {device.id}")
        print("=" * 60)

    finally:
        db.close()


if __name__ == "__main__":
    seed()
