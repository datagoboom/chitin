"""Mock Policy Server for testing enterprise features."""

import json
from datetime import datetime
from typing import Any, Optional
from unittest.mock import Mock

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop


class MockPolicyServer:
    """Mock Policy Server implementation."""

    def __init__(self):
        """Initialize mock server."""
        self.agents: dict[str, dict[str, Any]] = {}
        self.policies: dict[str, list[dict[str, Any]]] = {}
        self.audit_events: list[dict[str, Any]] = []

    async def enroll_agent(self, request: web.Request) -> web.Response:
        """Handle agent enrollment."""
        data = await request.json()
        agent_id = data.get("agent_id")
        tags = data.get("tags", [])

        if not agent_id:
            return web.json_response(
                {"error": "agent_id required"}, status=400
            )

        self.agents[agent_id] = {
            "agent_id": agent_id,
            "tags": tags,
            "enrolled_at": datetime.now().isoformat(),
            "capabilities": data.get("capabilities", {}),
        }

        return web.json_response({
            "agent_id": agent_id,
            "status": "enrolled",
            "enrolled_at": self.agents[agent_id]["enrolled_at"],
        })

    async def fetch_policies(self, request: web.Request) -> web.Response:
        """Handle policy fetch."""
        agent_id = request.query.get("agent_id")
        tags_str = request.query.get("tags", "")
        tags = [t.strip() for t in tags_str.split(",") if t.strip()]

        if not agent_id:
            return web.json_response(
                {"error": "agent_id required"}, status=400
            )

        # Get policies for this agent (filtered by tags if provided)
        agent_policies = self.policies.get(agent_id, [])

        # Filter by tags if provided
        if tags:
            filtered = []
            for policy in agent_policies:
                policy_tags = policy.get("tags", [])
                if any(tag in policy_tags for tag in tags):
                    filtered.append(policy)
            agent_policies = filtered

        return web.json_response({
            "policies": agent_policies,
            "count": len(agent_policies),
        })

    async def push_audit(self, request: web.Request) -> web.Response:
        """Handle audit event push."""
        data = await request.json()
        agent_id = data.get("agent_id")
        events = data.get("events", [])

        if not agent_id:
            return web.json_response(
                {"error": "agent_id required"}, status=400
            )

        # Store audit events
        for event in events:
            event["agent_id"] = agent_id
            event["received_at"] = datetime.now().isoformat()
            self.audit_events.append(event)

        return web.json_response({
            "status": "success",
            "events_received": len(events),
        })

    def add_policy(self, agent_id: str, policy: dict[str, Any]) -> None:
        """Add a policy for an agent (for testing)."""
        if agent_id not in self.policies:
            self.policies[agent_id] = []
        self.policies[agent_id].append(policy)

    def get_audit_events(self, agent_id: Optional[str] = None) -> list[dict[str, Any]]:
        """Get audit events (optionally filtered by agent_id)."""
        if agent_id:
            return [e for e in self.audit_events if e.get("agent_id") == agent_id]
        return self.audit_events.copy()

    def clear_audit_events(self) -> None:
        """Clear all audit events."""
        self.audit_events.clear()


def create_mock_server_app() -> tuple[web.Application, MockPolicyServer]:
    """Create aiohttp app with mock Policy Server routes."""
    app = web.Application()
    server = MockPolicyServer()

    app.router.add_post("/api/v1/agents/enroll", server.enroll_agent)
    app.router.add_get("/api/v1/policies", server.fetch_policies)
    app.router.add_post("/api/v1/audit/push", server.push_audit)

    # Store server instance in app for access in tests
    # Use a proper key to avoid warnings
    MOCK_SERVER_KEY = web.AppKey("mock_server", MockPolicyServer)
    app[MOCK_SERVER_KEY] = server

    return app, server
