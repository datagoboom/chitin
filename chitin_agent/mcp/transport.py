"""MCP transport implementations."""

import asyncio
import json
import subprocess
from abc import ABC, abstractmethod
from typing import Any, Optional

import aiohttp

from chitin_agent.config import MCPServerConfig


class Transport(ABC):
    """Base class for MCP transports."""

    @abstractmethod
    async def connect(self) -> None:
        """Connect to the MCP server."""

    @abstractmethod
    async def send_request(self, method: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """Send a JSON-RPC request."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the server."""


class StdioTransport(Transport):
    """stdio transport for MCP servers."""

    def __init__(self, config: MCPServerConfig):
        """Initialize stdio transport."""
        if not config.command:
            raise ValueError("stdio transport requires command")
        self.config = config
        self.process: Optional[subprocess.Popen] = None
        self.request_id = 0

    async def connect(self) -> None:
        """Start the MCP server process."""
        self.process = subprocess.Popen(
            self.config.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    async def send_request(self, method: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """Send a JSON-RPC request via stdio."""
        if not self.process:
            raise RuntimeError("Not connected")

        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
        }
        if params:
            request["params"] = params

        request_json = json.dumps(request) + "\n"
        self.process.stdin.write(request_json)
        self.process.stdin.flush()

        # Read response asynchronously
        loop = asyncio.get_event_loop()
        response_line = await loop.run_in_executor(
            None, self.process.stdout.readline
        )
        if not response_line:
            raise RuntimeError("No response from MCP server")

        response = json.loads(response_line)
        if "error" in response:
            raise RuntimeError(f"MCP error: {response['error']}")

        return response.get("result", {})

    async def disconnect(self) -> None:
        """Terminate the MCP server process."""
        if self.process:
            self.process.terminate()
            self.process.wait()
            self.process = None


class SSETransport(Transport):
    """SSE (Server-Sent Events) transport for MCP servers."""

    def __init__(self, config: MCPServerConfig):
        """Initialize SSE transport."""
        if not config.url:
            raise ValueError("SSE transport requires url")
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        self.request_id = 0
        self.pending_requests: dict[int, asyncio.Future] = {}

    async def connect(self) -> None:
        """Connect via SSE."""
        self.session = aiohttp.ClientSession()

    async def send_request(self, method: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """Send request via SSE."""
        if not self.session:
            raise RuntimeError("Not connected")

        self.request_id += 1
        request_id = self.request_id

        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        if params:
            request["params"] = params

        # Create future for response
        future: asyncio.Future = asyncio.Future()
        self.pending_requests[request_id] = future

        # Send request via HTTP POST (SSE is typically one-way, so we use HTTP for requests)
        try:
            async with self.session.post(
                self.config.url.replace("/sse", "/rpc"), json=request
            ) as response:
                if response.status != 200:
                    raise RuntimeError(f"HTTP error: {response.status}")
                result = await response.json()
                if "error" in result:
                    raise RuntimeError(f"MCP error: {result['error']}")
                return result.get("result", {})
        except Exception as e:
            if request_id in self.pending_requests:
                del self.pending_requests[request_id]
            raise

    async def disconnect(self) -> None:
        """Disconnect from SSE."""
        if self.session:
            await self.session.close()
            self.session = None
        self.pending_requests.clear()


class HTTPTransport(Transport):
    """HTTP transport for MCP servers (streamable HTTP)."""

    def __init__(self, config: MCPServerConfig):
        """Initialize HTTP transport."""
        if not config.url:
            raise ValueError("HTTP transport requires url")
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        self.request_id = 0

    async def connect(self) -> None:
        """Connect via HTTP."""
        self.session = aiohttp.ClientSession()

    async def send_request(self, method: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """Send request via HTTP."""
        if not self.session:
            raise RuntimeError("Not connected")

        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
        }
        if params:
            request["params"] = params

        try:
            async with self.session.post(self.config.url, json=request) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(f"HTTP error {response.status}: {error_text}")

                result = await response.json()
                if "error" in result:
                    raise RuntimeError(f"MCP error: {result['error']}")

                return result.get("result", {})
        except aiohttp.ClientError as e:
            raise RuntimeError(f"HTTP transport error: {e}") from e

    async def disconnect(self) -> None:
        """Disconnect from HTTP."""
        if self.session:
            await self.session.close()
            self.session = None


def create_transport(config: MCPServerConfig) -> Transport:
    """Create appropriate transport for config."""
    if config.transport == "stdio":
        return StdioTransport(config)
    elif config.transport == "sse":
        return SSETransport(config)
    elif config.transport == "http":
        return HTTPTransport(config)
    else:
        raise ValueError(f"Unknown transport: {config.transport}")
