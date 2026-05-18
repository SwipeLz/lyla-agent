# alembic/ — Database Migrations

## OVERVIEW
Alembic-managed schema migrations. SQLite for MVP, but written to be portable to PostgreSQL.

## FILES

```
env.py               # imports app.models metadata, configures online/offline migration
script.py.mako       # revision template
versions/            # actual migration revisions
```

## CONVENTIONS

- **UUID columns as `String(36)`** — never SQLite-specific types. Keeps PostgreSQL migration path clean.
- **Timezone-aware datetimes** (`DateTime(timezone=True)`) — always.
- **Filename template** is set in `alembic.ini`: `%%(year)d_%%(month).2d_%%(rev)s_%%(slug)s`. Don't override per-revision.
- **One revision per logical change.** Don't bundle unrelated table edits.
- **Always run `alembic upgrade head`** after pulling new migrations and after seeding for the first time.

## TYPICAL WORKFLOW

```bash
# Create a new revision after editing app/models/*.py
alembic revision --autogenerate -m "<short slug>"

# Inspect the generated file in alembic/versions/ — autogenerate is a starting point, not an oracle
# Edit if needed (e.g., custom data migration, type adjustments)

# Apply
alembic upgrade head

# Rollback last revision
alembic downgrade -1
```

## ANTI-PATTERNS

- **Editing an applied revision file** — breaks reproducibility. Create a new revision instead.
- **SQLite-only column types** (e.g., raw INTEGER PRIMARY KEY for ids) — blocks PostgreSQL migration.
- **Skipping autogenerate review** — it misses index/constraint changes; always read the diff.
- **Running migrations from a non-project-root CWD** — `script_location = alembic` is relative to the project root.
- **Multiple unrelated changes per revision** — hard to roll back surgically.
