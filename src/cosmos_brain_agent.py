"""
Cosmos Brain Agent (万象大脑) - PGA 小说创作引擎核心指挥官

本模块实现了“万象大脑”的自主审计与创意扩张逻辑。
其核心在于：
1. 全局审计 (Holistic Audit): 发现不同世界观、大纲、正文之间的逻辑冲突。
2. 创意扩张 (Creative Expansion): 主动推演尚未被用户触及的设定盲区。
3. 跨 Agent 驱动 (Orchestration): 产生指令并指派给 Worldview, Outline 或 Writing Agent。
"""
import os
import json
import datetime
from typing import Annotated, TypedDict, List, Union, Optional, Literal
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Command
from langchain_core.runnables import RunnableConfig

# Import shared utilities
from src.common.lore_utils import (
    get_llm, 
    get_vector_store, 
    get_prohibited_rules, 
    get_unified_context,
    parse_json_safely,
    get_db_path,
    dispatch_log,
    get_all_lore_items
)
from src.common.brain_utils import summarize_project_context, format_command_for_agent

# ==========================================
# 0. State Definition
# ==========================================
class BrainState(TypedDict):
    """
    大脑 Agent 运行时的全局认知上下文。
    """
    worldview_id: str          # 所属世界观 ID
    outline_id: Optional[str]     # 关联的小说项目 ID
    
    # 认知输入
    lore_summary: str          # 世界观核心背景摘要
    outline_summary: str       # 大纲核心背景摘要
    system_rules: str          # PGA 禁令与演化法则
    
    # 思考产出
    insights: List[dict]       # 发现的问题/洞察 (Problem, Severity, Suggestion)
    expansion_seeds: List[dict]# 主动推演的想法种子 (Name, Category, Description)
    pending_commands: List[dict] # 派发给子 Agent 的指令队列 (TargetAgent, Query, Priority)
    
    status_message: str        # 执行进度描述
    llm_interactions: dict     # [诊断] 存储流程数据

# ==========================================
# Nodes Implementation
# ==========================================

def scanner_node(state: BrainState, config: RunnableConfig):
    """
    全项目扫描节点：聚合世界观和大纲的全局视图。
    """
    dispatch_log(config, "🧠 大脑正在启动全局神经元扫描，聚合多源素材并提取核心摘要...")
    
    worldview_id = state.get('worldview_id', 'default_wv')
    outline_id = state.get('outline_id')
    
    # 调用摘要工具
    summaries = summarize_project_context(worldview_id=worldview_id, outline_id=outline_id)
    dispatch_log(config, "✅ 扫描完成。世界观/大纲/正文摘要提取完毕。")
    
    return {
        "lore_summary": summaries["worldview_summary"],
        "outline_summary": summaries["outline_summary"],
        "status_message": "🧠 神经网络认知建模完成，准备开启多维审计模式。"
    }

def auditor_node(state: BrainState, config: RunnableConfig):
    """
    逻辑审计节点：发现潜在的冲突点。
    """
    dispatch_log(config, "大脑执行逻辑并发扫描中，寻找叙事不一致性...")
    
    prompt = f"""你是一个运行在后台的“万象大脑 (Cosmos Brain)”。
你的任务是审计当前小说项目的逻辑一致性。

【世界观背景】: {state.get('lore_summary')}
【大纲背景】: {state.get('outline_summary')}
【最高禁令】: {state.get('system_rules')}

TASK:
请分析是否存在逻辑冲突、设定崩塌、或人物动机断层。
输出 JSON 数组格式: [{{"problem": "问题描述", "severity": "low/med/high", "suggestion": "修复建议"}}]
如果没有问题，返回空数组 []。
"""
    res = get_llm(json_mode=True, agent_name="brain").invoke(prompt)
    insights = parse_json_safely(res.content) or []
    
    return {
        "insights": insights,
        "status_message": f"🕵️ 审计完成，发现 {len(insights)} 个潜在逻辑节点需要注意。"
    }

def expansion_node(state: BrainState, config: RunnableConfig):
    """
    创意扩张节点：主动推演新的设定种子。
    """
    dispatch_log(config, "大脑正在进行多维创意发散，探索设定盲区...")
    
    prompt = f"""你是一个具备自主性的“万象大脑”。
请基于现有设定，主动推演并扩张出 3 个新的“设定种子”，以丰富世界观的厚度。

【现有设定】: {state.get('lore_summary')}

TASK:
请输出 3 个能够丰富世界观深度或增加冲突的新实体提案。
必须输出 JSON 数组格式: [{{"name": "实体名", "category": "分类", "description": "核心设定描述"}}]
"""
    res = get_llm(json_mode=True, agent_name="brain").invoke(prompt)
    seeds = parse_json_safely(res.content) or []
    
    return {
        "expansion_seeds": seeds,
        "status_message": f"✨ 创意扩张完成，大脑孵化了 {len(seeds)} 个全新的设定种子。"
    }

def orchestrator_node(state: BrainState, config: RunnableConfig):
    """
    指挥调度节点：将发现的问题或扩张种子转化为子 Agent 指令。
    """
    dispatch_log(config, "大脑正在下达指令，同步指挥子 Agent 矩阵...")
    
    insights = state.get("insights", [])
    seeds = state.get("expansion_seeds", [])
    commands = []
    
    # 规则1: 将严重问题转化为 Worldview 修正任务
    for ins in insights:
        if ins.get("severity") == "high":
            commands.append({
                "target": "worldview",
                "query": f"修复以下逻辑冲突: {ins['problem']}. 建议: {ins['suggestion']}",
                "priority": "high"
            })
            
    # 规则2: 将选定的种子转化为设定生成任务
    if seeds:
        commands.append({
            "target": "worldview",
            "query": f"根据大脑扩张种子创建新设定: {seeds[0]['name']}. 描述: {seeds[0]['description']}",
            "priority": "normal"
        })
        
    return {
        "pending_commands": commands,
        "status_message": f"📡 指标下达完毕，已向子 Agent 矩阵分发 {len(commands)} 个协同任务。"
    }

# ==========================================
# Graph Definition
# ==========================================
workflow = StateGraph(BrainState)
workflow.add_node("scanner", scanner_node)
workflow.add_node("auditor", auditor_node)
workflow.add_node("expansion", expansion_node)
workflow.add_node("orchestrator", orchestrator_node)

workflow.add_edge(START, "scanner")
workflow.add_edge("scanner", "auditor")
workflow.add_edge("auditor", "expansion")
workflow.add_edge("expansion", "orchestrator")
workflow.add_edge("orchestrator", END)

# Compile
app = workflow.compile(checkpointer=MemorySaver())
