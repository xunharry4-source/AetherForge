"""
Writing Execution Agent (正文执行 Agent) - PGA 小说创作引擎核心组件

本模块负责根据大纲和世界观设定，生成具体的小说章节正文。
设计思路:
1. 场次拆解 (Scene Breaking): 将大纲中的单一章节进一步细化为一系列具体场次，实现更精准的节奏控制。
2. 逻辑快照 (Logic Snapshot): 
   - 每次编写场次前，自动检索相关设定（RAG）。
   - 编写完成后，生成“人物状态”和“场景环境”的逻辑快照，确保下一场次写作时设定不偏航。
3. 视觉引导: 自动生成视觉快照描述，帮助创作者通过画面感进行微调。
4. 闭环审计: 对生成的正文进行逻辑矛盾审计（如人物突然出现在不可能出现的地方）。
"""
import os
import json
import datetime
from typing import Annotated, TypedDict, List
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Command

# Import shared utilities
from lore_utils import (
    get_llm, 
    get_vector_store, 
    get_prohibited_rules, 
    get_worldview_context_by_category, 
    get_unified_context,
    get_grounded_context,
    format_grounded_context_for_prompt,
    parse_json_safely,
    get_entity_registry, 
    format_entity_registry_for_prompt,
    register_draft_entity, 
    get_category_template,
    get_db_path
)

# ==========================================
# 0. State Definition
# ==========================================
class WritingState(TypedDict):
    """
    正文执行 Agent 运行时的状态机上下文。
    """
    # 输入信息
    outline_id: str             # 已保存的大纲 ID
    outline_content: str        # 大纲全文内容 (用于参考)
    current_act: str            # 当前编写的小说章节/幕
    
    # 过程数据
    scene_list: List[dict]      # 拆解后的场次清单 [{'title': '...', 'description': '...'}]
    active_scene_index: int     # 当前正在写的场次索引
    context_data: str           # 从 ChromaDB/MongoDB 检索出的背景知识
    grounding_sources: List[dict] # 绑定的源素材索引
    
    # 输出数据
    draft_content: str          # 生成的正文初稿
    audit_feedback: str         # 审计意见/逻辑漏洞报告
    user_feedback: str          # 用户的人工意见
    is_audit_passed: bool       # 审计是否通过
    is_approved: bool           # 用户是否批准
    status_message: str         # 执行进度描述
    
    # 批量控制 (Batch Control)
    is_batch_mode: bool         # 是否处于全自动化批量模式
    retry_count: int            # 审计失败重试次数
    
    # 快照数据
    char_status_summary: str    # 人物逻辑快照 (位置、状态、动机)
    scene_status_summary: str   # 场景逻辑快照 (天气、物品毁损)
    visual_snapshot_path: str   # 视觉快照图片路径
    visual_description_summary: str # 视觉描述摘要

# ==========================================
# Nodes Implementation
# ==========================================

def plan_scenes_func(state: WritingState):
    """场次拆解节点 (Scene Planner)"""
    print(f"\n[DEBUG] plan_scenes_func entry. State keys: {list(state.keys())}")
    outline_content = state.get('outline_content', '')
    current_act = state.get('current_act', '')
    
    prompt = f"""你是一个专业的小说场次策划师。
你的任务是将大纲拆解为具体的“原子场次”。必须输出 JSON。

【大纲内容】
{outline_content}

【当前编写部分】
{current_act}

请输出 JSON：
{{
  "scene_list": [
    {{ "id": 1, "title": "标题", "description": "场次核心内容描述" }},
    ...
  ]
}}
"""
    res = get_llm(json_mode=True).invoke(prompt)
    data = parse_json_safely(res.content)
    if not data:
        return {"status_message": "❌ 场次拆解失败：JSON 解析异常"}
        
    scenes = data.get("scene_list", [])
    return {
        "scene_list": scenes,
        "active_scene_index": 0,
        "retry_count": 0,
        "status_message": f"📑 已成功将大纲拆解为 {len(scenes)} 个具体场次。准备进入首场创作..."
    }

def writing_retriever_node(state: WritingState):
    """正文 RAG 检索节点"""
    print(f"\n[DEBUG] writing_retriever_node entry.")
    val = state.get('active_scene_index')
    idx = int(val) if isinstance(val, (int, str)) else 0
    scene_list = state.get('scene_list') or []
    if idx >= len(scene_list):
        return {"status_message": "检索异常：索引越界"}
    
    scene = scene_list[idx]
    query = f"{str(scene.get('title') or '')} {str(scene.get('description') or '')}"
    
    # 执行 RAG 检索
    sources = get_grounded_context(query)
    grounded_context_str = format_grounded_context_for_prompt(sources)
    
    return {
        "context_data": grounded_context_str,
        "grounding_sources": sources,
        "status_message": f"🔍 正在从知识库为第 {idx+1} 场检索世界观素材并提取锚点 [S1-S{len(sources)}]..."
    }

def load_context_func(state: WritingState):
    """语境加载节点 - 融合分布式 SKILL 与 实体注册表"""
    print(f"\n[DEBUG] load_context_func entry.")
    
    # 1. 加载分布式 SKILL (高优控制)
    skills_context = ""
    try:
        with open('.gemini/skills/lore/ANCHORS.md', 'r', encoding='utf-8') as f:
            skills_context += f"\n【剧情锚点 (不可违背)】\n{f.read()}\n"
        with open('.gemini/skills/catalog/ACTIVE_WINDOW.md', 'r', encoding='utf-8') as f:
            skills_context += f"\n【活跃章节窗口 (当前目标)】\n{f.read()}\n"
    except Exception as e:
        skills_context = "\n[警告] 未能加载分布式 SKILL 约束。\n"

    # 2. 加载实体注册表 (A 层约束)
    entity_registry = get_entity_registry()
    entity_constraint = format_entity_registry_for_prompt(entity_registry)

    current_context = state.get('context_data', '')
    return {
        "context_data": f"{skills_context}\n{entity_constraint}\n{current_context}",
        "status_message": f"⚙️ 语境协议已对齐，正在根据锚定素材调用 LLM 生成文学正文..."
    }

def write_draft_func(state: WritingState):
    """正文生成节点"""
    print(f"\n[DEBUG] write_draft_func entry.")
    
    val = state.get('active_scene_index')
    idx = int(val) if isinstance(val, (int, str)) else 0
    
    scene_list = state.get('scene_list') or []
    if idx >= len(scene_list):
        return {"status_message": "正文生成失败：索引越界"}
        
    scene = scene_list[idx]
    user_feedback = str(state.get('user_feedback') or '')
    feedback_section = ""
    if user_feedback:
        feedback_section = f"\n【！！！当前核心修改需求！！！】\n要求：{user_feedback}\n"

    prompt = f"""你是一个创作专家。撰写具体的小说正文。

{feedback_section}

【大纲】{state.get('outline_content', '')}
【场次计划】{str(scene.get('title') or '')}: {str(scene.get('description') or '')}
【语境】{state.get('context_data', '')}

要求：文采斐然，落实修改建议。
直接输出正文。

【重要：素材锚定规则】
1. 当你描写涉及世界观背景、科技原理、历史事件或硬性设定时，必须在对应的描述末尾标注来源索引编号，例如：[S1], [S3]。
2. 不要为了标注而标注，只有在使用了提供的源素材（References）中的特定事实时才需要标注。
3. 文学性的描写、抒情、对话（非设定解释类）无需标注。
"""
    res = get_llm().invoke(prompt)
    retries_val = state.get("retry_count", 0)
    current_retries = int(retries_val) if isinstance(retries_val, (int, str)) else 0
    
    return {
        "draft_content": res.content,
        "user_feedback": "", # 清空已处理的反馈
        "retry_count": current_retries + 1,
        "status_message": f"🖋️ 第 {idx+1} 场文学正文已生成，正在执行逻辑矛盾与素材引用一致性审计..."
    }

def audit_logic_func(state: WritingState):
    """逻辑审计节点"""
    print(f"\n[DEBUG] audit_logic_func entry.")
    prohibited_items = get_prohibited_rules()
    
    val = state.get('active_scene_index')
    idx = int(val) if isinstance(val, (int, str)) else 0
    
    scene_list = state.get('scene_list') or []
    if idx >= len(scene_list):
        return {"is_audit_passed": False, "status_message": "审计信息缺失"}
        
    scene = scene_list[idx]
    worldview_rules = get_worldview_context_by_category(f"{str(scene.get('title') or '')} {str(scene.get('description') or '')}")
    char_status = state.get("char_status_summary", "无")
    
    prompt = f"""小说逻辑与素材锚定审计员。检查冲突与引用准确性。
禁令: {prohibited_items}

【提供的源素材】
{format_grounded_context_for_prompt(state.get('grounding_sources', []))}

官方规则: {worldview_rules}
上场快照: {char_status}

待审计正文:
{state.get('draft_content', '')}

【审计任务】
1. 检查正文是否违背了禁令或官方规则。
2. 核查正文中的 [SX] 引用是否与素材内容匹配。
3. 识别出正文中提及了特定设定 battle 且未标注引用、或标注了引用但素材中找不到对应事实的现象。

输出 JSON: {{"is_consistent": true/false, "audit_log": "...", "grounding_score": 0-100}}
"""
    res = get_llm(json_mode=True).invoke(prompt)
    data = parse_json_safely(res.content)
    is_ok = data.get("is_consistent", False) if data else False
    
    # 检测新实体
    entity_warning = ""
    try:
        registry = get_entity_registry()
        known_names = set()
        for names_list in registry.values():
            known_names.update(names_list)
        
        draft_content = str(state.get('draft_content') or '')
        extract_prompt = f"""从以下小说正文中提取所有专有名词实体（人物、势力、种族、科技、地点）。
只输出 JSON 数组：[{{"name": "实体名", "type": "character/faction/race/tech/location/other"}}]

正文：
{draft_content[:2000]}
"""
        ent_res = get_llm(json_mode=True).invoke(extract_prompt)
        extracted = parse_json_safely(ent_res.content)
        
        if isinstance(extracted, list):
            new_count = 0
            for ent in extracted:
                if not isinstance(ent, dict): continue
                name = str(ent.get('name') or '')
                if name and name not in known_names:
                    register_draft_entity(name, ent.get('type','other'), "正文中首次出现", "writing")
                    new_count += 1
            if new_count > 0:
                entity_warning = f" 同时发现 {new_count} 个未注册实体并已登记待审。"
    except Exception as e:
        print(f"[Entity Sentinel] 异常: {e}")
    
    return {
        "is_audit_passed": is_ok,
        "audit_feedback": data.get("audit_log", "解析异常") if data else "解析异常",
        "status_message": ("✅ 逻辑一致性审计通过。" if is_ok else "❌ 审计发现逻辑冲突，正在自动修正...") + entity_warning
    }

def human_review_node(state: WritingState):
    """人工核准节点"""
    print(f"\n[DEBUG] human_review_node entry.")
    draft = state.get('draft_content', '')
    user_input = interrupt({
        "status_message": "🧪 正文草案已就绪，请核准或提供修改建议。",
        "proposal": draft
    })
    print(f"[DEBUG] human_review_node: Resumed. Received feedback: '{user_input}'")
    return {"user_feedback": user_input, "is_approved": user_input == "批准"}

def prose_saver_func(state: WritingState):
    """存档节点"""
    print(f"\n[DEBUG] prose_saver_func entry.")
    
    val = state.get('active_scene_index')
    idx = int(val) if isinstance(val, (int, str)) else 0
    
    scene_list = state.get('scene_list') or []
    if idx >= len(scene_list):
        return {"status_message": "存档越界"}
        
    scene = scene_list[idx]
    record = {
        "id": f"prose_{state.get('outline_id', 'unknown')}_{idx}",
        "outline_id": state.get('outline_id', 'unknown'),
        "scene_title": scene.get('title', 'unknown'),
        "content": state.get('draft_content', ''),
        "timestamp": datetime.datetime.now().isoformat()
    }
    with open(get_db_path("prose_db.json"), 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        
    return {
        "active_scene_index": idx + 1,
        "is_approved": False, 
        "retry_count": 0,
        "status_message": f"💾 第 {idx+1} 场正文已成功归档至分布式存储，正在提取逻辑快照..."
    }

def snapshot_node_func(state: WritingState):
    """快照生成节点"""
    print(f"\n[DEBUG] snapshot_node_func entry.")
    val = state.get('active_scene_index')
    idx = (int(val) if isinstance(val, (int, str)) else 0) - 1 
    
    prompt = f"""提取快照及视觉描述。JSON。
正文: {state.get('draft_content', '')}
输出 JSON: {{"char_status": "...", "scene_status": "...", "visual_description": "..."}}
"""
    res = get_llm(json_mode=True).invoke(prompt)
    data = parse_json_safely(res.content)
    
    return {
        "char_status_summary": data.get("char_status", "正常") if data else "解析异常",
        "scene_status_summary": data.get("scene_status", "正常") if data else "解析异常",
        "visual_description_summary": data.get("visual_description", "") if data else "",
        "status_message": f"📸 逻辑快照 [场次 {idx+1}] 已生成，准备处理下一场次。"
    }

# ==========================================
# Graph Definition
# ==========================================
workflow = StateGraph(WritingState)

workflow.add_node("plan_scenes", plan_scenes_func)
workflow.add_node("writing_retriever", writing_retriever_node)
workflow.add_node("load_context", load_context_func)
workflow.add_node("write_draft", write_draft_func)
workflow.add_node("audit_logic", audit_logic_func)
workflow.add_node("human_review", human_review_node)
workflow.add_node("prose_saver", prose_saver_func)
workflow.add_node("snapshot_node", snapshot_node_func)

workflow.add_edge(START, "plan_scenes")
workflow.add_edge("plan_scenes", "writing_retriever")
workflow.add_edge("writing_retriever", "load_context")
workflow.add_edge("load_context", "write_draft")
workflow.add_edge("write_draft", "audit_logic")

def route_after_audit(state: WritingState):
    is_ok = state.get("is_audit_passed", False)
    is_batch = state.get("is_batch_mode", False)
    if is_ok:
        return "prose_saver" if is_batch else "human_review"
    retries = int(state.get("retry_count", 0))
    return "human_review" if retries > 3 else "write_draft"

workflow.add_conditional_edges("audit_logic", route_after_audit, {"human_review": "human_review", "prose_saver": "prose_saver", "write_draft": "write_draft"})

def route_after_human(state: WritingState):
    fb = str(state.get("user_feedback") or "").strip()
    if fb == "批准": return "prose_saver"
    if fb == "终止": return END
    return "write_draft" if fb else END

workflow.add_conditional_edges("human_review", route_after_human, {"prose_saver": "prose_saver", "write_draft": "write_draft", END: END})
workflow.add_edge("prose_saver", "snapshot_node")

def route_next_scene(state: WritingState):
    idx = int(state.get('active_scene_index', 0))
    total = len(state.get('scene_list', []))
    return "writing_retriever" if idx < total else END

workflow.add_conditional_edges("snapshot_node", route_next_scene, {"writing_retriever": "writing_retriever", END: END})

app = workflow.compile(checkpointer=MemorySaver())
