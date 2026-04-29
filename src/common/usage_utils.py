
import json
import os
import threading
from datetime import datetime

from .lore_utils import get_db_path
_lock = threading.Lock()

def load_usage():
    """Load usage statistics from file."""
    with _lock:
        path = get_db_path("agent_usage.json")
        if not os.path.exists(path):
            return {}
        with open(path, 'r', encoding='utf-8') as f:
            return json.loads(f.read())

def save_usage(usage_data):
    """Save usage statistics to file."""
    with _lock:
        path = get_db_path("agent_usage.json")
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(usage_data, f, indent=2, ensure_ascii=False)

def update_agent_usage(agent_name, input_tokens, output_tokens):
    """Update statistics for a specific agent."""
    usage = load_usage()
    
    if agent_name not in usage:
        usage[agent_name] = {
            "calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "last_active": ""
        }
    
    stats = usage[agent_name]
    stats["calls"] += 1
    stats["input_tokens"] += input_tokens
    stats["output_tokens"] += output_tokens
    stats["total_tokens"] = stats["input_tokens"] + stats["output_tokens"]
    stats["last_active"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    save_usage(usage)
    return stats
