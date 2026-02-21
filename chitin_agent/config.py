"""Configuration loading and validation."""

import os
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMConfig(BaseModel):
    """LLM provider configuration."""

    provider: str = Field(default="anthropic", description="LLM provider")
    model: str = Field(default="claude-sonnet-4-20250514", description="Model name")
    max_tokens: int = Field(default=8192, description="Maximum tokens in response")
    api_key: Optional[str] = Field(default=None, description="API key (from env if not set)")


class MCPServerConfig(BaseModel):
    """MCP server configuration."""

    name: str = Field(description="Server name/identifier")
    transport: str = Field(description="Transport type: stdio, sse, or http")
    command: Optional[list[str]] = Field(default=None, description="Command for stdio transport")
    url: Optional[str] = Field(default=None, description="URL for sse/http transport")

    @field_validator("transport")
    @classmethod
    def validate_transport(cls, v: str) -> str:
        """Validate transport type."""
        if v not in ("stdio", "sse", "http"):
            raise ValueError(f"Invalid transport: {v}. Must be stdio, sse, or http")
        return v

    @field_validator("command", "url", mode="after")
    @classmethod
    def validate_transport_params(cls, v: Any, info) -> Any:
        """Validate that transport has appropriate parameters."""
        transport = info.data.get("transport")
        if transport == "stdio":
            # For stdio, command must be provided (not None/empty)
            if v is None or (isinstance(v, list) and len(v) == 0):
                raise ValueError("stdio transport requires 'command' field")
        elif transport in ("sse", "http"):
            # For sse/http, url must be provided
            url_value = info.data.get("url")
            if url_value is None or url_value == "":
                raise ValueError(f"{transport} transport requires 'url' field")
        return v


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
    def load(cls, config_path: Optional[Path] = None) -> "AgentConfig":
        """Load configuration from file and environment."""
        if config_path is None:
            config_path = find_config_file()

        config_dict: dict[str, Any] = {}
        if config_path and config_path.exists():
            with open(config_path, "r") as f:
                config_dict = yaml.safe_load(f) or {}

        # Override with environment variables
        env_overrides = {}
        if lib_path := os.getenv("CHITIN_LIB_PATH"):
            env_overrides.setdefault("chitin", {})["lib_path"] = lib_path
        if sidecar_url := os.getenv("CHITIN_SIDECAR_URL"):
            env_overrides.setdefault("chitin", {})["sidecar_url"] = sidecar_url
        if api_key := os.getenv("ANTHROPIC_API_KEY"):
            env_overrides.setdefault("llm", {})["api_key"] = api_key
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
    """Find config file in resolution order."""
    # Current directory
    local_config = Path(".chitin/config.yaml")
    if local_config.exists():
        return local_config

    # User config
    user_config = Path.home() / ".config" / "chitin" / "config.yaml"
    if user_config.exists():
        return user_config

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
