"""Lightweight serialization helpers for SQLAlchemy mapped instances."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import inspect


def model_to_dict(obj: Any) -> dict | None:
    """Convert a SQLAlchemy mapped instance to a plain ``dict``.

    - ``None`` input returns ``None``.
    - Only mapped columns are included; relationships are skipped.
    - ``datetime`` values are rendered via ``.isoformat()``.
    - Other values are returned verbatim.
    """
    if obj is None:
        return None

    mapper = inspect(obj).mapper
    result: dict[str, Any] = {}
    for column in mapper.columns:
        value = getattr(obj, column.key)
        if isinstance(value, datetime):
            result[column.key] = value.isoformat()
        else:
            result[column.key] = value
    return result
