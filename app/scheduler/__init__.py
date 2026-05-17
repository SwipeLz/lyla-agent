"""Reminder Scheduler package.

Wraps APScheduler `BackgroundScheduler` and the periodic Scheduler Tick that
processes Due Reminders. Importing this package SHALL NOT pull in any heavy
runtime dependency; submodules (`tick`, `lifecycle`) lazily import what they
need so tests can call `reminder_tick` directly without a running scheduler.
"""
