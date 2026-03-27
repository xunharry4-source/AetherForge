"""
LLM Factory - PGA 小说创作引擎模型工厂
支持多种模型提供商 (Gemini, OpenAI, Local) 的统一架构。
"""
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from config_utils import load_config
from logger_utils import get_logger

logger = get_logger("novel_agent.llm_factory")

def get_llm(json_mode: bool = False, agent_name: str = "unknown"):
    """
    根据 config.json 中的配置返回对应的 LLM 实例。
    """
    config = load_config()
    provider = config.get("LLM_PROVIDER", "gemini").lower()
    
    # 获取提供商特定的模型名称
    model_map = config.get("DEFAULT_MODEL_MAP", {})
    
    if provider == "gemini":
        from lore_utils import _key_manager
        key = _key_manager.get_key()
        if not key:
            raise ValueError("GOOGLE_API_KEYS missing in config.json")
        
        model_name = model_map.get("gemini", config.get("DEFAULT_MODEL", "gemini-2.0-flash"))
        
        if json_mode:
            return ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=key,
                max_retries=5,
                timeout=120,
                response_mime_type="application/json"
            )
        return ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=key,
            max_retries=5,
            timeout=120
        )
        
    elif provider == "openai":
        api_key = config.get("OPENAI_API_KEY")
        base_url = config.get("OPENAI_BASE_URL")
        model_name = model_map.get("openai", "gpt-4-turbo-preview")
        
        if not api_key:
            raise ValueError("OPENAI_API_KEY missing in config.json")
            
        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=base_url,
            temperature=0.7,
            model_kwargs={"response_format": {"type": "json_object"}} if json_mode else {}
        )
        
    elif provider == "local":
        # 本地模型通常兼容 OpenAI API 格式 (如 Oobabooga, vLLM, LM Studio)
        base_url = config.get("LOCAL_LLM_URL", "http://localhost:5000/v1")
        model_name = model_map.get("local", "local-model")
        
        return ChatOpenAI(
            model=model_name,
            api_key="sk-not-required", # 本地通常不需要真实 Key
            base_url=base_url,
            temperature=0.7,
            model_kwargs={"response_format": {"type": "json_object"}} if json_mode else {}
        )
        
    else:
        raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")

def get_provider_info():
    """返回当前提供商和模型信息的元数据，用于 Dashboard 显示"""
    config = load_config()
    provider = config.get("LLM_PROVIDER", "gemini")
    model_map = config.get("DEFAULT_MODEL_MAP", {})
    model_name = model_map.get(provider, config.get("DEFAULT_MODEL", "unknown"))
    return {
        "provider": provider,
        "model": model_name
    }
