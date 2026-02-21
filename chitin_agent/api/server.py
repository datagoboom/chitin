"""API server implementation."""

import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from chitin_agent.api.auth import get_auth
from chitin_agent.api.routes import router
from chitin_agent.config import AgentConfig


def create_app(config: AgentConfig) -> FastAPI:
    """Create FastAPI application."""
    app = FastAPI(
        title="Chitin Agent API",
        description="Local API for Chitin Agent management",
        version="0.1.0",
    )

    # CORS middleware (allow localhost for UI)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routes
    app.include_router(router)

    return app


def start_server(config: AgentConfig) -> None:
    """Start the API server."""
    # Generate/load token
    auth = get_auth()
    token = auth.get_token()

    # Print token to stderr (for UI to read)
    print(f"API token: {token}", file=sys.stderr)
    print(f"Token saved to: {auth.token_file}", file=sys.stderr)

    # Parse bind address
    bind = config.api.bind
    if ":" in bind:
        host, port_str = bind.rsplit(":", 1)
        port = int(port_str)
    else:
        host = bind
        port = 4830

    app = create_app(config)

    print(f"Starting API server on {host}:{port}", file=sys.stderr)
    print(f"API documentation: http://{host}:{port}/docs", file=sys.stderr)

    uvicorn.run(app, host=host, port=port, log_level="info")
