"""
世界观导入 Agent (Worldview Import Agent) - PGA 创作引擎核心入口

本 Agent 负责将外部各种格式的设定文档 (MD, PDF, Docx, OPML) 转化为系统可识别的结构化设定。
核心流程:
1. File Parsing: 提取原始文本。
2. Smart Segmentation: 使用 LLM 识别人类语言中的“设定边界”，将长文档切分为独立的实体 (Entities)。
3. PGA Categorization: 将切分后的实体归类到 {Races, Geographies, Factions, Mechanisms, History}。
4. Library Sync: 自动存入 MongoDB 和 ChromaDB。
"""
import os
import json
from typing import List, Dict, TypedDict, Annotated, Any
from langgraph.graph import StateGraph, END, START
from langchain_core.messages import HumanMessage, SystemMessage
from lore_utils import (
    get_llm, 
    extract_text_from_file, 
    sync_lore_to_db, 
    get_langfuse_callback,
    dispatch_log
)

# --- State Definition ---

class ImportState(TypedDict):
    file_path: str
    worldview_id: str
    outline_id: Optional[str]
    raw_text: str
    strategy: str # 'llm', 'regex', 'fixed'
    entities: List[Dict[str, Any]]
    results: List[str]
    status: str
    status_message: str
    llm_interactions: Dict[str, Any] # [诊断] 存储各节点的 LLM 入参与原始出参

# --- Nodes ---

def parse_file_node(state: ImportState, config: dict):
    """提取文件内容"""
    dispatch_log(config, f"正在从路径 {state['file_path']} 读取原始文本...")
    try:
        text = extract_text_from_file(state["file_path"])
        return {
            "raw_text": text, 
            "status": "parsed",
            "status_message": "📄 文件解析成功，正在提取原始文本内容..."
        }
    except Exception as e:
        return {
            "status": f"error: {str(e)}",
            "status_message": f"❌ 文件解析失败: {str(e)}"
        }

def segment_lore_node(state: ImportState, config: dict):
    """根据策略进行切片"""
    dispatch_log(config, f"正在启动分割引擎，策略: {state.get('strategy', 'llm').upper()}...")
    if state["status"].startswith("error"): return state
    
    strategy = state.get("strategy", "llm").lower()
    text = state["raw_text"]
    entities = []

    msg = f"🧩 正在使用 {strategy.upper()} 策略对世界观文档进行逻辑分篇..."
    
    if strategy == "regex":
        # 按照 Markdown 标题切分 (#, ##, ###)
        import re
        chunks = re.split(r'\n(?=#{1,3} )', text)
        for chunk in chunks:
            if not chunk.strip(): continue
            lines = chunk.strip().split('\n')
            title = lines[0].replace('#', '').strip()
            entities.append({"name": title, "content": chunk.strip()})
        return {"entities": entities, "status": "segmented", "status_message": msg}

    elif strategy == "fixed":
        size = 1000
        overlap = 200
        for i in range(0, len(text), size - overlap):
            chunk = text[i:i + size]
            title = f"片段_{i//(size-overlap) + 1}"
            entities.append({"name": title, "content": chunk})
        return {"entities": entities, "status": "segmented", "status_message": msg}

    else: # Default: llm
        model = get_llm(agent_name="import")
        prompt = f"""
        你是一个专业的设定分析师。请将以下世界观原始文档切分为多个独立的“设定实体 (Lore Entities)”。
        切分准则：
        1. 每个实体应描述一个具体的事物（如：具体某个种族、某个星球、某个技术原理、某个历史事件、某个组织结构）。
        2. 如果原文是分段的，保留逻辑上的完整性。
        3. 输出格式必须是 JSON List，包含 'name' 和 'content' 字段。

        原始文档：
        {text[:10000]} # 处理前 1w 字
        """
        response = model.invoke([HumanMessage(content=prompt)], config={"callbacks": [get_langfuse_callback()] if get_langfuse_callback() else []})
        try:
            from lore_utils import parse_json_safely
            dispatch_log(config, "LLM 已返回分段建议，正在解析 JSON 结构...")
            entities = parse_json_safely(response.content)
            dispatch_log(config, f"分段解析完成，获得 {len(entities)} 个设定实体。")
            return {"entities": entities, "status": "segmented", "status_message": msg}
        except Exception as e:
            return {"status": f"error_segment: {str(e)}", "status_message": "❌ LLM 切分解析异常"}

def categorize_pga_node(state: ImportState, config: dict):
    """分类到 PGA 0-4 架构"""
    dispatch_log(config, "启动 0-4 协议映射分类器...")
    if state["status"].startswith("error") or not state.get("entities"): return state
    
    model = get_llm(agent_name="import")
    entities = state["entities"]
    
    prompt = f"""
    将以下设定实体映射到 PGA 协议的 5 个核心类别中：
    - Races (种族): 生理结构、社会性、文明等级
    - Geographies (地理): 星区、星球环境、天体物理
    - Factions (势力): 组织、国家、公司、阵营
    - Mechanisms (机制): 技术细节、物理法则、社会契约
    - History (历史): 时间线、重大事件、神话传说

    输入列表：{json.dumps([e['name'] for e in entities], ensure_ascii=False)}
    
    请返回一个 JSON 字典，Key 是实体名称，Value 是所属类别名称 (仅限上述 5 个之一)。
    """
    
    response = model.invoke([HumanMessage(content=prompt)])
    from lore_utils import parse_json_safely
    dispatch_log(config, "分类结果已由 LLM 产出，正在执行实体映射...")
    mapping = parse_json_safely(response.content)
    
    updated_entities = []
    for e in entities:
        cat = mapping.get(e['name'], "Races")
        e['category'] = cat
        updated_entities.append(e)
        
    return {
        "entities": updated_entities, 
        "status": "analyzed",
        "status_message": f"📊 已完成 {len(updated_entities)} 个实体的 0-4 协议分类。准备进入入库预览..."
    }

def sync_library_node(state: ImportState, config: dict):
    """同步到数据库"""
    dispatch_log(config, "开始将分析后的实体同步至分布式数据库 (MongoDB & Chroma)...")
    if state["status"].startswith("error"): return state
    
    results = []
    outline_id = state.get("outline_id")
    worldview_id = state.get("worldview_id", "default_wv")
    
    for entity in state["entities"]:
        try:
            sync_lore_to_db(entity, outline_id=outline_id, worldview_id=worldview_id)
            results.append(f"Success: {entity['name']}")
        except Exception as e:
            results.append(f"Failed: {entity['name']} ({str(e)})")
            
    return {
        "results": results, 
        "status": "completed",
        "status_message": f"✨ 世界观导入任务已完成，实体已同步至世界观 '{worldview_id}' 的分布式数据库。"
    }

# --- Graph Construction ---

def create_import_agent():
    workflow = StateGraph(ImportState)
    
    workflow.add_node("parse", parse_file_node)
    workflow.add_node("segment", segment_lore_node)
    workflow.add_node("categorize", categorize_pga_node)
    workflow.add_node("sync", sync_library_node)
    
    workflow.add_edge(START, "parse")
    workflow.add_edge("parse", "segment")
    workflow.add_edge("segment", "categorize")
    workflow.add_edge("categorize", "sync")
    workflow.add_edge("sync", END)
    
    return workflow.compile()

app = create_import_agent()
