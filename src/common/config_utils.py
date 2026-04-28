import os
import json
import logging
from dotenv import load_dotenv
from .logger_utils import get_logger

logger = get_logger("novel_agent.config")

def load_config():
    """Centralized configuration loader for the Novel Agent system."""
    load_dotenv()
    
    # config.json is in the project root. This file is in src/common/
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    config_path = os.path.join(base_dir, 'config.json')
    config = {}
    
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load config.json: {e}")
    
    # Merge env vars for sensitive keys and LLM defaults
    env_keys = [
        "GOOGLE_API_KEY", "OPENAI_API_KEY", "SENTRY_DSN", 
        "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST",
        "MONGO_URI", "MONGO_DB_NAME", "CHROMA_COLLECTION_NAME",
        "LLM_PROVIDER", "DEFAULT_MODEL", "OLLAMA_BASE_URL",
        "EMBEDDING_PROVIDER", "DEFAULT_EMBEDDING_MODEL", "OLLAMA_EMBEDDING_MODEL",
        "DEFAULT_LLM_PROVIDER", "DEFAULT_LLM_MODEL",
        "DB_PATH", "LOG_PATH"
    ]
    
    for key in env_keys:
        # Env vars take precedence over config.json
        val = os.getenv(key)
        if val:
            # Handle aliases
            if key == "DEFAULT_LLM_PROVIDER":
                config["LLM_PROVIDER"] = val
            elif key == "DEFAULT_LLM_MODEL":
                config["DEFAULT_MODEL"] = val
            else:
                config[key] = val

    # Ensure GOOGLE_API_KEYS (list) and GOOGLE_API_KEY (str) consistency
    if "GOOGLE_API_KEYS" not in config:
        config["GOOGLE_API_KEYS"] = [config.get("GOOGLE_API_KEY")] if config.get("GOOGLE_API_KEY") else []
    elif config.get("GOOGLE_API_KEYS") and not config.get("GOOGLE_API_KEY"):
        config["GOOGLE_API_KEY"] = config["GOOGLE_API_KEYS"][0]

    # Default values for essential non-sensitive fields if missing
    defaults = {
        "LLM_PROVIDER": "ollama",
        "DEFAULT_MODEL": "gemma4:e2b",
        "OLLAMA_BASE_URL": "http://localhost:11434/v1",
        "EMBEDDING_PROVIDER": "ollama",
        "DEFAULT_EMBEDDING_MODEL": "embeddinggemma",
        "OLLAMA_EMBEDDING_MODEL": "embeddinggemma",
        "AGENT_MODELS": {},
        "LLM_MODELS": {
            "ollama": {
                "default": "gemma4:e2b",
                "models": ["gemma4:e2b"],
                "base_url": "http://localhost:11434/v1"
            },
            "gemini": {
                "default": "gemini-2.0-flash",
                "models": ["gemini-2.0-flash"]
            },
            "openai": {
                "default": "gpt-4-turbo-preview",
                "models": ["gpt-4-turbo-preview"]
            },
            "local": {
                "default": "local-model",
                "models": ["local-model"],
                "base_url": "http://localhost:5000/v1"
            }
        },
        "EMBEDDING_MODELS": {
            "ollama": {
                "default": "embeddinggemma",
                "models": ["embeddinggemma"],
                "base_url": "http://localhost:11434/v1"
            },
            "gemini": {
                "default": "models/gemini-embedding-001",
                "models": ["models/gemini-embedding-001"]
            }
        },
        "DEFAULT_MODEL_MAP": {
            "gemini": "gemini-2.0-flash",
            "openai": "gpt-4-turbo-preview",
            "local": "local-model",
            "ollama": "gemma4:e2b"
        },
        "DB_PATH": "data",
        "LOG_PATH": "logs"
    }
    for key, val in defaults.items():
        if key not in config:
            config[key] = val

    # Backfill model catalogs from legacy fields so older config.json files stay valid.
    llm_models = config.setdefault("LLM_MODELS", {})
    model_map = config.setdefault("DEFAULT_MODEL_MAP", {})
    for provider_name, default_model in model_map.items():
        provider_models = llm_models.get(provider_name)
        if not isinstance(provider_models, dict):
            provider_models = {"default": default_model, "models": [default_model] if default_model else []}
        provider_models.setdefault("default", default_model)
        provider_models.setdefault("models", [provider_models["default"]] if provider_models.get("default") else [])
        if provider_name in {"ollama", "local"}:
            provider_models.setdefault(
                "base_url",
                config.get("OLLAMA_BASE_URL") if provider_name == "ollama" else config.get("LOCAL_LLM_URL", "http://localhost:5000/v1")
            )
        llm_models[provider_name] = provider_models

    embedding_models = config.setdefault("EMBEDDING_MODELS", {})
    default_embedding_model = (
        config.get("DEFAULT_EMBEDDING_MODEL")
        or config.get("OLLAMA_EMBEDDING_MODEL")
        or "embeddinggemma"
    )
    config["DEFAULT_EMBEDDING_MODEL"] = default_embedding_model
    config["OLLAMA_EMBEDDING_MODEL"] = config.get("OLLAMA_EMBEDDING_MODEL") or default_embedding_model
    ollama_embedding_models = embedding_models.get("ollama")
    if not isinstance(ollama_embedding_models, dict):
        ollama_embedding_models = {
            "default": default_embedding_model,
            "models": [default_embedding_model],
            "base_url": config.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        }
    ollama_embedding_models.setdefault("default", default_embedding_model)
    ollama_embedding_models.setdefault("models", [ollama_embedding_models["default"]])
    ollama_embedding_models.setdefault("base_url", config.get("OLLAMA_BASE_URL", "http://localhost:11434/v1"))
    embedding_models["ollama"] = ollama_embedding_models

    return config

def save_config(new_config: dict):
    """Persists configuration to config.json."""
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    config_path = os.path.join(base_dir, 'config.json')
    try:
        # Save to file
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(new_config, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Failed to save config.json: {e}")
        return False

def get_config():
    return load_config()
