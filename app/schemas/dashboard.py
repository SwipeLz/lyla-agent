"""Pydantic schemas for the Minimal Dashboard API (Phase 8).

These schemas mirror the ORM rows defined in ``app/models/`` so the
dashboard router can build responses directly from SQLAlchemy objects
via ``model_config = ConfigDict(from_attributes=True)``. They also
define the inbound payloads for ``POST /dashboard/expenses`` and
``PATCH /dashboard/tasks/{task_id}``.

Field shapes follow Requirements 12.1, 12.3, 13.1, 13.2, 13.3, 13.4,
and 13.5 of the agent-runtime-and-apis spec.

Note on ID types: the ORM stores ``id``, ``user_id``, and ``device_id``
as string UUIDs (``app/models/*.py``), so every schema in this module —
both the ``Out`` shapes and the inbound ``ExpenseIn`` payload — types
those fields as ``str`` to match the real data. Requirement 13.2
nominally lists ``user_id: int`` for the create-expense body, but the
service layer (:func:`app.services.expense_service.create_expense`) and
``User.id`` itself are string UUIDs; an ``int`` payload would never
match an existing user and the endpoint would always return 404. This
deviation matches the same one already documented in
:mod:`app.schemas.agent` for ``AgentTextRequest`` and is consistent with
the design.md pseudocode for the dashboard endpoints.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class TaskOut(BaseModel):
    """Serialized ``Task`` row returned by the dashboard task endpoints.

    Validates: Requirement 12.1 (`GET /dashboard/tasks`) and 12.4
    (response shape of `PATCH /dashboard/tasks/{task_id}`).

    ``deadline_at``, ``reminder_at``, and ``created_at`` come from
    timezone-aware ``DateTime(timezone=True)`` columns.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    title: str
    course: Optional[str] = None
    status: str
    priority: Optional[str] = None
    deadline_at: Optional[datetime] = None
    reminder_at: Optional[datetime] = None
    created_at: datetime


class TaskPatch(BaseModel):
    """Partial update payload for ``PATCH /dashboard/tasks/{task_id}``.

    Every field is optional; only the supplied (non-``None``) fields are
    applied by ``task_service.update_task`` per Requirement 12.4.
    """

    model_config = ConfigDict(from_attributes=True)

    status: Optional[str] = None
    title: Optional[str] = None
    course: Optional[str] = None
    deadline_at: Optional[datetime] = None
    reminder_at: Optional[datetime] = None
    priority: Optional[str] = None


class ExpenseIn(BaseModel):
    """Request body for ``POST /dashboard/expenses``.

    Mirrors the keyword arguments of ``expense_service.create_expense``
    per Requirement 13.2. Service-layer validation (positive integer
    amount, timezone-aware ``spent_at``) is re-applied downstream and
    surfaced as HTTP 422 by the dashboard error handler.
    """

    user_id: str
    amount: int
    category: Optional[str] = None
    note: Optional[str] = None
    spent_at: Optional[datetime] = None


class ExpenseOut(BaseModel):
    """Serialized ``Expense`` row returned by dashboard expense endpoints.

    Validates: Requirements 13.1 (list) and 13.2 (create response).
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    amount: int
    category: Optional[str] = None
    note: Optional[str] = None
    spent_at: datetime
    created_at: datetime


class SummaryOut(BaseModel):
    """Response shape for ``GET /dashboard/summary``.

    Both counters are integers computed against the same Asia/Jakarta
    calendar-day window used by ``get_today_summary_tool`` per
    Requirement 13.3.
    """

    model_config = ConfigDict(from_attributes=True)

    tasks_due_today: int
    total_expenses_today: int


class LogOut(BaseModel):
    """Serialized ``VoiceCommandLog`` row returned by ``GET /dashboard/logs``.

    ``parsed_actions`` carries the list of Tool Result Dicts produced
    during the original agent invocation; the column is JSON-typed so we
    accept ``list[Any] | None``. Per Requirement 13.4 the dashboard
    endpoint orders these rows most-recent-first.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: Optional[str] = None
    device_id: Optional[str] = None
    input_text: str
    parsed_actions: Optional[list[Any]] = None
    response_text: Optional[str] = None
    status: str
    created_at: datetime


class DeviceOut(BaseModel):
    """Serialized ``Device`` row returned by ``GET /dashboard/devices``.

    Validates: Requirement 13.5.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    device_code: str
    status: str
    last_seen_at: Optional[datetime] = None
    created_at: datetime
