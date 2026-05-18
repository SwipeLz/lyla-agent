# app/api/ — FastAPI Handlers

## OVERVIEW
Thin async handlers. Validate via Pydantic, dispatch to service/agent layer, never embed business logic. Exception → HTTP mapping is centralized.

## FILES

```
agent.py      # POST /agent/text — main agent entry
devices.py    # /devices/{device_code}/... — token-gated, ESP32 polls here
dashboard.py  # /dashboard/... — task/expense/summary for web UI
health.py     # /healthz
_errors.py    # register_exception_handlers(app) — service exception → HTTP
```

## EXCEPTION MAPPING (do NOT raise HTTPException directly)

`_errors.register_exception_handlers(app)` runs once in `main.py` BEFORE routers are included. It maps:

| Service exception | HTTP | Body |
|---|---|---|
| `NotFoundError` | 404 | `{"detail": "..."}` |
| `ValidationError` | 422 | `{"detail": "..."}` |
| `PermissionDeniedError` | 403 | `{"detail": "..."}` |

Pydantic validation failures stay at FastAPI's default 422.

## ENDPOINT-SPECIFIC RULES

- **`POST /agent/text`** — body needs `user_id` + `text` (required), `device_id` + `timezone` (optional). Empty/whitespace `text` → 422. Invalid `user_id`/`device_id` → 404 (agent NOT invoked). Agent runtime exception → 500, but `VoiceCommandLog` is still written with `status="error"`. Never leak stack traces to client.
- **`/devices/{device_code}/...`** — guarded by device API token header. Used by ESP32 polling.
- **`/dashboard/...`** — `DASHBOARD_AUTH_MODE` config gates this. Default `"none"` for MVP; flip to `"shared_header"` before public exposure (sets `X-Dashboard-Token` requirement).

## RULES

- **Async handlers** wrap sync service calls; let SQLAlchemy run on the request thread.
- **No business logic.** If you find yourself writing an `if` over domain state, push it into `services/`.
- **Always log voice commands** in `POST /agent/text` even on failure (the test suite checks this).

## ANTI-PATTERNS

- Raising `HTTPException` from inside `services/` to "shortcut" the error path — bypasses the central mapping and breaks tests.
- Catching service exceptions in handlers and re-raising as HTTPException — duplicates work `_errors.py` already does.
- Skipping `VoiceCommandLog` write on the 500 path of `/agent/text`.
