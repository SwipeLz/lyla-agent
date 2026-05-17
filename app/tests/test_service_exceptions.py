"""Unit tests for service-layer exceptions.

Validates Requirement 7.1: ``NotFoundError``, ``ValidationError``, and
``PermissionDeniedError`` are direct subclasses of ``Exception`` and behave
like ordinary exceptions when raised and caught.
"""
from __future__ import annotations

import pytest

from app.services.exceptions import (
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)


@pytest.mark.parametrize(
    "exception_cls",
    [NotFoundError, ValidationError, PermissionDeniedError],
)
def test_service_exception_is_direct_subclass_of_exception(exception_cls):
    # Validates: Requirement 7.1
    assert issubclass(exception_cls, Exception) is True
    assert exception_cls.__bases__ == (Exception,)


@pytest.mark.parametrize(
    ("exception_cls", "message"),
    [
        (NotFoundError, "missing user"),
        (ValidationError, "title kosong"),
        (PermissionDeniedError, "akses ditolak"),
    ],
)
def test_service_exception_can_be_raised_and_caught(exception_cls, message):
    # Validates: Requirement 7.1
    with pytest.raises(exception_cls) as excinfo:
        raise exception_cls(message)
    assert str(excinfo.value) == message

    # And can be caught via the generic ``Exception`` base.
    try:
        raise exception_cls(message)
    except Exception as caught:  # noqa: BLE001 - intentional broad catch
        assert isinstance(caught, exception_cls)
        assert str(caught) == message
