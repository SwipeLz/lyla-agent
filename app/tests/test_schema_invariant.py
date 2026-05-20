"""Schema-invariant property test.

Covers Property X2 from the agent-runtime-and-apis design document:

    Property X2: Schema unchanged
    The set of tables and columns reported by ``Base.metadata`` after
    Phase 4–8 SHALL equal the set after Phase 3.

The Phase 3 reference set is captured below as ``PHASE3_SCHEMA``. Any
addition, removal, or column-type change to a model registered on
``Base.metadata`` will fail this test loudly, enforcing Requirement
15.8 ("SHALL NOT modify Phase 2 database schema columns; new tables or
columns are out of scope").

**Validates: Requirement 15.8**
"""
from __future__ import annotations

# Importing the models package registers every table on ``Base.metadata``.
import app.models  # noqa: F401
from app.db import Base


# ---------------------------------------------------------------------------
# Phase 3 reference snapshot — DO NOT EDIT without an explicit requirement
# update + matching Alembic migration. Tuples are
# ``(table_name, column_name, str(column.type))`` and the set is sorted at
# comparison time so ordering is irrelevant.
# ---------------------------------------------------------------------------
PHASE3_SCHEMA: frozenset[tuple[str, str, str]] = frozenset(
    {
        # device_commands
        ("device_commands", "acknowledged_at", "DATETIME"),
        ("device_commands", "command_type", "VARCHAR"),
        ("device_commands", "created_at", "DATETIME"),
        ("device_commands", "device_id", "VARCHAR"),
        ("device_commands", "id", "VARCHAR"),
        ("device_commands", "payload", "JSON"),
        ("device_commands", "sent_at", "DATETIME"),
        ("device_commands", "status", "VARCHAR"),
        # devices
        ("devices", "created_at", "DATETIME"),
        ("devices", "device_code", "VARCHAR"),
        ("devices", "id", "VARCHAR"),
        ("devices", "last_seen_at", "DATETIME"),
        ("devices", "name", "VARCHAR"),
        ("devices", "status", "VARCHAR"),
        ("devices", "user_id", "VARCHAR"),
        ("devices", "api_token", "VARCHAR"),
        ("devices", "firmware_version", "VARCHAR(64)"),
        ("devices", "wifi_rssi_dbm", "INTEGER"),
        ("devices", "battery_pct", "INTEGER"),
        ("devices", "free_heap_bytes", "INTEGER"),
        # expenses
        ("expenses", "amount", "INTEGER"),
        ("expenses", "category", "VARCHAR"),
        ("expenses", "created_at", "DATETIME"),
        ("expenses", "id", "VARCHAR"),
        ("expenses", "note", "VARCHAR"),
        ("expenses", "spent_at", "DATETIME"),
        ("expenses", "user_id", "VARCHAR"),
        # reminders
        ("reminders", "channel", "VARCHAR"),
        ("reminders", "created_at", "DATETIME"),
        ("reminders", "id", "VARCHAR"),
        ("reminders", "remind_at", "DATETIME"),
        ("reminders", "status", "VARCHAR"),
        ("reminders", "task_id", "VARCHAR"),
        ("reminders", "title", "VARCHAR"),
        ("reminders", "user_id", "VARCHAR"),
        # tasks
        ("tasks", "course", "VARCHAR"),
        ("tasks", "created_at", "DATETIME"),
        ("tasks", "deadline_at", "DATETIME"),
        ("tasks", "id", "VARCHAR"),
        ("tasks", "priority", "VARCHAR"),
        ("tasks", "reminder_at", "DATETIME"),
        ("tasks", "status", "VARCHAR"),
        ("tasks", "title", "VARCHAR"),
        ("tasks", "user_id", "VARCHAR"),
        # users
        ("users", "created_at", "DATETIME"),
        ("users", "email", "VARCHAR"),
        ("users", "id", "VARCHAR"),
        ("users", "name", "VARCHAR"),
        ("users", "whatsapp_number", "VARCHAR"),
        # voice_command_logs
        ("voice_command_logs", "created_at", "DATETIME"),
        ("voice_command_logs", "device_id", "VARCHAR"),
        ("voice_command_logs", "id", "VARCHAR"),
        ("voice_command_logs", "input_text", "TEXT"),
        ("voice_command_logs", "parsed_actions", "JSON"),
        ("voice_command_logs", "response_text", "TEXT"),
        ("voice_command_logs", "status", "VARCHAR"),
        ("voice_command_logs", "user_id", "VARCHAR"),
        ("voice_command_logs", "metadata_json", "JSON"),
        ("voice_command_logs", "request_received_at", "DATETIME"),
        ("voice_command_logs", "response_sent_at", "DATETIME"),
    }
)


def _live_schema() -> frozenset[tuple[str, str, str]]:
    """Return the current ``(table, column, type)`` set from Base.metadata."""
    return frozenset(
        (table_name, column.name, str(column.type))
        for table_name, table in Base.metadata.tables.items()
        for column in table.columns
    )


# ── Property X2: Schema unchanged ──────────────────────────────────


def test_schema_matches_phase3_reference() -> None:
    """Live schema set equals the captured Phase 3 reference set.

    **Validates: Requirement 15.8**
    """
    live = _live_schema()

    added = live - PHASE3_SCHEMA
    removed = PHASE3_SCHEMA - live

    assert not added, f"Unexpected schema additions in Phase 4–8: {sorted(added)}"
    assert not removed, f"Unexpected schema removals in Phase 4–8: {sorted(removed)}"
    assert live == PHASE3_SCHEMA
