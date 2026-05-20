import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship

from app.db import Base


class VoiceCommandLog(Base):
    __tablename__ = "voice_command_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    device_id = Column(String, ForeignKey("devices.id"), nullable=True)
    input_text = Column(Text, nullable=False)
    parsed_actions = Column(JSON, nullable=True)
    response_text = Column(Text, nullable=True)
    status = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    metadata_json = Column(JSON, nullable=True)
    request_received_at = Column(DateTime(timezone=True), nullable=True)
    response_sent_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="voice_command_logs")
    device = relationship("Device", back_populates="voice_command_logs")
