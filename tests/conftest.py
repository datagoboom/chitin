"""Pytest configuration and fixtures."""

# Mock chitin module before any imports
import sys
from unittest.mock import Mock

mock_chitin = type(sys)("chitin")
mock_chitin.Engine = Mock

# Mock TrustLevel enum
class MockTrustLevel:
    SYSTEM = 0
    OPERATOR = 1
    USER = 2
    EXTERNAL = 3
    UNKNOWN = 4

mock_chitin.TrustLevel = MockTrustLevel
sys.modules["chitin"] = mock_chitin

import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from chitin_agent.config import AgentConfig, LLMConfig, MCPServerConfig


@pytest.fixture
def temp_config_dir(tmp_path):
    """Create a temporary config directory."""
    config_dir = tmp_path / ".chitin"
    config_dir.mkdir()
    return config_dir


@pytest.fixture
def sample_config():
    """Create a sample agent configuration."""
    return AgentConfig(
        llm=LLMConfig(
            provider="anthropic",
            model="claude-sonnet-4-20250514",
            max_tokens=8192,
        ),
        mcp_servers=[
            MCPServerConfig(
                name="test_server",
                transport="stdio",
                command=["echo", "test"],
            )
        ],
    )


@pytest.fixture
def mock_chitin_engine():
    """Create a mock Chitin engine."""
    engine = Mock()
    engine.ingest = Mock(return_value="event_123")
    engine.propose = Mock(return_value=Mock(outcome="allow", reason="", event_id="event_456"))
    engine.record_result = Mock(return_value="event_789")
    engine.explain = Mock(return_value="trace_chain")
    engine.register_tool = Mock()
    engine.close = Mock()
    return engine


@pytest.fixture
def mock_mcp_tool():
    """Create a mock MCP tool."""
    from chitin_agent.mcp.client import MCPTool
    return MCPTool(
        name="test_tool",
        description="A test tool",
        input_schema={"type": "object", "properties": {}}
    )


@pytest.fixture
def mock_llm_response():
    """Create a mock LLM response."""
    from chitin_agent.llm.types import ContentBlock, LLMResponse
    return LLMResponse(
        content=[ContentBlock(type="text", text="Hello, world!")],
        stop_reason="end_turn"
    )
