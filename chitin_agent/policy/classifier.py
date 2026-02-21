"""Tool risk classification."""

from chitin_agent.config import AgentConfig, ToolDefaultsConfig
from chitin_agent.mcp.client import MCPTool


def classify_tool(
    tool: MCPTool, tool_classifications: dict[str, dict[str, str]], defaults: ToolDefaultsConfig
) -> tuple[str, str | None]:
    """
    Classify a tool's risk and category.

    Returns:
        Tuple of (risk_level, category)
    """
    classification = tool_classifications.get(tool.name, {})
    risk = classification.get("risk", defaults.unknown_risk)
    category = classification.get("category")
    return (risk, category)
