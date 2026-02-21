"""Common types for LLM responses."""

from dataclasses import dataclass
from typing import Any


@dataclass
class ContentBlock:
    """A content block in an LLM response."""

    type: str  # "text" or "tool_use"
    text: str = ""
    tool_call_id: str = ""
    tool_name: str = ""
    arguments: dict[str, Any] = None

    def __post_init__(self):
        """Initialize arguments if None."""
        if self.arguments is None:
            self.arguments = {}


@dataclass
class LLMResponse:
    """LLM response with content and tool calls."""

    content: list[ContentBlock]
    stop_reason: str

    def text_content(self) -> str:
        """Get all text content concatenated."""
        return "".join(block.text for block in self.content if block.type == "text")

    def has_tool_calls(self) -> bool:
        """Check if response contains tool calls."""
        return any(block.type == "tool_use" for block in self.content)

    def tool_calls(self) -> list[ContentBlock]:
        """Get all tool use blocks."""
        return [block for block in self.content if block.type == "tool_use"]
