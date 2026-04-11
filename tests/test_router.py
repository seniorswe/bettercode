import pytest
from bettercode.auth import set_api_key
from bettercode.context.tokens import count_tokens

def test_token_counter_safety():
    """Ensure token counter doesn't fail on unknown models."""
    count = count_tokens("Hello world", model="unknown_hacker_model")
    assert count == 2

def test_secure_key_manager_rejects_injected_keys():
    """Ensure our key manager prevents basic injection vectors."""
    with pytest.raises(ValueError, match="Invalid API key format"):
        set_api_key("openai", "sk-1234\\nrm -rf /")
        
    with pytest.raises(ValueError, match="Invalid API key format"):
        set_api_key("anthropic", "sk-1234 some_other_command")
        
    with pytest.raises(ValueError, match="API key cannot be empty"):
        set_api_key("openai", "")
