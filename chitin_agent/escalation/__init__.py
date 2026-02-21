"""Escalation handlers for policy decisions."""

from chitin_agent.escalation.auto_deny import AutoDenyEscalation
from chitin_agent.escalation.handler import EscalationHandler
from chitin_agent.escalation.terminal import TerminalEscalation

__all__ = ["EscalationHandler", "TerminalEscalation", "AutoDenyEscalation"]


def create_escalation_handler(handler_type: str, timeout_seconds: int = 300) -> EscalationHandler:
    """Create appropriate escalation handler."""
    if handler_type == "terminal":
        return TerminalEscalation(timeout_seconds=timeout_seconds)
    elif handler_type == "auto_deny":
        return AutoDenyEscalation()
    else:
        raise ValueError(f"Unknown escalation handler: {handler_type}")
