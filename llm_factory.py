"""
LLM Factory - PGA 小说创作引擎模型工厂
支持多种模型提供商 (Gemini, OpenAI, Local) 的统一架构。
"""
from langchain_core.callbacks import BaseCallbackHandler
from config_utils import load_config
from logger_utils import get_logger
from usage_utils import update_agent_usage

logger = get_logger("novel_agent.llm_factory")

class UsageTrackingCallbackHandler(BaseCallbackHandler):
    """Callback handler that tracks token usage per agent."""
    def __init__(self, agent_name: str):
        self.agent_name = agent_name

    def on_llm_end(self, response, **kwargs) -> None:
        """Collect usage data when LLM finished."""
        try:
            for generation in response.generations:
                for chunk in generation:
                    if hasattr(chunk, 'message') and hasattr(chunk.message, 'response_metadata'):
                        meta = chunk.message.response_metadata
                        # Try OpenAI style
                        usage = meta.get('token_usage')
                        if usage:
                            input_tokens = usage.get('prompt_tokens', 0)
                            output_tokens = usage.get('completion_tokens', 0)
                            update_agent_usage(self.agent_name, input_tokens, output_tokens)
                            return
                        
                        # Try Google Gemini style
                        usage = meta.get('usage_metadata')
                        if usage:
                            input_tokens = usage.get('prompt_token_count', 0)
                            output_tokens = usage.get('candidates_token_count', 0)
                            update_agent_usage(self.agent_name, input_tokens, output_tokens)
                            return
        except Exception as e:
            logger.error(f"Error tracking usage for {self.agent_name}: {e}")

def get_llm(json_mode: bool = False, agent_name: str = "unknown"):
    """
    根据 config.json 中的配置返回对应的 LLM 实例。
    优先级: Agent 专属配置 > Provider 默认配置 > 系统全局默认
    """
    config = load_config()
    provider = config.get("LLM_PROVIDER", "gemini").lower()
    
    # 1. 尝试获取 Agent 专属配置 (支持字符串或字典)
    agent_models = config.get("AGENT_MODELS", {})
    agent_config = agent_models.get(agent_name, {})
    
    if isinstance(agent_config, dict):
        provider = (agent_config.get("provider") or provider).lower()
        model_name = agent_config.get("model")
    else:
        model_name = agent_config

    # 2. 如果没有专属模型名，获取提供商默认映射
    if not model_name:
        model_map = config.get("DEFAULT_MODEL_MAP", {})
        model_name = model_map.get(provider)
        
    # 3. 如果依然没有，使用系统全局默认
    if not model_name:
        model_name = config.get("DEFAULT_MODEL", "gemini-2.0-flash")

    logger.info(f"Instantiating LLM for agent '{agent_name}' using model '{model_name}' (Provider: {provider})")

    # 4. 初始化模型
    usage_handler = UsageTrackingCallbackHandler(agent_name)
    
    if provider == "gemini":
        from lore_utils import _key_manager
        key = _key_manager.get_key()
        if not key:
            raise ValueError("GOOGLE_API_KEYS missing in config.json")
        
        args = {
            "model": model_name,
            "google_api_key": key,
            "max_retries": 5,
            "timeout": 120,
            "callbacks": [usage_handler]
        }
        if json_mode:
            args["response_mime_type"] = "application/json"
        
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(**args)
        
    elif provider == "openai":
        api_key = config.get("OPENAI_API_KEY")
        base_url = config.get("OPENAI_BASE_URL")
        
        if not api_key:
            raise ValueError("OPENAI_API_KEY missing in config.json")
            
        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=base_url,
            temperature=0.7,
            callbacks=[usage_handler],
            model_kwargs={"response_format": {"type": "json_object"}} if json_mode else {}
        )
        
    elif provider == "local":
        base_url = config.get("LOCAL_LLM_URL", "http://localhost:5000/v1")
        
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model_name,
            api_key="sk-not-required",
            base_url=base_url,
            temperature=0.7,
            callbacks=[usage_handler],
            model_kwargs={"response_format": {"type": "json_object"}} if json_mode else {}
        )
        
    else:
        raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")

def get_provider_info():
    """返回当前提供商和所有模型配置信息的元数据"""
    config = load_config()
    return {
        "provider": config.get("LLM_PROVIDER", "gemini"),
        "default_model": config.get("DEFAULT_MODEL", "gemini-2.0-flash"),
        "agent_models": config.get("AGENT_MODELS", {}),
        "model_map": config.get("DEFAULT_MODEL_MAP", {})
    }
