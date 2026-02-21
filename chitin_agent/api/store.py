"""Session store for API."""

import uuid
from datetime import datetime
from typing import Optional

from chitin_agent.engine import Session


class SessionStore:
    """Stores active and completed sessions."""

    def __init__(self):
        """Initialize session store."""
        self.sessions: dict[str, Session] = {}
        self.session_metadata: dict[str, dict] = {}

    def create_session(self, session: Session) -> str:
        """Store a session and return its ID."""
        session_id = str(uuid.uuid4())
        self.sessions[session_id] = session
        self.session_metadata[session_id] = {
            "id": session_id,
            "created_at": datetime.now(),
            "status": "active",
        }
        return session_id

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get a session by ID."""
        return self.sessions.get(session_id)

    def get_metadata(self, session_id: str) -> Optional[dict]:
        """Get session metadata."""
        return self.session_metadata.get(session_id)

    def list_sessions(self) -> list[dict]:
        """List all sessions."""
        return list(self.session_metadata.values())

    def update_status(self, session_id: str, status: str) -> None:
        """Update session status."""
        if session_id in self.session_metadata:
            self.session_metadata[session_id]["status"] = status

    def remove_session(self, session_id: str) -> None:
        """Remove a session."""
        self.sessions.pop(session_id, None)
        self.session_metadata.pop(session_id, None)


# Global session store
_session_store = SessionStore()


def get_session_store() -> SessionStore:
    """Get the global session store."""
    return _session_store
