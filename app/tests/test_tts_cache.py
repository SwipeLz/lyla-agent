from __future__ import annotations

import time

from app.audio.tts_cache import TtsCache


def test_put_and_get_returns_audio_bytes():
    cache = TtsCache(maxsize=10, ttl_seconds=60)
    cache.put("log1", b"audio_bytes_here", "audio/wav")
    entry = cache.get("log1")
    assert entry is not None
    audio_bytes, content_type = entry
    assert audio_bytes == b"audio_bytes_here"
    assert content_type == "audio/wav"


def test_get_miss_returns_none():
    cache = TtsCache(maxsize=10, ttl_seconds=60)
    assert cache.get("nonexistent") is None


def test_has_returns_correct_membership():
    cache = TtsCache(maxsize=10, ttl_seconds=60)
    assert cache.has("log1") is False
    cache.put("log1", b"x", "audio/wav")
    assert cache.has("log1") is True


def test_size_reflects_entries():
    cache = TtsCache(maxsize=10, ttl_seconds=60)
    assert cache.size() == 0
    cache.put("log1", b"x", "audio/wav")
    cache.put("log2", b"y", "audio/wav")
    assert cache.size() == 2


def test_clear_removes_all_entries():
    cache = TtsCache(maxsize=10, ttl_seconds=60)
    cache.put("log1", b"x", "audio/wav")
    cache.put("log2", b"y", "audio/wav")
    cache.clear()
    assert cache.size() == 0
    assert cache.get("log1") is None


def test_ttl_expires_entries():
    cache = TtsCache(maxsize=10, ttl_seconds=1)
    cache.put("log1", b"x", "audio/wav")
    assert cache.get("log1") is not None
    time.sleep(1.1)
    assert cache.get("log1") is None


def test_lru_evicts_when_over_capacity():
    cache = TtsCache(maxsize=2, ttl_seconds=60)
    cache.put("log1", b"a", "audio/wav")
    cache.put("log2", b"b", "audio/wav")
    cache.put("log3", b"c", "audio/wav")
    assert cache.size() == 2
    assert cache.get("log3") is not None


def test_overwrite_same_key():
    cache = TtsCache(maxsize=10, ttl_seconds=60)
    cache.put("log1", b"first", "audio/wav")
    cache.put("log1", b"second", "audio/mp3")
    entry = cache.get("log1")
    assert entry == (b"second", "audio/mp3")
