"""MCP client for discovering and calling tools."""

import asyncio
import logging
from typing import Any

from chitin_agent.config import AgentConfig, MCPServerConfig
from chitin_agent.mcp.transport import Transport, create_transport

logger = logging.getLogger(__name__)


class MCPTool:
    """Represents an MCP tool."""

    def __init__(self, name: str, description: str, input_schema: dict[str, Any]):
        """Initialize tool."""
        self.name = name
        self.description = description
        self.input_schema = input_schema


class MCPServer:
    """Represents a connected MCP server."""

    def __init__(self, config: MCPServerConfig, transport: Transport):
        """Initialize MCP server."""
        self.config = config
        self.transport = transport
        self.tools: dict[str, MCPTool] = {}
        self.connected = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 3

    async def connect(self) -> None:
        """Connect to the server and discover tools."""
        try:
            await self.transport.connect()

            # Initialize protocol
            init_result = await self.transport.send_request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "chitin-agent", "version": "0.1.0"},
                },
            )

            # List tools
            tools_result = await self.transport.send_request("tools/list")
            tools_list = tools_result.get("tools", [])

            for tool_def in tools_list:
                tool = MCPTool(
                    name=tool_def["name"],
                    description=tool_def.get("description", ""),
                    input_schema=tool_def.get("inputSchema", {}),
                )
                self.tools[tool.name] = tool

            self.connected = True
            self.reconnect_attempts = 0
            logger.info(f"Connected to MCP server: {self.config.name}")
        except Exception as e:
            self.connected = False
            logger.error(f"Failed to connect to MCP server {self.config.name}: {e}")
            raise

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call a tool by name with error recovery."""
        if name not in self.tools:
            raise ValueError(f"Tool {name} not found on server {self.config.name}")

        try:
            result = await self.transport.send_request(
                "tools/call",
                {"name": name, "arguments": arguments},
            )
            return result
        except (ConnectionError, RuntimeError) as e:
            # Server may have crashed - try to reconnect
            logger.warning(f"MCP server {self.config.name} connection lost: {e}")
            self.connected = False
            await self._reconnect()
            # Retry once after reconnect
            return await self.transport.send_request(
                "tools/call",
                {"name": name, "arguments": arguments},
            )

    async def _reconnect(self) -> None:
        """Attempt to reconnect to the server."""
        if self.reconnect_attempts >= self.max_reconnect_attempts:
            raise RuntimeError(
                f"Failed to reconnect to MCP server {self.config.name} after {self.max_reconnect_attempts} attempts"
            )

        self.reconnect_attempts += 1
        logger.info(f"Attempting to reconnect to {self.config.name} (attempt {self.reconnect_attempts})")

        try:
            await self.disconnect()
        except Exception:
            pass  # Ignore disconnect errors

        await asyncio.sleep(1)  # Brief delay before reconnect
        await self.connect()

    async def disconnect(self) -> None:
        """Disconnect from the server."""
        try:
            await self.transport.disconnect()
            self.connected = False
        except Exception as e:
            logger.warning(f"Error disconnecting from {self.config.name}: {e}")


class MCPClient:
    """Manages connections to multiple MCP servers."""

    def __init__(self, config: AgentConfig):
        """Initialize MCP client."""
        self.config = config
        self.servers: dict[str, MCPServer] = {}

    async def connect_all(self) -> None:
        """Connect to all configured MCP servers."""
        for server_config in self.config.mcp_servers:
            try:
                transport = create_transport(server_config)
                server = MCPServer(server_config, transport)
                await server.connect()
                self.servers[server_config.name] = server
            except Exception as e:
                logger.error(f"Failed to connect to MCP server {server_config.name}: {e}")
                # Continue with other servers even if one fails

    async def disconnect_all(self) -> None:
        """Disconnect from all servers."""
        for server in list(self.servers.values()):
            await server.disconnect()
        self.servers.clear()

    def list_all_tools(self) -> list[MCPTool]:
        """List all tools from all servers."""
        tools = []
        for server in self.servers.values():
            if server.connected:
                tools.extend(server.tools.values())
        return tools

    def tool_definitions(self) -> list[dict[str, Any]]:
        """Get tool definitions in format expected by LLM."""
        definitions = []
        for server in self.servers.values():
            if server.connected:
                for tool in server.tools.values():
                    definitions.append(
                        {
                            "name": tool.name,
                            "description": tool.description,
                            "input_schema": tool.input_schema,
                        }
                    )
        return definitions

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call a tool by name (searches all servers)."""
        for server in self.servers.values():
            if name in server.tools and server.connected:
                try:
                    return await server.call_tool(name, arguments)
                except Exception as e:
                    logger.error(f"Error calling tool {name} on {server.config.name}: {e}")
                    # Try next server if available
                    continue
        raise ValueError(f"Tool {name} not found on any connected server")
