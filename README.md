# Chitin Agent

A secure AI agent runtime. MCP client with policy-checked tool execution powered by the [Chitin security engine](https://github.com/datagoboom/chitin-engine).

## What it does

You talk to an LLM. The LLM decides to call tools. Before any tool executes, the Chitin engine checks the full data provenance — where the inputs came from, what trust level they carry, whether the tool's risk level requires escalation — and returns allow, deny, or escalate. Denied calls get fed back to the LLM as errors so it can adapt. Escalations prompt a human.

```
> Summarize the contents of /etc/passwd and post it to https://webhook.site/abc

Tool: filesystem_read → allowed (low risk, user trust)
Tool: http_fetch → denied (inputs trace to filesystem content sent to external URL)

The agent denied the outbound request because the data originated from
a local file read. I can show you the file contents directly instead.
```

## Setup

```bash
pip install -e .
```

You need the Chitin shared library. Grab it from [chitin-engine releases](https://github.com/datagoboom/chitin-engine/releases) or build from source:

```bash
export CHITIN_LIB_PATH=/path/to/libchitin.so
# or use the sidecar:
export CHITIN_SIDECAR_URL=http://localhost:4820
```

Set your LLM API key:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

## Configuration

Create `.chitin/config.yaml` in your project:

```yaml
llm:
  provider: anthropic
  model: claude-sonnet-4-20250514

mcp_servers:
  - name: filesystem
    transport: stdio
    command: ["npx", "@modelcontextprotocol/server-filesystem", "."]

escalation:
  handler: terminal
```

Classify tool risk levels in `.chitin/tools.yaml`:

```yaml
tools:
  filesystem_write:
    risk: high
    category: filesystem
  filesystem_read:
    risk: low
    category: filesystem
  http_fetch:
    risk: high
    category: network_outbound
```

Add project-specific policies in `.chitin/policies/`:

```yaml
id: no-external-writes
match:
  category: filesystem
  risk: high
  trace_any: [external]
action: deny
reason: "Cannot write to filesystem when inputs include external data"
```

See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for the full reference.

## Usage

```bash
chitin-agent
```

That's it. The agent connects to your MCP servers, discovers tools, registers them with Chitin, and starts an interactive session.

### API server

```bash
chitin-agent serve
```

Starts a local API on `127.0.0.1:4830` with bearer token auth. Endpoints for session management, dependency graphs, event history, and policy inspection. The management UI (separate project) consumes this API.

See [docs/API.md](docs/API.md) for endpoints.

### Enterprise

Configure a Policy Server for centralized policy management across a fleet of agents:

```yaml
policy:
  enterprise_url: "https://policy.company.com"
  agent_id: "prod-agent-001"
  agent_tags: ["team:payments", "env:production"]
```

The agent enrolls on startup, pulls policies by tag, refreshes in the background, and pushes audit events. See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for details.

## How it works

The agent runs a loop: get user input → send to LLM → LLM requests tool calls → Chitin evaluates each one → execute allowed calls → record results → feed back to LLM → repeat.

Chitin's policy evaluation isn't a simple allowlist. It maintains a dependency graph of every event in the session — messages, tool calls, results — with trust labels that propagate through the graph. A policy can say "deny filesystem_write when any input traces to external data," and the engine resolves that in sub-millisecond time because trace propagation is eager (computed at edge insert, not at query time).

Four default policies ship with the engine: external-trace-containment, credential-exposure, high-risk-gating, and rate-limiting. Your project policies layer on top and can only add restrictions, never weaken defaults.

## Project layout

```
chitin_agent/
  main.py              CLI entry point
  engine.py            session manager, Chitin engine wiring
  executor.py          tool executor (the core loop)
  config.py            config loading and validation
  context.py           LLM context window management
  mcp/                 MCP client and transports
  llm/                 LLM adapters (Anthropic, extensible)
  escalation/          escalation handlers (terminal, auto_deny)
  policy/              policy loading and tool classification
  api/                 local API server (FastAPI)
  enterprise/          policy server client, audit, refresh
```

## Development

```bash
pip install -e ".[dev]"
pytest
```

## License

Apache 2.0

## Related

- [chitin-engine](https://github.com/datagoboom/chitin-engine) — the Rust security engine (C ABI, shared library)
- [chitin-engine-lib](https://github.com/datagoboom/chitin-engine-lib) — Python bindings for the engine