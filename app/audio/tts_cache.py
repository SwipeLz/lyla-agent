"""TTS audio cache (Phase 11b).

In-process LRU+TTL cache for synthesized TTS bytes, keyed by
``voice_command_log_id``. ESP firmware fetches the bytes via
``GET /agent/audio/{log_id}/tts`` after receiving a response whose
``directive.audio_code == "fallback_tts"``.

The cache is intentionally **in-memory** and **per-process**:
- Bytes are large (~200 KB per response).
- Persistence is not required: if cache misses, ESP plays an error
  fallback and the user re-asks. No data loss.
- Multi-worker uvicorn deployment would each have its own cache;
  acceptable for MVP because one client (one ESP) talks to one worker
  per request via session affinity or single-worker config.
"""
from __future__ import annotations

from threading import Lock

from cachetools import TTLCache

from app.config import settings


class TtsCache:
    def __init__(self, maxsize: int = 100, ttl_seconds: int | None = None) -> None:
        self._cache: TTLCache[str, tuple[bytes, str]] = TTLCache(
            maxsize=maxsize,
            ttl=ttl_seconds if ttl_seconds is not None else settings.tts_cache_ttl_seconds,
        )
        self._lock = Lock()

    def put(self, log_id: str, audio_bytes: bytes, content_type: str) -> None:
        with self._lock:
            self._cache[log_id] = (audio_bytes, content_type)

    def get(self, log_id: str) -> tuple[bytes, str] | None:
        with self._lock:
            return self._cache.get(log_id)

    def has(self, log_id: str) -> bool:
        with self._lock:
            return log_id in self._cache

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def size(self) -> int:
        with self._lock:
            return len(self._cache)


tts_cache = TtsCache()


__all__ = ["TtsCache", "tts_cache"]
