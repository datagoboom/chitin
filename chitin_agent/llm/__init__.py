"""LLM adapters for different providers."""

from chitin_agent.llm.adapter import LLMAdapter


def create_llm_adapter(config):
    """Create appropriate LLM adapter based on provider."""
    from chitin_agent.config import LLMConfig
    
    if config.provider == "anthropic":
        from chitin_agent.llm.anthropic import AnthropicAdapter
        return AnthropicAdapter(config)
    elif config.provider == "ollama":
        from chitin_agent.llm.ollama import OllamaAdapter
        return OllamaAdapter(config)
    else:
        raise ValueError(f"Unknown LLM provider: {config.provider}")


__all__ = ["LLMAdapter", "create_llm_adapter"]
