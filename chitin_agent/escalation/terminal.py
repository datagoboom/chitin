"""Terminal escalation handler."""

import sys
from typing import Any

from chitin_agent.escalation.handler import EscalationHandler


class TerminalEscalation(EscalationHandler):
    """Terminal-based escalation handler with y/n prompt."""

    def __init__(self, timeout_seconds: int = 300):
        """Initialize terminal escalation."""
        self.timeout_seconds = timeout_seconds

    async def handle(
        self, tool_call: Any, reason: str, trace_chain: Any
    ) -> bool:
        """Prompt user for approval in terminal."""
        print("\n" + "=" * 80)
        print("ESCALATION REQUIRED")
        print("=" * 80)
        print(f"\nTool: {tool_call.tool_name}")
        print(f"Arguments: {tool_call.arguments}")
        print(f"\nReason: {reason}")
        if trace_chain:
            print(f"\nTrace: {trace_chain}")
        print("\n" + "-" * 80)
        print("Approve this tool call? (y/n): ", end="", flush=True)

        try:
            response = input().strip().lower()
            approved = response in ("y", "yes")
            if approved:
                print("✓ Approved")
            else:
                print("✗ Denied")
            return approved
        except (EOFError, KeyboardInterrupt):
            print("\n✗ Denied (interrupted)")
            return False
