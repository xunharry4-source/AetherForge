"""
Novel Agent (小说 Agent) - PGA 0-4 协议小说元数据策划
负责定义：小说基调 (Tone)、核心矛盾、目标受众、主角性格曲线、核心主题。
"""
import os
import json
import datetime
from typing import Annotated, TypedDict, List, Union, Optional
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt
from langchain_core.runnables import RunnableConfig

from src.common.lore_utils import (
    get_llm, 
    get_vector_store, 
    get_prohibited_rules, 
    get_unified_context,
    parse_json_safely,
    get_db_path,
    dispatch_log
)

class AgentState(TypedDict):
    query: str
    worldview_id: str
    outline_id: str
    context: str
    proposal: str
    review_log: str
    user_feedback: str
    iterations: int
    is_approved: bool
    status_message: str

def generator_node(state: AgentState, config: RunnableConfig):
    dispatch_log(config, "小说元策划启动：正在构思核心矛盾与基调...")
    query = state.get('query', '')
    wv_id = state.get('worldview_id', 'default_wv')
    
    rag_context = get_unified_context(query, worldview_id=wv_id)
    
    prompt = f"""你是一个“小说策划总监 (Novel Agent)”。
你的任务是为一部星际小说定义元数据（基调、主题、核心矛盾）。
你必须确保小说设定不违反【PGA 协议】。

【当前需求】：{query}
【世界观背景】：{rag_context}

请生成一个结构化的 JSON 提案，包含：
1. 小说基调 (例如: 硬核、压抑、史诗)
2. 核心矛盾 (例如: 熵增与文明延续的冲突)
3. 目标受众
4. 主题
"""
    res = get_llm(json_mode=True, agent_name="novel").invoke(prompt)
    return {
        "proposal": res.content,
        "iterations": state.get('iterations', 0) + 1,
        "status_message": "🎭 小说元策划草案已完成，正在进行创意合规性审计..."
    }

def reviewer_node(state: AgentState, config: RunnableConfig):
    dispatch_log(config, "创意审计：正在核实小说基调与世界观的匹配度...")
    proposal = state.get('proposal', '')
    
    prompt = f"""你是文学审计官。请审核以下小说元策划提案。
检查点：
1. 基调是否与 PGA 世界观兼容？
2. 核心矛盾是否具有足够的文学张力？
3. 主题是否深刻？

内容：
{proposal}

请输出 JSON: {{"status": "通过/不通过", "reason": "..."}}
"""
    res = get_llm(json_mode=True, agent_name="novel").invoke(prompt)
    audit = parse_json_safely(res.content)
    is_ok = audit.get("status") == "通过"
    
    return {
        "review_log": audit.get("reason", ""),
        "is_approved": is_ok,
        "status_message": "✅ 创意方案已通过初步审计，等待人类主编（人工）核准..." if is_ok else "❌ 创意张力不足或风格偏离，正在重新策划..."
    }

def human_node(state: AgentState):
    proposal = state.get('proposal', '')
    user_input = interrupt({
        "status_message": "🎭 小说元策划方案已就绪，请主编审阅。",
        "proposal": proposal
    })
    
    is_approved = any(word in str(user_input).lower() for word in ["批准", "通过", "ok", "yes", "保存"])
    return {
        "user_feedback": str(user_input),
        "is_approved": is_approved,
        "status_message": "正在固化小说元数据..." if is_approved else "正在根据反馈调整创意细节..."
    }

def saver_node(state: AgentState, config: RunnableConfig):
    dispatch_log(config, "正在持久化小说策划变更...")
    outline_id = state.get('outline_id', 'default_novel')
    # 支持修改逻辑
    doc_id = state.get('doc_id') or f"novel_meta_{datetime.datetime.now().strftime('%H%M%S')}"
    
    doc = {
        "doc_id": doc_id,
        "outline_id": outline_id,
        "type": "novel_meta",
        "content": state.get('proposal', ''),
        "query": state.get('query', ''),
        "timestamp": datetime.datetime.now().isoformat(),
        "is_update": "doc_id" in state
    }
    
    db_path = get_db_path("novel_db.json", worldview_id=state.get('worldview_id', 'default_wv'))
    with open(db_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(doc, ensure_ascii=False) + "\n")
        
    status = "✨ 小说策划方案已成功更新。" if state.get('doc_id') else "✨ 小说策划方案已生效。"
    return {"status_message": status}

# Graph
workflow = StateGraph(AgentState)
workflow.add_node("generator", generator_node)
workflow.add_node("reviewer", reviewer_node)
workflow.add_node("human", human_node)
workflow.add_node("saver", saver_node)

workflow.add_edge(START, "generator")
workflow.add_edge("generator", "reviewer")

def route_after_review(state: AgentState):
    if state.get("is_approved"): return "human"
    if state.get("iterations", 0) >= 3: return "human"
    return "generator"

workflow.add_conditional_edges("reviewer", route_after_review, {"human": "human", "generator": "generator"})

def route_after_human(state: AgentState):
    if state.get("is_approved"): return "saver"
    if "终止" in state.get("user_feedback", ""): return END
    return "generator"

workflow.add_conditional_edges("human", route_after_human, {"saver": "saver", "generator": "generator", END: END})
workflow.add_edge("saver", END)

app = workflow.compile(checkpointer=MemorySaver())
