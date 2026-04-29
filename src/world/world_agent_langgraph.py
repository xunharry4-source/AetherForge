"""
World Agent (世界 Agent) - 纯粹造物主共创模式
负责定义：宇宙底层物理法则、常数、多维空间规则。
此 Agent 不设自动审查，完全依赖人工反馈进行无限次迭代。
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
    world_id: str
    context: str
    proposal: str
    user_feedback: str
    iterations: int
    is_approved: bool
    status_message: str

def generator_node(state: AgentState, config: RunnableConfig):
    dispatch_log(config, "🌌 宇宙创世引擎已激活，正在为您重塑世界...")
    query = state.get('query', '')
    world_id = state.get('world_id', 'world_default')
    user_feedback = state.get('user_feedback', '')
    
    rag_context = get_unified_context(query, worldview_id=world_id)
    
    feedback_prompt = f"\n【造物主反馈】：{user_feedback}\n请根据此反馈进行完全不同的创意演化。" if user_feedback else ""
    
    prompt = f"""你是一个“宇宙创世 Agent (World Agent)”。
你的目标是与人工合作，迭代出一个【完全不同】且【极具想象力】的世界。
不要受限于现有的物理逻辑，你的任务是提供令人惊叹的创意方案。

【初始愿景】：{query}
【现有宇宙上下文】：{rag_context}{feedback_prompt}

请生成一个结构化的 JSON 提案。
"""
    res = get_llm(json_mode=True, agent_name="world").invoke(prompt)
    return {
        "proposal": res.content,
        "iterations": state.get('iterations', 0) + 1,
        "status_message": "✨ 新的世界形态已构思完成，请造物主进行降临核准。"
    }

def human_node(state: AgentState):
    proposal = state.get('proposal', '')
    # 使用 interrupt 挂起，强制人工介入
    user_input = interrupt({
        "status_message": "🌌 世界演化已就绪，请给出您的修正意见或批准保存。",
        "proposal": proposal
    })
    
    # 只要用户输入包含批准性质的词汇，才通过
    is_approved = any(word in str(user_input).lower() for word in ["批准", "通过", "ok", "yes", "保存", "确定"])
    return {
        "user_feedback": str(user_input),
        "is_approved": is_approved,
        "status_message": "正在固化物理常数..." if is_approved else "正在解析您的反馈，准备下一轮宇宙重塑..."
    }

def saver_node(state: AgentState, config: RunnableConfig):
    dispatch_log(config, "正在持久化宇宙法则变更...")
    world_id = state.get('world_id', 'world_default')
    # 优先使用 state 中的 doc_id 以支持修改逻辑
    doc_id = state.get('doc_id') or f"world_core_{datetime.datetime.now().strftime('%H%M%S')}"
    
    doc = {
        "doc_id": doc_id,
        "type": "world_core",
        "content": state.get('proposal', ''),
        "query": state.get('query', ''),
        "timestamp": datetime.datetime.now().isoformat(),
        "is_update": "doc_id" in state 
    }
    
    db_path = get_db_path("world_db.json", worldview_id=world_id)
    # 简易实现：在追加模式下，后续读取逻辑会取最后一个 doc_id 匹配的记录作为最新版
    with open(db_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(doc, ensure_ascii=False) + "\n")
        
    status = "✨ 宇宙法则已成功更新。" if state.get('doc_id') else "✨ 宇宙基石已成功固化。"
    return {"status_message": status}

# Graph
workflow = StateGraph(AgentState)
workflow.add_node("generator", generator_node)
workflow.add_node("human", human_node)
workflow.add_node("saver", saver_node)

workflow.add_edge(START, "generator")
workflow.add_edge("generator", "human")

def route_after_human(state: AgentState):
    if state.get("is_approved"): return "saver"
    return "generator" # 只要未批准，就不断迭代

workflow.add_conditional_edges("human", route_after_human, {"saver": "saver", "generator": "generator"})
workflow.add_edge("saver", END)

app = workflow.compile(checkpointer=MemorySaver())
