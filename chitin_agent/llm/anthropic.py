"""Anthropic/Claude LLM adapter."""

import os
from typing import Any, AsyncIterator

from anthropic import Anthropic, APIError, RateLimitError

from chitin_agent.config import LLMConfig
from chitin_agent.llm.adapter import LLMAdapter
from chitin_agent.llm.errors import retry_with_backoff
from chitin_agent.llm.types import ContentBlock, LLMResponse


class AnthropicAdapter(LLMAdapter):
    """Anthropic Claude adapter."""

    def __init__(self, config: LLMConfig):
        """Initialize Anthropic adapter."""
        api_key = config.api_key or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        self.client = Anthropic(api_key=api_key)
        self.config = config

    async def chat(
        self, messages: list[dict[str, str]], tools: list[dict[str, Any]]
    ) -> LLMResponse:
        """Send messages to Claude and get response."""
        # Convert messages to Anthropic format
        anthropic_messages = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            if role == "user":
                # Handle tool results (list of tool result dicts)
                if isinstance(content, list):
                    # Convert tool results to Anthropic format
                    tool_results = []
                    for result in content:
                        if result.get("type") == "tool_success":
                            tool_results.append(
                                {
                                    "type": "tool_result",
                                    "tool_use_id": result["tool_call_id"],
                                    "content": result["content"],
                                }
                            )
                        elif result.get("type") == "tool_error":
                            tool_results.append(
                                {
                                    "type": "tool_result",
                                    "tool_use_id": result["tool_call_id"],
                                    "is_error": True,
                                    "content": result["content"],
                                }
                            )
                    anthropic_messages.append({"role": "user", "content": tool_results})
                else:
                    anthropic_messages.append({"role": "user", "content": content})
            elif role == "assistant":
                # Assistant messages can be text or tool_use blocks
                if isinstance(content, list):
                    # List of ContentBlock objects - convert to Anthropic format
                    anthropic_content = []
                    for block in content:
                        if block.type == "text":
                            anthropic_content.append({"type": "text", "text": block.text})
                        elif block.type == "tool_use":
                            anthropic_content.append(
                                {
                                    "type": "tool_use",
                                    "id": block.tool_call_id,
                                    "name": block.tool_name,
                                    "input": block.arguments,
                                }
                            )
                    anthropic_messages.append({"role": "assistant", "content": anthropic_content})
                else:
                    # Plain text
                    anthropic_messages.append({"role": "assistant", "content": content})

        # Convert tools to Anthropic format
        anthropic_tools = []
        for tool in tools:
            input_schema = tool.get("input_schema", {})
            anthropic_tools.append(
                {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "input_schema": {
                        "type": "object",
                        "properties": input_schema.get("properties", {}),
                        "required": input_schema.get("required", []),
                    },
                }
            )

        # Call API with retry logic
        # Note: Anthropic SDK is synchronous, so we run it in executor
        import asyncio

        def _call_api():
            return self.client.messages.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                messages=anthropic_messages,
                tools=anthropic_tools if anthropic_tools else None,
            )

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, _call_api)
        except RateLimitError as e:
            raise RuntimeError(f"Rate limit exceeded: {e}. Please try again later.") from e
        except APIError as e:
            raise RuntimeError(f"Anthropic API error: {e}") from e

        # Convert response to common format
        content_blocks: list[ContentBlock] = []
        for block in response.content:
            if block.type == "text":
                content_blocks.append(ContentBlock(type="text", text=block.text))
            elif block.type == "tool_use":
                content_blocks.append(
                    ContentBlock(
                        type="tool_use",
                        tool_call_id=block.id,
                        tool_name=block.name,
                        arguments=block.input,
                    )
                )

        return LLMResponse(
            content=content_blocks,
            stop_reason=response.stop_reason or "end_turn",
        )

    async def chat_stream(
        self, messages: list[dict[str, str]], tools: list[dict[str, Any]]
    ) -> AsyncIterator[ContentBlock]:
        """Send messages to Claude and stream response tokens."""
        # For now, use non-streaming and yield blocks
        # Full streaming implementation would require proper event handling
        response = await self.chat(messages, tools)
        for block in response.content:
            yield block


def create_llm_adapter(config: LLMConfig) -> LLMAdapter:
    """Create appropriate LLM adapter."""
    if config.provider == "anthropic":
        return AnthropicAdapter(config)
    else:
        raise ValueError(f"Unknown LLM provider: {config.provider}")
