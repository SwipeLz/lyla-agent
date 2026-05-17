# Database Plan

## Overview
- **MVP Strategy:** SQLite-first for rapid prototyping and simplified local development.
- **Future Migration:** Designed to migrate smoothly to PostgreSQL using SQLAlchemy and Alembic.
- **Connection:** Managed via the `DATABASE_URL` environment variable.

## Implemented Tables (Phase 2)

### `users`
Stores user accounts. Fields: id (UUID), name, email (unique), whatsapp_number, created_at.

### `devices`
Registered ESP32 devices linked to a user. Fields: id (UUID), user_id (FK), device_code (unique), name, status, last_seen_at, created_at.

### `tasks`
Academic tasks. Fields: id (UUID), user_id (FK), title, course, deadline_at, reminder_at, status, priority, created_at.

### `expenses`
Daily financial transactions. Fields: id (UUID), user_id (FK), amount, category, note, spent_at, created_at.

### `reminders`
Scheduled reminders, optionally linked to a task. Fields: id (UUID), user_id (FK), task_id (FK, nullable), title, remind_at, channel, status, created_at.

### `voice_command_logs`
Logs agent interactions for debugging and analytics. Fields: id (UUID), user_id (FK), device_id (FK), input_text, parsed_actions (JSON), response_text, status, created_at.

### `device_commands`
Command queue for ESP32 devices. Fields: id (UUID), device_id (FK), command_type, payload (JSON), status, created_at, sent_at, acknowledged_at.

## Migration Strategy
- **Alembic** manages all schema changes via versioned migration scripts.
- Migrations are SQLite-compatible using `render_as_batch=True`.
- `DATABASE_URL` drives the connection — switch to PostgreSQL by changing this variable.

## SQLite Implementation Notes
- Foreign keys are enforced via `PRAGMA foreign_keys=ON` on every connection.
- WAL mode can be enabled in production for better concurrent read performance.
