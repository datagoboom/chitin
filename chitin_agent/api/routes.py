"""API route handlers."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from chitin_agent.api.auth import verify_token
from chitin_agent.api.models import (
    EventDetail,
    EventSummary,
    GraphEdge,
    GraphNode,
    GraphResponse,
    PolicyInfo,
    SessionDetail,
    SessionSummary,
    ToolInfo,
)
from chitin_agent.api.store import get_session_store

router = APIRouter(prefix="/api", tags=["api"])


# Session management endpoints
@router.get("/sessions", response_model=list[SessionSummary])
async def list_sessions(token: str = Depends(verify_token)) -> list[SessionSummary]:
    """List all sessions."""
    store = get_session_store()
    sessions = store.list_sessions()

    summaries = []
    for metadata in sessions:
        session = store.get_session(metadata["id"])
        event_count = len(session.event_ids) if session else 0

        summaries.append(
            SessionSummary(
                id=metadata["id"],
                created_at=metadata["created_at"],
                event_count=event_count,
                status=metadata["status"],
            )
        )

    return summaries


@router.get("/sessions/{session_id}", response_model=SessionDetail)
async def get_session(
    session_id: str, token: str = Depends(verify_token)
) -> SessionDetail:
    """Get session details."""
    store = get_session_store()
    session = store.get_session(session_id)
    metadata = store.get_metadata(session_id)

    if not session or not metadata:
        raise HTTPException(status_code=404, detail="Session not found")

    return SessionDetail(
        id=session_id,
        created_at=metadata["created_at"],
        event_ids=session.event_ids,
        message_count=len(session.message_history),
        status=metadata["status"],
    )


@router.get("/sessions/{session_id}/graph", response_model=GraphResponse)
async def get_session_graph(
    session_id: str, token: str = Depends(verify_token)
) -> GraphResponse:
    """Get dependency graph for a session."""
    store = get_session_store()
    session = store.get_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Build graph from event IDs
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []

    # For each event, create a node
    # This is simplified - in reality, we'd query Chitin engine for event details
    for event_id in session.event_ids:
        nodes.append(
            GraphNode(
                id=event_id,
                type="event",  # Would be determined from Chitin
                content=f"Event {event_id}",
            )
        )

    # Create edges between consecutive events
    for i in range(len(session.event_ids) - 1):
        edges.append(
            GraphEdge(
                from_id=session.event_ids[i],
                to_id=session.event_ids[i + 1],
                relation="triggers",
            )
        )

    return GraphResponse(nodes=nodes, edges=edges)


@router.get("/sessions/{session_id}/events", response_model=list[EventSummary])
async def list_session_events(
    session_id: str, token: str = Depends(verify_token)
) -> list[EventSummary]:
    """List events for a session."""
    store = get_session_store()
    session = store.get_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    events = []
    for event_id in session.event_ids:
        # In a real implementation, we'd query Chitin for event details
        events.append(
            EventSummary(
                event_id=event_id,
                type="event",  # Would be determined from Chitin
                content=f"Event {event_id}",
            )
        )

    return events


@router.get("/sessions/{session_id}/events/{event_id}", response_model=EventDetail)
async def get_event_detail(
    session_id: str, event_id: int, token: str = Depends(verify_token)
) -> EventDetail:
    """Get event detail with explain output."""
    store = get_session_store()
    session = store.get_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if event_id not in session.event_ids:
        raise HTTPException(status_code=404, detail="Event not found")

    # Get explain result from Chitin engine
    explain_result = None
    try:
        explain_result_obj = session.engine.explain(event_id)
        explain_result = {
            "trace_chain": str(explain_result_obj),
            # Would include more details from ExplainResult
        }
    except Exception:
        pass  # Explain may not be available for all events

    return EventDetail(
        event_id=event_id,
        type="event",
        content=f"Event {event_id}",
        trust_level="unknown",
        metadata={},
        explain_result=explain_result,
    )


# Policy endpoints
@router.get("/policies", response_model=list[PolicyInfo])
async def list_policies(token: str = Depends(verify_token)) -> list[PolicyInfo]:
    """List all active policies, grouped by source."""
    # TODO: Implement policy listing
    return []


@router.get("/policies/local", response_model=list[PolicyInfo])
async def list_local_policies(token: str = Depends(verify_token)) -> list[PolicyInfo]:
    """List editable local policies."""
    # TODO: Implement local policy listing
    return []


@router.put("/policies/local/{policy_id}")
async def update_local_policy(
    policy_id: str, policy_data: dict[str, Any], token: str = Depends(verify_token)
) -> dict[str, str]:
    """Update a local policy."""
    # TODO: Implement policy update
    raise HTTPException(status_code=404, detail="Policy not found")


# Tool endpoints
@router.get("/tools", response_model=list[ToolInfo])
async def list_tools(token: str = Depends(verify_token)) -> list[ToolInfo]:
    """List registered tools with risk/category."""
    from chitin_agent.config import load_tool_classifications

    classifications = load_tool_classifications()
    tools = []

    for tool_name, classification in classifications.items():
        tools.append(
            ToolInfo(
                name=tool_name,
                risk=classification.get("risk", "medium"),
                category=classification.get("category"),
            )
        )

    return tools
