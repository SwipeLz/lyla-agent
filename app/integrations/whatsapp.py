"""WhatsApp integration stub.

This module intentionally does NOT call any real WhatsApp Cloud API.
It only logs that a send was requested and returns a stub success payload.

Per Requirements 8.6 and 15.2, the WhatsApp Stub is the only
WhatsApp-shaped integration in Phase 4-8 and MUST NOT make outbound
HTTP calls. To enforce that at the import level, this module does not
import any HTTP client (`httpx`, `requests`, `urllib`).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def whatsapp_send_stub(reminder: Any) -> dict:
    """Stub WhatsApp send.

    Logs a single line describing the reminder being "sent" and returns a
    fixed payload `{"sent": True, "stub": True}`.

    The function accepts any reminder-like object (a `Reminder` ORM row or
    a duck-typed stand-in used in tests). It reads `id`, `user_id`,
    `title`, `channel`, and `remind_at` defensively so monkeypatched test
    doubles do not need to provide every attribute.
    """
    reminder_id = getattr(reminder, "id", None)
    user_id = getattr(reminder, "user_id", None)
    title = getattr(reminder, "title", None)
    channel = getattr(reminder, "channel", None)
    remind_at = getattr(reminder, "remind_at", None)

    logger.info(
        "whatsapp_send_stub: reminder_id=%s user_id=%s title=%r channel=%s remind_at=%s",
        reminder_id,
        user_id,
        title,
        channel,
        remind_at,
    )

    return {"sent": True, "stub": True}
