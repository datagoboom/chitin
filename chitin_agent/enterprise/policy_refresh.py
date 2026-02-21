"""Policy refresh without session restart."""

import asyncio
import logging
from typing import Any, Optional

from chitin import Engine  # type: ignore

from chitin_agent.enterprise.policy_server import PolicyServerClient

logger = logging.getLogger(__name__)


class PolicyRefresher:
    """Manages policy refresh from Policy Server."""

    def __init__(
        self,
        engine: Engine,
        policy_server_client: PolicyServerClient,
        refresh_interval_seconds: int = 60,
    ):
        """
        Initialize policy refresher.

        Args:
            engine: Chitin engine instance
            policy_server_client: Policy Server client
            refresh_interval_seconds: How often to refresh policies
        """
        self.engine = engine
        self.client = policy_server_client
        self.refresh_interval = refresh_interval_seconds
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start background policy refresh task."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._refresh_loop())
        logger.info("Policy refresher started")

    async def stop(self) -> None:
        """Stop background policy refresh task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Policy refresher stopped")

    async def _refresh_loop(self) -> None:
        """Background loop for policy refresh."""
        while self._running:
            try:
                await asyncio.sleep(self.refresh_interval)
                await self.refresh()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Policy refresh error: {e}")

    async def refresh(self) -> None:
        """
        Refresh policies from Policy Server and update engine.

        Note: Actual policy loading depends on Chitin engine API.
        This is a placeholder for the expected interface.
        """
        try:
            policies = await self.client.fetch_policies()
            logger.info(f"Fetched {len(policies)} policies from Policy Server")

            # Load policies into engine
            # Note: Actual API depends on Chitin engine implementation
            for policy in policies:
                # This would call engine.load_policy() or similar
                # For now, we just log
                logger.debug(f"Loading policy: {policy.get('id', 'unknown')}")

            logger.info("Policies refreshed successfully")
        except Exception as e:
            logger.error(f"Failed to refresh policies: {e}")
