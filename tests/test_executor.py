"""Tests for tool executor."""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from chitin_agent.engine import Session
from chitin_agent.escalation.handler import EscalationHandler
from chitin_agent.executor import ToolExecutor
from chitin_agent.llm.types import ContentBlock, LLMResponse
from chitin_agent.mcp.client import MCPClient


@pytest.mark.asyncio
async def test_executor_process_text_response(mock_chitin_engine, sample_config):
    """Test executor processing text-only LLM response."""
    from chitin_agent.llm.types import ContentBlock, LLMResponse

    session = Session(mock_chitin_engine, sample_config)
    mcp = Mock(spec=MCPClient)
    escalation = Mock(spec=EscalationHandler)

    executor = ToolExecutor(session, mcp, escalation)

    response = LLMResponse(
        content=[ContentBlock(type="text", text="Hello, world!")],
        stop_reason="end_turn"
    )

    text, results = await executor.process_llm_response(response)

    assert text == "Hello, world!"
    assert results == []
    mock_chitin_engine.ingest.assert_called_once()


@pytest.mark.asyncio
async def test_executor_process_tool_call_allow(mock_chitin_engine, sample_config):
    """Test executor processing tool call with allow decision."""
    session = Session(mock_chitin_engine, sample_config)
    mcp = Mock(spec=MCPClient)
    mcp.call_tool = AsyncMock(return_value={"content": "result", "exitCode": 0})
    escalation = Mock(spec=EscalationHandler)

    # Set up decision to allow
    decision = Mock()
    decision.outcome = "allow"
    decision.reason = ""
    decision.event_id = "event_123"
    mock_chitin_engine.propose.return_value = decision

    executor = ToolExecutor(session, mcp, escalation)

    response = LLMResponse(
        content=[
            ContentBlock(
                type="tool_use",
                tool_call_id="call_123",
                tool_name="test_tool",
                arguments={"arg": "value"}
            )
        ],
        stop_reason="end_turn"
    )

    text, results = await executor.process_llm_response(response)

    assert len(results) == 1
    assert results[0]["type"] == "tool_success"
    assert results[0]["content"] == "result"
    mock_chitin_engine.propose.assert_called_once()
    mcp.call_tool.assert_called_once_with("test_tool", {"arg": "value"})


@pytest.mark.asyncio
async def test_executor_process_tool_call_deny(mock_chitin_engine, sample_config):
    """Test executor processing tool call with deny decision."""
    session = Session(mock_chitin_engine, sample_config)
    mcp = Mock(spec=MCPClient)
    escalation = Mock(spec=EscalationHandler)

    # Set up decision to deny
    decision = Mock()
    decision.outcome = "deny"
    decision.reason = "Policy violation"
    decision.event_id = "event_123"
    mock_chitin_engine.propose.return_value = decision

    executor = ToolExecutor(session, mcp, escalation)

    response = LLMResponse(
        content=[
            ContentBlock(
                type="tool_use",
                tool_call_id="call_123",
                tool_name="test_tool",
                arguments={"arg": "value"}
            )
        ],
        stop_reason="end_turn"
    )

    text, results = await executor.process_llm_response(response)

    assert len(results) == 1
    assert results[0]["type"] == "tool_error"
    assert "Policy denied" in results[0]["content"]
    mcp.call_tool.assert_not_called()


@pytest.mark.asyncio
async def test_executor_process_tool_call_escalate_approved(mock_chitin_engine, sample_config):
    """Test executor processing tool call with escalate decision that's approved."""
    session = Session(mock_chitin_engine, sample_config)
    mcp = Mock(spec=MCPClient)
    mcp.call_tool = AsyncMock(return_value={"content": "result", "exitCode": 0})
    escalation = Mock(spec=EscalationHandler)
    escalation.handle = AsyncMock(return_value=True)  # Approved

    # Set up decision to escalate
    decision = Mock()
    decision.outcome = "escalate"
    decision.reason = "Requires approval"
    decision.event_id = "event_123"
    mock_chitin_engine.propose.return_value = decision
    mock_chitin_engine.explain.return_value = "trace_chain"

    executor = ToolExecutor(session, mcp, escalation)

    response = LLMResponse(
        content=[
            ContentBlock(
                type="tool_use",
                tool_call_id="call_123",
                tool_name="test_tool",
                arguments={"arg": "value"}
            )
        ],
        stop_reason="end_turn"
    )

    text, results = await executor.process_llm_response(response)

    assert len(results) == 1
    assert results[0]["type"] == "tool_success"
    escalation.handle.assert_called_once()
    mcp.call_tool.assert_called_once()


@pytest.mark.asyncio
async def test_executor_process_tool_call_escalate_denied(mock_chitin_engine, sample_config):
    """Test executor processing tool call with escalate decision that's denied."""
    session = Session(mock_chitin_engine, sample_config)
    mcp = Mock(spec=MCPClient)
    escalation = Mock(spec=EscalationHandler)
    escalation.handle = AsyncMock(return_value=False)  # Denied

    # Set up decision to escalate
    decision = Mock()
    decision.outcome = "escalate"
    decision.reason = "Requires approval"
    decision.event_id = "event_123"
    mock_chitin_engine.propose.return_value = decision
    mock_chitin_engine.explain.return_value = "trace_chain"

    executor = ToolExecutor(session, mcp, escalation)

    response = LLMResponse(
        content=[
            ContentBlock(
                type="tool_use",
                tool_call_id="call_123",
                tool_name="test_tool",
                arguments={"arg": "value"}
            )
        ],
        stop_reason="end_turn"
    )

    text, results = await executor.process_llm_response(response)

    assert len(results) == 1
    assert results[0]["type"] == "tool_error"
    assert "Escalation denied" in results[0]["content"]
    mcp.call_tool.assert_not_called()


@pytest.mark.asyncio
async def test_executor_parallel_tool_calls(mock_chitin_engine, sample_config):
    """Test executor handling multiple tool calls in parallel."""
    session = Session(mock_chitin_engine, sample_config)
    mcp = Mock(spec=MCPClient)
    mcp.call_tool = AsyncMock(side_effect=[
        {"content": "result1", "exitCode": 0},
        {"content": "result2", "exitCode": 0}
    ])
    escalation = Mock(spec=EscalationHandler)

    # Set up decisions to allow
    decision = Mock()
    decision.outcome = "allow"
    decision.reason = ""
    decision.event_id = "event_123"
    mock_chitin_engine.propose.return_value = decision

    executor = ToolExecutor(session, mcp, escalation)

    response = LLMResponse(
        content=[
            ContentBlock(
                type="tool_use",
                tool_call_id="call_1",
                tool_name="tool1",
                arguments={}
            ),
            ContentBlock(
                type="tool_use",
                tool_call_id="call_2",
                tool_name="tool2",
                arguments={}
            )
        ],
        stop_reason="end_turn"
    )

    text, results = await executor.process_llm_response(response)

    assert len(results) == 2
    assert results[0]["type"] == "tool_success"
    assert results[1]["type"] == "tool_success"
    assert mcp.call_tool.call_count == 2
