from __future__ import annotations

import os
import statistics
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api._auth_dependencies import require_session
from app.config import settings
from app.db import get_db
from app.models.device import Device
from app.models.voice_command_log import VoiceCommandLog
from app.schemas.observability import (
    DeviceStatusOut,
    RecentLogSummary,
    RequestTrace,
    StageTimings,
    StatsResponse,
    TopAudioCode,
    TraceAudio,
    TraceClient,
    TraceDirective,
    TraceError,
    TraceTranscription,
    TraceTts,
)


router = APIRouter(
    prefix="/observability",
    tags=["Observability"],
    dependencies=[Depends(require_session)],
)


def _ensure_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _build_stage_timings(metadata: dict[str, Any]) -> StageTimings:
    timings = _ensure_dict(metadata.get("stage_timings_ms"))
    return StageTimings(
        validate=timings.get("validate"),
        stt=timings.get("stt"),
        agent=timings.get("agent"),
        classify=timings.get("classify"),
        tts=timings.get("tts"),
    )


def _build_trace(log: VoiceCommandLog) -> RequestTrace:
    metadata = _ensure_dict(log.metadata_json)
    audio = _ensure_dict(metadata.get("audio")) if metadata.get("audio") else None
    transcription = (
        _ensure_dict(metadata.get("transcription"))
        if metadata.get("transcription")
        else None
    )
    directive = (
        _ensure_dict(metadata.get("directive"))
        if metadata.get("directive")
        else None
    )
    tts = _ensure_dict(metadata.get("tts")) if metadata.get("tts") else None
    client = _ensure_dict(metadata.get("client")) if metadata.get("client") else None
    error = _ensure_dict(metadata.get("error")) if metadata.get("error") else None

    return RequestTrace(
        id=log.id,
        user_id=log.user_id,
        device_id=log.device_id,
        input_text=log.input_text,
        response_text=log.response_text,
        parsed_actions=log.parsed_actions if isinstance(log.parsed_actions, list) else None,
        status=log.status,
        created_at=log.created_at,
        request_received_at=log.request_received_at,
        response_sent_at=log.response_sent_at,
        stage_timings=_build_stage_timings(metadata),
        audio=TraceAudio(**audio) if audio else None,
        audio_url=_audio_url_for(log.id),
        transcription=TraceTranscription(**transcription) if transcription else None,
        directive=TraceDirective(**directive) if directive else None,
        tts=TraceTts(**tts) if tts else None,
        client=TraceClient(**client) if client else None,
        error=TraceError(**error) if error else None,
    )


def _audio_url_for(log_id: str) -> str | None:
    if not settings.audio_persist_input_dir:
        return None
    persist_dir = Path(settings.audio_persist_input_dir)
    for ext in (".wav", ".mp3", ".m4a", ".webm"):
        if (persist_dir / f"{log_id}{ext}").exists():
            return f"/observability/audio/{log_id}"
    return None


def _total_ms(log: VoiceCommandLog) -> int | None:
    if log.request_received_at is None or log.response_sent_at is None:
        return None
    delta = log.response_sent_at - log.request_received_at
    return int(delta.total_seconds() * 1000)


@router.get("/trace/{log_id}", response_model=RequestTrace)
def get_trace(log_id: str, db: Session = Depends(get_db)) -> RequestTrace:
    log = db.query(VoiceCommandLog).filter(VoiceCommandLog.id == log_id).one_or_none()
    if log is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Log tidak ditemukan",
        )
    return _build_trace(log)


@router.get("/audio/{log_id}")
def get_audio(log_id: str, db: Session = Depends(get_db)) -> FileResponse:
    if not settings.audio_persist_input_dir:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audio persistence disabled (set AUDIO_PERSIST_INPUT_DIR).",
        )
    log = db.query(VoiceCommandLog).filter(VoiceCommandLog.id == log_id).one_or_none()
    if log is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Log tidak ditemukan",
        )
    persist_dir = Path(settings.audio_persist_input_dir)
    for ext in (".wav", ".mp3", ".m4a", ".webm"):
        candidate = persist_dir / f"{log_id}{ext}"
        if candidate.exists():
            media_type = {
                ".wav": "audio/wav",
                ".mp3": "audio/mpeg",
                ".m4a": "audio/mp4",
                ".webm": "audio/webm",
            }[ext]
            return FileResponse(
                path=str(candidate),
                media_type=media_type,
                filename=f"{log_id}{ext}",
            )
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Audio file not persisted for this log_id.",
    )


@router.get("/recent", response_model=list[RecentLogSummary])
def list_recent(
    limit: int = Query(50, ge=1, le=200),
    device_id: str | None = Query(None),
    log_status: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
) -> list[RecentLogSummary]:
    query = db.query(VoiceCommandLog)
    if device_id is not None:
        query = query.filter(VoiceCommandLog.device_id == device_id)
    if log_status is not None:
        query = query.filter(VoiceCommandLog.status == log_status)
    rows = query.order_by(VoiceCommandLog.created_at.desc()).limit(limit).all()

    summaries: list[RecentLogSummary] = []
    for row in rows:
        metadata = _ensure_dict(row.metadata_json)
        directive = _ensure_dict(metadata.get("directive"))
        audio_code = directive.get("audio_code") if directive else None
        summaries.append(
            RecentLogSummary(
                id=row.id,
                device_id=row.device_id,
                created_at=row.created_at,
                audio_code=audio_code,
                status=row.status,
                total_ms=_total_ms(row),
            )
        )
    return summaries


_WINDOW_DELTAS = {
    "1h": timedelta(hours=1),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
}


def _percentile(values: list[int], q: float) -> int | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    s = sorted(values)
    idx = int(round(q * (len(s) - 1)))
    idx = max(0, min(idx, len(s) - 1))
    return s[idx]


@router.get("/stats", response_model=StatsResponse)
def get_stats(
    window: str = Query("1h"),
    db: Session = Depends(get_db),
) -> StatsResponse:
    delta = _WINDOW_DELTAS.get(window)
    if delta is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="window harus salah satu dari '1h', '24h', '7d'",
        )

    cutoff = datetime.now(tz=timezone.utc) - delta
    rows = (
        db.query(VoiceCommandLog)
        .filter(VoiceCommandLog.created_at >= cutoff)
        .all()
    )

    success_count = sum(1 for r in rows if r.status == "success")
    error_count = sum(1 for r in rows if r.status == "error")

    durations: list[int] = []
    code_counter: Counter[str] = Counter()
    for row in rows:
        ms = _total_ms(row)
        if ms is not None:
            durations.append(ms)
        metadata = _ensure_dict(row.metadata_json)
        directive = _ensure_dict(metadata.get("directive"))
        code = directive.get("audio_code") if directive else None
        if isinstance(code, str) and code:
            code_counter[code] += 1

    top = [
        TopAudioCode(code=code, count=count)
        for code, count in code_counter.most_common(5)
    ]

    return StatsResponse(
        count=len(rows),
        success_count=success_count,
        error_count=error_count,
        p50_ms=_percentile(durations, 0.50),
        p95_ms=_percentile(durations, 0.95),
        p99_ms=_percentile(durations, 0.99),
        top_audio_codes=top,
    )


@router.get("/devices", response_model=list[DeviceStatusOut])
def list_devices(db: Session = Depends(get_db)) -> list[DeviceStatusOut]:
    rows = db.query(Device).all()
    now = datetime.now(tz=timezone.utc)
    online_threshold = timedelta(seconds=60)
    sort_floor = datetime.min.replace(tzinfo=timezone.utc)

    def _aware(dt: datetime | None) -> datetime | None:
        if dt is None:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    rows.sort(key=lambda d: _aware(d.last_seen_at) or sort_floor, reverse=True)

    out: list[DeviceStatusOut] = []
    for device in rows:
        last_seen = _aware(device.last_seen_at)
        is_online = last_seen is not None and (now - last_seen) < online_threshold
        out.append(
            DeviceStatusOut(
                id=device.id,
                device_code=device.device_code,
                name=device.name,
                status=device.status,
                is_online=is_online,
                last_seen_at=last_seen,
                firmware_version=device.firmware_version,
                wifi_rssi_dbm=device.wifi_rssi_dbm,
                battery_pct=device.battery_pct,
                free_heap_bytes=device.free_heap_bytes,
            )
        )
    return out
