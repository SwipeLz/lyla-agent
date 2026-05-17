"""Property tests for ``app/api/dashboard.py`` — Property DB1.

Property tested in this module is listed in
``.kiro/specs/agent-runtime-and-apis/design.md`` (section "Correctness
Properties → Dashboard API"):

**Property DB1: User existence gate**
*For any* Dashboard endpoint requiring ``user_id``, an unknown
``user_id`` SHALL produce HTTP 404 and SHALL NOT call any service
mutation.

**Validates: Requirement 13.6**

Scope
-----
The dashboard endpoints that take a ``user_id`` (and therefore fall
under DB1) are:

- ``GET /dashboard/tasks?user_id=...``
- ``GET /dashboard/expenses?user_id=...``
- ``POST /dashboard/expenses`` (``user_id`` in JSON body)
- ``GET /dashboard/summary?user_id=...``
- ``GET /dashboard/logs?user_id=...``
- ``GET /dashboard/devices?user_id=...``

The two task-by-id endpoints (``PATCH`` / ``DELETE
/dashboard/tasks/{task_id}``) gate on ``task_id`` rather than
``user_id`` and therefore are not part of DB1's user-existence
property; they are covered by Property DB4 in a separate task.

Test infrastructure
-------------------
The dashboard handlers depend on a SQLAlchemy session via
``Depends(get_db)``. We override that dependency to yield the per-test
``db_session`` fixture so both the API call and our pre/post snapshots
observe the exact same in-memory SQLite database.

We also pin ``settings.dashboard_auth_mode`` to ``"none"`` via
``monkeypatch.setattr`` so the test is hermetic against any local
``.env`` overrides — Property DB6 covers the auth-mode behaviour
separately, and DB1 is purely about the user-existence gate.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings as hyp_settings, strategies as st

from app.config import settings
from app.db import get_db
from app.main import app
from app.models import (
    Device,
    DeviceCommand,
    Expense,
    Reminder,
    Task,
    User,
    VoiceCommandLog,
)
from app.models.constants import (
    DeviceCommandStatus,
    DeviceStatus,
    ReminderStatus,
    TaskStatus,
)
from app.schemas.dashboard import ExpenseOut, SummaryOut, TaskOut
from app.services import expense_service, task_service
from app.tools.summary_tools import get_today_summary_tool


# ── Test infrastructure ────────────────────────────────────────────


def _seed_baseline(db) -> User:
    """Seed one User plus one related row in every relevant table.

    The seeded rows give the snapshot something concrete to protect:
    if a buggy handler accidentally ran a service mutation despite an
    unknown ``user_id`` (e.g. by partially deleting a task or
    inserting a stray voice command log), the snapshot diff would
    surface the change.
    """
    sfx = uuid4().hex
    user = User(name=f"User {sfx}", email=f"user-{sfx}@taskbot.local")
    db.add(user)
    db.commit()
    db.refresh(user)

    device = Device(
        user_id=user.id,
        device_code=f"dev-{uuid4()}",
        name="Bench device",
        status=DeviceStatus.OFFLINE,
    )
    db.add(device)
    db.commit()
    db.refresh(device)

    db.add(
        Task(
            user_id=user.id,
            title="Baseline task",
            status=TaskStatus.PENDING,
        )
    )
    db.add(
        Expense(
            user_id=user.id,
            amount=10_000,
            category="food",
            spent_at=datetime.now(timezone.utc),
        )
    )
    db.add(
        Reminder(
            user_id=user.id,
            title="Baseline reminder",
            remind_at=datetime.now(timezone.utc) + timedelta(hours=1),
            channel="both",
            status=ReminderStatus.SCHEDULED,
        )
    )
    db.add(
        VoiceCommandLog(
            user_id=user.id,
            device_id=device.id,
            input_text="hello",
            parsed_actions=[],
            response_text="ok",
            status="success",
        )
    )
    db.add(
        DeviceCommand(
            device_id=device.id,
            command_type="ping",
            payload={"x": 1},
            status=DeviceCommandStatus.PENDING,
        )
    )
    db.commit()
    return user


def _snapshot_all_rows(db) -> dict:
    """Capture a deep snapshot of every row that DB1 protects.

    The snapshot includes mutable columns from every table the
    dashboard endpoints might write to, plus the related tables that
    a buggy handler could plausibly touch through cascaded service
    calls. Two snapshots compare equal iff no row was added, removed,
    or modified.
    """
    db.expire_all()
    return {
        "users": {
            (u.id, u.name, u.email, u.whatsapp_number)
            for u in db.query(User).all()
        },
        "devices": {
            (
                d.id,
                d.user_id,
                d.device_code,
                d.name,
                d.status,
                d.last_seen_at,
            )
            for d in db.query(Device).all()
        },
        "tasks": {
            (
                t.id,
                t.user_id,
                t.title,
                t.course,
                t.status,
                t.priority,
                t.deadline_at,
                t.reminder_at,
            )
            for t in db.query(Task).all()
        },
        "expenses": {
            (
                e.id,
                e.user_id,
                e.amount,
                e.category,
                e.note,
                e.spent_at,
            )
            for e in db.query(Expense).all()
        },
        "reminders": {
            (
                r.id,
                r.user_id,
                r.task_id,
                r.title,
                r.remind_at,
                r.channel,
                r.status,
            )
            for r in db.query(Reminder).all()
        },
        "voice_command_logs": {
            (
                v.id,
                v.user_id,
                v.device_id,
                v.input_text,
                v.response_text,
                v.status,
            )
            for v in db.query(VoiceCommandLog).all()
        },
        "device_commands": {
            (
                c.id,
                c.device_id,
                c.command_type,
                c.status,
                c.sent_at,
                c.acknowledged_at,
            )
            for c in db.query(DeviceCommand).all()
        },
    }


@pytest.fixture
def client(db_session, monkeypatch):
    """TestClient wired to the per-test ``db_session`` and ``auth_mode="none"``.

    Overrides ``get_db`` so the handler and the test share the same
    in-memory SQLite session. Pins ``dashboard_auth_mode`` to ``"none"``
    so the test stays hermetic against local ``.env`` overrides;
    Property DB6 covers the auth-mode behaviour separately.
    """

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(settings, "dashboard_auth_mode", "none")
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


# ── Generators ─────────────────────────────────────────────────────


# The six dashboard endpoints that take a ``user_id`` (Req 12.1, 13.1,
# 13.2, 13.3, 13.4, 13.5). PATCH/DELETE ``/dashboard/tasks/{task_id}``
# gate on ``task_id`` and are not part of DB1.
ENDPOINT_KINDS = (
    "tasks",
    "expenses_get",
    "expenses_post",
    "summary",
    "logs",
    "devices",
)
endpoint_strategy = st.sampled_from(ENDPOINT_KINDS)


# Unknown user_id values: visible ASCII (no whitespace, CR/LF) so
# httpx accepts them as a valid URL path/query value, and definitely
# not equal to the seeded user's id (we drop any value that equals
# the seeded id below). Length kept >= 1 so FastAPI never sees an
# empty ``user_id`` query string (which would surface as a 422 from
# Pydantic, not the 404 we are asserting).
unknown_user_id_strategy = st.text(
    alphabet=st.characters(min_codepoint=33, max_codepoint=126),
    min_size=1,
    max_size=40,
)


def _issue_request(
    test_client: TestClient,
    *,
    endpoint: str,
    user_id: str,
):
    """Issue a request to one of the six DB1 endpoints with ``user_id``.

    For ``POST /dashboard/expenses`` we send a body that would otherwise
    be valid (positive integer ``amount``) so the test cannot trip a
    422 from body validation instead of the 404 we are asserting.
    """
    if endpoint == "tasks":
        return test_client.get(
            "/dashboard/tasks", params={"user_id": user_id}
        )
    if endpoint == "expenses_get":
        return test_client.get(
            "/dashboard/expenses", params={"user_id": user_id}
        )
    if endpoint == "expenses_post":
        return test_client.post(
            "/dashboard/expenses",
            json={
                "user_id": user_id,
                "amount": 12345,
                "category": "food",
                "note": "db1 probe",
            },
        )
    if endpoint == "summary":
        return test_client.get(
            "/dashboard/summary", params={"user_id": user_id}
        )
    if endpoint == "logs":
        return test_client.get(
            "/dashboard/logs", params={"user_id": user_id}
        )
    if endpoint == "devices":
        return test_client.get(
            "/dashboard/devices", params={"user_id": user_id}
        )
    raise AssertionError(f"unknown endpoint kind {endpoint!r}")  # pragma: no cover


# ── Property DB1: User existence gate ──────────────────────────────


# Feature: agent-runtime-and-apis, Property DB1: User existence gate
# **Validates: Requirement 13.6**
@hyp_settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    endpoint=endpoint_strategy,
    unknown_user_id=unknown_user_id_strategy,
)
def test_property_db1_user_existence_gate(
    endpoint,
    unknown_user_id,
    client,
    db_session,
):
    """Property DB1: unknown user_id returns 404 and never mutates state.

    For any of the six DB1 endpoints and any ``user_id`` that does not
    match an existing :class:`User`, the response must be HTTP 404 and
    the full snapshot of every protected table (users, devices, tasks,
    expenses, reminders, voice_command_logs, device_commands) must be
    identical before and after the call.

    Validates: Requirement 13.6
    """
    seeded_user = _seed_baseline(db_session)

    # Reject any Hypothesis draw that happens to collide with the
    # seeded user — that would test the happy path, not the gate.
    if unknown_user_id == seeded_user.id:
        return

    snapshot_before = _snapshot_all_rows(db_session)

    response = _issue_request(
        client,
        endpoint=endpoint,
        user_id=unknown_user_id,
    )

    # Req 13.6: unknown user_id → 404.
    assert response.status_code == 404, (
        f"Expected 404 for endpoint={endpoint!r} "
        f"user_id={unknown_user_id!r}, got "
        f"{response.status_code}: {response.text}"
    )

    # Req 13.6: no row may be mutated when the user gate fails.
    snapshot_after = _snapshot_all_rows(db_session)
    assert snapshot_after == snapshot_before, (
        "Unknown-user requests must not mutate any row (Req 13.6). "
        f"endpoint={endpoint!r} user_id={unknown_user_id!r} "
        f"before={snapshot_before!r} after={snapshot_after!r}"
    )


# ── Concrete table-driven supplement ───────────────────────────────


@pytest.mark.parametrize(
    "endpoint",
    [
        "tasks",
        "expenses_get",
        "expenses_post",
        "summary",
        "logs",
        "devices",
    ],
)
def test_db1_concrete_examples(endpoint, client, db_session):
    """Concrete table-driven example exercising every DB1 endpoint.

    Acts as a deterministic supplement to the Hypothesis-driven
    property test above — easier to read when triaging a shrinker
    output.

    Validates: Requirement 13.6
    """
    _seed_baseline(db_session)
    snapshot_before = _snapshot_all_rows(db_session)

    # A UUID with no chance of colliding with the seeded user's id.
    unknown_user_id = f"missing-{uuid4()}"

    response = _issue_request(
        client,
        endpoint=endpoint,
        user_id=unknown_user_id,
    )

    assert response.status_code == 404, (
        f"Expected 404 for endpoint={endpoint!r}, got "
        f"{response.status_code}: {response.text}"
    )
    assert _snapshot_all_rows(db_session) == snapshot_before


# ── Property DB2: List endpoints reflect service results ────────────
#
# Property tested in this module is listed in
# ``.kiro/specs/agent-runtime-and-apis/design.md`` (section "Correctness
# Properties → Dashboard API"):
#
# **Property DB2: List endpoints reflect service results**
# *For any* ``GET /dashboard/tasks?user_id`` (optional ``status``), the
# response SHALL equal a serialization of
# ``task_service.list_tasks(db, user_id, status)``. Same for
# ``GET /dashboard/expenses`` ↔ ``expense_service.list_expenses`` and
# ``GET /dashboard/summary`` ↔ ``get_today_summary_tool``.
#
# **Validates: Requirements 12.1, 12.2, 13.1, 13.3**
#
# Strategy
# --------
# We seed a deterministic but Hypothesis-driven mix of tasks and
# expenses for one user, then call the three list endpoints and assert
# that each response equals what the corresponding service / tool
# wrapper returns when called directly against the same session.
#
# The serialisation layer is the ``TaskOut`` / ``ExpenseOut`` /
# ``SummaryOut`` Pydantic schemas already used by the dashboard router
# (`app/schemas/dashboard.py`); we apply them ourselves so the
# comparison is byte-for-byte against the same shape the handler
# produces. Comparing as JSON-decoded dicts (`response.json()` vs
# ``model.model_dump(mode="json")``) keeps the equality check
# transport-agnostic — datetimes are compared as ISO 8601 strings on
# both sides, which is what the wire actually carries.

# Status values used for the optional ``status`` filter on
# ``GET /dashboard/tasks`` (Req 12.1). Drawing from the same
# ``TaskStatus`` constants the service/ORM uses keeps the filter values
# realistic and ensures the seeded rows can match.
_TASK_STATUS_VALUES = (
    TaskStatus.PENDING,
    TaskStatus.DONE,
)

task_status_strategy = st.sampled_from(_TASK_STATUS_VALUES)
task_title_strategy = st.text(
    alphabet=st.characters(
        min_codepoint=33, max_codepoint=126, blacklist_characters="\\\"'"
    ),
    min_size=1,
    max_size=24,
).map(lambda s: s.strip()).filter(lambda s: bool(s))

# Tasks: small batches with mixed statuses so the optional ``status``
# filter and the no-filter path both have something to bite on.
task_seed_strategy = st.lists(
    st.tuples(task_title_strategy, task_status_strategy),
    min_size=0,
    max_size=5,
)

# Expenses: positive integer amounts (Req 13.7 — service rejects
# ``amount <= 0``) bounded so SQLite ``Integer`` never overflows.
expense_amount_strategy = st.integers(min_value=1, max_value=10_000_000)
expense_category_strategy = st.sampled_from(("food", "transport", "books", "misc"))
expense_seed_strategy = st.lists(
    st.tuples(expense_amount_strategy, expense_category_strategy),
    min_size=0,
    max_size=5,
)


def _seed_user_with(
    db,
    *,
    tasks: list[tuple[str, str]],
    expenses: list[tuple[int, str]],
):
    """Seed one user, plus the supplied tasks and expenses against it.

    Returns the seeded ``User``. Tasks are persisted via
    ``task_service.create_task`` so the ``deadline_at`` falls inside
    today's Asia/Jakarta calendar window — that way the
    ``get_today_summary`` endpoint has a non-trivial number of rows to
    count and DB2's summary leg is meaningful.

    Expenses use ``expense_service.create_expense`` with ``spent_at``
    set to ``now_utc()`` so they also fall inside today's window for the
    same reason. Both helpers exercise the real Service Layer
    validation paths instead of bypassing them with raw ORM inserts.
    """
    sfx = uuid4().hex
    user = User(name=f"User {sfx}", email=f"user-{sfx}@taskbot.local")
    db.add(user)
    db.commit()
    db.refresh(user)

    # Today's Asia/Jakarta calendar window (in UTC). Pick a deadline
    # comfortably inside it so the summary tool counts every seeded
    # task; ``get_today_summary_tool`` filters on
    # ``start_utc <= deadline_at < end_utc``.
    from app.utils.timezone import jakarta_today_window_utc, now_utc

    start_utc, end_utc = jakarta_today_window_utc()
    deadline_at = start_utc + (end_utc - start_utc) / 2

    for title, status_value in tasks:
        task = task_service.create_task(
            db,
            user_id=user.id,
            title=title,
            deadline_at=deadline_at,
        )
        if status_value != TaskStatus.PENDING:
            # ``create_task`` always starts at PENDING; flip after
            # insert so the optional ``status`` filter has something
            # other than PENDING to match against.
            task.status = status_value
            db.commit()

    for amount, category in expenses:
        expense_service.create_expense(
            db,
            user_id=user.id,
            amount=amount,
            category=category,
            spent_at=now_utc(),
        )

    return user


def _serialize_tasks(rows) -> list[dict]:
    return [TaskOut.model_validate(row).model_dump(mode="json") for row in rows]


def _serialize_expenses(rows) -> list[dict]:
    return [ExpenseOut.model_validate(row).model_dump(mode="json") for row in rows]


def _serialize_summary(result: dict) -> dict:
    return SummaryOut(
        tasks_due_today=int(result["tasks_due_today"]),
        total_expenses_today=int(result["total_expenses_today"]),
    ).model_dump(mode="json")


# Feature: agent-runtime-and-apis, Property DB2: List endpoints reflect
# service results.
# **Validates: Requirements 12.1, 12.2, 13.1, 13.3**
@hyp_settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    seeded_tasks=task_seed_strategy,
    seeded_expenses=expense_seed_strategy,
    status_filter=st.one_of(st.none(), task_status_strategy),
)
def test_property_db2_list_endpoints_reflect_service_results(
    seeded_tasks,
    seeded_expenses,
    status_filter,
    client,
    db_session,
):
    """Property DB2: list endpoints serialise their service results.

    For a fresh user seeded with ``seeded_tasks`` and ``seeded_expenses``:

    - ``GET /dashboard/tasks?user_id=...&status=...`` equals
      ``task_service.list_tasks(db, user_id, status)`` serialised through
      ``TaskOut`` (Req 12.1, 12.2).
    - ``GET /dashboard/expenses?user_id=...`` equals
      ``expense_service.list_expenses(db, user_id)`` serialised through
      ``ExpenseOut`` (Req 13.1).
    - ``GET /dashboard/summary?user_id=...`` equals
      ``get_today_summary_tool(db, user_id)`` projected onto
      ``SummaryOut`` — the two scalar counters (Req 13.3).

    Validates: Requirements 12.1, 12.2, 13.1, 13.3.
    """
    user = _seed_user_with(
        db_session,
        tasks=seeded_tasks,
        expenses=seeded_expenses,
    )

    # ── /dashboard/tasks ────────────────────────────────────────────
    params: dict[str, str] = {"user_id": user.id}
    if status_filter is not None:
        params["status"] = status_filter

    response_tasks = client.get("/dashboard/tasks", params=params)
    assert response_tasks.status_code == 200, response_tasks.text

    expected_task_rows = task_service.list_tasks(
        db_session, user.id, status=status_filter
    )
    assert response_tasks.json() == _serialize_tasks(expected_task_rows), (
        "GET /dashboard/tasks must serialise task_service.list_tasks "
        "verbatim (Req 12.1, 12.2)."
    )

    # ── /dashboard/expenses ─────────────────────────────────────────
    response_expenses = client.get(
        "/dashboard/expenses", params={"user_id": user.id}
    )
    assert response_expenses.status_code == 200, response_expenses.text

    expected_expense_rows = expense_service.list_expenses(db_session, user.id)
    assert response_expenses.json() == _serialize_expenses(
        expected_expense_rows
    ), (
        "GET /dashboard/expenses must serialise "
        "expense_service.list_expenses verbatim (Req 13.1)."
    )

    # ── /dashboard/summary ──────────────────────────────────────────
    response_summary = client.get(
        "/dashboard/summary", params={"user_id": user.id}
    )
    assert response_summary.status_code == 200, response_summary.text

    expected_summary = get_today_summary_tool(db_session, user.id)
    assert expected_summary["success"] is True, expected_summary
    assert response_summary.json() == _serialize_summary(expected_summary), (
        "GET /dashboard/summary must mirror get_today_summary_tool's "
        "two counters (Req 13.3)."
    )


# ── Concrete table-driven supplement ───────────────────────────────


def test_db2_concrete_examples(client, db_session):
    """Concrete supplement: hand-crafted seed for every DB2 endpoint.

    Easier to read when triaging a Hypothesis shrinker counter-example.
    Seeds a small fixed mix and replays the same equality assertions as
    the property test above.

    Validates: Requirements 12.1, 12.2, 13.1, 13.3.
    """
    user = _seed_user_with(
        db_session,
        tasks=[
            ("Tugas A", TaskStatus.PENDING),
            ("Tugas B", TaskStatus.DONE),
            ("Tugas C", TaskStatus.PENDING),
        ],
        expenses=[
            (5_000, "food"),
            (12_500, "transport"),
            (3_000, "books"),
        ],
    )

    # Tasks — no filter.
    response_all = client.get("/dashboard/tasks", params={"user_id": user.id})
    assert response_all.status_code == 200, response_all.text
    assert response_all.json() == _serialize_tasks(
        task_service.list_tasks(db_session, user.id)
    )

    # Tasks — filter on PENDING.
    response_pending = client.get(
        "/dashboard/tasks",
        params={"user_id": user.id, "status": TaskStatus.PENDING},
    )
    assert response_pending.status_code == 200, response_pending.text
    assert response_pending.json() == _serialize_tasks(
        task_service.list_tasks(db_session, user.id, status=TaskStatus.PENDING)
    )

    # Expenses — no window.
    response_expenses = client.get(
        "/dashboard/expenses", params={"user_id": user.id}
    )
    assert response_expenses.status_code == 200, response_expenses.text
    assert response_expenses.json() == _serialize_expenses(
        expense_service.list_expenses(db_session, user.id)
    )

    # Summary.
    response_summary = client.get(
        "/dashboard/summary", params={"user_id": user.id}
    )
    assert response_summary.status_code == 200, response_summary.text
    assert response_summary.json() == _serialize_summary(
        get_today_summary_tool(db_session, user.id)
    )


# ── Property DB3: Patch applies only supplied fields ────────────────
#
# Property tested in this module is listed in
# ``.kiro/specs/agent-runtime-and-apis/design.md`` (section "Correctness
# Properties → Dashboard API"):
#
# **Property DB3: Patch applies only supplied fields**
# *For any* existing ``task_id`` and any subset ``S`` of patchable
# fields, ``PATCH /dashboard/tasks/{task_id}`` with body ``S`` SHALL
# produce a task whose updated fields equal ``S`` and whose other
# fields equal the pre-patch values.
#
# **Validates: Requirement 12.4**
#
# Strategy
# --------
# Every example seeds a fresh user + task with **known initial values
# for every patchable field** (status, title, course, deadline_at,
# reminder_at, priority). Hypothesis then draws a non-empty subset
# ``S`` of those fields plus a fresh value per field — guaranteed
# different from the initial value, and (for datetimes) future-aware
# so ``task_service.update_task``'s ``reminder_at >= now_utc()``
# validation always passes.
#
# We then PATCH ``/dashboard/tasks/{task_id}`` with exactly ``S`` in
# the body and assert:
#
# - Response is 200.
# - For every field ∈ ``S``, the response carries the new value.
# - For every field ∉ ``S``, the response carries the original value.
#
# Datetime comparisons go through ``datetime.fromisoformat`` so the
# wire-level ISO 8601 round-trip stays transport-agnostic.

# The six fields ``task_service.update_task`` accepts (Req 12.4 / the
# ``_UPDATABLE_FIELDS`` set in :mod:`app.services.task_service`).
PATCHABLE_FIELDS: tuple[str, ...] = (
    "status",
    "title",
    "course",
    "deadline_at",
    "reminder_at",
    "priority",
)


def _seed_task_with_known_values(db) -> tuple[User, Task, dict]:
    """Seed a fresh ``User`` plus one ``Task`` populating every
    patchable field with a known initial value.

    Returns ``(user, task, initial_values)`` where ``initial_values``
    is a dict keyed on every member of :data:`PATCHABLE_FIELDS`.
    Initial datetime values are placed comfortably in the future so
    the seeding call itself satisfies ``reminder_at >= now_utc()``
    in :func:`task_service.create_task`.
    """
    from app.utils.timezone import now_utc

    sfx = uuid4().hex
    user = User(name=f"User {sfx}", email=f"db3-{sfx}@taskbot.local")
    db.add(user)
    db.commit()
    db.refresh(user)

    initial_deadline = now_utc() + timedelta(days=7)
    initial_reminder = now_utc() + timedelta(days=3)

    task = task_service.create_task(
        db,
        user_id=user.id,
        title="initial-title",
        course="initial-course",
        deadline_at=initial_deadline,
        reminder_at=initial_reminder,
        priority="medium",
    )

    initial_values = {
        "status": task.status,  # "pending" — set by ``create_task``
        "title": "initial-title",
        "course": "initial-course",
        "deadline_at": initial_deadline,
        "reminder_at": initial_reminder,
        "priority": "medium",
    }
    return user, task, initial_values


# ── Generators for a partial ``TaskPatch`` body ────────────────────


# Status values different from the seeded "pending"; ``update_task``
# does not validate this set, but staying within the documented
# ``TaskStatus`` constants keeps the test realistic.
_NEW_STATUS_VALUES = ("done", "cancelled")
# Priority values different from the seeded "medium".
_NEW_PRIORITY_VALUES = ("low", "high")

# Title/course strategies: visible ASCII, minus quote-like chars that
# would confuse JSON encoding, with explicit filters guaranteeing the
# generated value differs from the seeded "initial-title" /
# "initial-course".
_text_alphabet = st.characters(
    min_codepoint=33, max_codepoint=126, blacklist_characters="\\\"'"
)
_new_title_strategy = (
    st.text(alphabet=_text_alphabet, min_size=1, max_size=24)
    .map(lambda s: s.strip())
    .filter(lambda s: bool(s) and s != "initial-title")
)
_new_course_strategy = (
    st.text(alphabet=_text_alphabet, min_size=1, max_size=24)
    .map(lambda s: s.strip())
    .filter(lambda s: bool(s) and s != "initial-course")
)
# Datetime strategies generate a *day offset* (always > 7 so the
# resulting datetime exceeds the seeded ``initial_deadline`` and
# ``initial_reminder`` of 7 / 3 days). The actual aware datetime is
# materialised inside the test body using ``now_utc()`` so each
# example uses a fresh "now" relative to its own execution time.
_new_dt_offset_days_strategy = st.integers(min_value=10, max_value=10_000)


@st.composite
def _patch_subset_strategy(draw) -> dict:
    """Hypothesis composite drawing a non-empty subset of patchable
    fields paired with fresh values different from the seeded values.

    The returned dict is the request body shape (still in *Python*
    types — datetime offsets remain integers; the test body converts
    them to actual aware datetimes at run time).
    """
    subset = draw(
        st.lists(
            st.sampled_from(PATCHABLE_FIELDS),
            min_size=1,
            max_size=len(PATCHABLE_FIELDS),
            unique=True,
        )
    )
    patch: dict = {}
    if "status" in subset:
        patch["status"] = draw(st.sampled_from(_NEW_STATUS_VALUES))
    if "title" in subset:
        patch["title"] = draw(_new_title_strategy)
    if "course" in subset:
        patch["course"] = draw(_new_course_strategy)
    if "deadline_at" in subset:
        patch["deadline_at"] = draw(_new_dt_offset_days_strategy)
    if "reminder_at" in subset:
        patch["reminder_at"] = draw(_new_dt_offset_days_strategy)
    if "priority" in subset:
        patch["priority"] = draw(st.sampled_from(_NEW_PRIORITY_VALUES))
    return patch


def _materialise_patch(
    raw_patch: dict,
) -> tuple[dict, dict]:
    """Turn the raw composite output into ``(json_body, expected_new)``.

    ``json_body`` is the dict actually sent in the PATCH request:
    datetime offsets become ISO 8601 strings.
    ``expected_new`` is the dict of expected post-patch values keyed
    on the same fields, with datetimes kept as aware ``datetime``
    objects so the assertion can compare instants instead of strings.
    """
    from app.utils.timezone import now_utc

    json_body: dict = {}
    expected_new: dict = {}
    for field, value in raw_patch.items():
        if field in ("deadline_at", "reminder_at"):
            new_dt = now_utc() + timedelta(days=int(value))
            json_body[field] = new_dt.isoformat()
            expected_new[field] = new_dt
        else:
            json_body[field] = value
            expected_new[field] = value
    return json_body, expected_new


def _parse_iso_or_none(value):
    """Helper: ``datetime.fromisoformat`` that tolerates ``None``.

    SQLite's ``DateTime(timezone=True)`` columns lose the explicit
    ``tzinfo`` on round-trip (the SQLite type system has no tz), so
    the ISO string returned to the wire may be naive. We normalise by
    stripping ``tzinfo`` from the parsed value — and the assertion
    helper below also strips ``tzinfo`` from the reference value — so
    instants are compared as naive UTC on both sides.
    """
    if value is None:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return parsed


def _to_naive_utc(dt: datetime) -> datetime:
    """Return ``dt`` as a naive UTC datetime.

    Aware datetimes are converted to UTC then stripped of ``tzinfo``;
    naive datetimes are returned as-is. Mirrors the SQLite round-trip
    so both sides of an equality assertion compare cleanly.
    """
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


# Feature: agent-runtime-and-apis, Property DB3: Patch applies only
# supplied fields.
# **Validates: Requirement 12.4**
@hyp_settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(raw_patch=_patch_subset_strategy())
def test_property_db3_patch_applies_only_supplied_fields(
    raw_patch,
    client,
    db_session,
):
    """Property DB3: PATCH applies only supplied fields and leaves the
    rest untouched.

    For a freshly seeded task with known initial values across all six
    patchable fields, sending a non-empty subset ``S`` in the PATCH
    body yields HTTP 200, and the returned ``TaskOut``:

    - has every field ∈ ``S`` equal to the new value;
    - has every field ∉ ``S`` equal to the original pre-patch value.

    Validates: Requirement 12.4.
    """
    user, task, initial_values = _seed_task_with_known_values(db_session)
    json_body, expected_new = _materialise_patch(raw_patch)

    response = client.patch(
        f"/dashboard/tasks/{task.id}",
        json=json_body,
    )

    assert response.status_code == 200, (
        f"Expected 200 for PATCH with body={json_body!r}, got "
        f"{response.status_code}: {response.text}"
    )
    body = response.json()

    # Field-by-field assertion across every patchable field.
    for field in PATCHABLE_FIELDS:
        actual = body[field]
        if field in raw_patch:
            # Field was in S → response must reflect the new value.
            expected = expected_new[field]
            if isinstance(expected, datetime):
                assert _parse_iso_or_none(actual) == _to_naive_utc(expected), (
                    f"Field {field!r} ∈ S must hold the new value "
                    f"(Req 12.4). expected={expected!r} "
                    f"got={actual!r}"
                )
            else:
                assert actual == expected, (
                    f"Field {field!r} ∈ S must hold the new value "
                    f"(Req 12.4). expected={expected!r} "
                    f"got={actual!r}"
                )
        else:
            # Field was NOT in S → response must hold the original.
            initial = initial_values[field]
            if isinstance(initial, datetime):
                assert _parse_iso_or_none(actual) == _to_naive_utc(initial), (
                    f"Field {field!r} ∉ S must remain at its "
                    f"pre-patch value (Req 12.4). "
                    f"expected={initial!r} got={actual!r}"
                )
            else:
                assert actual == initial, (
                    f"Field {field!r} ∉ S must remain at its "
                    f"pre-patch value (Req 12.4). "
                    f"expected={initial!r} got={actual!r}"
                )


# ── Concrete table-driven supplement ───────────────────────────────


def test_db3_concrete_examples(client, db_session):
    """Concrete supplement: hand-crafted single-field patch + multi-
    field patch exercising Property DB3.

    Acts as a deterministic anchor when triaging a Hypothesis shrinker
    counter-example; replays the same equality assertions on a fixed
    subset.

    Validates: Requirement 12.4.
    """
    from app.utils.timezone import now_utc

    user, task, initial_values = _seed_task_with_known_values(db_session)

    # --- Patch a single non-datetime field: ``status``. ------------
    response = client.patch(
        f"/dashboard/tasks/{task.id}",
        json={"status": "done"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "done"
    # Other fields preserved.
    assert body["title"] == initial_values["title"]
    assert body["course"] == initial_values["course"]
    assert body["priority"] == initial_values["priority"]
    assert _parse_iso_or_none(body["deadline_at"]) == _to_naive_utc(
        initial_values["deadline_at"]
    )
    assert _parse_iso_or_none(body["reminder_at"]) == _to_naive_utc(
        initial_values["reminder_at"]
    )

    # --- Patch a multi-field subset including a datetime. ----------
    new_deadline = now_utc() + timedelta(days=42)
    response = client.patch(
        f"/dashboard/tasks/{task.id}",
        json={
            "title": "new-title",
            "deadline_at": new_deadline.isoformat(),
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["title"] == "new-title"
    assert _parse_iso_or_none(body["deadline_at"]) == _to_naive_utc(new_deadline)
    # ``status`` was just updated to "done" by the previous PATCH —
    # that's the new "pre-patch" baseline for this second call.
    assert body["status"] == "done"
    # Untouched fields keep their pre-patch values.
    assert body["course"] == initial_values["course"]
    assert body["priority"] == initial_values["priority"]
    assert _parse_iso_or_none(body["reminder_at"]) == _to_naive_utc(
        initial_values["reminder_at"]
    )


# ── Property DB4: Delete behavior ───────────────────────────────────
#
# Property tested in this section is listed in
# ``.kiro/specs/agent-runtime-and-apis/design.md`` (section "Correctness
# Properties → Dashboard API"):
#
# **Property DB4: Delete behavior**
# *For any* existing ``task_id``, ``DELETE /dashboard/tasks/{task_id}``
# SHALL respond 204 and the row SHALL no longer exist. *For any*
# missing ``task_id``, the response SHALL be 404 and no row SHALL be
# mutated.
#
# **Validates: Requirements 12.6, 12.7**
#
# Strategy
# --------
# Every example seeds a fresh ``User`` plus exactly one ``Task`` so the
# property can verify, in one call, that:
#
# - In the ``"existing"`` scenario, ``DELETE
#   /dashboard/tasks/{task.id}`` returns HTTP 204, the body is empty,
#   the task row is gone from the database, and **no other** seeded
#   row has been touched.
# - In the ``"missing"`` scenario, ``DELETE
#   /dashboard/tasks/{random_uuid}`` returns HTTP 404, the seeded task
#   still exists, and the full multi-table snapshot is unchanged
#   before vs. after the call.
#
# To make the "no other row mutated" leg of the property meaningful we
# also seed one row in every related table the dashboard router could
# plausibly reach (``Device``, ``Expense``, ``Reminder``,
# ``VoiceCommandLog``, ``DeviceCommand``) — same shape as
# :func:`_seed_baseline` used by Property DB1.
#
# Hypothesis draws the scenario discriminator (``"existing"`` /
# ``"missing"``) plus a fresh missing UUID per example so the shrinker
# can isolate failure modes by scenario.


@st.composite
def _db4_scenario_strategy(draw) -> dict:
    """Hypothesis composite drawing a scenario for Property DB4.

    Returns a dict with keys:

    - ``"kind"``: ``"existing"`` or ``"missing"``.
    - ``"missing_id"``: a UUID-shaped string that will not collide with
      any seeded row (only used when ``kind == "missing"``).
    """
    kind = draw(st.sampled_from(("existing", "missing")))
    # Fresh UUID per example so even with shrinker collapse the missing
    # id stays unique across runs and never collides with the seeded
    # task's UUID-based primary key.
    missing_id = f"missing-{uuid4()}"
    return {"kind": kind, "missing_id": missing_id}


def _seed_user_task_and_neighbours(db) -> tuple[User, Task]:
    """Seed one ``User`` + one ``Task`` plus baseline rows in every
    related table.

    The neighbouring rows let the snapshot diff in the missing-id leg
    of Property DB4 catch any incidental mutation a buggy delete
    handler might cause (e.g. cascading through a service call). The
    layout mirrors :func:`_seed_baseline` used by Property DB1.

    Returns ``(user, task)`` so the caller can address the seeded task
    by id in the existing-id leg.
    """
    sfx = uuid4().hex
    user = User(name=f"User {sfx}", email=f"db4-{sfx}@taskbot.local")
    db.add(user)
    db.commit()
    db.refresh(user)

    device = Device(
        user_id=user.id,
        device_code=f"dev-{uuid4()}",
        name="Bench device",
        status=DeviceStatus.OFFLINE,
    )
    db.add(device)
    db.commit()
    db.refresh(device)

    task = Task(
        user_id=user.id,
        title="db4 baseline task",
        status=TaskStatus.PENDING,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    db.add(
        Expense(
            user_id=user.id,
            amount=10_000,
            category="food",
            spent_at=datetime.now(timezone.utc),
        )
    )
    db.add(
        Reminder(
            user_id=user.id,
            title="db4 baseline reminder",
            remind_at=datetime.now(timezone.utc) + timedelta(hours=1),
            channel="both",
            status=ReminderStatus.SCHEDULED,
        )
    )
    db.add(
        VoiceCommandLog(
            user_id=user.id,
            device_id=device.id,
            input_text="hello",
            parsed_actions=[],
            response_text="ok",
            status="success",
        )
    )
    db.add(
        DeviceCommand(
            device_id=device.id,
            command_type="ping",
            payload={"x": 1},
            status=DeviceCommandStatus.PENDING,
        )
    )
    db.commit()
    return user, task


# Feature: agent-runtime-and-apis, Property DB4: Delete behavior.
# **Validates: Requirements 12.6, 12.7**
@hyp_settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(scenario=_db4_scenario_strategy())
def test_property_db4_delete_behavior(
    scenario,
    client,
    db_session,
):
    """Property DB4: DELETE /dashboard/tasks/{task_id}.

    For an ``"existing"`` ``task_id``:
        - response status is 204 (Req 12.6),
        - response body is empty,
        - the task row is gone from the database,
        - all other seeded rows remain untouched.

    For a ``"missing"`` ``task_id``:
        - response status is 404 (Req 12.7),
        - the full multi-table snapshot is identical before and after
          the call (no row mutated).

    Validates: Requirements 12.6, 12.7.
    """
    user, task = _seed_user_task_and_neighbours(db_session)

    if scenario["kind"] == "existing":
        # ── Existing branch ───────────────────────────────────────
        target_task_id = task.id

        # Snapshot every row *except* the task we're about to delete,
        # so we can verify nothing else was touched.
        snapshot_before = _snapshot_all_rows(db_session)

        response = client.delete(f"/dashboard/tasks/{target_task_id}")

        # Req 12.6: 204 + empty body.
        assert response.status_code == 204, (
            f"Expected 204 for DELETE existing task_id={target_task_id!r}, "
            f"got {response.status_code}: {response.text}"
        )
        assert response.content == b"", (
            "DELETE 204 must have an empty body "
            f"(got {response.content!r})"
        )

        # Req 12.6: the task row is gone.
        db_session.expire_all()
        assert (
            db_session.query(Task).filter(Task.id == target_task_id).first()
            is None
        ), (
            "DELETE existing task must remove the row "
            f"(task_id={target_task_id!r} still present)"
        )

        # Req 12.6: every other seeded row is untouched. We rebuild the
        # expected snapshot by removing the deleted task from the
        # before-snapshot's ``tasks`` set so the equality check catches
        # any *additional* incidental mutation.
        snapshot_after = _snapshot_all_rows(db_session)
        expected_after = dict(snapshot_before)
        expected_after["tasks"] = {
            row for row in snapshot_before["tasks"] if row[0] != target_task_id
        }
        assert snapshot_after == expected_after, (
            "DELETE existing task must remove only the targeted row. "
            f"before={snapshot_before!r} after={snapshot_after!r}"
        )

    else:
        # ── Missing branch ────────────────────────────────────────
        missing_id = scenario["missing_id"]
        # Defensive: in the astronomically unlikely case Hypothesis
        # produced a string equal to the seeded task's UUID, fall back
        # to a guaranteed-fresh value so the test still exercises the
        # missing leg.
        if missing_id == task.id:
            missing_id = f"missing-{uuid4()}"

        snapshot_before = _snapshot_all_rows(db_session)

        response = client.delete(f"/dashboard/tasks/{missing_id}")

        # Req 12.7: 404 for unknown task_id.
        assert response.status_code == 404, (
            f"Expected 404 for DELETE missing task_id={missing_id!r}, got "
            f"{response.status_code}: {response.text}"
        )

        # Req 12.7: no row may be mutated when the task is missing.
        snapshot_after = _snapshot_all_rows(db_session)
        assert snapshot_after == snapshot_before, (
            "DELETE missing task must not mutate any row "
            f"(missing_id={missing_id!r}). "
            f"before={snapshot_before!r} after={snapshot_after!r}"
        )


# ── Concrete table-driven supplement ───────────────────────────────


def test_db4_concrete_examples(client, db_session):
    """Concrete supplement: hand-crafted ``existing`` and ``missing``
    examples for Property DB4.

    Acts as a deterministic anchor when triaging a Hypothesis shrinker
    counter-example; replays the same equality assertions on a fixed
    pair of scenarios.

    Validates: Requirements 12.6, 12.7.
    """
    user, task = _seed_user_task_and_neighbours(db_session)
    target_task_id = task.id

    # ── Existing: 204 + row gone, neighbours untouched. ─────────────
    snapshot_before = _snapshot_all_rows(db_session)
    response = client.delete(f"/dashboard/tasks/{target_task_id}")
    assert response.status_code == 204, response.text
    assert response.content == b""

    db_session.expire_all()
    assert (
        db_session.query(Task).filter(Task.id == target_task_id).first() is None
    )
    snapshot_after = _snapshot_all_rows(db_session)
    expected_after = dict(snapshot_before)
    expected_after["tasks"] = {
        row for row in snapshot_before["tasks"] if row[0] != target_task_id
    }
    assert snapshot_after == expected_after

    # ── Missing: 404 + full snapshot unchanged. ─────────────────────
    snapshot_before_missing = _snapshot_all_rows(db_session)
    missing_id = f"missing-{uuid4()}"
    response = client.delete(f"/dashboard/tasks/{missing_id}")
    assert response.status_code == 404, response.text
    assert _snapshot_all_rows(db_session) == snapshot_before_missing


# ── Property DB5: Validation propagation ────────────────────────────
#
# Property tested in this section is listed in
# ``.kiro/specs/agent-runtime-and-apis/design.md`` (section "Correctness
# Properties → Dashboard API"):
#
# **Property DB5: Validation propagation**
# *For any* request whose body/query violates Service-Layer validation
# (e.g., ``amount <= 0``, naive datetime), the response SHALL be HTTP
# 422 and no row SHALL be mutated.
#
# **Validates: Requirement 13.7**
#
# Scope
# -----
# Per the task brief we focus the property on ``POST /dashboard/expenses``
# because it has a single inbound code path that exercises both kinds of
# Service-Layer validation in scope:
#
# - ``expense_service.create_expense`` rejects ``amount <= 0`` with
#   :class:`app.services.exceptions.ValidationError`.
# - ``expense_service.create_expense`` rejects a naive (no ``tzinfo``)
#   ``spent_at`` with :class:`ValidationError`.
#
# Both raise after the user-existence check, so the user *does* exist
# and any failure to gate would result in a stray ``Expense`` row.
#
# A naive datetime is encoded on the wire as an ISO 8601 string with no
# ``Z`` and no ``±HH:MM`` offset (e.g. ``"2025-01-01T12:00:00"``).
# Pydantic v2 happily parses that into a ``datetime`` whose ``tzinfo``
# is ``None``, and the service layer's ``_is_aware`` check then rejects
# it — so the request reaches the service layer (this is what makes the
# property a *propagation* property) before being turned into HTTP 422
# by the global ``ValidationError`` handler in :mod:`app.api._errors`.
#
# Strategy
# --------
# Hypothesis draws one of three scenario discriminators
# (``"amount_zero"``, ``"amount_negative"``, ``"naive_spent_at"``) and
# the value(s) needed to materialise that scenario. The test seeds a
# fresh user plus baseline rows in every related table (same shape as
# Property DB1 / DB4 use), snapshots the whole DB, issues the POST, and
# asserts:
#
# - response status is 422;
# - the ``Expense`` table is unchanged (no stray row created);
# - the full multi-table snapshot is identical before and after.
#
# Defensively, we also accept HTTP 400 to match the task brief's note
# (``Assert 422 (or possibly 400)``), even though the current handler
# emits 422. The "no row mutated" leg is the load-bearing assertion of
# Req 13.7 either way.


# Scenario discriminators for Property DB5.
_DB5_SCENARIOS = ("amount_zero", "amount_negative", "naive_spent_at")


# Negative amounts: bounded so SQLite ``Integer`` never overflows even
# if a buggy handler tried to insert the row anyway. ``max_value=-1``
# ensures the value is strictly less than zero (Pydantic accepts it as
# ``int`` so the service layer is what must reject it).
_negative_amount_strategy = st.integers(min_value=-10_000_000, max_value=-1)


# Positive amounts to pair with a naive ``spent_at`` so the service
# layer's only objection is the missing ``tzinfo``. Bounded to a sane
# range (Req 13.7's complementary bound — ``amount > 0``).
_positive_amount_strategy = st.integers(min_value=1, max_value=10_000_000)


# Naive ISO 8601 datetime strings (no ``Z``, no ``±HH:MM`` offset).
# Hypothesis draws a year/month/day/hour/minute combination and we
# format it manually so the result is *guaranteed* naive on the wire.
@st.composite
def _naive_iso_datetime_strategy(draw) -> str:
    """Draw an ISO 8601 datetime string with no timezone designator.

    Pydantic v2 parses this into a ``datetime`` whose ``tzinfo`` is
    ``None``; ``expense_service.create_expense`` then rejects it with
    :class:`ValidationError`. Year range stays within SQLite's safe
    span so even a buggy handler that attempted to persist the row
    would not blow up on column conversion before reaching the
    rejection point.
    """
    year = draw(st.integers(min_value=2000, max_value=2099))
    month = draw(st.integers(min_value=1, max_value=12))
    day = draw(st.integers(min_value=1, max_value=28))  # avoid month-end edges
    hour = draw(st.integers(min_value=0, max_value=23))
    minute = draw(st.integers(min_value=0, max_value=59))
    second = draw(st.integers(min_value=0, max_value=59))
    return (
        f"{year:04d}-{month:02d}-{day:02d}"
        f"T{hour:02d}:{minute:02d}:{second:02d}"
    )


@st.composite
def _db5_invalid_payload_strategy(draw) -> dict:
    """Hypothesis composite drawing one Property DB5 scenario.

    Returns a dict with keys:

    - ``"scenario"``: one of ``_DB5_SCENARIOS``.
    - ``"amount"``: the ``amount`` to send in the JSON body.
    - ``"spent_at"``: the ``spent_at`` to send in the JSON body, or
      ``None`` when the scenario does not need it.
    """
    scenario = draw(st.sampled_from(_DB5_SCENARIOS))
    if scenario == "amount_zero":
        return {"scenario": scenario, "amount": 0, "spent_at": None}
    if scenario == "amount_negative":
        return {
            "scenario": scenario,
            "amount": draw(_negative_amount_strategy),
            "spent_at": None,
        }
    # ``naive_spent_at``: positive amount paired with a naive ISO 8601
    # datetime string so the service layer's only objection is the
    # missing ``tzinfo``.
    return {
        "scenario": scenario,
        "amount": draw(_positive_amount_strategy),
        "spent_at": draw(_naive_iso_datetime_strategy()),
    }


# Feature: agent-runtime-and-apis, Property DB5: Validation propagation.
# **Validates: Requirement 13.7**
@hyp_settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(payload=_db5_invalid_payload_strategy())
def test_property_db5_validation_propagation(
    payload,
    client,
    db_session,
):
    """Property DB5: invalid POST /dashboard/expenses → HTTP 422, no
    row mutated.

    For each Hypothesis-drawn scenario in
    ``{"amount_zero", "amount_negative", "naive_spent_at"}``, the test
    seeds a user (so the user-existence gate passes and the request
    reaches the service-layer validation), captures a multi-table
    snapshot, issues ``POST /dashboard/expenses`` with the invalid
    body, and asserts:

    - response status is HTTP 422 (the global ``ValidationError``
      handler in :mod:`app.api._errors` maps the service-layer
      :class:`ValidationError` to 422). The task brief notes that 400
      is also acceptable, so the assertion is ``in {400, 422}``.
    - the ``Expense`` table is unchanged (no stray expense was
      persisted).
    - the full multi-table snapshot is unchanged (no other row was
      mutated either).

    Validates: Requirement 13.7.
    """
    seeded_user = _seed_baseline(db_session)
    snapshot_before = _snapshot_all_rows(db_session)

    body: dict = {
        "user_id": seeded_user.id,
        "amount": payload["amount"],
        "category": "food",
        "note": "db5 probe",
    }
    if payload["spent_at"] is not None:
        body["spent_at"] = payload["spent_at"]

    response = client.post("/dashboard/expenses", json=body)

    # Req 13.7: validation failure → HTTP 422 (or 400 per task brief).
    assert response.status_code in (400, 422), (
        f"Expected 422/400 for scenario={payload['scenario']!r} "
        f"amount={payload['amount']!r} "
        f"spent_at={payload.get('spent_at')!r}, got "
        f"{response.status_code}: {response.text}"
    )

    # Req 13.7: no row may be mutated when validation fails.
    snapshot_after = _snapshot_all_rows(db_session)
    assert snapshot_after == snapshot_before, (
        "Invalid POST /dashboard/expenses must not mutate any row "
        f"(scenario={payload['scenario']!r}). "
        f"before={snapshot_before!r} after={snapshot_after!r}"
    )

    # Stronger leg: explicitly verify no new Expense row was added for
    # the seeded user beyond the baseline. Surfaces a clearer message
    # than the snapshot diff when only the ``expenses`` slice differs.
    db_session.expire_all()
    expenses_for_user = (
        db_session.query(Expense)
        .filter(Expense.user_id == seeded_user.id)
        .all()
    )
    # ``_seed_baseline`` inserts exactly one expense for the seeded user.
    assert len(expenses_for_user) == 1, (
        "Service-Layer validation failure must not persist a new Expense "
        f"row (scenario={payload['scenario']!r}, "
        f"found={len(expenses_for_user)} expenses for user, expected 1)."
    )


# ── Concrete table-driven supplement ───────────────────────────────


@pytest.mark.parametrize(
    "scenario, body_extra",
    [
        ("amount_zero", {"amount": 0}),
        ("amount_negative", {"amount": -1}),
        (
            "naive_spent_at",
            {"amount": 1234, "spent_at": "2025-01-01T12:00:00"},
        ),
    ],
)
def test_db5_concrete_examples(scenario, body_extra, client, db_session):
    """Concrete supplement: one fixed example per Property DB5 scenario.

    Acts as a deterministic anchor when triaging a Hypothesis shrinker
    counter-example; replays the same equality assertions on a fixed
    set of invalid bodies.

    Validates: Requirement 13.7.
    """
    seeded_user = _seed_baseline(db_session)
    snapshot_before = _snapshot_all_rows(db_session)

    body: dict = {
        "user_id": seeded_user.id,
        "category": "food",
        "note": f"db5 concrete {scenario}",
    }
    body.update(body_extra)

    response = client.post("/dashboard/expenses", json=body)

    assert response.status_code in (400, 422), (
        f"Expected 422/400 for scenario={scenario!r}, got "
        f"{response.status_code}: {response.text}"
    )
    assert _snapshot_all_rows(db_session) == snapshot_before
    db_session.expire_all()
    assert (
        db_session.query(Expense)
        .filter(Expense.user_id == seeded_user.id)
        .count()
        == 1
    )


# ── Property DB6: Auth mode behavior ────────────────────────────────
#
# Property tested in this section is listed in
# ``.kiro/specs/agent-runtime-and-apis/design.md`` (section "Correctness
# Properties → Dashboard API"):
#
# **Property DB6: Auth mode behavior**
# *For any* configured ``dashboard_auth_mode``:
# - ``"none"``: requests succeed without ``X-Dashboard-Token`` header.
# - ``"shared_header"``: requests without/with-wrong
#   ``X-Dashboard-Token`` produce HTTP 401; with-correct token produce
#   normal response.
#
# **Validates: Requirements 14.2, 14.3**
#
# Strategy
# --------
# Property DB6 exercises a single, simple, side-effect-free dashboard
# endpoint — ``GET /dashboard/devices?user_id=...`` — so the test
# focuses entirely on the auth-mode contract and doesn't entangle with
# body validation or other endpoints' behaviour. The endpoint returns
# HTTP 200 with an empty list when the seeded user owns no devices,
# which makes the happy-path assertion crisp.
#
# Five scenarios, drawn from Hypothesis as a discriminator and forming
# the truth table from Req 14.2 / 14.3:
#
# - ``("none",          absent_header)``  → 200 (Req 14.2)
# - ``("none",          any_header)``     → 200 (Req 14.2; header ignored)
# - ``("shared_header", absent_header)``  → 401 (Req 14.3)
# - ``("shared_header", wrong_header)``   → 401 (Req 14.3)
# - ``("shared_header", correct_header)`` → 200 (Req 14.3)
#
# Because the existing ``client`` fixture pins
# ``dashboard_auth_mode == "none"``, Property DB6 cannot reuse it. We
# instead build a fresh ``TestClient`` per Hypothesis example via the
# helper :func:`_make_dashboard_client`, which sets the auth config
# directly on ``settings`` and registers a ``get_db`` override against
# the per-test ``db_session``. Each example wraps the call in a
# ``try/finally`` that restores the original ``settings`` values and
# clears the dependency override, so successive examples — and other
# tests in this module — observe a hermetic baseline.


# Tokens are visible-ASCII only so they survive HTTP header transport
# without unicode-normalisation surprises. Length stays > 0 so we can
# always tell "absent header" apart from "empty string header".
_DB6_TOKEN_ALPHABET = st.characters(
    min_codepoint=33, max_codepoint=126, blacklist_characters=" \t\r\n"
)
_db6_token_strategy = st.text(
    alphabet=_DB6_TOKEN_ALPHABET, min_size=1, max_size=24
)


# The five scenario discriminators that exhaust the truth table from
# Req 14.2 / 14.3.
_DB6_SCENARIOS: tuple[tuple[str, str], ...] = (
    ("none", "absent"),
    ("none", "any"),
    ("shared_header", "absent"),
    ("shared_header", "wrong"),
    ("shared_header", "correct"),
)


@st.composite
def _db6_scenario_strategy(draw) -> dict:
    """Hypothesis composite drawing one Property DB6 scenario.

    Returns a dict with keys:

    - ``"mode"``: the ``dashboard_auth_mode`` value to set on
      ``settings`` (``"none"`` or ``"shared_header"``).
    - ``"header_kind"``: discriminator describing what header (if any)
      should accompany the request — one of ``"absent"``, ``"any"``,
      ``"wrong"``, ``"correct"``.
    - ``"configured_token"``: the token to install on
      ``settings.dashboard_token``.
    - ``"header_token"``: the actual token value sent on the wire,
      or ``None`` for the ``"absent"`` case.
    """
    mode, header_kind = draw(st.sampled_from(_DB6_SCENARIOS))
    configured_token = draw(_db6_token_strategy)

    if header_kind == "absent":
        header_token = None
    elif header_kind == "correct":
        header_token = configured_token
    elif header_kind == "wrong":
        # Draw an unrelated token; if Hypothesis happens to pick the
        # same value as ``configured_token``, mutate it so this scenario
        # truly exercises the "wrong" path rather than the "correct"
        # path under a misleading label.
        candidate = draw(_db6_token_strategy)
        header_token = (
            candidate if candidate != configured_token else configured_token + "x"
        )
    else:  # "any"
        # ``mode == "none"`` here; the header value is irrelevant by
        # contract (Req 14.2: header MUST NOT be checked), so any
        # non-empty token suffices.
        header_token = draw(_db6_token_strategy)

    return {
        "mode": mode,
        "header_kind": header_kind,
        "configured_token": configured_token,
        "header_token": header_token,
    }


@pytest.fixture
def db6_user(db_session):
    """Seed exactly one ``User`` so Property DB6 reaches the auth gate
    cleanly.

    The user-existence gate (Req 13.6) runs *after* the auth dependency
    in the FastAPI dependency chain; by ensuring the user always
    exists, a happy-path scenario that returned HTTP 404 would
    unambiguously indicate that the auth gate let the request through
    but a downstream check failed — which is not what DB6 is testing.
    """
    sfx = uuid4().hex
    user = User(name=f"User {sfx}", email=f"db6-{sfx}@taskbot.local")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _make_dashboard_client(db_session, *, mode: str, token: str) -> TestClient:
    """Construct a ``TestClient`` pinned to the supplied auth config.

    Side effects on ``settings`` are intentionally *not* rolled back
    here; the caller is responsible for restoring the original values
    via a ``try/finally`` block. This separation keeps the test body
    explicit about what it mutates and lets each Hypothesis example
    own its cleanup window.

    The ``get_db`` dependency is overridden so the handler and the
    test share the per-test in-memory SQLite session.
    """
    settings.dashboard_auth_mode = mode
    settings.dashboard_token = token

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app)


# Feature: agent-runtime-and-apis, Property DB6: Auth mode behavior.
# **Validates: Requirements 14.2, 14.3**
@hyp_settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(scenario=_db6_scenario_strategy())
def test_property_db6_auth_mode_behavior(scenario, db_session, db6_user):
    """Property DB6: auth mode honours the spec's truth table.

    For ``GET /dashboard/devices?user_id=<seeded>``:

    - ``mode="none"`` with no header               → 200 (Req 14.2)
    - ``mode="none"`` with any header              → 200 (Req 14.2)
    - ``mode="shared_header"`` with no header      → 401 (Req 14.3)
    - ``mode="shared_header"`` with wrong header   → 401 (Req 14.3)
    - ``mode="shared_header"`` with correct header → 200 (Req 14.3)

    Each Hypothesis example builds a fresh ``TestClient`` against the
    drawn auth config, issues the GET, and restores ``settings`` plus
    ``app.dependency_overrides`` in a ``finally`` block — so the rest
    of the suite observes a hermetic baseline regardless of which
    scenario ran last.

    Validates: Requirements 14.2, 14.3.
    """
    original_mode = settings.dashboard_auth_mode
    original_token = settings.dashboard_token

    headers: dict[str, str] = {}
    if scenario["header_token"] is not None:
        headers["X-Dashboard-Token"] = scenario["header_token"]

    # Truth-table prediction: 401 only on shared_header with no/wrong
    # token; everything else is the happy path.
    expected_status = (
        401
        if (
            scenario["mode"] == "shared_header"
            and scenario["header_kind"] in ("absent", "wrong")
        )
        else 200
    )

    try:
        client = _make_dashboard_client(
            db_session,
            mode=scenario["mode"],
            token=scenario["configured_token"],
        )
        with client:
            response = client.get(
                "/dashboard/devices",
                params={"user_id": db6_user.id},
                headers=headers,
            )
    finally:
        settings.dashboard_auth_mode = original_mode
        settings.dashboard_token = original_token
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == expected_status, (
        f"DB6: scenario={scenario!r} expected {expected_status}, "
        f"got {response.status_code}: {response.text}"
    )
    if expected_status == 200:
        # Happy path: endpoint actually returned the user's device list.
        # The user has no devices seeded, so the list is empty — that's
        # the crispest possible "the handler ran" signal.
        assert response.json() == [], (
            f"DB6 happy path must return the device list shape "
            f"(got {response.text!r})"
        )


# ── Concrete table-driven supplement ───────────────────────────────


@pytest.mark.parametrize(
    "mode, header_kind, expected_status",
    [
        ("none", "absent", 200),
        ("none", "any", 200),
        ("shared_header", "absent", 401),
        ("shared_header", "wrong", 401),
        ("shared_header", "correct", 200),
    ],
)
def test_db6_concrete_examples(
    mode, header_kind, expected_status, db_session, db6_user
):
    """Concrete supplement: one fixed example per Property DB6 scenario.

    Acts as a deterministic anchor when triaging a Hypothesis shrinker
    counter-example; replays the same equality assertions as the
    property test above on a fixed truth-table row.

    Validates: Requirements 14.2, 14.3.
    """
    original_mode = settings.dashboard_auth_mode
    original_token = settings.dashboard_token

    configured_token = "correct-token-abc123"
    if header_kind == "absent":
        headers: dict[str, str] = {}
    elif header_kind == "correct":
        headers = {"X-Dashboard-Token": configured_token}
    elif header_kind == "wrong":
        headers = {"X-Dashboard-Token": "definitely-not-the-token"}
    else:  # "any"
        headers = {"X-Dashboard-Token": "stray-header-that-is-ignored"}

    try:
        client = _make_dashboard_client(
            db_session, mode=mode, token=configured_token
        )
        with client:
            response = client.get(
                "/dashboard/devices",
                params={"user_id": db6_user.id},
                headers=headers,
            )
    finally:
        settings.dashboard_auth_mode = original_mode
        settings.dashboard_token = original_token
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == expected_status, response.text
    if expected_status == 200:
        assert response.json() == []
