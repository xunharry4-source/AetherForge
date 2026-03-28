import os
import json
import logging
from dotenv import load_dotenv
from logger_utils import get_logger

logger = get_logger("novel_agent.config")

def load_config():
    """Centralized configuration loader for the Novel Agent system."""
    load_dotenv()
    
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
    config = {}
    
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load config.json: {e}")
    
    # Merge env vars for sensitive keys if not in config.json
    env_keys = [
        "GOOGLE_API_KEY", "OPENAI_API_KEY", "SENTRY_DSN", 
        "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST",
        "MONGO_URI", "MONGO_DB_NAME", "CHROMA_COLLECTION_NAME"
    ]
    for key in env_keys:
        if key not in config or not config[key]:
            val = os.getenv(key)
            if val:
                config[key] = val

    # Ensure GOOGLE_API_KEYS (list) and GOOGLE_API_KEY (str) consistency
    if "GOOGLE_API_KEYS" not in config:
        config["GOOGLE_API_KEYS"] = [config.get("GOOGLE_API_KEY")] if config.get("GOOGLE_API_KEY") else []
    elif config.get("GOOGLE_API_KEYS") and not config.get("GOOGLE_API_KEY"):
        config["GOOGLE_API_KEY"] = config["GOOGLE_API_KEYS"][0]

    # Default values for essential non-sensitive fields if missing
    defaults = {
        "LLM_PROVIDER": "gemini",
        "DEFAULT_MODEL": "gemini-2.0-flash",
        "AGENT_MODELS": {},
        "DEFAULT_MODEL_MAP": {
            "gemini": "gemini-2.0-flash",
            "openai": "gpt-4-turbo-preview",
            "local": "local-model"
        }
    }
    for key, val in defaults.items():
        if key not in config:
            config[key] = val

    return config

def save_config(new_config: dict):
    """Persists configuration to config.json."""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
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
