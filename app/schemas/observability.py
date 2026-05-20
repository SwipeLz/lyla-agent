from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class StageTimings(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    validate_ms: Optional[int] = Field(default=None, alias="validate")
    stt: Optional[int] = None
    agent: Optional[int] = None
    classify: Optional[int] = None
    tts: Optional[int] = None


class TraceAudio(BaseModel):
    filename: Optional[str] = None
    size_bytes: Optional[int] = None
    content_type: Optional[str] = None


class TraceTranscription(BaseModel):
    mode: Optional[str] = None
    duration_ms: Optional[int] = None


class TraceDirective(BaseModel):
    audio_code: Optional[str] = None
    face: Optional[str] = None
    screen_text: Optional[str] = None


class TraceTts(BaseModel):
    mode: Optional[str] = None
    available: Optional[bool] = None
    content_type: Optional[str] = None


class TraceClient(BaseModel):
    request_id: Optional[str] = None
    firmware_version: Optional[str] = None
    wifi_rssi_dbm: Optional[int] = None
    battery_pct: Optional[int] = None
    recording_duration_ms: Optional[int] = None


class TraceError(BaseModel):
    layer: Optional[str] = None
    detail: Optional[str] = None


class RequestTrace(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: Optional[str] = None
    device_id: Optional[str] = None
    input_text: Optional[str] = None
    response_text: Optional[str] = None
    parsed_actions: Optional[list[Any]] = None
    status: str
    created_at: datetime
    request_received_at: Optional[datetime] = None
    response_sent_at: Optional[datetime] = None
    stage_timings: StageTimings = StageTimings()
    audio: Optional[TraceAudio] = None
    transcription: Optional[TraceTranscription] = None
    directive: Optional[TraceDirective] = None
    tts: Optional[TraceTts] = None
    client: Optional[TraceClient] = None
    error: Optional[TraceError] = None


class RecentLogSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    device_id: Optional[str] = None
    created_at: datetime
    audio_code: Optional[str] = None
    status: str
    total_ms: Optional[int] = None


class TopAudioCode(BaseModel):
    code: str
    count: int


class StatsResponse(BaseModel):
    count: int
    success_count: int
    error_count: int
    p50_ms: Optional[int] = None
    p95_ms: Optional[int] = None
    p99_ms: Optional[int] = None
    top_audio_codes: list[TopAudioCode] = []


class DeviceStatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    device_code: str
    name: str
    status: str
    is_online: bool = False
    last_seen_at: Optional[datetime] = None
    firmware_version: Optional[str] = None
    wifi_rssi_dbm: Optional[int] = None
    battery_pct: Optional[int] = None
    free_heap_bytes: Optional[int] = None
