"""Base escalation handler interface."""

from abc import ABC, abstractmethod
from typing import Any


class EscalationHandler(ABC):
    """Base class for escalation handlers."""

    @abstractmethod
    async def handle(
        self, tool_call: Any, reason: str, trace_chain: Any
    ) -> bool:
        """
        Handle an escalation request.

        Args:
            tool_call: The tool call that triggered escalation
            reason: Reason for escalation
            trace_chain: Trace chain from engine.explain()

        Returns:
            True if approved, False if denied
        """
