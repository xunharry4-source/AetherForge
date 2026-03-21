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
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, SystemMessage
from lore_utils import (
    get_llm, 
    extract_text_from_file, 
    sync_lore_to_db, 
    get_langfuse_callback
)

# --- State Definition ---

class ImportState(TypedDict):
    file_path: str
    raw_text: str
    strategy: str # 'llm', 'regex', 'fixed'
    entities: List[Dict[str, Any]]
    results: List[str]
    status: str

# --- Nodes ---

def parse_file_node(state: ImportState):
    """提取文件内容"""
    try:
        text = extract_text_from_file(state["file_path"])
        return {"raw_text": text, "status": "parsed"}
    except Exception as e:
        return {"status": f"error: {str(e)}"}

def segment_lore_node(state: ImportState):
    """根据策略进行切片"""
    if state["status"].startswith("error"): return state
    
    strategy = state.get("strategy", "llm").lower()
    text = state["raw_text"]
    entities = []

    if strategy == "regex":
        # 按照 Markdown 标题切分 (#, ##, ###)
        import re
        # 寻找 ### 或 ## 或 # 开头的行
        chunks = re.split(r'\n(?=#{1,3} )', text)
        for chunk in chunks:
            if not chunk.strip(): continue
            lines = chunk.strip().split('\n')
            title = lines[0].replace('#', '').strip()
            entities.append({"name": title, "content": chunk.strip()})
        return {"entities": entities, "status": "segmented"}

    elif strategy == "fixed":
        # 固定字符长度切分 (1000字 200字重叠)
        size = 1000
        overlap = 200
        for i in range(0, len(text), size - overlap):
            chunk = text[i:i + size]
            title = f"片段_{i//(size-overlap) + 1}"
            entities.append({"name": title, "content": chunk})
        return {"entities": entities, "status": "segmented"}

    else: # Default: llm
        model = get_llm()
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
            entities = parse_json_safely(response.content)
            return {"entities": entities, "status": "segmented"}
        except Exception as e:
            return {"status": f"error_segment: {str(e)}"}

def categorize_pga_node(state: ImportState):
    """分类到 PGA 0-4 架构"""
    if state["status"].startswith("error") or not state.get("entities"): return state
    
    model = get_llm()
    entities = state["entities"]
    
    # 分批处理以避免 Token 限制
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
    mapping = parse_json_safely(response.content)
    
    updated_entities = []
    for e in entities:
        cat = mapping.get(e['name'], "Races")
        e['category'] = cat
        updated_entities.append(e)
        
    return {"entities": updated_entities, "status": "analyzed"}

def sync_library_node(state: ImportState):
    """
    同步到数据库 (该节点在预览模式下被跳过，由 API 层面二次确认后调用 lore_utils 直接执行)
    """
    if state["status"].startswith("error"): return state
    
    results = []
    for entity in state["entities"]:
        try:
            sync_lore_to_db(entity)
            results.append(f"Success: {entity['name']}")
        except Exception as e:
            results.append(f"Failed: {entity['name']} ({str(e)})")
            
    return {"results": results, "status": "completed"}

# --- Graph Construction ---

def create_import_agent():
    workflow = StateGraph(ImportState)
    
    workflow.add_node("parse", parse_file_node)
    workflow.add_node("segment", segment_lore_node)
    workflow.add_node("categorize", categorize_pga_node)
    
    workflow.set_entry_point("parse")
    workflow.add_edge("parse", "segment")
    workflow.add_edge("segment", "categorize")
    workflow.add_edge("categorize", END)
    
    return workflow.compile()

app = create_import_agent()

if __name__ == "__main__":
    # Test script
    test_file = "科幻.md"
    if os.path.exists(test_file):
        print(f"Starting import test for {test_file} (Strategy: regex)...")
        for output in app.stream({"file_path": test_file, "strategy": "regex"}):
            print(output)
