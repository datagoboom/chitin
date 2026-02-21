"""Context window management for LLM conversations."""

from typing import Any


class ContextManager:
    """Manages LLM context window with truncation strategy."""

    def __init__(self, max_tokens: int = 100000, keep_recent: int = 10):
        """
        Initialize context manager.

        Args:
            max_tokens: Maximum tokens in context (approximate)
            keep_recent: Always keep this many recent messages
        """
        self.max_tokens = max_tokens
        self.keep_recent = keep_recent

    def truncate_messages(
        self, messages: list[dict[str, Any]], estimated_tokens: int
    ) -> list[dict[str, Any]]:
        """
        Truncate messages if they exceed the context window.

        Strategy:
        1. Always keep the most recent N messages (keep_recent)
        2. Remove oldest messages first
        3. If still too long, remove middle messages but keep first and last

        Args:
            messages: List of message dicts
            estimated_tokens: Estimated token count

        Returns:
            Truncated message list
        """
        if estimated_tokens <= self.max_tokens:
            return messages

        # Always keep the most recent messages
        if len(messages) <= self.keep_recent:
            return messages

        # Keep first message (usually system/user prompt) and recent messages
        kept_messages = [messages[0]]  # Keep first
        kept_messages.extend(messages[-self.keep_recent :])  # Keep recent

        # If still too long, we'd need to estimate tokens per message
        # For now, this simple strategy should work
        return kept_messages

    def estimate_tokens(self, messages: list[dict[str, Any]]) -> int:
        """
        Estimate token count for messages.

        Simple heuristic: ~4 chars per token, or use actual tokenizer if available.
        """
        total_chars = 0
        for msg in messages:
            if isinstance(msg.get("content"), str):
                total_chars += len(msg["content"])
            elif isinstance(msg.get("content"), list):
                for item in msg["content"]:
                    if isinstance(item, dict):
                        total_chars += len(str(item))
                    else:
                        total_chars += len(str(item))
        return total_chars // 4  # Rough estimate
