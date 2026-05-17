"""Agent Runtime package.

Intentionally lightweight: importing :mod:`app.agent` MUST NOT pull in
``google.adk`` or any other heavy SDK so that ``agent_mode == "fake"`` runs
remain hermetic. Submodules (``adk_agent``, ``runtime``) defer those imports
to the real-agent code path only.
"""

