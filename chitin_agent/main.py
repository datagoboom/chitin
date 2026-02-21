"""CLI entry point for chitin-agent."""

import argparse
import asyncio
import sys
from typing import Any

from chitin_agent.api.server import start_server
from chitin_agent.api.store import get_session_store
from chitin_agent.config import AgentConfig, load_tool_classifications
from chitin_agent.engine import SessionManager
from chitin_agent.enterprise.audit import AuditBatcher, AuditEvent
from chitin_agent.enterprise.policy_refresh import PolicyRefresher
from chitin_agent.enterprise.policy_server import PolicyServerClient
from chitin_agent.escalation import create_escalation_handler
from chitin_agent.executor import ToolExecutor
from chitin_agent.llm import create_llm_adapter
from chitin_agent.mcp.client import MCPClient
from chitin_agent.policy.classifier import classify_tool
from chitin_agent.policy.loader import PolicyLoader


async def run_session(config: AgentConfig) -> None:
    """Run a single agent session."""
    # Initialize enterprise components if configured
    policy_server_client = None
    audit_batcher = None
    policy_refresher = None

    if config.policy.enterprise_url:
        policy_server_client = PolicyServerClient(config.policy)
        await policy_server_client.connect()

        # Initialize audit batcher
        audit_batcher = AuditBatcher(policy_server_client)

    # Initialize components
    session_manager = SessionManager(config)
    session = session_manager.create_session()

    # Register session in API store (if API is enabled)
    if config.api.enabled:
        session_store = get_session_store()
        session_id = session_store.create_session(session)
        print(f"Session ID: {session_id}", file=sys.stderr)

    # Load policies (including enterprise if configured)
    policy_loader = PolicyLoader(config)
    tool_classifications = load_tool_classifications()

    enterprise_policies = None
    if policy_server_client:
        try:
            enterprise_policies = await policy_server_client.fetch_policies()
            print(f"Loaded {len(enterprise_policies)} policies from Policy Server", file=sys.stderr)
        except Exception as e:
            print(f"Warning: Failed to fetch enterprise policies: {e}", file=sys.stderr)

    policy_loader.load_and_register(
        session.engine, tool_classifications, enterprise_policies=enterprise_policies
    )

    # Start policy refresher if enterprise is enabled
    if policy_server_client:
        policy_refresher = PolicyRefresher(
            session.engine,
            policy_server_client,
            refresh_interval_seconds=config.policy.refresh_interval_seconds,
        )
        await policy_refresher.start()

    # Connect to MCP servers
    # Ensure we have mcp_servers list (from either format)
    if config.mcp_servers is None:
        config.mcp_servers = []
    
    mcp = MCPClient(config)
    try:
        await mcp.connect_all()

        # Register discovered tools with Chitin
        all_tools = mcp.list_all_tools()
        for tool in all_tools:
            risk, category = classify_tool(tool, tool_classifications, config.tool_defaults)
            session.engine.register_tool(tool.name, risk=risk, category=category)
        
        if len(all_tools) == 0:
            print("Warning: No MCP tools discovered. Check MCP server connections.", file=sys.stderr)

        # Create LLM adapter
        llm = create_llm_adapter(config.llm)

        # Create escalation handler
        escalation = create_escalation_handler(
            config.escalation.handler, config.escalation.timeout_seconds
        )

        # Create tool executor
        executor = ToolExecutor(session, mcp, escalation, audit_batcher=audit_batcher)

        # Message history for LLM
        messages: list[dict[str, Any]] = []
        
        # Add system message about available tools if any
        tool_count = len(mcp.list_all_tools())
        if tool_count > 0:
            tool_names = [t.name for t in mcp.list_all_tools()[:10]]  # First 10 tools
            system_msg = f"You are a helpful AI assistant with access to {tool_count} MCP (Model Context Protocol) tools. Available tools include: {', '.join(tool_names)}. When users ask about MCP tools or capabilities, you can use these tools to help them."
            messages.append({"role": "system", "content": system_msg})
        
        print("Chitin Agent ready. Type your message (or 'exit' to quit):\n")

        # Main loop
        while True:
            try:
                # Get user input
                user_input = input("> ").strip()
                if not user_input or user_input.lower() in ("exit", "quit"):
                    break

                # Record user input in Chitin
                from chitin import TrustLevel
                input_event_id = session.engine.ingest(
                    user_input,
                    trust_level=TrustLevel.USER,
                )
                session.track_event(input_event_id)
                messages.append({"role": "user", "content": user_input})

                # Agent loop: LLM may request tools, which produce results,
                # which get fed back, which may trigger more tool calls
                while True:
                    # Get LLM response
                    tool_defs = mcp.tool_definitions()
                    response = await llm.chat(messages, tools=tool_defs)

                    # Process response and execute tool calls
                    text_content, tool_results = await executor.process_llm_response(response)

                    # Display text content if any
                    if text_content:
                        print(f"\n{text_content}\n")

                    # Add assistant message
                    assistant_content = response.content
                    messages.append({"role": "assistant", "content": assistant_content})

                    # If no tool calls, we're done with this turn
                    if not response.has_tool_calls():
                        break

                    # Add tool results as user message
                    messages.append({"role": "user", "content": tool_results})

            except KeyboardInterrupt:
                print("\n\nInterrupted. Exiting...")
                break
            except Exception as e:
                print(f"\nError: {e}", file=sys.stderr)
                import traceback

                traceback.print_exc()
                break

    finally:
        # Flush audit events
        if audit_batcher:
            await audit_batcher.flush()

        # Stop policy refresher
        if policy_refresher:
            await policy_refresher.stop()

        # Disconnect from Policy Server
        if policy_server_client:
            await policy_server_client.disconnect()

        await mcp.disconnect_all()
        # Close LLM adapter session if it has a close method
        if hasattr(llm, "close"):
            await llm.close()
        session_manager.close_session()


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Chitin Agent - AI agent runtime with policy-checked tool execution")
    parser.add_argument(
        "command",
        nargs="?",
        default="chat",
        choices=["chat", "serve", "ui"],
        help="Command to run: chat (default), serve (start API server), or ui (start API server for UI)",
    )

    args = parser.parse_args()

    try:
        config = AgentConfig.load()
    except Exception as e:
        print(f"Failed to load configuration: {e}", file=sys.stderr)
        sys.exit(1)

    if args.command in ("serve", "ui"):
        # Start API server
        start_server(config)
    else:
        # Run interactive session
        try:
            asyncio.run(run_session(config))
        except KeyboardInterrupt:
            print("\nExiting...")
            sys.exit(0)


if __name__ == "__main__":
    main()
