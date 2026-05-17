"""Global exception handlers for Service Layer exceptions.

Service Layer functions raise exactly three exception types
(``NotFoundError``, ``ValidationError``, ``PermissionDeniedError`` —
see :mod:`app.services.exceptions`). HTTP routers in :mod:`app.api`
should not need to wrap every service call in a ``try/except`` block
just to translate those exceptions into HTTP responses; this module
provides a single set of FastAPI exception handlers and a helper to
register them on a ``FastAPI`` app, giving every router a uniform
contract:

- :class:`NotFoundError` → HTTP 404
- :class:`ValidationError` → HTTP 422 (Unprocessable Entity)
- :class:`PermissionDeniedError` → HTTP 403

The dashboard router (:mod:`app.api.dashboard`) already maps these
exceptions inline as a defensive measure; once registered globally,
the handlers below act as the authoritative backstop and ensure
consistent JSON shape (``{"detail": "..."}``) across every endpoint.

Validates: Requirements 12.7, 13.6, 13.7.
"""
from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.services.exceptions import (
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)


async def validation_error_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Translate :class:`ValidationError` into HTTP 422.

    The exception's stringified message is surfaced as the ``detail``
    field. Service-layer ``ValidationError`` is raised with a short,
    user-facing Indonesian message (e.g. ``"amount harus > 0"``) and is
    safe to echo verbatim.
    """
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": str(exc) or "Validation error"},
    )


async def not_found_error_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Translate :class:`NotFoundError` into HTTP 404."""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": str(exc) or "Not found"},
    )


async def permission_denied_error_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Translate :class:`PermissionDeniedError` into HTTP 403."""
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={"detail": str(exc) or "Permission denied"},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register Service Layer exception handlers on ``app``.

    Called from :mod:`app.main` immediately after the ``FastAPI``
    instance is constructed so that every router included afterwards
    inherits the global mapping.
    """
    app.add_exception_handler(ValidationError, validation_error_handler)
    app.add_exception_handler(NotFoundError, not_found_error_handler)
    app.add_exception_handler(
        PermissionDeniedError, permission_denied_error_handler
    )
