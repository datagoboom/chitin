"""Tool Executor - the core loop that integrates Chitin."""

import asyncio
import json
from typing import Any, Optional

from chitin import Engine, TrustLevel  # type: ignore

from chitin_agent.escalation.handler import EscalationHandler
from chitin_agent.llm.types import ContentBlock, LLMResponse
from chitin_agent.mcp.client import MCPClient
from chitin_agent.engine import Session


class ToolExecutor:
    """Executes tool calls with Chitin policy checking."""

    def __init__(
        self,
        session: Session,
        mcp: MCPClient,
        escalation: EscalationHandler,
        audit_batcher: Optional[Any] = None,  # AuditBatcher
    ):
        """Initialize tool executor."""
        self.session = session
        self.mcp = mcp
        self.escalation = escalation
        self.audit_batcher = audit_batcher

    async def process_llm_response(
        self, response: LLMResponse
    ) -> tuple[str, list[dict[str, Any]]]:
        """
        Process LLM response and execute tool calls.

        Returns:
            Tuple of (text_content, tool_results)
        """
        # Record LLM response in Chitin
        llm_text = response.text_content()
        if llm_text:
            llm_event_id = self.session.engine.ingest(
                llm_text,
                trust_level=TrustLevel.SYSTEM,
                metadata={"source": "llm"},
            )
            self.session.track_event(llm_event_id)

        if not response.has_tool_calls():
            return (llm_text, [])

        # Process tool calls in parallel
        tool_calls = response.tool_calls()
        tasks = [self._execute_tool_call(tool_call) for tool_call in tool_calls]
        tool_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to error results
        final_results = []
        for i, result in enumerate(tool_results):
            if isinstance(result, Exception):
                final_results.append(
                    {
                        "type": "tool_error",
                        "tool_call_id": tool_calls[i].tool_call_id,
                        "content": f"Tool execution failed: {str(result)}",
                    }
                )
            else:
                final_results.append(result)

        return (llm_text, final_results)

    async def _execute_tool_call(self, tool_call: ContentBlock) -> dict[str, Any]:
        """Execute a single tool call with policy checking."""
        # Propose tool call to Chitin
        decision = self.session.engine.propose(
            tool=tool_call.tool_name,
            params=json.dumps(tool_call.arguments),
            input_sources=self.session.recent_event_ids(),
        )

        # Handle decision outcome
        # Decision has: allowed (bool), outcome (str), event_id (int), rule_id (int), reason (str)
        outcome = decision.outcome
        reason = decision.reason
        event_id = decision.event_id
        allowed = decision.allowed

        if outcome == "deny" or not allowed:
            return {
                "type": "tool_error",
                "tool_call_id": tool_call.tool_call_id,
                "content": f"Policy denied: {reason}",
            }

        if outcome == "escalate":
            # Get trace for escalation
            trace = self.session.engine.explain(event_id) if event_id else None
            approved = await self.escalation.handle(tool_call, reason, trace)

            if not approved:
                return {
                    "type": "tool_error",
                    "tool_call_id": tool_call.tool_call_id,
                    "content": f"Escalation denied by user: {reason}",
                }

            # Record human approval
            approval_event_id = self.session.engine.ingest(
                "Human approved escalation",
                trust_level=TrustLevel.OPERATOR,
            )
            self.session.track_event(approval_event_id)

        # Execute tool call
        try:
            result = await self.mcp.call_tool(tool_call.tool_name, tool_call.arguments)
            result_content = result.get("content", "")
            exit_code = result.get("exitCode", 0)

            # Record result in Chitin
            # event_id is the tool_call_id from the propose decision
            result_event_id = self.session.engine.record_result(
                event_id, result_content, exit_code
            )
            self.session.track_event(result_event_id)

            # Record audit event if batcher is available
            if self.audit_batcher:
                from chitin_agent.enterprise.audit import AuditEvent
                audit_event = AuditEvent(
                    event_id=event_id,
                    event_type="tool_call",
                    content=f"Tool {tool_call.tool_name} executed",
                    decision={"outcome": outcome, "allowed": allowed, "reason": reason},
                    metadata={"tool": tool_call.tool_name, "arguments": tool_call.arguments},
                )
                await self.audit_batcher.add_event(audit_event)

            return {
                "type": "tool_success",
                "tool_call_id": tool_call.tool_call_id,
                "content": result_content,
            }
        except Exception as e:
            # Record error
            if event_id:
                error_event_id = self.session.engine.record_result(
                    event_id, str(e), 1
                )
                self.session.track_event(error_event_id)

            return {
                "type": "tool_error",
                "tool_call_id": tool_call.tool_call_id,
                "content": f"Tool execution failed: {str(e)}",
            }
