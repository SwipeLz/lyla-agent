"""Taskbot dev agent package — discoverable by ADK CLI tools.

This package exists *only* so that ``adk web``/``adk run``/``adk api_server``
can find a module-level ``root_agent`` and let you chat with the LLM in the
ADK developer UI. Production traffic does NOT go through this module — it
is served by ``app.api.agent.POST /agent/text`` which uses the per-request
factory in ``app.agent.tool_factory`` instead.

See ``docs/ADK_DEV_UI.md`` for the development workflow.
"""
from . import agent  # noqa: F401  (required by ADK discovery)
