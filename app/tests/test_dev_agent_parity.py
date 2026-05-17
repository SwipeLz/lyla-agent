"""Parity smoke test: dev ADK agent vs production tool factory.

The dev agent in ``agents/taskbot_agent/agent.py`` exists *only* so the
ADK CLI tools (``adk web``/``adk run``) can discover a top-level
``root_agent``. To prevent drift between that dev shell and the real
production agent built by ``app.agent.tool_factory.build_tools``, this
test asserts:

1. Both expose the same five tool names, in the same order.
2. Both use the exact same Indonesian system instruction string
   (``app.agent.adk_agent.INSTRUCTION``).
3. The dev agent's tool callables share the same model-visible argument
   names as the production tools (signatures parsed via
   :func:`inspect.signature`).

If any of these assertions fail, you almost certainly added/renamed a
tool in one place and forgot the other. Fix the dev file
``agents/taskbot_agent/agent.py`` to match the production factory.
"""
from __future__ import annotations

import inspect

from agents.taskbot_agent import agent as dev_agent
from app.agent.adk_agent import INSTRUCTION
from app.agent.tool_factory import build_tools


_EXPECTED_TOOL_NAMES = (
    "create_task",
    "create_expense",
    "set_reminder",
    "get_today_summary",
    "send_device_command",
)


def _model_visible_params(fn) -> tuple[str, ...]:
    """Return the model-visible parameter names of ``fn`` in order.

    Strips ``**_kwargs`` (which absorbs spurious injected-context kwargs
    from a hallucinating LLM) so it isn't compared between agents.
    """
    sig = inspect.signature(fn)
    return tuple(
        name
        for name, p in sig.parameters.items()
        if p.kind != inspect.Parameter.VAR_KEYWORD
    )


def test_dev_agent_uses_production_instruction():
    """Dev agent must use the same system prompt as production."""
    assert dev_agent.root_agent.instruction == INSTRUCTION


def test_dev_agent_tool_names_match_production_order():
    """Dev tool list must have the same names in the same order as prod."""
    dev_names = tuple(t.__name__ for t in dev_agent.root_agent.tools)
    prod_tools = build_tools(db=None, user_id="u", device_id="d")
    prod_names = tuple(t.__name__ for t in prod_tools)
    assert dev_names == _EXPECTED_TOOL_NAMES
    assert dev_names == prod_names


def test_dev_agent_tool_signatures_match_production():
    """Each dev tool must expose the same model-visible params as prod."""
    prod_tools = {
        t.__name__: t for t in build_tools(db=None, user_id="u", device_id="d")
    }
    for dev_tool in dev_agent.root_agent.tools:
        prod_tool = prod_tools[dev_tool.__name__]
        assert _model_visible_params(dev_tool) == _model_visible_params(
            prod_tool
        ), f"Signature drift in tool {dev_tool.__name__!r}"
