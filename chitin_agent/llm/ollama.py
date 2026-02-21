"""Ollama LLM adapter for local models."""

import asyncio
import json
import logging
import os
import re
from typing import Any, AsyncIterator

import aiohttp

logger = logging.getLogger(__name__)

from chitin_agent.config import LLMConfig
from chitin_agent.llm.adapter import LLMAdapter
from chitin_agent.llm.types import ContentBlock, LLMResponse


class OllamaAdapter(LLMAdapter):
    """Ollama adapter for local LLM models."""

    def __init__(self, config: LLMConfig):
        """Initialize Ollama adapter."""
        self.config = config
        # Default Ollama URL, can be overridden in config
        self.base_url = config.base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.session: aiohttp.ClientSession | None = None
        self._session_lock = asyncio.Lock()

    async def _ensure_session(self) -> None:
        """Ensure HTTP session is created."""
        if self.session is None:
            async with self._session_lock:
                if self.session is None:
                    self.session = aiohttp.ClientSession()

    async def chat(
        self, messages: list[dict[str, str]], tools: list[dict[str, Any]]
    ) -> LLMResponse:
        """Send messages to Ollama and get response."""
        await self._ensure_session()

        # Convert messages to Ollama format
        ollama_messages = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            
            # Ollama supports "system" role for system messages
            if role == "system":
                ollama_messages.append({"role": "system", "content": content})
                continue

            if role == "user":
                # Handle tool results (list of tool result dicts)
                if isinstance(content, list):
                    # Convert tool results to text format for Ollama
                    tool_results_text = []
                    for result in content:
                        if result.get("type") == "tool_success":
                            tool_results_text.append(
                                f"Tool {result.get('tool_call_id', 'unknown')} succeeded: {result.get('content', '')}"
                            )
                        elif result.get("type") == "tool_error":
                            tool_results_text.append(
                                f"Tool {result.get('tool_call_id', 'unknown')} failed: {result.get('content', '')}"
                            )
                    ollama_messages.append({"role": "user", "content": "\n".join(tool_results_text)})
                else:
                    ollama_messages.append({"role": "user", "content": content})
            elif role == "assistant":
                # Assistant messages can be text or tool_use blocks
                if isinstance(content, list):
                    # List of ContentBlock objects - convert to text format
                    text_parts = []
                    for block in content:
                        if block.type == "text":
                            text_parts.append(block.text)
                        elif block.type == "tool_use":
                            # Format tool use as text for Ollama
                            text_parts.append(
                                f"[Tool Call: {block.tool_name} with args {json.dumps(block.arguments)}]"
                            )
                    ollama_messages.append({"role": "assistant", "content": "\n".join(text_parts)})
                else:
                    ollama_messages.append({"role": "assistant", "content": content})

        # Prepare request payload
        payload = {
            "model": self.config.model,
            "messages": ollama_messages,
            "stream": False,
        }

        # Add tools if available (Ollama supports tools via format parameter)
        if tools:
            # Convert tools to Ollama format
            ollama_tools = []
            for tool in tools:
                # Ollama expects parameters to be a JSON schema object
                input_schema = tool.get("input_schema", {})
                # Ensure it's a proper JSON schema
                if not isinstance(input_schema, dict):
                    input_schema = {}
                
                ollama_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "parameters": input_schema,
                    },
                })
            payload["tools"] = ollama_tools
            payload["tool_choice"] = "auto"
            # Debug logging only (not printed to stdout)
            logger.debug(f"Sending {len(ollama_tools)} tools to Ollama: {[t['function']['name'] for t in ollama_tools[:5]]}...")

        try:
            async with self.session.post(
                f"{self.base_url}/api/chat", json=payload
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(f"Ollama API error {response.status}: {error_text}")

                result = await response.json()

                # Parse Ollama response
                content_blocks: list[ContentBlock] = []
                message = result.get("message", {})

                # Check for structured tool calls (Ollama format)
                tool_calls = message.get("tool_calls", [])
                if not tool_calls and "tool_calls" in message:
                    # Sometimes tool_calls is a list directly
                    tool_calls = message["tool_calls"] if isinstance(message["tool_calls"], list) else []

                # Parse structured tool calls
                for tool_call in tool_calls:
                    function = tool_call.get("function", {})
                    tool_name = function.get("name", "")
                    tool_args_str = function.get("arguments", "{}")
                    
                    try:
                        tool_args = json.loads(tool_args_str) if isinstance(tool_args_str, str) else tool_args_str
                    except json.JSONDecodeError:
                        tool_args = {}

                    content_blocks.append(
                        ContentBlock(
                            type="tool_use",
                            tool_call_id=tool_call.get("id", f"call_{len(content_blocks)}"),
                            tool_name=tool_name,
                            arguments=tool_args,
                        )
                    )

                # Add text content
                message_content = message.get("content", "")
                
                # Parse text-based tool calls if no structured ones found
                # Some models return tool calls as text: [Tool Call: tool_name with args {...}]
                if message_content and not tool_calls:
                    # Pattern: [Tool Call: tool_name with args {...}]
                    # Handle nested JSON by matching balanced braces
                    tool_call_pattern = r'\[Tool Call:\s*(\w+)\s+with args\s+(\{.*?\}|{})\s*\]'
                    matches = list(re.finditer(tool_call_pattern, message_content, re.DOTALL))
                    
                    # If simple pattern doesn't work, try a more flexible one
                    if not matches:
                        # More flexible: match any JSON-like structure
                        tool_call_pattern = r'\[Tool Call:\s*(\w+)\s+with args\s+([^\]]+)\s*\]'
                        matches = list(re.finditer(tool_call_pattern, message_content))
                    
                    last_end = 0
                    for match in matches:
                        # Add text before tool call
                        if match.start() > last_end:
                            text_before = message_content[last_end:match.start()].strip()
                            if text_before:
                                content_blocks.append(ContentBlock(type="text", text=text_before))
                        
                        # Parse tool call
                        tool_name = match.group(1)
                        tool_args_str = match.group(2)
                        try:
                            tool_args = json.loads(tool_args_str) if tool_args_str else {}
                        except json.JSONDecodeError:
                            tool_args = {}
                        
                        content_blocks.append(
                            ContentBlock(
                                type="tool_use",
                                tool_call_id=f"call_{len(content_blocks)}",
                                tool_name=tool_name,
                                arguments=tool_args,
                            )
                        )
                        last_end = match.end()
                    
                    # Add remaining text after last tool call
                    if last_end < len(message_content):
                        text_after = message_content[last_end:].strip()
                        if text_after:
                            content_blocks.append(ContentBlock(type="text", text=text_after))
                elif message_content:
                    # No tool calls in text, just add the content
                    content_blocks.append(ContentBlock(type="text", text=message_content))

                # If no content blocks, create empty text block
                if not content_blocks:
                    content_blocks.append(ContentBlock(type="text", text=""))

                return LLMResponse(
                    content=content_blocks,
                    stop_reason=result.get("done_reason", "stop") or "end_turn",
                )
        except aiohttp.ClientError as e:
            raise RuntimeError(f"Ollama connection error: {e}") from e

    async def chat_stream(
        self, messages: list[dict[str, str]], tools: list[dict[str, Any]]
    ) -> AsyncIterator[ContentBlock]:
        """Send messages to Ollama and stream response tokens."""
        await self._ensure_session()

        # Convert messages (same as chat method)
        ollama_messages = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            if role == "user":
                if isinstance(content, list):
                    tool_results_text = []
                    for result in content:
                        if result.get("type") == "tool_success":
                            tool_results_text.append(
                                f"Tool {result.get('tool_call_id', 'unknown')} succeeded: {result.get('content', '')}"
                            )
                        elif result.get("type") == "tool_error":
                            tool_results_text.append(
                                f"Tool {result.get('tool_call_id', 'unknown')} failed: {result.get('content', '')}"
                            )
                    ollama_messages.append({"role": "user", "content": "\n".join(tool_results_text)})
                else:
                    ollama_messages.append({"role": "user", "content": content})
            elif role == "assistant":
                if isinstance(content, list):
                    text_parts = []
                    for block in content:
                        if block.type == "text":
                            text_parts.append(block.text)
                        elif block.type == "tool_use":
                            text_parts.append(
                                f"[Tool Call: {block.tool_name} with args {json.dumps(block.arguments)}]"
                            )
                    ollama_messages.append({"role": "assistant", "content": "\n".join(text_parts)})
                else:
                    ollama_messages.append({"role": "assistant", "content": content})

        payload = {
            "model": self.config.model,
            "messages": ollama_messages,
            "stream": True,
        }

        if tools:
            ollama_tools = []
            for tool in tools:
                ollama_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "parameters": tool.get("input_schema", {}),
                    },
                })
            payload["tools"] = ollama_tools
            payload["tool_choice"] = "auto"

        try:
            async with self.session.post(
                f"{self.base_url}/api/chat", json=payload
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(f"Ollama API error {response.status}: {error_text}")

                async for line in response.content:
                    if not line:
                        continue

                    try:
                        chunk = json.loads(line)
                        if "message" in chunk:
                            content = chunk["message"].get("content", "")
                            if content:
                                yield ContentBlock(type="text", text=content)

                            # Check for tool calls in stream
                            if "tool_calls" in chunk["message"]:
                                for tool_call in chunk["message"]["tool_calls"]:
                                    yield ContentBlock(
                                        type="tool_use",
                                        tool_call_id=tool_call.get("id", ""),
                                        tool_name=tool_call["function"]["name"],
                                        arguments=json.loads(tool_call["function"]["arguments"]),
                                    )
                    except json.JSONDecodeError:
                        continue
        except aiohttp.ClientError as e:
            raise RuntimeError(f"Ollama connection error: {e}") from e

    async def __aenter__(self):
        """Async context manager entry."""
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def close(self) -> None:
        """Close the HTTP session."""
        if self.session:
            await self.session.close()
            self.session = None
