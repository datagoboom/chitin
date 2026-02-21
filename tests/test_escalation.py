"""Tests for escalation handlers."""

import pytest
from unittest.mock import Mock

from chitin_agent.escalation.auto_deny import AutoDenyEscalation
from chitin_agent.escalation.terminal import TerminalEscalation
from chitin_agent.llm.types import ContentBlock


@pytest.mark.asyncio
async def test_auto_deny_escalation():
    """Test auto-deny escalation handler."""
    handler = AutoDenyEscalation()
    tool_call = ContentBlock(
        type="tool_use",
        tool_call_id="call_123",
        tool_name="test_tool",
        arguments={}
    )

    result = await handler.handle(tool_call, "test reason", "trace")
    assert result is False


@pytest.mark.asyncio
async def test_terminal_escalation(monkeypatch):
    """Test terminal escalation handler."""
    handler = TerminalEscalation()

    # Mock input to return 'y'
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")

    tool_call = ContentBlock(
        type="tool_use",
        tool_call_id="call_123",
        tool_name="test_tool",
        arguments={"arg": "value"}
    )

    result = await handler.handle(tool_call, "test reason", "trace")
    assert result is True


@pytest.mark.asyncio
async def test_terminal_escalation_deny(monkeypatch):
    """Test terminal escalation handler with denial."""
    handler = TerminalEscalation()

    # Mock input to return 'n'
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")

    tool_call = ContentBlock(
        type="tool_use",
        tool_call_id="call_123",
        tool_name="test_tool",
        arguments={}
    )

    result = await handler.handle(tool_call, "test reason", "trace")
    assert result is False
