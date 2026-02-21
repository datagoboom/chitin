"""API response models."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class SessionSummary(BaseModel):
    """Session summary for list endpoint."""

    id: str
    created_at: datetime
    event_count: int
    status: str  # "active", "completed", "saved"


class SessionDetail(BaseModel):
    """Detailed session information."""

    id: str
    created_at: datetime
    event_ids: list[int]
    message_count: int
    status: str


class GraphNode(BaseModel):
    """Graph node representation."""

    id: int  # event_id
    type: str  # "user_input", "llm_response", "tool_call", "tool_result"
    content: str
    timestamp: Optional[datetime] = None


class GraphEdge(BaseModel):
    """Graph edge representation."""

    from_id: int
    to_id: int
    relation: str  # "triggers", "results_from", "depends_on"


class GraphResponse(BaseModel):
    """Dependency graph response."""

    nodes: list[GraphNode]
    edges: list[GraphEdge]


class EventSummary(BaseModel):
    """Event summary for list endpoint."""

    event_id: int
    type: str
    content: str
    decision: Optional[str] = None  # "allow", "deny", "escalate"
    timestamp: Optional[datetime] = None


class EventDetail(BaseModel):
    """Detailed event information."""

    event_id: int
    type: str
    content: str
    trust_level: str
    metadata: dict[str, Any]
    decision: Optional[dict[str, Any]] = None
    explain_result: Optional[dict[str, Any]] = None
    timestamp: Optional[datetime] = None


class PolicyInfo(BaseModel):
    """Policy information."""

    id: str
    source: str  # "default", "user", "project", "enterprise"
    name: str
    description: Optional[str] = None
    rules: list[dict[str, Any]]


class ToolInfo(BaseModel):
    """Tool information."""

    name: str
    risk: str
    category: Optional[str] = None
    description: Optional[str] = None
