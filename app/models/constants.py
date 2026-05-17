"""Simple string constants for status fields across models."""


class TaskStatus:
    PENDING = "pending"
    DONE = "done"
    CANCELLED = "cancelled"


class DeviceStatus:
    ONLINE = "online"
    OFFLINE = "offline"


class ReminderStatus:
    SCHEDULED = "scheduled"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DeviceCommandStatus:
    PENDING = "pending"
    SENT = "sent"
    ACKNOWLEDGED = "acknowledged"
    FAILED = "failed"
