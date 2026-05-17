"""Service-layer exception types.

These are the only exceptions raised intentionally by service functions.
Tool wrappers catch exactly these three; other exceptions (e.g. SQLAlchemy
``IntegrityError``) are considered bugs or infrastructure problems and are
allowed to propagate.
"""


class NotFoundError(Exception):
    """Raised when a referenced entity does not exist."""


class ValidationError(Exception):
    """Raised when an argument fails service-level validation."""


class PermissionDeniedError(Exception):
    """Raised when a caller attempts to act on a resource it does not own."""
