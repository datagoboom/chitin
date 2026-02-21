# Chitin Agent Configuration Directory

This directory contains **user-specific configuration files** that should **NOT** be committed to the repository.

## What Goes Here (Local Only)

- `config.yaml` or `config.json` - Your personal agent configuration
- `tools.yaml` - Your tool risk classifications
- `policies/*.yaml` - Your custom policies

These files are ignored by git (see `.gitignore`).

## What Goes in the Repo

- `examples/` directory - Example configuration files
- `*.example` files - Template files for users to copy

## Getting Started

1. Copy an example config to get started:
   ```bash
   cp examples/basic_config.json .chitin/config.json
   # or
   cp examples/ollama_config.json .chitin/config.json
   ```

2. Edit the config file with your settings:
   - API keys (or use environment variables)
   - MCP servers
   - Policies
   - Tool classifications

3. Run the agent:
   ```bash
   chitin-agent
   ```

## File Resolution

The agent looks for config files in this order:
1. `.chitin/config.json` (preferred if exists)
2. `.chitin/config.yaml`
3. `.chitin/config.yml`
4. `~/.config/chitin/config.json`
5. `~/.config/chitin/config.yaml`
6. `~/.config/chitin/config.yml`

JSON files take precedence over YAML if both exist.
