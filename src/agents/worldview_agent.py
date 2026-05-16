"""Worldview Agent - 独立世界观工作流。

符合需求：Input -> Initial Expansion -> World Rule Review -> Worldview Consistency Review -> Human -> Commit；
人工不同意或任一审查失败进入 Modify Content，再回到 World Rule Review。
"""

import json
import uuid
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from src.agents.review_nodes.world_review import make_world_review_node, make_world_review_route
from src.agents.review_nodes.worldview_review import make_worldview_review_node, make_worldview_review_route
from src.common.config_utils import get_config
from src.common.lore_utils import get_langfuse_callback, get_llm, get_mongodb_db, get_unified_context, parse_json_safely


AGENT_NAME = "worldview_agent"
ENTITY_TYPE = "worldview"
PRIMARY_FIELD = "summary"
MAX_AUTO_REVIEW_ITERATIONS = 3
WORKFLOW_DESCRIPTION = "世界观 Agent 流程：接收设定输入 -> 初始扩充设定内容 -> 世界规则审查 -> 既有世界观一致性审查 -> 人工确认 -> 批准后写入 worldviews；人工不同意或任一审查失败进入修改内容节点，再从世界规则审查重新开始。"
WORKFLOW_STEPS = {
    "input": {
        "step_index": 1,
        "step_title": "步骤 1：接收世界观输入",
        "function": "接收设定条目 payload 与父级 world_id",
        "description": "记录世界观名称、摘要、world_id、worldview_id 或 target_id，以及用户消息，确保本次任务只处理该世界下的 Canon 设定。",
    },
    "initial_expansion": {
        "step_index": 2,
        "step_title": "步骤 2：初始扩充",
        "function": "调用 worldview_agent 专属 LLM 整理世界观输入",
        "description": "对碎片化设定进行初步补全并直接生成可审查的世界观 payload，明确条目名称、分类、核心规则、父级 world_id、需要检索的 Canon 关键词和不可改写的用户原意；不得写库，不得跳过 LLM，不得使用通用 Prompt。",
    },
    "world_rule_review": {
        "step_index": 3,
        "step_title": "步骤 3：世界规则审查",
        "function": "检查是否违反世界禁止规则与基本设定",
        "description": "基于 worlds 中的 forbidden_rules 与 basic_settings 审查当前世界观内容是否违反世界根禁令、基础时代、力量体系、地理边界、资源机制或组织结构；失败时写入 world_rule_review_feedback 并进入修改内容节点。",
    },
    "worldview_consistency_review": {
        "step_index": 4,
        "step_title": "步骤 4：既有世界观一致性审查",
        "function": "检查是否违反同一世界下已有世界观设定",
        "description": "基于同一 world_id 下已经入库的世界观设定审查 Canon 冲突、逻辑漏洞和前后矛盾；失败时写入 worldview_consistency_feedback 并进入修改内容节点。",
    },
    "human": {
        "step_index": 5,
        "step_title": "步骤 5：人工确认",
        "function": "等待用户批准、重写或中止",
        "description": "两个审查节点都通过后进入人工节点。用户可批准写库，也可选择修改模式并提交反馈进入修改内容节点；修改后必须重新通过两个审查节点。",
    },
    "modify_content": {
        "step_index": 6,
        "step_title": "步骤 6：修改内容",
        "function": "根据审查意见或人工反馈调用 worldview_agent 专属 LLM 修改世界观内容",
        "description": "仅在世界规则审查失败、既有世界观一致性审查失败或人工不同意时执行。根据审查反馈或用户反馈修正世界观 payload，保留未要求修改的内容和业务 ID；不得写库，不得使用通用 Prompt。",
    },
    "commit": {
        "step_index": 7,
        "step_title": "步骤 7：写库固化",
        "function": "执行 worldviews 集合写入",
        "description": "人工批准后写入或更新 MongoDB worldviews 集合，并保留 world_id、worldview_id 和真实写库结果。",
    },
}
NODE_ANNOTATIONS = {
    "input": {
        "input_annotation": "输入必须包含 world_id，并可包含 worldview_id 或 target_id；本节点确认任务只处理该世界下的世界观设定。",
        "output_annotation": "输出 accepted=true，并把 payload 固定为后续初始扩充与审查的基准。",
        "next_step_annotation": "下一步进入初始扩充节点，先整理设定意图、分类和 Canon 检索关键词。",
    },
    "initial_expansion": {
        "input_annotation": "输入是用户消息、世界观 payload、人工反馈和修改模式；必须保留 world_id 和用户原始设定。",
        "output_annotation": "输出可审查的世界观 payload、expanded_input、llm_call、raw_response 和 parsed_response。",
        "next_step_annotation": "下一步进入世界规则审查，先检查是否违反世界禁止规则与基本设定。",
    },
    "world_rule_review": {
        "input_annotation": "输入是当前世界观 payload、world_id 和 worlds 中的 forbidden_rules/basic_settings。",
        "output_annotation": "输出包含 passed、errors 和 reviewer；失败原因会写入 world_rule_review_feedback。",
        "next_step_annotation": "通过则进入既有世界观一致性审查；失败且未超出自动迭代上限则进入修改内容节点。",
    },
    "worldview_consistency_review": {
        "input_annotation": "输入是通过世界规则审查后的世界观 payload 和同一世界下已有世界观上下文。",
        "output_annotation": "输出包含 passed、errors 和 reviewer；失败原因会写入 worldview_consistency_feedback。",
        "next_step_annotation": "通过则进入人工确认；失败且未超出自动迭代上限则进入修改内容节点。",
    },
    "human": {
        "input_annotation": "输入是两次审查通过后的世界观内容、审查意见、用户决策和修改模式。",
        "output_annotation": "输出记录 approve、request_changes 或 reject，以及用户反馈内容。",
        "next_step_annotation": "批准则写库；要求修改则进入修改内容节点并重新审查；中止则结束。",
    },
    "modify_content": {
        "input_annotation": "输入是当前世界观 payload、world_rule_review_feedback、worldview_consistency_feedback、人工反馈和修改模式。",
        "output_annotation": "输出修改后的世界观 payload、llm_call、raw_response、parsed_response 和 change_summary。",
        "next_step_annotation": "下一步回到世界规则审查，必须连续通过两个审查节点后才能进入人工确认。",
    },
    "commit": {
        "input_annotation": "输入是人工批准后的最终 worldview payload。",
        "output_annotation": "输出是真实 MongoDB worldviews 写入结果，包含 world_id 与 worldview_id。",
        "next_step_annotation": "写库完成后工作流结束。",
    },
}


class WorldviewAgentState(TypedDict, total=False):
    action: str
    message: str
    payload: Dict[str, Any]
    pending_payload: Dict[str, Any]
    feedback: str
    review_feedback: str
    revision_mode: str
    decision: str
    manual_edit: bool
    expanded_input: Dict[str, Any]
    initial_expansion: Dict[str, Any]
    modification: Dict[str, Any]
    review_passed: bool
    review_errors: List[str]
    world_rule_review_passed: bool
    world_rule_review_errors: List[str]
    world_rule_review_feedback: str
    worldview_consistency_passed: bool
    worldview_consistency_errors: List[str]
    worldview_consistency_feedback: str
    nodes: List[Dict[str, Any]]
    conversation: List[Dict[str, Any]]
    iterations: int
    status: str
    current_node: str
    commit_result: Dict[str, Any]
    committed: bool


def _extract_llm_content(response: Any) -> str:
    """提取 LLM 返回正文，兼容字符串、Message 和分段 content。"""
    content = getattr(response, "content", response)
    if isinstance(content, list):
        return "\n".join(str(item) for item in content)
    return str(content or "")


def _llm_metadata(raw_content: str) -> Dict[str, Any]:
    """生成本次 worldview_agent LLM 调用的中文可审计元数据。"""
    config = get_config()
    provider = str(config.get("LLM_PROVIDER", "ollama")).lower()
    agent_config = (config.get("AGENT_MODELS") or {}).get(AGENT_NAME) or {}
    model_name = agent_config.get("model") if isinstance(agent_config, dict) else agent_config
    provider_config = (config.get("LLM_MODELS") or {}).get(provider) or {}
    if isinstance(provider_config, dict) and not model_name:
        model_name = provider_config.get("default")
    return {"llm_invoked": True, "llm_agent_name": AGENT_NAME, "provider": provider, "model": model_name or config.get("DEFAULT_MODEL"), "json_mode": True, "raw_response_chars": len(raw_content)}


def _invoke_llm(prompt: str) -> tuple[str, Dict[str, Any]]:
    """真实调用 worldview_agent 对应 LLM；空响应直接报错，禁止伪成功。"""
    llm = get_llm(json_mode=True, agent_name=AGENT_NAME)
    config: Dict[str, Any] = {}
    callback = get_langfuse_callback()
    if callback:
        config["callbacks"] = [callback]
    response = llm.invoke(prompt, config=config if config else None)
    raw_content = _extract_llm_content(response)
    if not raw_content.strip():
        raise ValueError(f"{AGENT_NAME} returned empty LLM response")
    return raw_content, _llm_metadata(raw_content)


def _node(node_id: str, status: str, node_input: Dict[str, Any], output: Dict[str, Any]) -> Dict[str, Any]:
    """构造带中文步骤说明、节点注解、输入输出说明的工作流节点。"""
    step = WORKFLOW_STEPS[node_id]
    annotations = NODE_ANNOTATIONS[node_id]
    return {"node_id": node_id, "label": step["step_title"], **step, "node_annotation": f"{step['step_title']}：{step['description']}", **annotations, "status": status, "input": node_input, "output": output}


def build_initial_expansion_prompt(action: str, payload: Dict[str, Any], message: str, *, revision_mode: Optional[str], feedback: str) -> str:
    """构造 worldview_agent 初始扩充 Prompt，专门整理世界观设定输入。"""
    return f"""你是 worldview_agent 的初始扩充节点，只负责世界观 Canon 设定输入整理。
禁止使用通用 Agent 口径。禁止生成小说项目、大纲或章节正文。禁止写库。禁止返回解释文字。

【业务动作】{action}
【所属世界 world_id】{payload.get("world_id", "")}
【世界观 ID】{payload.get("worldview_id", "") or payload.get("target_id", "")}
【用户消息】{message}
【人工反馈】{feedback}
【修改模式】{revision_mode or "initial_expansion"}
【原始 payload】
{json.dumps(payload or {}, ensure_ascii=False, indent=2)}

任务：
1. 保留用户原始设定、父级 world_id、worldview_id 或 target_id。
2. 补全条目名称、分类、核心规则、Canon 检索关键词和冲突风险。
3. 明确后续要先接受世界禁止规则与基本设定审查，再接受既有世界观一致性审查。
4. 输出必须是可直接提交审查的世界观 payload，但不得写库。

只返回合法 JSON：
{{
  "metadata": {{"agent": "worldview_agent", "node": "initial_expansion", "entity_type": "worldview", "action": "{action}"}},
  "payload": {{
    "world_id": "{payload.get("world_id", "")}",
    "worldview_id": "{payload.get("worldview_id", "")}",
    "target_id": "{payload.get("target_id", "")}",
    "name": "世界观名称",
    "summary": "结构化世界观设定条目"
  }},
  "expanded_input": {{
    "world_id": "{payload.get("world_id", "")}",
    "worldview_id": "{payload.get("worldview_id", "")}",
    "target_id": "{payload.get("target_id", "")}",
    "name": "{payload.get("name", "")}",
    "summary_seed": "{payload.get("summary", "")}",
    "category": "从用户输入提炼的设定分类",
    "canon_keywords": ["需要检索的 Canon 关键词"],
    "must_keep": ["不可改写的用户原意"],
    "review_focus": "审查节点需要重点检查的 Canon 约束"
  }},
  "expansion_notes": "初始扩充节点整理了哪些设定约束"
}}
"""


def generate_initial_expansion(action: str, payload: Dict[str, Any], message: str, *, revision_mode: Optional[str] = None, feedback: str = "") -> Dict[str, Any]:
    """调用 LLM 生成世界观初始扩充结果，确保第二节点真实使用 worldview_agent LLM。"""
    prompt = build_initial_expansion_prompt(action, payload or {}, message, revision_mode=revision_mode, feedback=feedback)
    raw_content, llm_call = _invoke_llm(prompt)
    parsed = parse_json_safely(raw_content)
    if not isinstance(parsed, dict):
        raise ValueError(f"{AGENT_NAME} initial expansion returned non-object JSON: {raw_content[:500]}")
    expanded_input = parsed.get("expanded_input") or {}
    initial_payload = parsed.get("payload") or expanded_input
    if not isinstance(initial_payload, dict):
        raise ValueError(f"{AGENT_NAME} initial expansion missing payload object: {raw_content[:500]}")
    if not isinstance(expanded_input, dict):
        expanded_input = {}
    if payload.get("name") and revision_mode != "full_rewrite":
        initial_payload["name"] = payload["name"]
    return {"payload": initial_payload, "expanded_input": expanded_input, "llm_invoked": True, "agent_name": AGENT_NAME, "llm_agent_name": AGENT_NAME, "llm_call": llm_call, "raw_response": raw_content, "parsed_response": parsed, "expansion_notes": parsed.get("expansion_notes", "")}


def build_modification_prompt(action: str, payload: Dict[str, Any], message: str, *, revision_mode: Optional[str], feedback: str, expansion_error: str = "") -> str:
    """构造 worldview_agent 修改内容 Prompt，只允许按反馈修正世界观 Canon 设定。"""
    rag_context = get_unified_context(
        f"{message}\n{payload.get('name', '')}\n{payload.get('summary', '')}",
        worldview_id=str(payload.get("worldview_id") or payload.get("target_id") or "default_wv"),
    )
    retry_clause = f"\n【审查失败原因】{expansion_error}\n必须根据失败原因修正后重新扩充。" if expansion_error else ""
    return f"""你是 worldview_agent 的修改内容节点，只负责按反馈修正世界观规则与设定库。
禁止生成小说项目、大纲或章节正文。禁止写库。禁止返回解释文字。

【业务动作】{action}
【所属世界 world_id】{payload.get("world_id", "")}
【世界观 ID】{payload.get("worldview_id", "") or payload.get("target_id", "")}
【用户消息】{message}
【人工反馈或审查意见】{feedback}
【修改模式】{revision_mode or "partial_rewrite"}
【当前 payload】
{json.dumps(payload or {}, ensure_ascii=False, indent=2)}
【RAG 上下文】
{rag_context}{retry_clause}

修改规则：
1. 只修正审查失败原因或人工反馈要求修改的内容。
2. 必须包含条目名称、核心描述、规则约束、分类标签。
3. 必须保留 world_id、worldview_id、target_id，且不得破坏未点名内容。

只返回合法 JSON：
{{
  "metadata": {{"agent": "worldview_agent", "node": "modify_content", "entity_type": "worldview", "action": "{action}"}},
  "payload": {{
    "world_id": "{payload.get("world_id", "")}",
    "worldview_id": "{payload.get("worldview_id", "")}",
    "target_id": "{payload.get("target_id", "")}",
    "name": "世界观名称",
    "summary": "结构化世界观设定条目"
  }},
  "modification_notes": "worldview_agent 本轮修正的设定维度",
  "change_summary": "相对输入 payload 的变化摘要"
}}
"""


def generate_content_modification(action: str, payload: Dict[str, Any], message: str, *, revision_mode: Optional[str] = None, feedback: str = "", expansion_error: str = "") -> Dict[str, Any]:
    """调用 LLM 根据审查意见或人工反馈修改世界观内容。"""
    prompt = build_modification_prompt(action, payload or {}, message, revision_mode=revision_mode, feedback=feedback, expansion_error=expansion_error)
    raw_content, llm_call = _invoke_llm(prompt)
    parsed = parse_json_safely(raw_content)
    if not isinstance(parsed, dict):
        raise ValueError(f"{AGENT_NAME} modification returned non-object JSON: {raw_content[:500]}")
    modified_payload = parsed.get("payload")
    if not isinstance(modified_payload, dict):
        raise ValueError(f"{AGENT_NAME} modification missing payload object: {raw_content[:500]}")
    if payload.get("name") and revision_mode != "full_rewrite":
        modified_payload["name"] = payload["name"]
    return {"payload": modified_payload, "llm_invoked": True, "agent_name": AGENT_NAME, "llm_agent_name": AGENT_NAME, "llm_call": llm_call, "raw_response": raw_content, "parsed_response": parsed, "modification_notes": parsed.get("modification_notes", ""), "change_summary": parsed.get("change_summary", "")}


def input_node(state: WorldviewAgentState) -> WorldviewAgentState:
    """输入节点：记录世界观 payload、父级 world_id 和用户消息。"""
    nodes = list(state.get("nodes") or [])
    payload = dict(state.get("payload") or {})
    nodes.append(_node("input", "completed", {"message": state.get("message", ""), "payload": payload}, {"accepted": True}))
    return {"nodes": nodes, "pending_payload": payload, "current_node": "initial_expansion", "status": "running"}


def initial_expansion_node(state: WorldviewAgentState) -> WorldviewAgentState:
    """初始扩充节点：调用 worldview_agent LLM 扩充世界观内容并提交世界规则审查。"""
    payload = dict(state.get("pending_payload") or state.get("payload") or {})
    expansion = generate_initial_expansion(state.get("action", "create"), payload, state.get("message", ""), revision_mode=state.get("revision_mode"), feedback=state.get("feedback", ""))
    nodes = list(state.get("nodes") or [])
    iteration = int(state.get("iterations") or 0) + 1
    nodes.append(_node("initial_expansion", "completed", {"payload": payload, "feedback": state.get("feedback", "")}, {**expansion, "iteration": iteration}))
    return {"initial_expansion": expansion, "expanded_input": expansion["expanded_input"], "pending_payload": expansion["payload"], "nodes": nodes, "iterations": iteration, "current_node": "world_rule_review", "status": "reviewing_world_rules"}


def modify_content_node(state: WorldviewAgentState) -> WorldviewAgentState:
    """修改内容节点：按审查意见或人工反馈调用 worldview_agent LLM 修改世界观内容。"""
    payload = dict(state.get("pending_payload") or state.get("payload") or {})
    feedback = state.get("world_rule_review_feedback") or state.get("worldview_consistency_feedback") or state.get("review_feedback") or state.get("feedback", "")
    modification = generate_content_modification(state.get("action", "create"), payload, state.get("message", ""), revision_mode=state.get("revision_mode"), feedback=feedback, expansion_error=feedback)
    iteration = int(state.get("iterations") or 0) + 1
    nodes = list(state.get("nodes") or [])
    nodes.append(_node("modify_content", "completed", {"payload": payload, "feedback": feedback, "revision_mode": state.get("revision_mode")}, {**modification, "iteration": iteration}))
    return {"modification": modification, "pending_payload": modification["payload"], "nodes": nodes, "iterations": iteration, "current_node": "world_rule_review", "status": "reviewing_world_rules"}


world_rule_review_node = make_world_review_node(
    node_id="world_rule_review",
    entity_type="worldview_world_rules",
    reviewer="worldview_world_rules_review_agent",
    passed_key="world_rule_review_passed",
    errors_key="world_rule_review_errors",
    feedback_key="world_rule_review_feedback",
    next_node="worldview_consistency_review",
    next_status="reviewing_worldview_consistency",
    max_auto_review_iterations=MAX_AUTO_REVIEW_ITERATIONS,
    node_factory=_node,
)
route_after_world_rule_review = make_world_review_route(
    passed_key="world_rule_review_passed",
    next_node="worldview_consistency_review",
    max_auto_review_iterations=MAX_AUTO_REVIEW_ITERATIONS,
)
worldview_consistency_review_node = make_worldview_review_node(
    node_id="worldview_consistency_review",
    entity_type="worldview_consistency",
    reviewer="worldview_consistency_review_agent",
    passed_key="worldview_consistency_passed",
    errors_key="worldview_consistency_errors",
    feedback_key="worldview_consistency_feedback",
    next_node="human",
    next_status="waiting_human",
    max_auto_review_iterations=MAX_AUTO_REVIEW_ITERATIONS,
    node_factory=_node,
)
route_after_worldview_consistency_review = make_worldview_review_route(
    passed_key="worldview_consistency_passed",
    next_node="human",
    max_auto_review_iterations=MAX_AUTO_REVIEW_ITERATIONS,
)


def human_node(state: WorldviewAgentState) -> WorldviewAgentState:
    """人工节点：等待批准、重写或中止，并记录反馈与修改模式。"""
    decision = state.get("decision")
    feedback = state.get("feedback", "")
    revision_mode = state.get("revision_mode") or "partial_rewrite"
    if not decision:
        user_input = interrupt({
            "agent": AGENT_NAME,
            "status": "waiting_human",
            "payload": state.get("pending_payload"),
            "review_errors": state.get("review_errors", []),
            "world_rule_review_errors": state.get("world_rule_review_errors", []),
            "worldview_consistency_errors": state.get("worldview_consistency_errors", []),
            "actions": ["approve", "request_changes", "reject"],
            "revision_modes": ["partial_rewrite", "content_rewrite", "full_rewrite"],
        })
        if isinstance(user_input, dict):
            decision = user_input.get("decision")
            feedback = user_input.get("feedback", "")
            revision_mode = user_input.get("revision_mode") or revision_mode
        else:
            decision = "approve" if str(user_input).lower() in {"approve", "批准", "ok", "yes"} else "request_changes"
            feedback = str(user_input)
    nodes = list(state.get("nodes") or [])
    nodes.append(_node("human", "completed", {"decision": decision, "feedback": feedback, "revision_mode": revision_mode}, {"received": True}))
    return {"decision": decision, "feedback": feedback, "revision_mode": revision_mode, "nodes": nodes}


def route_after_human(state: WorldviewAgentState) -> str:
    """人工节点路由：批准进入写库，要求修改进入修改内容节点，中止结束。"""
    if state.get("decision") == "approve":
        return "commit"
    if state.get("decision") == "reject":
        return "end"
    return "modify_content"


def commit_node(state: WorldviewAgentState) -> WorldviewAgentState:
    """写库节点：人工批准后真实创建或更新 MongoDB worldviews 集合。"""
    db = get_mongodb_db()
    action = state.get("action", "create")
    payload = dict(state.get("pending_payload") or {})
    if action == "create":
        worldview_id = payload.get("worldview_id") or f"wv_{uuid.uuid4().hex[:8]}"
        doc = {"worldview_id": worldview_id, "world_id": payload["world_id"], "name": payload["name"], "summary": payload.get("summary", "")}
        db["worldviews"].insert_one(doc)
        result = doc
    elif action == "update":
        target_id = payload["target_id"]
        update = {k: payload[k] for k in ("name", "summary") if k in payload}
        db["worldviews"].update_one({"worldview_id": target_id}, {"$set": update})
        result = {"worldview_id": target_id, **update}
    else:
        raise ValueError(f"{AGENT_NAME} does not handle delete operations")
    nodes = list(state.get("nodes") or [])
    nodes.append(_node("commit", "completed", {"payload": payload}, {"result": result}))
    return {"commit_result": result, "committed": True, "nodes": nodes, "current_node": "commit", "status": "completed"}


workflow = StateGraph(WorldviewAgentState)
workflow.add_node("input", input_node)
workflow.add_node("initial_expansion", initial_expansion_node)
workflow.add_node("world_rule_review", world_rule_review_node)
workflow.add_node("worldview_consistency_review", worldview_consistency_review_node)
workflow.add_node("human", human_node)
workflow.add_node("modify_content", modify_content_node)
workflow.add_node("commit", commit_node)
workflow.add_edge(START, "input")
workflow.add_edge("input", "initial_expansion")
workflow.add_edge("initial_expansion", "world_rule_review")
workflow.add_conditional_edges("world_rule_review", route_after_world_rule_review, {"worldview_consistency_review": "worldview_consistency_review", "modify_content": "modify_content", "human": "human"})
workflow.add_conditional_edges("worldview_consistency_review", route_after_worldview_consistency_review, {"modify_content": "modify_content", "human": "human"})
workflow.add_conditional_edges("human", route_after_human, {"modify_content": "modify_content", "commit": "commit", "end": END})
workflow.add_edge("modify_content", "world_rule_review")
workflow.add_edge("commit", END)

app = workflow.compile(checkpointer=MemorySaver())
