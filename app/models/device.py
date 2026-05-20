import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.db import Base
from app.models.constants import DeviceStatus


class Device(Base):
    __tablename__ = "devices"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    device_code = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    status = Column(String, nullable=False, default=DeviceStatus.OFFLINE)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    api_token = Column(String, nullable=True)
    firmware_version = Column(String(64), nullable=True)
    wifi_rssi_dbm = Column(Integer, nullable=True)
    battery_pct = Column(Integer, nullable=True)
    free_heap_bytes = Column(Integer, nullable=True)

    user = relationship("User", back_populates="devices")
    commands = relationship("DeviceCommand", back_populates="device", cascade="all, delete-orphan")
    voice_command_logs = relationship("VoiceCommandLog", back_populates="device")
