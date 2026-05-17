"""Property tests for ``app/api/devices.py`` — Properties DA1 and DA2.

Properties tested in this module are listed in
``.kiro/specs/agent-runtime-and-apis/design.md`` (section "Correctness
Properties → Device Command Queue API"):

**Property DA1: Token check precedes lookup**
*For any* request to a device-facing route with a missing or wrong
``X-Device-Token`` header, the response SHALL be HTTP 401, no ``Device``
lookup SHALL be performed, and no row SHALL be mutated.

**Validates: Requirements 9.2, 9.4**

**Property DA2: Unknown device_code → 404**
*For any* request to a device-facing route with a valid
``X-Device-Token`` header but a ``device_code`` that does not match any
``Device`` row, the response SHALL be HTTP 404 and no row SHALL be
mutated.

**Validates: Requirement 9.3**

Test infrastructure
-------------------

The handler depends on a SQLAlchemy session via ``Depends(get_db)``. We
override that dependency to yield the per-test ``db_session`` fixture so
both the API call and our pre/post snapshots observe the exact same
in-memory SQLite database.

We also pin ``settings.device_api_token`` to a known value via
``monkeypatch.setattr`` so the test does not depend on the developer's
local ``.env`` and the "wrong token" generator can produce values
guaranteed to differ from the configured token.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings as hyp_settings, strategies as st

from app.config import settings
from app.db import get_db
from app.main import app
from app.models import Device, DeviceCommand, User
from app.models.constants import DeviceCommandStatus, DeviceStatus


# ── Test infrastructure ────────────────────────────────────────────


VALID_TOKEN = "valid_token"


def _seed(db) -> tuple[User, Device, DeviceCommand]:
    """Insert one User, one Device, and one Pending DeviceCommand.

    The seeded rows give the snapshot something concrete to protect:
    if a buggy handler accidentally ran (e.g. by transitioning the
    pending command to ``SENT`` before the token check), the snapshot
    diff would catch it.
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

    cmd = DeviceCommand(
        device_id=device.id,
        command_type="ping",
        payload={"x": 1},
        status=DeviceCommandStatus.PENDING,
    )
    db.add(cmd)
    db.commit()
    db.refresh(cmd)

    return user, device, cmd


def _snapshot_rows(db) -> dict:
    """Capture a deep snapshot of all Device and DeviceCommand rows.

    The snapshot includes every mutable column we care about so we can
    detect any in-place update that leaves row counts unchanged. Two
    snapshots compare equal if and only if no row was added, removed,
    or modified.
    """
    db.expire_all()
    devices = {
        d.id: (
            d.user_id,
            d.device_code,
            d.name,
            d.status,
            d.last_seen_at,
        )
        for d in db.query(Device).all()
    }
    commands = {
        c.id: (
            c.device_id,
            c.command_type,
            tuple(sorted(c.payload.items()))
            if isinstance(c.payload, dict)
            else c.payload,
            c.status,
            c.sent_at,
            c.acknowledged_at,
        )
        for c in db.query(DeviceCommand).all()
    }
    return {"devices": devices, "commands": commands}


@pytest.fixture
def client(db_session, monkeypatch):
    """TestClient wired to the per-test ``db_session`` and a known token.

    Overrides ``get_db`` so the handler and the test share the same
    in-memory SQLite session. Sets ``settings.device_api_token`` to a
    fixed value so the "wrong token" Hypothesis strategy can always
    produce a non-matching value.
    """

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(settings, "device_api_token", VALID_TOKEN)
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


# ── Generators ─────────────────────────────────────────────────────


# The three device-facing routes (Req 9.1).
ROUTE_KINDS = ("pending", "ack", "status")
route_strategy = st.sampled_from(ROUTE_KINDS)


# Three "bad token" modes covering the full Req 9.2 surface:
#   * "missing": no ``X-Device-Token`` header at all
#   * "empty":   ``X-Device-Token`` sent with an empty string value
#   * "wrong":   ``X-Device-Token`` sent with a non-matching value
TOKEN_MODES = ("missing", "empty", "wrong")
token_mode_strategy = st.sampled_from(TOKEN_MODES)


# Wrong-token values: visible ASCII (no whitespace, CR/LF) so httpx
# accepts them as valid HTTP header values, and never equal to the
# configured ``VALID_TOKEN``.
wrong_token_strategy = st.text(
    alphabet=st.characters(min_codepoint=33, max_codepoint=126),
    min_size=1,
    max_size=24,
).filter(lambda s: s != VALID_TOKEN)


def _build_headers(*, mode: str, wrong_token: str) -> dict[str, str]:
    if mode == "missing":
        return {}
    if mode == "empty":
        return {"X-Device-Token": ""}
    if mode == "wrong":
        return {"X-Device-Token": wrong_token}
    raise AssertionError(f"unknown token mode {mode!r}")  # pragma: no cover


def _issue_request(
    test_client: TestClient,
    *,
    route: str,
    device_code: str,
    command_id: str,
    headers: dict[str, str],
):
    """Issue a request to one of the three device-facing routes.

    For ``status`` we send a syntactically valid JSON body so the test
    cannot accidentally trip a 422 from body parsing instead of the 401
    we are asserting against.
    """
    if route == "pending":
        return test_client.get(
            f"/devices/{device_code}/commands/pending",
            headers=headers,
        )
    if route == "ack":
        return test_client.post(
            f"/devices/{device_code}/commands/{command_id}/ack",
            headers=headers,
        )
    if route == "status":
        return test_client.post(
            f"/devices/{device_code}/status",
            headers=headers,
            json={"status": "online"},
        )
    raise AssertionError(f"unknown route kind {route!r}")  # pragma: no cover


# ── Property DA1: Token check precedes lookup ─────────────────────


# Feature: agent-runtime-and-apis, Property DA1: Token check precedes lookup
# **Validates: Requirements 9.2, 9.4**
@hyp_settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    route=route_strategy,
    token_mode=token_mode_strategy,
    wrong_token=wrong_token_strategy,
    use_unknown_device_code=st.booleans(),
)
def test_property_da1_token_check_precedes_lookup(
    route,
    token_mode,
    wrong_token,
    use_unknown_device_code,
    client,
    db_session,
):
    """Property DA1: bad-token requests return 401 and never mutate state.

    For any of the three device-facing routes and any "bad token" mode
    (missing, empty, or wrong), the response must be HTTP 401 and the
    full ``Device`` + ``DeviceCommand`` row state must be identical
    before and after the call. The same must hold whether the path
    ``device_code`` exists or not — proving the token check fires before
    any DB lookup.

    Validates: Requirements 9.2, 9.4
    """
    _, device, cmd = _seed(db_session)

    device_code = (
        device.device_code
        if not use_unknown_device_code
        else f"missing-{uuid4()}"
    )
    command_id = cmd.id

    snapshot_before = _snapshot_rows(db_session)

    headers = _build_headers(mode=token_mode, wrong_token=wrong_token)
    response = _issue_request(
        client,
        route=route,
        device_code=device_code,
        command_id=command_id,
        headers=headers,
    )

    # Req 9.2: bad token → 401.
    assert response.status_code == 401, (
        f"Expected 401 for route={route!r} token_mode={token_mode!r} "
        f"unknown_device={use_unknown_device_code!r}, got "
        f"{response.status_code}: {response.text}"
    )

    # Req 9.4: the *configured* ``device_api_token`` must NOT appear in
    # the response body. We deliberately do not assert that a
    # client-supplied wrong token is absent from the body: Req 9.4
    # protects the server's secret, and Hypothesis can shrink
    # ``wrong_token`` to a single character (e.g. ``'U'``) that
    # legitimately occurs inside a generic 401 envelope like
    # ``{"detail":"Unauthorized"}`` without representing a leak.
    body_text = response.text
    assert VALID_TOKEN not in body_text, (
        "Configured device_api_token must not leak into the response body."
    )

    # Req 9.2: no row may be mutated when the token check fails.
    snapshot_after = _snapshot_rows(db_session)
    assert snapshot_after == snapshot_before, (
        "Bad-token requests must not mutate any Device or DeviceCommand "
        f"row (Req 9.2). before={snapshot_before!r} "
        f"after={snapshot_after!r}"
    )


# ── Concrete table-driven supplement ───────────────────────────────


@pytest.mark.parametrize(
    "route",
    ["pending", "ack", "status"],
)
@pytest.mark.parametrize(
    "token_mode",
    ["missing", "empty", "wrong"],
)
def test_da1_concrete_examples(
    route, token_mode, client, db_session
):
    """Concrete table-driven example exercising every (route, mode) pair.

    Acts as a deterministic supplement to the Hypothesis-driven property
    test above — easier to read when triaging a shrinker output.

    Validates: Requirements 9.2, 9.4
    """
    _, device, cmd = _seed(db_session)
    snapshot_before = _snapshot_rows(db_session)

    headers = _build_headers(mode=token_mode, wrong_token="not-the-token")
    response = _issue_request(
        client,
        route=route,
        device_code=device.device_code,
        command_id=cmd.id,
        headers=headers,
    )

    assert response.status_code == 401
    assert VALID_TOKEN not in response.text
    assert _snapshot_rows(db_session) == snapshot_before


# ── Property DA2: Unknown device_code → 404 ───────────────────────


# Unknown ``device_code`` strategy: visible ASCII without forward
# slashes (which would break the URL path), non-empty, and prefixed
# with ``"missing-"`` so it can never collide with the seeded device
# code (which uses ``f"dev-{uuid4()}"``).
unknown_device_code_strategy = st.text(
    alphabet=st.characters(
        min_codepoint=33,
        max_codepoint=126,
        blacklist_characters="/?#",
    ),
    min_size=1,
    max_size=24,
).map(lambda s: f"missing-{s}")


# Feature: agent-runtime-and-apis, Property DA2: Unknown device_code → 404
# **Validates: Requirement 9.3**
@hyp_settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    route=route_strategy,
    unknown_device_code=unknown_device_code_strategy,
)
def test_property_da2_unknown_device_code_returns_404(
    route,
    unknown_device_code,
    client,
    db_session,
):
    """Property DA2: valid token + unknown device_code → 404, no mutation.

    For any of the three device-facing routes, when the request carries
    a valid ``X-Device-Token`` header but a ``device_code`` that does
    not match any ``Device`` row, the response must be HTTP 404. The
    full ``Device`` + ``DeviceCommand`` row state must remain identical
    before and after the call (no row may be created, deleted, or
    modified by a 404 path).

    Validates: Requirement 9.3
    """
    _, _, cmd = _seed(db_session)

    snapshot_before = _snapshot_rows(db_session)

    headers = {"X-Device-Token": VALID_TOKEN}
    response = _issue_request(
        client,
        route=route,
        device_code=unknown_device_code,
        command_id=cmd.id,
        headers=headers,
    )

    # Req 9.3: unknown device_code with a valid token → 404.
    assert response.status_code == 404, (
        f"Expected 404 for route={route!r} "
        f"unknown_device_code={unknown_device_code!r}, got "
        f"{response.status_code}: {response.text}"
    )

    # No mutation must occur on the 404 path.
    snapshot_after = _snapshot_rows(db_session)
    assert snapshot_after == snapshot_before, (
        "Unknown-device 404 responses must not mutate any Device or "
        f"DeviceCommand row (Req 9.3). before={snapshot_before!r} "
        f"after={snapshot_after!r}"
    )


@pytest.mark.parametrize("route", ["pending", "ack", "status"])
def test_da2_concrete_unknown_device_code(route, client, db_session):
    """Concrete example exercising every route with a fixed unknown code.

    Acts as a deterministic supplement to the Hypothesis-driven property
    test above — easier to read when triaging a shrinker output.

    Validates: Requirement 9.3
    """
    _, _, cmd = _seed(db_session)
    snapshot_before = _snapshot_rows(db_session)

    headers = {"X-Device-Token": VALID_TOKEN}
    unknown_code = f"missing-{uuid4()}"
    response = _issue_request(
        client,
        route=route,
        device_code=unknown_code,
        command_id=cmd.id,
        headers=headers,
    )

    assert response.status_code == 404
    assert _snapshot_rows(db_session) == snapshot_before


# ── Property DA3: Atomic Mark-Sent invariant ───────────────────────


def _seed_user_device(db) -> tuple[User, Device]:
    """Insert one User and one Device with no commands.

    Used by DA3 so the test can control exactly how many ``PENDING``
    commands exist for the device.
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

    return user, device


def _seed_pending_commands(db, device: Device, n: int) -> list[str]:
    """Insert ``n`` ``PENDING`` ``DeviceCommand`` rows for ``device``.

    Returns the list of inserted ``command.id`` values in insertion
    order so the test can assert ``poll_1`` returns the exact same set
    (Req 10.1, 10.2).
    """
    ids: list[str] = []
    for i in range(n):
        cmd = DeviceCommand(
            device_id=device.id,
            command_type="ping",
            payload={"i": i},
            status=DeviceCommandStatus.PENDING,
        )
        db.add(cmd)
        db.commit()
        db.refresh(cmd)
        ids.append(cmd.id)
    return ids


# Feature: agent-runtime-and-apis, Property DA3: Atomic Mark-Sent invariant
# **Validates: Requirements 10.1, 10.2, 10.3, 10.4**
@hyp_settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(n=st.integers(min_value=0, max_value=8))
def test_property_da3_atomic_mark_sent_invariant(n, client, db_session):
    """Property DA3: two consecutive polls drain the pending queue atomically.

    For any number ``n ∈ [0, 8]`` of ``PENDING`` commands seeded for one
    device, the first ``GET /devices/{device_code}/commands/pending``
    call must:

    1. Return HTTP 200 with a JSON list of exactly ``n`` items, each
       whose ``command_id`` matches a seeded id (Req 10.1, 10.2).
    2. Transition every returned row to ``DeviceCommandStatus.SENT``
       with a non-null ``sent_at`` timestamp before responding
       (Req 10.4 — single-transaction Atomic Mark-Sent).

    A second poll, with no new pending command queued in between, must
    return HTTP 200 with an empty list ``[]`` (Req 10.3).

    Validates: Requirements 10.1, 10.2, 10.3, 10.4
    """
    # Clear any leftover rows from a prior Hypothesis example reusing
    # the same function-scoped ``db_session``.
    db_session.query(DeviceCommand).delete()
    db_session.query(Device).delete()
    db_session.query(User).delete()
    db_session.commit()

    _, device = _seed_user_device(db_session)
    seeded_ids = _seed_pending_commands(db_session, device, n)

    headers = {"X-Device-Token": VALID_TOKEN}

    # ── poll_1 ─────────────────────────────────────────────────────
    poll_1 = client.get(
        f"/devices/{device.device_code}/commands/pending",
        headers=headers,
    )
    assert poll_1.status_code == 200, poll_1.text
    body_1 = poll_1.json()
    assert isinstance(body_1, list), f"poll_1.body must be a JSON list (Req 10.1), got {body_1!r}"
    assert len(body_1) == n, (
        f"poll_1 must return all {n} pending commands (Req 10.1, 10.2); "
        f"got {len(body_1)} items"
    )

    returned_ids = [item["command_id"] for item in body_1]
    assert set(returned_ids) == set(seeded_ids), (
        "poll_1 must include exactly the seeded pending command ids "
        f"(Req 10.2); seeded={seeded_ids!r} returned={returned_ids!r}"
    )

    # Req 10.4: every returned row must now be SENT with sent_at set.
    db_session.expire_all()
    for cmd_id in returned_ids:
        row = (
            db_session.query(DeviceCommand)
            .filter(DeviceCommand.id == cmd_id)
            .one()
        )
        assert row.status == DeviceCommandStatus.SENT, (
            f"Command {cmd_id} must be SENT after poll_1 (Req 10.4); "
            f"got status={row.status!r}"
        )
        assert row.sent_at is not None, (
            f"Command {cmd_id} must have sent_at set after poll_1 (Req 10.4)"
        )

    # ── poll_2 ─────────────────────────────────────────────────────
    poll_2 = client.get(
        f"/devices/{device.device_code}/commands/pending",
        headers=headers,
    )
    assert poll_2.status_code == 200, poll_2.text
    assert poll_2.json() == [], (
        "poll_2 must be empty when no new pending command was queued "
        f"between polls (Req 10.3); got {poll_2.json()!r}"
    )


@pytest.mark.parametrize("n", [0, 1, 3])
def test_da3_concrete_examples(n, client, db_session):
    """Concrete examples for DA3 across small ``n`` values.

    Acts as a deterministic supplement to the Hypothesis-driven property
    test above — easier to read when triaging a shrinker output.

    Validates: Requirements 10.1, 10.2, 10.3, 10.4
    """
    _, device = _seed_user_device(db_session)
    seeded_ids = _seed_pending_commands(db_session, device, n)

    headers = {"X-Device-Token": VALID_TOKEN}

    poll_1 = client.get(
        f"/devices/{device.device_code}/commands/pending",
        headers=headers,
    )
    assert poll_1.status_code == 200
    body_1 = poll_1.json()
    assert isinstance(body_1, list)
    assert len(body_1) == n
    assert {item["command_id"] for item in body_1} == set(seeded_ids)

    db_session.expire_all()
    for cmd_id in seeded_ids:
        row = (
            db_session.query(DeviceCommand)
            .filter(DeviceCommand.id == cmd_id)
            .one()
        )
        assert row.status == DeviceCommandStatus.SENT
        assert row.sent_at is not None

    poll_2 = client.get(
        f"/devices/{device.device_code}/commands/pending",
        headers=headers,
    )
    assert poll_2.status_code == 200
    assert poll_2.json() == []


# ── Property DA4: Ack happy-path and not-found ─────────────────────


def _seed_two_devices_with_commands(
    db,
) -> tuple[User, Device, Device, DeviceCommand, DeviceCommand]:
    """Insert one User, two Devices (A and B), each with a PENDING command.

    Returns ``(user, device_a, device_b, cmd_a, cmd_b)`` where:

    - ``cmd_a.device_id == device_a.id``
    - ``cmd_b.device_id == device_b.id``
    - both commands start in ``DeviceCommandStatus.PENDING`` with
      ``acknowledged_at`` unset.

    This shape is the minimum needed to exercise the three DA4
    scenarios: ``owned`` (ack ``cmd_a`` against ``device_a``),
    ``missing`` (ack a non-existent ``command_id`` against ``device_a``),
    and ``other_device`` (ack ``cmd_b`` against ``device_a``).
    """
    sfx = uuid4().hex
    user = User(name=f"User {sfx}", email=f"user-{sfx}@taskbot.local")
    db.add(user)
    db.commit()
    db.refresh(user)

    device_a = Device(
        user_id=user.id,
        device_code=f"dev-a-{uuid4()}",
        name="Device A",
        status=DeviceStatus.OFFLINE,
    )
    device_b = Device(
        user_id=user.id,
        device_code=f"dev-b-{uuid4()}",
        name="Device B",
        status=DeviceStatus.OFFLINE,
    )
    db.add_all([device_a, device_b])
    db.commit()
    db.refresh(device_a)
    db.refresh(device_b)

    cmd_a = DeviceCommand(
        device_id=device_a.id,
        command_type="ping",
        payload={"side": "a"},
        status=DeviceCommandStatus.PENDING,
    )
    cmd_b = DeviceCommand(
        device_id=device_b.id,
        command_type="ping",
        payload={"side": "b"},
        status=DeviceCommandStatus.PENDING,
    )
    db.add_all([cmd_a, cmd_b])
    db.commit()
    db.refresh(cmd_a)
    db.refresh(cmd_b)

    return user, device_a, device_b, cmd_a, cmd_b


# Three DA4 scenarios. ``hypothesis`` picks one per example; the test
# body branches on it to build the request and the assertions.
DA4_SCENARIOS = ("owned", "missing", "other_device")
da4_scenario_strategy = st.sampled_from(DA4_SCENARIOS)


# Feature: agent-runtime-and-apis, Property DA4: Ack happy-path and not-found
# **Validates: Requirements 11.1, 11.2**
@hyp_settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(scenario=da4_scenario_strategy)
def test_property_da4_ack_happy_path_and_not_found(
    scenario, client, db_session
):
    """Property DA4: ack returns 200 only for a command owned by the device.

    Seeds one User with two Devices (``A`` and ``B``), each carrying one
    ``PENDING`` ``DeviceCommand``. For each scenario the test issues
    ``POST /devices/{device_a.code}/commands/{command_id}/ack`` and
    verifies:

    - ``owned``: ``command_id == cmd_a.id`` → HTTP 200 with body
      ``{"success": True, "command_id": cmd_a.id}``; ``cmd_a`` becomes
      ``ACKNOWLEDGED`` with a non-null ``acknowledged_at``; ``cmd_b``
      stays ``PENDING`` and untouched (Req 11.1).
    - ``missing``: ``command_id`` is a fresh string that matches no row
      → HTTP 404; ``cmd_a`` stays ``PENDING`` and untouched (Req 11.2).
    - ``other_device``: ``command_id == cmd_b.id`` (belongs to
      ``device_b``) → HTTP 404; ``cmd_b`` stays ``PENDING`` and
      untouched (Req 11.2).

    Validates: Requirements 11.1, 11.2
    """
    # Clear any leftover rows from a prior Hypothesis example reusing
    # the same function-scoped ``db_session``.
    db_session.query(DeviceCommand).delete()
    db_session.query(Device).delete()
    db_session.query(User).delete()
    db_session.commit()

    _, device_a, device_b, cmd_a, cmd_b = _seed_two_devices_with_commands(
        db_session
    )
    cmd_a_id = cmd_a.id
    cmd_b_id = cmd_b.id

    # Decide which command_id to use in the URL based on the scenario.
    if scenario == "owned":
        target_command_id = cmd_a_id
    elif scenario == "missing":
        target_command_id = f"missing-{uuid4()}"
    elif scenario == "other_device":
        target_command_id = cmd_b_id
    else:  # pragma: no cover - exhaustive on DA4_SCENARIOS
        raise AssertionError(f"unknown scenario {scenario!r}")

    snapshot_before = _snapshot_rows(db_session)

    headers = {"X-Device-Token": VALID_TOKEN}
    response = client.post(
        f"/devices/{device_a.device_code}/commands/{target_command_id}/ack",
        headers=headers,
    )

    db_session.expire_all()
    row_a = (
        db_session.query(DeviceCommand)
        .filter(DeviceCommand.id == cmd_a_id)
        .one()
    )
    row_b = (
        db_session.query(DeviceCommand)
        .filter(DeviceCommand.id == cmd_b_id)
        .one()
    )

    if scenario == "owned":
        # Req 11.1: 200 + acknowledgement body.
        assert response.status_code == 200, response.text
        assert response.json() == {
            "success": True,
            "command_id": cmd_a_id,
        }, (
            "Owned ack must echo {success: true, command_id: <id>} "
            f"(Req 11.1); got {response.json()!r}"
        )

        # Req 11.1: cmd_a transitioned to ACKNOWLEDGED with timestamp.
        assert row_a.status == DeviceCommandStatus.ACKNOWLEDGED, (
            "Owned ack must transition the command to ACKNOWLEDGED "
            f"(Req 11.1); got status={row_a.status!r}"
        )
        assert row_a.acknowledged_at is not None, (
            "Owned ack must set acknowledged_at on the command (Req 11.1)"
        )

        # The other device's command must remain PENDING and untouched.
        assert row_b.status == DeviceCommandStatus.PENDING, (
            "Owned ack must not touch commands of other devices "
            f"(Req 11.2); got cmd_b.status={row_b.status!r}"
        )
        assert row_b.acknowledged_at is None
    else:
        # Both ``missing`` and ``other_device`` resolve to a 404 with
        # zero mutation (Req 11.2).
        assert response.status_code == 404, (
            f"Scenario {scenario!r} must return 404 (Req 11.2); got "
            f"{response.status_code}: {response.text}"
        )

        # Both commands must remain PENDING with no ack timestamp.
        assert row_a.status == DeviceCommandStatus.PENDING
        assert row_a.acknowledged_at is None
        assert row_b.status == DeviceCommandStatus.PENDING
        assert row_b.acknowledged_at is None

        # And no row anywhere may have been added/removed/modified.
        snapshot_after = _snapshot_rows(db_session)
        assert snapshot_after == snapshot_before, (
            f"404 ack ({scenario!r}) must not mutate any row "
            f"(Req 11.2). before={snapshot_before!r} "
            f"after={snapshot_after!r}"
        )


@pytest.mark.parametrize("scenario", ["owned", "missing", "other_device"])
def test_da4_concrete_examples(scenario, client, db_session):
    """Concrete table-driven example for each DA4 scenario.

    Acts as a deterministic supplement to the Hypothesis-driven property
    test above — easier to read when triaging a shrinker output.

    Validates: Requirements 11.1, 11.2
    """
    _, device_a, _, cmd_a, cmd_b = _seed_two_devices_with_commands(db_session)
    cmd_a_id = cmd_a.id
    cmd_b_id = cmd_b.id

    if scenario == "owned":
        target_command_id = cmd_a_id
    elif scenario == "missing":
        target_command_id = f"missing-{uuid4()}"
    else:
        target_command_id = cmd_b_id

    snapshot_before = _snapshot_rows(db_session)

    headers = {"X-Device-Token": VALID_TOKEN}
    response = client.post(
        f"/devices/{device_a.device_code}/commands/{target_command_id}/ack",
        headers=headers,
    )

    db_session.expire_all()
    row_a = (
        db_session.query(DeviceCommand)
        .filter(DeviceCommand.id == cmd_a_id)
        .one()
    )
    row_b = (
        db_session.query(DeviceCommand)
        .filter(DeviceCommand.id == cmd_b_id)
        .one()
    )

    if scenario == "owned":
        assert response.status_code == 200
        assert response.json() == {"success": True, "command_id": cmd_a_id}
        assert row_a.status == DeviceCommandStatus.ACKNOWLEDGED
        assert row_a.acknowledged_at is not None
        assert row_b.status == DeviceCommandStatus.PENDING
        assert row_b.acknowledged_at is None
    else:
        assert response.status_code == 404
        assert row_a.status == DeviceCommandStatus.PENDING
        assert row_a.acknowledged_at is None
        assert row_b.status == DeviceCommandStatus.PENDING
        assert row_b.acknowledged_at is None
        assert _snapshot_rows(db_session) == snapshot_before


# ── Property DA5: Status update validation ─────────────────────────


# The set of values the API must accept on the status update endpoint
# (Req 11.3). Anything outside this set must be rejected with HTTP 422
# and zero mutation (Req 11.4).
VALID_STATUS_VALUES = frozenset({DeviceStatus.ONLINE, DeviceStatus.OFFLINE})


# Curated set of status values that exercises both sides of the
# validation boundary in obvious ways:
# - "online", "offline": valid (Req 11.3)
# - "OFFLINE", "weird", "", "999": invalid (Req 11.4); covers the four
#   most plausible client mistakes — uppercase variant, free-form text,
#   blank string, and a numeric-looking string.
_CURATED_STATUS_VALUES = (
    "online",
    "offline",
    "OFFLINE",
    "weird",
    "",
    "999",
)


# General free-form strategy. Restricted to printable ASCII (no quotes
# that would break JSON, no control characters) so that ``httpx`` and
# the Pydantic schema treat the value as a string field, allowing it to
# reach the handler's explicit validation check rather than tripping a
# JSON-decode error.
_freeform_status_strategy = st.text(
    alphabet=st.characters(
        min_codepoint=33,
        max_codepoint=126,
        blacklist_characters="\"\\",
    ),
    min_size=0,
    max_size=12,
)


status_value_strategy = st.one_of(
    st.sampled_from(_CURATED_STATUS_VALUES),
    _freeform_status_strategy,
)


# Feature: agent-runtime-and-apis, Property DA5: Status update validation
# **Validates: Requirements 11.3, 11.4**
@hyp_settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(status_value=status_value_strategy)
def test_property_da5_status_update_validation(
    status_value, client, db_session
):
    """Property DA5: ``POST /devices/{device_code}/status`` validates the
    ``status`` field strictly against ``{"online", "offline"}``.

    For any string ``status_value``:

    - If ``status_value ∈ {"online", "offline"}`` (Req 11.3), the
      endpoint must respond with HTTP 200, the JSON body must include
      ``status == status_value`` and a non-null ``last_seen_at``, and
      the persisted ``Device`` row must be updated to match (its
      ``status`` column equal to ``status_value`` and its
      ``last_seen_at`` column populated with a timezone-aware datetime).
    - Otherwise (Req 11.4), the endpoint must respond with HTTP 422 and
      the full ``Device`` + ``DeviceCommand`` row state must be
      identical before and after the call (no mutation).

    Validates: Requirements 11.3, 11.4
    """
    # Clear any leftover rows from a prior Hypothesis example reusing
    # the same function-scoped ``db_session``.
    db_session.query(DeviceCommand).delete()
    db_session.query(Device).delete()
    db_session.query(User).delete()
    db_session.commit()

    # Seed a User + Device with a known starting state so the assertions
    # have something concrete to verify against. ``last_seen_at`` is
    # left at ``None`` so the post-update non-null assertion is
    # meaningful.
    sfx = uuid4().hex
    user = User(name=f"User {sfx}", email=f"user-{sfx}@taskbot.local")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    device = Device(
        user_id=user.id,
        device_code=f"dev-{uuid4()}",
        name="Bench device",
        status=DeviceStatus.OFFLINE,
    )
    db_session.add(device)
    db_session.commit()
    db_session.refresh(device)

    device_id = device.id
    device_code = device.device_code

    snapshot_before = _snapshot_rows(db_session)

    headers = {"X-Device-Token": VALID_TOKEN}
    response = client.post(
        f"/devices/{device_code}/status",
        headers=headers,
        json={"status": status_value},
    )

    db_session.expire_all()

    if status_value in VALID_STATUS_VALUES:
        # Req 11.3: valid status → 200 with echoed fields.
        assert response.status_code == 200, (
            f"Expected 200 for valid status={status_value!r}, got "
            f"{response.status_code}: {response.text}"
        )

        body = response.json()
        assert body.get("status") == status_value, (
            "Response body must echo the new status (Req 11.3); "
            f"got {body!r}"
        )
        assert body.get("last_seen_at") is not None, (
            "Response body must include a non-null last_seen_at after "
            f"a successful status update (Req 11.3); got {body!r}"
        )

        # The persisted row must mirror the response.
        row = (
            db_session.query(Device)
            .filter(Device.id == device_id)
            .one()
        )
        assert row.status == status_value, (
            "Device.status column must be updated to match the supplied "
            f"value (Req 11.3); got {row.status!r}"
        )
        assert row.last_seen_at is not None, (
            "Device.last_seen_at column must be set after a successful "
            "status update (Req 11.3)"
        )
    else:
        # Req 11.4: invalid status → 422 with no mutation.
        assert response.status_code == 422, (
            f"Expected 422 for invalid status={status_value!r}, got "
            f"{response.status_code}: {response.text}"
        )

        snapshot_after = _snapshot_rows(db_session)
        assert snapshot_after == snapshot_before, (
            "Invalid-status 422 responses must not mutate any Device "
            f"or DeviceCommand row (Req 11.4). status={status_value!r} "
            f"before={snapshot_before!r} after={snapshot_after!r}"
        )


@pytest.mark.parametrize(
    "status_value,expected_code",
    [
        ("online", 200),
        ("offline", 200),
        ("OFFLINE", 422),
        ("weird", 422),
        ("", 422),
        ("999", 422),
    ],
)
def test_da5_concrete_examples(
    status_value, expected_code, client, db_session
):
    """Concrete table-driven example for DA5.

    Acts as a deterministic supplement to the Hypothesis-driven property
    test above — easier to read when triaging a shrinker output.

    Validates: Requirements 11.3, 11.4
    """
    sfx = uuid4().hex
    user = User(name=f"User {sfx}", email=f"user-{sfx}@taskbot.local")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    device = Device(
        user_id=user.id,
        device_code=f"dev-{uuid4()}",
        name="Bench device",
        status=DeviceStatus.OFFLINE,
    )
    db_session.add(device)
    db_session.commit()
    db_session.refresh(device)

    device_id = device.id
    snapshot_before = _snapshot_rows(db_session)

    headers = {"X-Device-Token": VALID_TOKEN}
    response = client.post(
        f"/devices/{device.device_code}/status",
        headers=headers,
        json={"status": status_value},
    )

    db_session.expire_all()

    assert response.status_code == expected_code

    if expected_code == 200:
        body = response.json()
        assert body["status"] == status_value
        assert body["last_seen_at"] is not None

        row = (
            db_session.query(Device)
            .filter(Device.id == device_id)
            .one()
        )
        assert row.status == status_value
        assert row.last_seen_at is not None
    else:
        assert _snapshot_rows(db_session) == snapshot_before
