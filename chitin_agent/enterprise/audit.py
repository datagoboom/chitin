"""Audit event batching and management."""

import asyncio
import logging
from collections import deque
from datetime import datetime, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)


class AuditEvent:
    """Represents an audit event."""

    def __init__(
        self,
        event_id: int,
        event_type: str,
        content: str,
        decision: Optional[dict[str, Any]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ):
        """Initialize audit event."""
        self.event_id = event_id
        self.event_type = event_type
        self.content = content
        self.decision = decision or {}
        self.metadata = metadata or {}
        self.timestamp = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "content": self.content,
            "decision": self.decision,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }


class AuditBatcher:
    """Batches audit events and pushes them to Policy Server."""

    def __init__(
        self,
        policy_server_client: Any,  # PolicyServerClient
        batch_size: int = 100,
        batch_interval_seconds: int = 60,
    ):
        """
        Initialize audit batcher.

        Args:
            policy_server_client: Policy Server client instance
            batch_size: Maximum events per batch
            batch_interval_seconds: Maximum time between batches
        """
        self.client = policy_server_client
        self.batch_size = batch_size
        self.batch_interval = timedelta(seconds=batch_interval_seconds)
        self.queue: deque[AuditEvent] = deque()
        self.last_push = datetime.now()
        self._lock = asyncio.Lock()

    async def add_event(self, event: AuditEvent) -> None:
        """Add an event to the batch queue."""
        async with self._lock:
            self.queue.append(event)

            # Check if we should push
            should_push = False
            if len(self.queue) >= self.batch_size:
                should_push = True
                logger.debug(f"Batch size reached ({len(self.queue)} events)")
            elif datetime.now() - self.last_push >= self.batch_interval:
                should_push = True
                logger.debug("Batch interval reached")

            if should_push:
                await self._push_batch()

    async def _push_batch(self) -> None:
        """Push current batch to Policy Server."""
        if not self.queue:
            return

        # Extract events from queue
        events = [self.queue.popleft() for _ in range(min(len(self.queue), self.batch_size))]
        event_dicts = [event.to_dict() for event in events]

        try:
            await self.client.push_audit_events(event_dicts)
            self.last_push = datetime.now()
            logger.info(f"Pushed {len(events)} audit events to Policy Server")
        except Exception as e:
            # Re-queue events on failure
            logger.error(f"Failed to push audit events: {e}")
            for event in reversed(events):
                self.queue.appendleft(event)
            raise

    async def flush(self) -> None:
        """Flush all pending events."""
        async with self._lock:
            while self.queue:
                await self._push_batch()
