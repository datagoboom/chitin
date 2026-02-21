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
        import os
        
        # Prioritize native library over sidecar
        # If lib_path is set, use it and clear sidecar_url to force native mode
        if self.config.chitin.lib_path:
            os.environ["CHITIN_LIB_PATH"] = self.config.chitin.lib_path
            # Clear sidecar URL to ensure native library is used
            if "CHITIN_SIDECAR_URL" in os.environ:
                del os.environ["CHITIN_SIDECAR_URL"]
        elif self.config.chitin.sidecar_url:
            # Only use sidecar if lib_path is not set
            os.environ["CHITIN_SIDECAR_URL"] = self.config.chitin.sidecar_url
            # Clear lib_path to ensure sidecar is used
            if "CHITIN_LIB_PATH" in os.environ:
                del os.environ["CHITIN_LIB_PATH"]
        else:
            # Check environment variables
            if os.getenv("CHITIN_LIB_PATH"):
                # Native library available, clear sidecar
                if "CHITIN_SIDECAR_URL" in os.environ:
                    del os.environ["CHITIN_SIDECAR_URL"]
            elif not os.getenv("CHITIN_SIDECAR_URL"):
                # Try to use native library from wheel if available
                # The chitin package should find it automatically
                pass
        
        config_path = None
        try:
            engine = ChitinEngine(config_path=config_path)
        except Exception as e:
            # If initialization fails, provide helpful error
            if "sidecar" in str(e).lower() or "http" in str(e).lower():
                raise RuntimeError(
                    f"Chitin engine initialization failed: {e}\n"
                    "The engine is trying to use HTTP/sidecar mode.\n"
                    "To use the native library:\n"
                    "  1. Ensure chitin-engine-lib is installed with the native library\n"
                    "  2. Unset CHITIN_SIDECAR_URL if it's set: unset CHITIN_SIDECAR_URL\n"
                    "  3. The native library should be found automatically from the wheel\n"
                    "\n"
                    "See SETUP_CHITIN.md for more details."
                ) from e
            raise

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
