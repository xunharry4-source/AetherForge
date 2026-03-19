import os
import json
from typing import Annotated, TypedDict, List
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Command
import datetime

# Import shared utilities
from lore_utils import (
    get_llm, 
    get_vector_store, 
    get_prohibited_rules, 
    get_worldview_context_by_category, 
    get_unified_context,
    parse_json_safely
)

# ==========================================
# 0. State Definition
# ==========================================
class OutlineState(TypedDict):
    query: str             # 用户的小说想法/需求
    context: str           # 检索到的世界观背景
    proposal: str          # 当前生成的大纲草案
    review_log: str        # 逻辑审计日志
    user_feedback: str     # 用户的调整意见
    iterations: int        # 总生成次数
    audit_count: int       # 当前自审重试次数
    is_approved: bool      # 是否通过审核/用户批准
    status_message: str    # 执行进度描述

# ==========================================
# Nodes Implementation
# ==========================================

def outline_planner(state: OutlineState):
    """大纲策划节点"""
    # 使用智能路由检索世界观 (优先 MongoDB 权威定义)
    rag_context = get_unified_context(state['query'])
    
    feedback_section = ""
    if state.get('user_feedback'):
        feedback_section = f"""
【！！！当前核心修改需求 - 必须首先满足！！！】
用户指出以下问题或要求：
>>> {state['user_feedback']} <<<
你必须在本次生成中根据此反馈调整大纲。
"""

    prompt = f"""你是一个专精于“万象星际协议体 (PGA)”世界观的小说策划专家。
你的任务是根据用户的需求编写一份详尽的小说大纲。

{feedback_section}

【JSON Schema】
{{
  "meta_info": {{
    "title": "暂定书名",
    "genre": ["题材分类"],
    "tone": "基调",
    "target_audience": "目标受众",
    "writing_style": "写作风格描述：如 硬核科幻、意识流、极简主义"
  }},
  "core_hook": {{
    "logline": "一句话核心创意",
    "inciting_incident": "激励事件",
    "core_conflict": "核心矛盾"
  }},
  "world_building_ref": {{
    "base_rules": "底层逻辑",
    "key_locations": ["关键地点"],
    "power_system": "力量/科技等级体系"
  }},
  "character_roster": [
    {{
      "name": "名称",
      "role": "Protagonist/Antagonist/Supporting/Mentor",
      "motivation": "动机",
      "internal_flaw": "缺陷",
      "character_arc": "成长曲线"
    }}
  ],
  "plot_beats": {{
    "act_1": "开端与建置",
    "midpoint": "中点转换",
    "climax": "最终高潮",
    "resolution": "结局"
  }},
  "themes": ["主题"]
}}

【世界观背景/权威参考】
{rag_context}

【用户需求】
{state['query']}

【之前的审核意见】
{state['review_log']}

请直接输出符合 Schema 的 JSON 对象。
"""
    res = get_llm(json_mode=True).invoke(prompt)
    curr_iterations = state.get('iterations', 0)
    
    return {
        "proposal": res.content,
        "iterations": int(curr_iterations) + 1,
        "user_feedback": "",
        "status_message": "大纲（JSON格式）已生成，正在进行逻辑一致性审计..."
    }

def outline_critic(state: OutlineState):
    """大纲审计节点"""
    prohibited_items = get_prohibited_rules()
    worldview_rules = get_worldview_context_by_category(state['query'])
    
    prompt = f"""你是一个负责维护 PGA 世界观与故事逻辑严谨性的“剧本审核官”。
你必须将审核结果输出为 **JSON 格式**。

【最高禁令 - 必须绝对遵循】
{prohibited_items}

【官方定义参考】
{worldview_rules}

【审核标准】
1. 物理一致性：是否存在非法的时间旅行、无限能量或违背热力学的情况？
2. Schema 完备性：是否完整填充了所有字段？
3. 角色动机：角色的行为是否在其背景下具备物理与社会合理性？
4. 官方定义匹配：如果涉及特定种族或势力，是否符合库内权威定义？

【输出格式】
{{
  "status": "合理" 或 "不合理",
  "audit_log": "详细的逻辑审查记录。若涉及字段缺失或逻辑冲突，请明确指出。",
  "is_consistent": true/false
}}

待审核大纲 JSON：
{state['proposal']}
"""
    res = get_llm(json_mode=True).invoke(prompt)
    try:
        audit_data = parse_json_safely(res.content)
        if not audit_data:
             raise ValueError("Invalid audit JSON")
        is_ok = audit_data.get("status") == "合理"
        curr_audit_count = state.get('audit_count', 0)
        
        return {
            "review_log": audit_data.get("audit_log", ""),
            "is_approved": is_ok,
            "audit_count": int(curr_audit_count) + 1,
            "status_message": "审计完成：" + ("逻辑自洽" if is_ok else "发现逻辑漏洞，正在打回重修")
        }
    except Exception:
        curr_audit_count = state.get('audit_count', 0)
        return {"is_approved": False, "audit_count": int(curr_audit_count) + 1, "status_message": "审计解析异常"}

def human_gate(state: OutlineState):
    """等待用户反馈节点"""
    user_input = interrupt({"status_message": "大纲已就绪，等待您的调整建议或批准...", "proposal": state['proposal']})
    return {"user_feedback": user_input, "is_approved": user_input == "批准"}

def outline_saver(state: OutlineState):
    """持久化节点：将通过审核的大纲存入 outlines_db.json"""
    try:
        outline_data = parse_json_safely(state['proposal'])
        if not outline_data:
            raise ValueError("Invalid proposal JSON")
        record = {
            "id": f"outline_{int(datetime.datetime.now().timestamp())}",
            "timestamp": datetime.datetime.now().isoformat(),
            "query": state['query'],
            "outline": outline_data,
            "iterations": state['iterations']
        }
        
        with open('outlines_db.json', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            
        return {"status_message": "大纲已最终确立并成功存入 outlines_db.json。"}
    except Exception as e:
        return {"status_message": f"大纲存档失败: {str(e)}"}

# ==========================================
# Graph Definition
# ==========================================
workflow = StateGraph(OutlineState)
workflow.add_node("planner", outline_planner)
workflow.add_node("critic", outline_critic)
workflow.add_node("human", human_gate)
workflow.add_node("saver", outline_saver)

workflow.add_edge(START, "planner")
workflow.add_edge("planner", "critic")

def route_after_critic(state: OutlineState):
    audit_count = state.get("audit_count", 0)
    if state["is_approved"] or int(audit_count) >= 3:
        return "human"
    return "planner"

workflow.add_conditional_edges("critic", route_after_critic, {"human": "human", "planner": "planner"})

def route_after_human(state: OutlineState):
    fb = state.get("user_feedback", "").strip()
    if fb == "批准": return "saver"
    if fb == "终止": return END
    if fb: return "planner" # 有反馈则重新生成
    return END

workflow.add_conditional_edges("human", route_after_human, {"saver": "saver", "planner": "planner", END: END})
workflow.add_edge("saver", END)

app = workflow.compile(checkpointer=MemorySaver())
