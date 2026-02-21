"""Session Manager and Chitin engine wiring."""

from typing import Optional

from chitin import Engine as ChitinEngine  # type: ignore
import chitin

from chitin_agent.config import AgentConfig, load_tool_classifications


class Session:
    """Manages a single agent session."""

    def __init__(self, engine: ChitinEngine, config: AgentConfig, session_id: Optional[str] = None):
        """Initialize session with Chitin engine."""
        self.engine = engine
        self.config = config
        self.session_id = session_id
        self.event_ids: list[int] = []  # Chitin returns int event IDs
        self.message_history: list[dict[str, str]] = []
        self.agent_tags = config.policy.agent_tags

    def track_event(self, event_id: int) -> None:
        """Track an event ID for context windowing."""
        self.event_ids.append(event_id)

    def recent_event_ids(self, limit: int = 50) -> list[int]:
        """Get recent event IDs for trace propagation."""
        return self.event_ids[-limit:]


class SessionManager:
    """Manages Chitin engine instances and sessions."""

    def __init__(self, config: AgentConfig):
        """Initialize session manager."""
        self.config = config
        self.current_session: Optional[Session] = None

    def create_session(self) -> Session:
        """Create a new session with a Chitin engine instance."""
        # Initialize Chitin engine
        # Engine takes config_path (optional) - policies are loaded from config path
        config_path = None
        if self.config.chitin.lib_path:
            # If lib_path is set, use it as config_path (or set env var)
            import os
            os.environ["CHITIN_LIB_PATH"] = self.config.chitin.lib_path
        if self.config.chitin.sidecar_url:
            import os
            os.environ["CHITIN_SIDECAR_URL"] = self.config.chitin.sidecar_url

        engine = ChitinEngine(config_path=config_path)

        # Register tools from classifications
        tool_classifications = load_tool_classifications()
        for tool_name, classification in tool_classifications.items():
            risk = classification.get("risk", self.config.tool_defaults.unknown_risk)
            category = classification.get("category")
            engine.register_tool(tool_name, risk=risk, category=category)

        session = Session(engine, self.config)
        self.current_session = session
        return session

    def close_session(self) -> None:
        """Close the current session."""
        if self.current_session:
            self.current_session.engine.close()
            self.current_session = None
