import os
import json
import logging
from dotenv import load_dotenv
from logger_utils import get_logger

logger = get_logger("novel_agent.config")

def load_config():
    """Centralized configuration loader for the Novel Agent system."""
    # Explicitly load .env file if it exists, enhancing security and secret management
    load_dotenv()
    
    config = {}
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
    logger.info(f"Checking config at: {config_path}")
    
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            logger.info(f"Loaded keys from JSON: {list(config.keys())}")
        except Exception as e:
            logger.error(f"Failed to load config.json: {e}")
    else:
        logger.info(f"config.json NOT FOUND at {config_path}")
    
    # Priority: config.json > Environment Variables
    google_keys = config.get("GOOGLE_API_KEYS", [])
    google_key = config.get("GOOGLE_API_KEY")
    
    if not google_key:
        google_key = os.getenv("GOOGLE_API_KEY")

    if not google_key and google_keys:
        google_key = google_keys[0]
        logger.info(f"No GOOGLE_API_KEY found in config or env. Using first key from GOOGLE_API_KEYS.")
    
    if not google_keys and google_key:
        google_keys = [google_key]

    if not google_key:
        logger.warning("GOOGLE_API_KEY is empty or None!")

    return {
        "GOOGLE_API_KEY": google_key,
        "GOOGLE_API_KEYS": google_keys,
        "DEFAULT_MODEL": "gemini-2.5-flash-lite",
        "SENTRY_DSN": config.get("SENTRY_DSN") or os.getenv("SENTRY_DSN"),
        "LANGFUSE_PUBLIC_KEY": config.get("LANGFUSE_PUBLIC_KEY") or os.getenv("LANGFUSE_PUBLIC_KEY"),
        "LANGFUSE_SECRET_KEY": config.get("LANGFUSE_SECRET_KEY") or os.getenv("LANGFUSE_SECRET_KEY"),
        "LANGFUSE_HOST": config.get("LANGFUSE_HOST") or os.getenv("LANGFUSE_HOST") or "https://cloud.langfuse.com",
        "MONGO_URI": config.get("MONGO_URI") or os.getenv("MONGO_URI") or "mongodb://localhost:27017/",
        "MONGO_DB_NAME": config.get("MONGO_DB_NAME") or os.getenv("MONGO_DB_NAME") or "pga_worldview",
        "CHROMA_COLLECTION_NAME": config.get("CHROMA_COLLECTION_NAME") or os.getenv("CHROMA_COLLECTION_NAME") or "pga_worldview_v1"
    }

# No global CONFIG object here to force fresh loading if needed, 
# but we'll provide a getter for convenience.
def get_config():
    return load_config()
