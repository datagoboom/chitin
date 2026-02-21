"""Tests for context window management."""

from chitin_agent.context import ContextManager


def test_context_manager_estimate_tokens():
    """Test token estimation."""
    manager = ContextManager()
    messages = [
        {"role": "user", "content": "Hello, world!"},
        {"role": "assistant", "content": "Hi there!"}
    ]
    tokens = manager.estimate_tokens(messages)
    assert tokens > 0
    # Rough estimate: ~30 chars / 4 = ~7-8 tokens
    assert tokens < 20


def test_context_manager_no_truncation():
    """Test that short messages aren't truncated."""
    manager = ContextManager(max_tokens=1000)
    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi"}
    ]
    truncated = manager.truncate_messages(messages, 10)
    assert len(truncated) == len(messages)


def test_context_manager_truncation():
    """Test message truncation when over limit."""
    manager = ContextManager(max_tokens=100, keep_recent=3)
    messages = [
        {"role": "user", "content": "First message"},
    ] + [
        {"role": "assistant", "content": f"Message {i}"}
        for i in range(20)
    ]

    # Estimate would be high
    truncated = manager.truncate_messages(messages, 1000)

    # Should keep first + recent 3
    assert len(truncated) == 4  # First + 3 recent
    assert truncated[0]["content"] == "First message"
    assert truncated[-1]["content"] == "Message 19"


def test_context_manager_keep_recent():
    """Test that keep_recent setting is respected."""
    manager = ContextManager(max_tokens=100, keep_recent=5)
    messages = [
        {"role": "user", "content": "First"},
    ] + [
        {"role": "assistant", "content": f"Msg {i}"}
        for i in range(10)
    ]

    truncated = manager.truncate_messages(messages, 1000)

    # Should keep first + 5 recent = 6 total
    assert len(truncated) == 6
