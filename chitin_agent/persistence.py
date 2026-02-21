"""Session persistence - save and resume sessions."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from chitin_agent.config import AgentConfig
from chitin_agent.engine import Session


class SessionPersistence:
    """Handles saving and loading sessions."""

    def __init__(self, sessions_dir: Optional[Path] = None):
        """
        Initialize session persistence.

        Args:
            sessions_dir: Directory to store sessions (default: ~/.config/chitin/sessions)
        """
        if sessions_dir is None:
            sessions_dir = Path.home() / ".config" / "chitin" / "sessions"
        self.sessions_dir = sessions_dir
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def save_session(self, session: Session, session_id: str) -> None:
        """Save session state to disk."""
        session_file = self.sessions_dir / f"{session_id}.json"

        # Save session metadata (not the full engine state - that's not serializable)
        session_data = {
            "session_id": session_id,
            "created_at": datetime.now().isoformat(),
            "event_ids": session.event_ids,
            "message_history": session.message_history,
            "config": session.config.model_dump() if hasattr(session.config, "model_dump") else {},
        }

        with open(session_file, "w") as f:
            json.dump(session_data, f, indent=2)

    def load_session(self, session_id: str) -> Optional[dict[str, Any]]:
        """Load session state from disk."""
        session_file = self.sessions_dir / f"{session_id}.json"
        if not session_file.exists():
            return None

        with open(session_file, "r") as f:
            return json.load(f)

    def list_sessions(self) -> list[dict[str, Any]]:
        """List all saved sessions."""
        sessions = []
        for session_file in self.sessions_dir.glob("*.json"):
            try:
                with open(session_file, "r") as f:
                    session_data = json.load(f)
                    sessions.append(session_data)
            except Exception:
                continue
        return sorted(sessions, key=lambda x: x.get("created_at", ""), reverse=True)

    def delete_session(self, session_id: str) -> None:
        """Delete a saved session."""
        session_file = self.sessions_dir / f"{session_id}.json"
        if session_file.exists():
            session_file.unlink()
