"""Expense service: business logic for personal expense tracking.

All functions take a SQLAlchemy ``Session`` and primitive/Python objects.
They never depend on FastAPI, agent frameworks, or formatting concerns.

Validation order for ``create_expense`` (per design):
    1. user exists
    2. ``amount`` is a positive ``int`` (``bool`` is rejected explicitly
       because ``bool`` is a subclass of ``int`` in Python)
    3. ``spent_at`` is timezone-aware OR ``None``

When ``spent_at is None``, the service sets it to ``now_utc()`` before
insert so behavior is deterministic and easy to test (independent of the
ORM column default).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.expense import Expense
from app.models.user import User
from app.services.exceptions import NotFoundError, ValidationError
from app.utils.timezone import now_utc


def _is_aware(dt: datetime) -> bool:
    return dt.tzinfo is not None and dt.tzinfo.utcoffset(dt) is not None


def create_expense(
    db: Session,
    user_id: str,
    amount: int,
    category: Optional[str] = None,
    note: Optional[str] = None,
    spent_at: Optional[datetime] = None,
) -> Expense:
    """Persist a new ``Expense`` and return it.

    Raises ``NotFoundError`` if ``user_id`` is unknown, or
    ``ValidationError`` when input fails validation. Persists no rows when
    validation fails.
    """
    # 1. user must exist
    user = db.query(User).filter(User.id == user_id).one_or_none()
    if user is None:
        raise NotFoundError(f"User {user_id!r} not found")

    # 2. amount must be a positive int (bool is rejected explicitly because
    #    bool is a subclass of int in Python).
    if isinstance(amount, bool) or not isinstance(amount, int):
        raise ValidationError("amount must be a positive int")
    if amount <= 0:
        raise ValidationError("amount must be a positive int")

    # 3. spent_at, if provided, must be a timezone-aware datetime
    if spent_at is not None:
        if not isinstance(spent_at, datetime) or not _is_aware(spent_at):
            raise ValidationError("spent_at must be a timezone-aware datetime")

    # Default spent_at to now_utc() so the service is deterministic.
    effective_spent_at = spent_at if spent_at is not None else now_utc()

    expense = Expense(
        user_id=user_id,
        amount=amount,
        category=category,
        note=note,
        spent_at=effective_spent_at,
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return expense


def list_expenses(
    db: Session,
    user_id: str,
    start_at: Optional[datetime] = None,
    end_at: Optional[datetime] = None,
) -> list[Expense]:
    """Return expenses owned by ``user_id``, optionally restricted to a
    ``[start_at, end_at]`` window on ``spent_at``.

    Either bound is optional and applied independently when supplied.
    """
    query = db.query(Expense).filter(Expense.user_id == user_id)
    if start_at is not None:
        query = query.filter(Expense.spent_at >= start_at)
    if end_at is not None:
        query = query.filter(Expense.spent_at <= end_at)
    return query.all()


def get_expense_summary(
    db: Session,
    user_id: str,
    start_at: Optional[datetime] = None,
    end_at: Optional[datetime] = None,
) -> dict:
    """Return ``{"total": int, "count": int}`` over the same set of rows
    that ``list_expenses`` would return for the same arguments.

    Returns ``{"total": 0, "count": 0}`` when no rows match.
    """
    rows = list_expenses(db, user_id, start_at=start_at, end_at=end_at)
    total = sum(row.amount for row in rows)
    return {"total": total, "count": len(rows)}
