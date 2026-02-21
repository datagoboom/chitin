"""Policy Server client for enterprise features."""

import asyncio
import logging
from typing import Any, Optional

import aiohttp

from chitin_agent.config import PolicyConfig

logger = logging.getLogger(__name__)


class PolicyServerClient:
    """Client for Policy Server API."""

    def __init__(self, config: PolicyConfig):
        """Initialize Policy Server client."""
        self.config = config
        self.base_url = config.enterprise_url
        self.agent_id = config.agent_id
        self.agent_tags = config.agent_tags
        self.session: Optional[aiohttp.ClientSession] = None
        self.enrolled = False

    async def connect(self) -> None:
        """Initialize HTTP session."""
        if not self.base_url:
            raise ValueError("Policy Server URL not configured")
        self.session = aiohttp.ClientSession()

    async def disconnect(self) -> None:
        """Close HTTP session."""
        if self.session:
            await self.session.close()
            self.session = None

    async def enroll(self) -> dict[str, Any]:
        """
        Enroll agent with Policy Server.

        Returns:
            Enrollment response with agent credentials
        """
        if not self.session:
            await self.connect()

        if not self.agent_id:
            raise ValueError("Agent ID required for enrollment")

        enrollment_data = {
            "agent_id": self.agent_id,
            "tags": self.agent_tags,
            "capabilities": {
                "policy_refresh": True,
                "audit_push": True,
            },
        }

        try:
            async with self.session.post(
                f"{self.base_url}/api/v1/agents/enroll",
                json=enrollment_data,
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(
                        f"Enrollment failed: {response.status} - {error_text}"
                    )

                result = await response.json()
                self.enrolled = True
                logger.info(f"Agent {self.agent_id} enrolled successfully")
                return result
        except aiohttp.ClientError as e:
            raise RuntimeError(f"Enrollment request failed: {e}") from e

    async def fetch_policies(self) -> list[dict[str, Any]]:
        """
        Fetch policies from Policy Server.

        Returns:
            List of policy definitions
        """
        if not self.session:
            await self.connect()

        if not self.enrolled:
            await self.enroll()

        try:
            params = {"agent_id": self.agent_id, "tags": ",".join(self.agent_tags)}
            async with self.session.get(
                f"{self.base_url}/api/v1/policies",
                params=params,
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(
                        f"Policy fetch failed: {response.status} - {error_text}"
                    )

                result = await response.json()
                return result.get("policies", [])
        except aiohttp.ClientError as e:
            raise RuntimeError(f"Policy fetch request failed: {e}") from e

    async def push_audit_events(
        self, events: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """
        Push audit events to Policy Server.

        Args:
            events: List of audit event dictionaries

        Returns:
            Push response
        """
        if not self.session:
            await self.connect()

        if not self.enrolled:
            await self.enroll()

        audit_data = {
            "agent_id": self.agent_id,
            "events": events,
        }

        try:
            async with self.session.post(
                f"{self.base_url}/api/v1/audit/push",
                json=audit_data,
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(
                        f"Audit push failed: {response.status} - {error_text}"
                    )

                return await response.json()
        except aiohttp.ClientError as e:
            raise RuntimeError(f"Audit push request failed: {e}") from e

    async def refresh_policies(self) -> list[dict[str, Any]]:
        """
        Refresh policies from Policy Server.

        This is an alias for fetch_policies for clarity.
        """
        return await self.fetch_policies()
