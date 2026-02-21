"""Tests for MCP client."""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from chitin_agent.config import MCPServerConfig
from chitin_agent.mcp.client import MCPClient, MCPServer, MCPTool
from chitin_agent.mcp.transport import Transport


class MockTransport(Transport):
    """Mock transport for testing."""

    def __init__(self):
        self.connected = False
        self.request_id = 0

    async def connect(self):
        self.connected = True

    async def send_request(self, method: str, params=None):
        self.request_id += 1
        if method == "initialize":
            return {"protocolVersion": "2024-11-05"}
        elif method == "tools/list":
            return {
                "tools": [
                    {
                        "name": "test_tool",
                        "description": "A test tool",
                        "inputSchema": {"type": "object"}
                    }
                ]
            }
        elif method == "tools/call":
            return {"content": "test result", "exitCode": 0}
        return {}

    async def disconnect(self):
        self.connected = False


@pytest.mark.asyncio
async def test_mcp_server_connect():
    """Test MCP server connection."""
    config = MCPServerConfig(
        name="test",
        transport="stdio",
        command=["echo", "test"]
    )
    transport = MockTransport()
    server = MCPServer(config, transport)

    await server.connect()

    assert server.connected
    assert "test_tool" in server.tools
    assert server.tools["test_tool"].name == "test_tool"


@pytest.mark.asyncio
async def test_mcp_server_call_tool():
    """Test calling a tool on MCP server."""
    config = MCPServerConfig(
        name="test",
        transport="stdio",
        command=["echo", "test"]
    )
    transport = MockTransport()
    server = MCPServer(config, transport)
    await server.connect()

    result = await server.call_tool("test_tool", {"arg": "value"})

    assert result["content"] == "test result"
    assert result["exitCode"] == 0


@pytest.mark.asyncio
async def test_mcp_client_connect_all():
    """Test MCP client connecting to all servers."""
    from chitin_agent.config import AgentConfig

    config = AgentConfig(
        mcp_servers=[
            MCPServerConfig(
                name="server1",
                transport="stdio",
                command=["echo", "test1"]
            )
        ]
    )

    client = MCPClient(config)

    with patch("chitin_agent.mcp.client.create_transport", return_value=MockTransport()):
        await client.connect_all()

    assert len(client.servers) == 1
    assert "server1" in client.servers


@pytest.mark.asyncio
async def test_mcp_client_list_tools():
    """Test listing all tools from MCP client."""
    from chitin_agent.config import AgentConfig

    config = AgentConfig(
        mcp_servers=[
            MCPServerConfig(
                name="server1",
                transport="stdio",
                command=["echo", "test1"]
            )
        ]
    )

    client = MCPClient(config)

    with patch("chitin_agent.mcp.client.create_transport", return_value=MockTransport()):
        await client.connect_all()

    tools = client.list_all_tools()
    assert len(tools) == 1
    assert tools[0].name == "test_tool"


@pytest.mark.asyncio
async def test_mcp_client_call_tool():
    """Test calling a tool through MCP client."""
    from chitin_agent.config import AgentConfig

    config = AgentConfig(
        mcp_servers=[
            MCPServerConfig(
                name="server1",
                transport="stdio",
                command=["echo", "test1"]
            )
        ]
    )

    client = MCPClient(config)

    with patch("chitin_agent.mcp.client.create_transport", return_value=MockTransport()):
        await client.connect_all()

        result = await client.call_tool("test_tool", {"arg": "value"})
        assert result["content"] == "test result"


@pytest.mark.asyncio
async def test_mcp_server_reconnect():
    """Test MCP server reconnection on failure."""
    config = MCPServerConfig(
        name="test",
        transport="stdio",
        command=["echo", "test"]
    )

    class FailingTransport(MockTransport):
        """Transport that fails first call, then succeeds."""

        def __init__(self):
            super().__init__()
            self.call_count = 0

        async def send_request(self, method: str, params=None):
            self.call_count += 1
            if self.call_count == 1 and method == "tools/call":
                raise ConnectionError("Connection lost")
            return await super().send_request(method, params)

    transport = FailingTransport()
    server = MCPServer(config, transport)
    await server.connect()

    # First call should trigger reconnect
    result = await server.call_tool("test_tool", {})
    assert result["content"] == "test result"
