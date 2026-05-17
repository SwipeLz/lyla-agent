"""Manual smoke-test CLI for the Agent Runtime.

Usage:
    python -m scripts.run_agent_text "<text>" [--user-id N] [--device-id N]

Resolves ``user_id`` from ``--user-id`` or env ``TASKBOT_USER_ID``,
``device_id`` from ``--device-id`` or env ``TASKBOT_DEVICE_ID``, opens a
DB session via :data:`app.db.SessionLocal`, then runs
:func:`app.agent.runtime.run_text` against the supplied text and prints
the resulting :class:`~app.agent.result.AgentRunResult` as JSON to
stdout.

Behavioural contract (Requirement 4):

- A non-empty ``text`` argument is required (Requirement 4.2).
- Empty / whitespace-only ``text`` prints the usage to stderr and exits
  with status 2 (Requirement 4.3). The check runs before any DB session
  is opened.
- The script never imports the Google ADK SDK directly; it goes through
  ``run_text``, which only loads ``google.adk`` when
  ``agent_mode == "real"``. With ``agent_mode == "fake"`` this script
  contacts no external API (Requirement 4.4).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

from app.agent.runtime import run_text
from app.config import settings
from app.db import SessionLocal


USAGE = (
    'usage: python -m scripts.run_agent_text "<text>" '
    "[--user-id N] [--device-id N]"
)


def _build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser for the CLI.

    ``--user-id`` / ``--device-id`` fall back to ``TASKBOT_USER_ID`` /
    ``TASKBOT_DEVICE_ID`` env vars respectively. ``argparse``'s
    ``type=int`` only applies when a value is supplied on the command
    line, so env-sourced defaults are converted explicitly in
    :func:`_coerce_optional_int` after parsing.
    """
    parser = argparse.ArgumentParser(
        prog="python -m scripts.run_agent_text",
        description="Run taskbot_agent against a single text command.",
    )
    parser.add_argument("text", help="The user's text command.")
    parser.add_argument(
        "--user-id",
        default=os.environ.get("TASKBOT_USER_ID"),
        help="User id (defaults to env TASKBOT_USER_ID).",
    )
    parser.add_argument(
        "--device-id",
        default=os.environ.get("TASKBOT_DEVICE_ID"),
        help="Optional device id (defaults to env TASKBOT_DEVICE_ID).",
    )
    return parser


def _coerce_optional_int(value, *, flag: str) -> int | None:
    """Convert a CLI/env value to ``int`` or ``None``.

    Empty string and ``None`` map to ``None`` (no value supplied).
    A non-integer string prints an error to stderr and exits with
    status 2, matching argparse's own conventions.
    """
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        print(f"error: {flag} harus integer, dapat: {value!r}", file=sys.stderr)
        sys.exit(2)


async def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    # Cheap validation before opening any DB session (Requirement 4.3).
    if not args.text or not args.text.strip():
        print(USAGE, file=sys.stderr)
        sys.exit(2)

    user_id = _coerce_optional_int(args.user_id, flag="--user-id")
    device_id = _coerce_optional_int(args.device_id, flag="--device-id")

    db = SessionLocal()
    try:
        result = await run_text(
            db,
            user_id=user_id,
            device_id=device_id,
            text=args.text,
            timezone=settings.timezone,
        )
    finally:
        db.close()

    payload = {
        "reply": result.reply,
        "actions": result.actions,
        "device_feedback": result.device_feedback,
        "status": result.status,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
