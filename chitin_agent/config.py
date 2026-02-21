"""Configuration loading and validation."""

import json
import os
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMConfig(BaseModel):
    """LLM provider configuration."""

    provider: str = Field(default="anthropic", description="LLM provider: anthropic, ollama, openai")
    model: str = Field(default="claude-sonnet-4-20250514", description="Model name")
    max_tokens: int = Field(default=8192, description="Maximum tokens in response")
    api_key: Optional[str] = Field(default=None, description="API key (from env if not set)")
    base_url: Optional[str] = Field(default=None, description="Base URL for LLM API (for Ollama, etc.)")


class MCPServerConfig(BaseModel):
    """MCP server configuration (standard MCP format)."""

    # Standard MCP format: command + args for stdio
    command: Optional[str | list[str]] = Field(default=None, description="Command for stdio transport")
    args: Optional[list[str]] = Field(default=None, description="Command arguments")
    
    # Alternative: URL for sse/http transports
    url: Optional[str] = Field(default=None, description="URL for sse/http transport")
    
    # Legacy format support (deprecated)
    transport: Optional[str] = Field(default=None, description="Transport type: stdio, sse, or http (deprecated)")
    name: Optional[str] = Field(default=None, description="Server name (deprecated, use key in mcpServers dict)")

    def model_post_init(self, __context: Any) -> None:
        """Post-init validation and normalization."""
        # Normalize command to list format
        if isinstance(self.command, str):
            if self.args:
                # If command is string and args exist, combine them
                self.command = [self.command] + self.args
                self.args = None
            else:
                # Single command string
                self.command = [self.command]
        
        # Determine transport from config
        if self.transport is None:
            # Auto-detect: if url is set, use http; otherwise stdio
            if self.url:
                self.transport = "http"  # Default to http for URLs
            else:
                self.transport = "stdio"  # Default to stdio for commands
        
        # Validate transport
        if self.transport not in ("stdio", "sse", "http"):
            raise ValueError(f"Invalid transport: {self.transport}. Must be stdio, sse, or http")
        
        # Validate transport-specific params
        if self.transport == "stdio":
            if not self.command:
                raise ValueError("stdio transport requires 'command' field")
            # Ensure command is a list
            if isinstance(self.command, str):
                self.command = [self.command]
        elif self.transport in ("sse", "http"):
            if not self.url:
                raise ValueError(f"{self.transport} transport requires 'url' field")


class EscalationConfig(BaseModel):
    """Escalation handler configuration."""

    handler: str = Field(default="terminal", description="Handler type: terminal, auto_deny, queue")
    timeout_seconds: int = Field(default=300, description="Timeout for terminal escalation")


class PolicyConfig(BaseModel):
    """Policy configuration."""

    enterprise_url: Optional[str] = Field(default=None, description="Policy Server URL")
    refresh_interval_seconds: int = Field(default=60, description="Policy refresh interval")
    agent_id: Optional[str] = Field(default=None, description="Agent ID for enterprise enrollment")
    agent_tags: list[str] = Field(default_factory=list, description="Agent tags")


class APIConfig(BaseModel):
    """Local API configuration."""

    enabled: bool = Field(default=False, description="Enable local API server")
    bind: str = Field(default="127.0.0.1:4830", description="Bind address")


class ChitinConfig(BaseModel):
    """Chitin engine configuration."""

    lib_path: Optional[str] = Field(default=None, description="Path to libchitin.so")
    sidecar_url: Optional[str] = Field(default=None, description="Sidecar URL fallback")


class ToolDefaultsConfig(BaseModel):
    """Tool risk defaults."""

    unknown_risk: str = Field(default="medium", description="Risk for unclassified tools")

    @field_validator("unknown_risk")
    @classmethod
    def validate_risk(cls, v: str) -> str:
        """Validate risk level."""
        if v not in ("low", "medium", "high", "critical"):
            raise ValueError(f"Invalid risk level: {v}")
        return v


class AgentConfig(BaseSettings):
    """Main agent configuration."""

    model_config = SettingsConfigDict(
        env_prefix="CHITIN_",
        case_sensitive=False,
        extra="ignore",
    )

    llm: LLMConfig = Field(default_factory=LLMConfig)
    mcp_servers: list[MCPServerConfig] = Field(default_factory=list)
    tool_defaults: ToolDefaultsConfig = Field(default_factory=ToolDefaultsConfig)
    escalation: EscalationConfig = Field(default_factory=EscalationConfig)
    policy: PolicyConfig = Field(default_factory=PolicyConfig)
    api: APIConfig = Field(default_factory=APIConfig)
    chitin: ChitinConfig = Field(default_factory=ChitinConfig)

    @classmethod
    def load(cls, config_path: Optional[Path | str] = None) -> "AgentConfig":
        """Load configuration from file and environment."""
        if config_path is None:
            config_path = find_config_file()
        elif isinstance(config_path, str):
            config_path = Path(config_path)

        config_dict: dict[str, Any] = {}
        if config_path and config_path.exists():
            # Load JSON or YAML based on file extension
            if config_path.suffix.lower() == ".json":
                with open(config_path, "r") as f:
                    config_dict = json.load(f) or {}
            else:
                # Default to YAML for .yaml, .yml, or no extension
                with open(config_path, "r") as f:
                    config_dict = yaml.safe_load(f) or {}

        # Convert standard MCP format (mcpServers) to internal format
        # Standard format: mcpServers: { server_name: { command, args } }
        # Internal format: mcp_servers: [ { name, transport, command, url } ]
        if "mcpServers" in config_dict and config_dict["mcpServers"]:
            mcp_servers_list = []
            for server_name, server_config in config_dict["mcpServers"].items():
                # Convert to internal format
                server_dict = dict(server_config) if isinstance(server_config, dict) else {}
                server_dict["name"] = server_name
                # If command is a string, convert to list
                if "command" in server_dict and isinstance(server_dict["command"], str):
                    if "args" in server_dict and server_dict["args"]:
                        server_dict["command"] = [server_dict["command"]] + server_dict["args"]
                        del server_dict["args"]
                    else:
                        server_dict["command"] = [server_dict["command"]]
                # Auto-detect transport
                if "transport" not in server_dict:
                    if "url" in server_dict:
                        server_dict["transport"] = "http"
                    else:
                        server_dict["transport"] = "stdio"
                mcp_servers_list.append(server_dict)
            config_dict["mcp_servers"] = mcp_servers_list
            # Remove mcpServers from config_dict to avoid conflicts
            del config_dict["mcpServers"]
        
        # Legacy format support: mcp_servers as list
        # This is already in the right format, just ensure it's processed

        # Override with environment variables
        env_overrides = {}
        if lib_path := os.getenv("CHITIN_LIB_PATH"):
            env_overrides.setdefault("chitin", {})["lib_path"] = lib_path
        if sidecar_url := os.getenv("CHITIN_SIDECAR_URL"):
            env_overrides.setdefault("chitin", {})["sidecar_url"] = sidecar_url
        if api_key := os.getenv("ANTHROPIC_API_KEY"):
            env_overrides.setdefault("llm", {})["api_key"] = api_key
        if ollama_url := os.getenv("OLLAMA_BASE_URL"):
            env_overrides.setdefault("llm", {})["base_url"] = ollama_url
        if policy_url := os.getenv("CHITIN_POLICY_SERVER_URL"):
            env_overrides.setdefault("policy", {})["enterprise_url"] = policy_url

        # Merge env overrides
        for key, value in env_overrides.items():
            if key in config_dict:
                config_dict[key].update(value)
            else:
                config_dict[key] = value

        return cls(**config_dict)


def find_config_file() -> Optional[Path]:
    """Find config file in resolution order. Prefers JSON over YAML if both exist."""
    # Current directory - check both JSON and YAML
    local_json = Path(".chitin/config.json")
    local_yaml = Path(".chitin/config.yaml")
    local_yml = Path(".chitin/config.yml")
    
    # Prefer JSON over YAML
    if local_json.exists():
        return local_json
    if local_yaml.exists():
        return local_yaml
    if local_yml.exists():
        return local_yml

    # User config - check both JSON and YAML
    user_json = Path.home() / ".config" / "chitin" / "config.json"
    user_yaml = Path.home() / ".config" / "chitin" / "config.yaml"
    user_yml = Path.home() / ".config" / "chitin" / "config.yml"
    
    # Prefer JSON over YAML
    if user_json.exists():
        return user_json
    if user_yaml.exists():
        return user_yaml
    if user_yml.exists():
        return user_yml

    return None


def load_tool_classifications(tools_path: Optional[Path] = None) -> dict[str, dict[str, str]]:
    """Load tool classifications from tools.yaml."""
    if tools_path is None:
        tools_path = find_tools_file()

    if tools_path and tools_path.exists():
        with open(tools_path, "r") as f:
            data = yaml.safe_load(f) or {}
            return data.get("tools", {})

    return {}


def find_tools_file() -> Optional[Path]:
    """Find tools.yaml file."""
    local_tools = Path(".chitin/tools.yaml")
    if local_tools.exists():
        return local_tools

    user_tools = Path.home() / ".config" / "chitin" / "tools.yaml"
    if user_tools.exists():
        return user_tools

    return None


def find_policy_files() -> list[Path]:
    """Find all policy YAML files in resolution order."""
    policy_files: list[Path] = []

    # Explicit override
    if policy_path := os.getenv("CHITIN_POLICY_PATH"):
        policy_dir = Path(policy_path)
        if policy_dir.exists() and policy_dir.is_dir():
            policy_files.extend(policy_dir.glob("*.yaml"))
            policy_files.extend(policy_dir.glob("*.yml"))

    # Project-level
    project_policies = Path(".chitin/policies")
    if project_policies.exists() and project_policies.is_dir():
        policy_files.extend(project_policies.glob("*.yaml"))
        policy_files.extend(project_policies.glob("*.yml"))

    # User-level
    user_policies = Path.home() / ".config" / "chitin" / "policies"
    if user_policies.exists() and user_policies.is_dir():
        policy_files.extend(user_policies.glob("*.yaml"))
        policy_files.extend(user_policies.glob("*.yml"))

    return policy_files
