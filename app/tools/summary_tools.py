"""Summary tool wrapper.

Plain Python wrapper that produces a *Tool Result Dict* describing the
user's "today" snapshot in the Asia/Jakarta calendar day. Like the other
tool wrappers, this module never accesses the ORM directly through the
agent path; instead it composes a couple of read-only queries against the
existing models and uses :func:`app.utils.timezone.jakarta_today_window_utc`
to compute the time window.

Result shape:

- Success::

    {
        "success": True,
        "type": "summary",
        "tasks_due_today": <int>,
        "total_expenses_today": <int>,
        "message": "Ringkasan hari ini siap.",
    }

- Failure (user not found)::

    {"success": False, "type": "summary", "error": "User tidak ditemukan."}

The wrapper does not catch unexpected DB exceptions — those are bugs and
must propagate.
"""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.expense import Expense
from app.models.task import Task
from app.models.user import User
from app.utils.timezone import jakarta_today_window_utc

_TYPE = "summary"


def get_today_summary_tool(db: Session, user_id) -> dict:
    """Return a snapshot of tasks due and expenses spent today (Asia/Jakarta)."""
    user = db.query(User).filter(User.id == user_id).one_or_none()
    if user is None:
        return {
            "success": False,
            "type": _TYPE,
            "error": "User tidak ditemukan.",
        }

    start_utc, end_utc = jakarta_today_window_utc()

    tasks_due_today = (
        db.query(func.count(Task.id))
        .filter(
            Task.user_id == user_id,
            Task.deadline_at.isnot(None),
            Task.deadline_at >= start_utc,
            Task.deadline_at < end_utc,
        )
        .scalar()
        or 0
    )

    total_expenses_today = (
        db.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= start_utc,
            Expense.spent_at < end_utc,
        )
        .scalar()
        or 0
    )

    return {
        "success": True,
        "type": _TYPE,
        "tasks_due_today": int(tasks_due_today),
        "total_expenses_today": int(total_expenses_today),
        "message": "Ringkasan hari ini siap.",
    }
