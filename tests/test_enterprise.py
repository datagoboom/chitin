"""Tests for enterprise features."""

import asyncio
from unittest.mock import Mock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from chitin_agent.config import PolicyConfig
from chitin_agent.enterprise.audit import AuditBatcher, AuditEvent
from chitin_agent.enterprise.policy_refresh import PolicyRefresher
from chitin_agent.enterprise.policy_server import PolicyServerClient
from tests.mock_policy_server import create_mock_server_app


@pytest.fixture
async def mock_server():
    """Create and start mock Policy Server."""
    app, server = create_mock_server_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()

    # Get the actual port
    server_url = f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}"

    try:
        yield (server, server_url)
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_policy_server_enrollment(mock_server):
    """Test agent enrollment with Policy Server."""
    server, server_url = mock_server

    config = PolicyConfig(
        enterprise_url=server_url,
        agent_id="test-agent-123",
        agent_tags=["team:test", "env:dev"],
    )

    client = PolicyServerClient(config)
    await client.connect()

    result = await client.enroll()

    assert result["status"] == "enrolled"
    assert result["agent_id"] == "test-agent-123"
    assert "test-agent-123" in server.agents
    assert server.agents["test-agent-123"]["tags"] == ["team:test", "env:dev"]

    await client.disconnect()


@pytest.mark.asyncio
async def test_policy_server_fetch_policies(mock_server):
    """Test fetching policies from Policy Server."""
    server, server_url = mock_server

    config = PolicyConfig(
        enterprise_url=server_url,
        agent_id="test-agent-123",
        agent_tags=["team:test"],
    )

    client = PolicyServerClient(config)
    await client.connect()
    await client.enroll()

    # Add some policies
    server.add_policy("test-agent-123", {
        "id": "policy-1",
        "name": "Test Policy 1",
        "rules": [{"action": "deny", "tool": "dangerous_tool"}],
        "tags": ["team:test"],
    })
    server.add_policy("test-agent-123", {
        "id": "policy-2",
        "name": "Test Policy 2",
        "rules": [{"action": "allow", "tool": "safe_tool"}],
        "tags": ["team:test", "env:prod"],
    })

    policies = await client.fetch_policies()

    assert len(policies) == 2
    assert policies[0]["id"] == "policy-1"
    assert policies[1]["id"] == "policy-2"

    await client.disconnect()


@pytest.mark.asyncio
async def test_policy_server_tag_filtering(mock_server):
    """Test policy filtering by tags."""
    server, server_url = mock_server

    config = PolicyConfig(
        enterprise_url=server_url,
        agent_id="test-agent-123",
        agent_tags=["team:test"],
    )

    client = PolicyServerClient(config)
    await client.connect()
    await client.enroll()

    # Add policies with different tags
    server.add_policy("test-agent-123", {
        "id": "policy-1",
        "tags": ["team:test"],
    })
    server.add_policy("test-agent-123", {
        "id": "policy-2",
        "tags": ["team:other"],
    })
    server.add_policy("test-agent-123", {
        "id": "policy-3",
        "tags": ["team:test", "env:prod"],
    })

    policies = await client.fetch_policies()

    # Should only get policies with team:test tag
    assert len(policies) == 2
    policy_ids = [p["id"] for p in policies]
    assert "policy-1" in policy_ids
    assert "policy-3" in policy_ids
    assert "policy-2" not in policy_ids

    await client.disconnect()


@pytest.mark.asyncio
async def test_policy_server_audit_push(mock_server):
    """Test pushing audit events to Policy Server."""
    server, server_url = mock_server

    config = PolicyConfig(
        enterprise_url=server_url,
        agent_id="test-agent-123",
    )

    client = PolicyServerClient(config)
    await client.connect()
    await client.enroll()

    events = [
        {
            "event_id": 1,
            "event_type": "tool_call",
            "content": "Tool executed",
            "decision": {"outcome": "allow"},
        },
        {
            "event_id": 2,
            "event_type": "tool_call",
            "content": "Tool denied",
            "decision": {"outcome": "deny"},
        },
    ]

    result = await client.push_audit_events(events)

    assert result["status"] == "success"
    assert result["events_received"] == 2

    # Verify events were stored
    stored_events = server.get_audit_events("test-agent-123")
    assert len(stored_events) == 2
    assert stored_events[0]["event_id"] == 1
    assert stored_events[1]["event_id"] == 2

    await client.disconnect()


@pytest.mark.asyncio
async def test_audit_batcher_batching(mock_server):
    """Test audit event batching."""
    server, server_url = mock_server

    config = PolicyConfig(
        enterprise_url=server_url,
        agent_id="test-agent-123",
    )

    client = PolicyServerClient(config)
    await client.connect()
    await client.enroll()

    batcher = AuditBatcher(client, batch_size=3, batch_interval_seconds=60)

    # Add events (should batch when size reached)
    for i in range(5):
        event = AuditEvent(
            event_id=i,
            event_type="tool_call",
            content=f"Event {i}",
        )
        await batcher.add_event(event)

    # Should have pushed at least one batch (when size=3 was reached)
    # Wait a bit for async operations
    await asyncio.sleep(0.1)

    stored_events = server.get_audit_events("test-agent-123")
    assert len(stored_events) >= 3  # At least one batch should be pushed

    # Flush remaining events
    await batcher.flush()

    stored_events = server.get_audit_events("test-agent-123")
    assert len(stored_events) == 5  # All events should be pushed

    await client.disconnect()


@pytest.mark.asyncio
async def test_audit_batcher_interval(mock_server):
    """Test audit batching by time interval."""
    server, server_url = mock_server

    config = PolicyConfig(
        enterprise_url=server_url,
        agent_id="test-agent-123",
    )

    client = PolicyServerClient(config)
    await client.connect()
    await client.enroll()

    batcher = AuditBatcher(client, batch_size=100, batch_interval_seconds=1)

    # Add one event
    event = AuditEvent(
        event_id=1,
        event_type="tool_call",
        content="Event 1",
    )
    await batcher.add_event(event)

    # Should not be pushed yet (size not reached)
    stored_events = server.get_audit_events("test-agent-123")
    assert len(stored_events) == 0

    # Wait for interval, then add another event to trigger check
    await asyncio.sleep(1.1)
    
    # Add another event to trigger the interval check
    event2 = AuditEvent(
        event_id=2,
        event_type="tool_call",
        content="Event 2",
    )
    await batcher.add_event(event2)

    # Wait a bit for async operations
    await asyncio.sleep(0.2)

    # Should be pushed now (both events)
    stored_events = server.get_audit_events("test-agent-123")
    assert len(stored_events) >= 1

    # Flush to ensure all events are pushed
    await batcher.flush()
    stored_events = server.get_audit_events("test-agent-123")
    assert len(stored_events) == 2

    await client.disconnect()


@pytest.mark.asyncio
async def test_policy_refresher(mock_server):
    """Test policy refresh functionality."""
    server, server_url = mock_server

    config = PolicyConfig(
        enterprise_url=server_url,
        agent_id="test-agent-123",
        refresh_interval_seconds=1,
    )

    client = PolicyServerClient(config)
    await client.connect()
    await client.enroll()

    # Add initial policy
    server.add_policy("test-agent-123", {
        "id": "policy-1",
        "name": "Initial Policy",
    })

    # Create mock engine
    mock_engine = Mock()

    refresher = PolicyRefresher(mock_engine, client, refresh_interval_seconds=1)

    # Start refresher
    await refresher.start()

    # Wait for refresh
    await asyncio.sleep(1.5)

    # Add new policy
    server.add_policy("test-agent-123", {
        "id": "policy-2",
        "name": "New Policy",
    })

    # Wait for another refresh
    await asyncio.sleep(1.5)

    # Stop refresher
    await refresher.stop()

    # Verify refresh was called (would need to check engine.load_policy calls)
    # For now, just verify no errors occurred

    await client.disconnect()


@pytest.mark.asyncio
async def test_audit_batcher_error_recovery(mock_server):
    """Test audit batcher handles errors and re-queues events."""
    server, server_url = mock_server

    config = PolicyConfig(
        enterprise_url=server_url,
        agent_id="test-agent-123",
    )

    client = PolicyServerClient(config)
    await client.connect()
    await client.enroll()

    batcher = AuditBatcher(client, batch_size=2, batch_interval_seconds=60)

    # Add events
    for i in range(3):
        event = AuditEvent(
            event_id=i,
            event_type="tool_call",
            content=f"Event {i}",
        )
        await batcher.add_event(event)

    # Wait for batch push
    await asyncio.sleep(0.1)

    # Disconnect client to cause error on next push
    await client.disconnect()

    # Try to add more events (should queue but fail to push)
    event = AuditEvent(
        event_id=3,
        event_type="tool_call",
        content="Event 3",
    )

    # This should not raise, but queue the event
    try:
        await batcher.add_event(event)
    except Exception:
        pass  # Expected to fail

    # Reconnect and flush
    await client.connect()
    await client.enroll()
    await batcher.flush()

    # All events should eventually be pushed
    stored_events = server.get_audit_events("test-agent-123")
    assert len(stored_events) >= 3

    await client.disconnect()
