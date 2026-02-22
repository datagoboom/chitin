"""Policy loader for resolving and loading policies."""

import yaml
from pathlib import Path
from typing import Any, Optional

from chitin import Engine  # type: ignore

from chitin_agent.config import AgentConfig, find_policy_files, load_tool_classifications


class PolicyLoader:
    """Loads and registers policies with Chitin engine."""

    def __init__(self, config: AgentConfig):
        """Initialize policy loader."""
        self.config = config

    def load_and_register(
        self,
        engine: Engine,
        tool_classifications: dict[str, dict[str, str]],
        enterprise_policies: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        """
        Load policies from all sources and register with engine.

        Resolution order:
        1. Embedded defaults (loaded automatically by engine)
        2. User-level (~/.config/chitin/policies/*.yaml)
        3. Project-level (./.chitin/policies/*.yaml)
        4. Explicit override ($CHITIN_POLICY_PATH/*.yaml)
        5. Enterprise (from Policy Server if provided)

        Args:
            engine: Chitin engine instance
            tool_classifications: Tool risk classifications
            enterprise_policies: Optional list of policies from Policy Server
        """
        # Load policy files in resolution order
        policy_files = find_policy_files()
        
        import sys
        if policy_files:
            print(f"[POLICIES] Loading {len(policy_files)} policy file(s): {[str(p) for p in policy_files]}", file=sys.stderr)
        else:
            print("[POLICIES] No policy files found. Using engine defaults (if any).", file=sys.stderr)

        for policy_file in policy_files:
            with open(policy_file, "r") as f:
                policy_data = yaml.safe_load(f)
                if policy_data:
                    print(f"[POLICIES] Parsed policy from {policy_file}: {policy_data}", file=sys.stderr)
                    # Register policy with engine
                    # Note: Actual API depends on chitin-engine-lib implementation
                    # The engine may load policies automatically from files,
                    # or may require explicit registration. Adjust based on actual API.
                    if hasattr(engine, "load_policies_yaml"):
                        try:
                            # Read the raw YAML string and pass to engine
                            with open(policy_file, "r") as raw:
                                yaml_str = raw.read()
                            engine.load_policies_yaml(yaml_str)
                            print(f"[POLICIES] Successfully loaded policy from {policy_file}", file=sys.stderr)
                        except Exception as e:
                            print(f"[POLICIES] ERROR loading policy from {policy_file}: {e}", file=sys.stderr)
                            import traceback
                            traceback.print_exc(file=sys.stderr)
                    else:
                        print(f"[POLICIES] WARNING: engine.load_policies_yaml() not found.", file=sys.stderr)

        # Load enterprise policies (highest priority)
        if enterprise_policies:
            for policy in enterprise_policies:
                if hasattr(engine, "load_policies_yaml"):
                    import json as _json
                    # Enterprise policies come as dicts; wrap in YAML-compatible format
                    yaml_str = yaml.dump({"policies": [policy]})
                    try:
                        engine.load_policies_yaml(yaml_str)
                    except Exception as e:
                        print(f"[POLICIES] ERROR loading enterprise policy: {e}", file=sys.stderr)

        # Register tool classifications
        for tool_name, classification in tool_classifications.items():
            risk = classification.get("risk", self.config.tool_defaults.unknown_risk)
            category = classification.get("category")
            engine.register_tool(tool_name, risk=risk, category=category)
