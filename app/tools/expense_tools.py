"""Expense tool wrapper: agent-friendly facade over ``expense_service``.

This module belongs to the Tool Wrapper Layer. It calls into
``app.services.expense_service`` and converts the three service-layer
exceptions (``ValidationError``, ``NotFoundError``,
``PermissionDeniedError``) into a normalized *Tool Result Dict* that is
easy for an LLM agent to consume. Other exceptions (e.g.
``IntegrityError``) are intentionally **not** caught here — they signal
bugs or infrastructure problems and must bubble up to the caller.

Tool Result Dict shape:
    success → {"success": True,  "type": "expense", "id": <int>,
               "message": <str>}
    failure → {"success": False, "type": "expense", "error": <str>}

The wrapper never accesses the ORM directly; all DB work goes through
the service layer.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.services import expense_service
from app.services.exceptions import (
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)


def create_expense_tool(
    db: Session,
    user_id: str,
    amount: int,
    category: Optional[str] = None,
    note: Optional[str] = None,
    spent_at: Optional[datetime] = None,
) -> dict:
    """Wrap ``expense_service.create_expense`` and return a Tool Result Dict."""
    try:
        expense = expense_service.create_expense(
            db,
            user_id=user_id,
            amount=amount,
            category=category,
            note=note,
            spent_at=spent_at,
        )
    except (ValidationError, NotFoundError, PermissionDeniedError) as e:
        return {"success": False, "type": "expense", "error": str(e)}
    return {
        "success": True,
        "type": "expense",
        "id": expense.id,
        "message": "Pengeluaran berhasil dicatat.",
    }
