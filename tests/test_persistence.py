"""Tests for session persistence."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from chitin_agent.config import AgentConfig
from chitin_agent.engine import Session
from chitin_agent.persistence import SessionPersistence


def test_save_session(tmp_path):
    """Test saving a session."""
    persistence = SessionPersistence(sessions_dir=tmp_path)

    mock_engine = Mock()
    config = AgentConfig()
    session = Session(mock_engine, config)
    session.event_ids = ["event1", "event2"]
    session.message_history = [{"role": "user", "content": "test"}]

    persistence.save_session(session, "test_session")

    session_file = tmp_path / "test_session.json"
    assert session_file.exists()

    with open(session_file) as f:
        data = json.load(f)
        assert data["session_id"] == "test_session"
        assert data["event_ids"] == ["event1", "event2"]


def test_load_session(tmp_path):
    """Test loading a session."""
    persistence = SessionPersistence(sessions_dir=tmp_path)

    session_file = tmp_path / "test_session.json"
    session_data = {
        "session_id": "test_session",
        "created_at": "2024-01-01T00:00:00",
        "event_ids": ["event1", "event2"],
        "message_history": [{"role": "user", "content": "test"}],
        "config": {}
    }

    with open(session_file, "w") as f:
        json.dump(session_data, f)

    loaded = persistence.load_session("test_session")

    assert loaded is not None
    assert loaded["session_id"] == "test_session"
    assert loaded["event_ids"] == ["event1", "event2"]


def test_load_nonexistent_session(tmp_path):
    """Test loading a non-existent session."""
    persistence = SessionPersistence(sessions_dir=tmp_path)
    loaded = persistence.load_session("nonexistent")
    assert loaded is None


def test_list_sessions(tmp_path):
    """Test listing all sessions."""
    persistence = SessionPersistence(sessions_dir=tmp_path)

    # Create multiple sessions
    for i in range(3):
        session_file = tmp_path / f"session_{i}.json"
        session_data = {
            "session_id": f"session_{i}",
            "created_at": f"2024-01-0{i+1}T00:00:00",
            "event_ids": [],
            "message_history": [],
            "config": {}
        }
        with open(session_file, "w") as f:
            json.dump(session_data, f)

    sessions = persistence.list_sessions()
    assert len(sessions) == 3


def test_delete_session(tmp_path):
    """Test deleting a session."""
    persistence = SessionPersistence(sessions_dir=tmp_path)

    session_file = tmp_path / "test_session.json"
    session_file.write_text('{"session_id": "test_session"}')

    persistence.delete_session("test_session")

    assert not session_file.exists()
