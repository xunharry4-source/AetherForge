from src.common.config_utils import load_config
from src.common.llm_factory import get_llm

config = load_config()
print(f"Global Provider: {config.get('LLM_PROVIDER')}")

try:
    llm = get_llm(agent_name="writing")
    print(f"LLM Instance: {llm}")
except Exception as e:
    print(f"Error getting LLM: {e}")
