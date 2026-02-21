"""Auto-deny escalation handler."""

from typing import Any

from chitin_agent.escalation.handler import EscalationHandler


class AutoDenyEscalation(EscalationHandler):
    """Escalation handler that automatically denies all requests."""

    async def handle(
        self, tool_call: Any, reason: str, trace_chain: Any
    ) -> bool:
        """Automatically deny escalation."""
        return False
