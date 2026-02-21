"""Base LLM adapter interface."""

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

from chitin_agent.llm.types import ContentBlock, LLMResponse


class LLMAdapter(ABC):
    """Base class for LLM adapters."""

    @abstractmethod
    async def chat(
        self, messages: list[dict[str, str]], tools: list[dict[str, Any]]
    ) -> LLMResponse:
        """Send messages to LLM and get response."""

    async def chat_stream(
        self, messages: list[dict[str, str]], tools: list[dict[str, Any]]
    ) -> AsyncIterator[ContentBlock]:
        """
        Send messages to LLM and stream response tokens.

        Yields ContentBlock objects as they arrive.
        """
        # Default implementation: call chat() and yield blocks
        # Subclasses should override for true streaming
        response = await self.chat(messages, tools)
        for block in response.content:
            yield block
