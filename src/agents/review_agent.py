import json
import logging
from typing import Dict, Any, Tuple, List

from langchain_core.messages import SystemMessage, HumanMessage
from src.common.llm_factory import get_llm
from src.common.lore_utils import get_unified_context, parse_json_safely

logger = logging.getLogger("novel_agent.review_agent")

def _get_context_for_review(entity_type: str, payload: Dict[str, Any]) -> str:
    """获取审核所需的上下文信息"""
    try:
        query = f"{payload.get('name', '')} {payload.get('title', '')} {payload.get('summary', '')} {payload.get('content', '')}"
        outline_id = payload.get("outline_id") or "default"
        worldview_id = payload.get("worldview_id") or "default_wv"
        
        # 只在有具体内容时进行检索，且如果报错则静默失败，避免阻塞审核
        if len(query.strip()) > 5:
            return get_unified_context(query, outline_id=outline_id, worldview_id=worldview_id)
    except Exception as e:
        logger.warning(f"Failed to get context for review: {e}")
    return "未能获取到有效的背景上下文设定。"


def _get_world_policy_context(db, entity_type: str, payload: Dict[str, Any]) -> str:
    """读取世界根实体中的禁止规则与基本设定，供审查节点强制校验。"""
    world_id = payload.get("world_id")
    target_id = payload.get("target_id")
    novel_id = payload.get("novel_id")
    outline_id = payload.get("outline_id")
    inline_forbidden = payload.get("forbidden_rules")
    inline_basic = payload.get("basic_settings")
    world_doc: Dict[str, Any] = {}
    if not world_id and novel_id and db is not None:
        try:
            source_doc = db["novels"].find_one({"novel_id": novel_id}) or {}
            world_id = source_doc.get("world_id")
        except Exception as e:
            logger.warning(f"Failed to resolve world_id from novel for review: {e}")
    if not world_id and outline_id and db is not None:
        try:
            source_doc = db["outlines"].find_one({"outline_id": outline_id}) or db["outlines"].find_one({"id": outline_id}) or {}
            world_id = source_doc.get("world_id")
        except Exception as e:
            logger.warning(f"Failed to resolve world_id from outline for review: {e}")
    if not world_id and target_id and db is not None:
        try:
            if entity_type.startswith("worldview"):
                source_doc = db["worldviews"].find_one({"worldview_id": target_id}) or {}
                world_id = source_doc.get("world_id")
            elif entity_type.startswith("novel"):
                source_doc = db["novels"].find_one({"novel_id": target_id}) or {}
                world_id = source_doc.get("world_id")
            elif entity_type.startswith("outline"):
                source_doc = db["outlines"].find_one({"outline_id": target_id}) or db["outlines"].find_one({"id": target_id}) or {}
                world_id = source_doc.get("world_id")
            elif entity_type.startswith("chapter"):
                source_doc = db["prose"].find_one({"id": target_id}) or db["prose"].find_one({"scene_id": target_id}) or {}
                world_id = source_doc.get("world_id")
        except Exception as e:
            logger.warning(f"Failed to resolve world_id for review: {e}")
    if world_id and db is not None:
        try:
            world_doc = db["worlds"].find_one({"world_id": world_id}) or {}
        except Exception as e:
            logger.warning(f"Failed to load world policy for review: {e}")

    forbidden_rules = world_doc.get("forbidden_rules", inline_forbidden)
    basic_settings = world_doc.get("basic_settings", inline_basic)
    return (
        "【世界禁止规则】\n"
        f"{json.dumps(forbidden_rules or [], ensure_ascii=False, indent=2)}\n\n"
        "【世界基本设定】\n"
        f"{json.dumps(basic_settings or {}, ensure_ascii=False, indent=2)}"
    )


def _get_novel_policy_context(db, entity_type: str, payload: Dict[str, Any]) -> str:
    """读取小说项目中的禁止规则与基本设定，供大纲和章节审查强制校验。"""
    novel_id = payload.get("novel_id")
    target_id = payload.get("target_id")
    outline_id = payload.get("outline_id")
    inline_forbidden = payload.get("novel_forbidden_rules") or payload.get("forbidden_rules")
    inline_basic = payload.get("novel_basic_settings") or payload.get("basic_settings")
    novel_doc: Dict[str, Any] = {}
    if not novel_id and db is not None:
        try:
            if entity_type.startswith("outline") and target_id:
                source_doc = db["outlines"].find_one({"outline_id": target_id}) or {}
                novel_id = source_doc.get("novel_id")
            elif entity_type.startswith("chapter") and outline_id:
                source_doc = db["outlines"].find_one({"outline_id": outline_id}) or {}
                novel_id = source_doc.get("novel_id")
            elif entity_type.startswith("chapter") and target_id:
                source_doc = db["prose"].find_one({"id": target_id}) or {}
                novel_id = source_doc.get("novel_id")
        except Exception as e:
            logger.warning(f"Failed to resolve novel_id for review: {e}")
    if novel_id and db is not None:
        try:
            novel_doc = db["novels"].find_one({"novel_id": novel_id}) or {}
        except Exception as e:
            logger.warning(f"Failed to load novel policy for review: {e}")

    forbidden_rules = novel_doc.get("forbidden_rules", inline_forbidden)
    basic_settings = novel_doc.get("basic_settings", inline_basic)
    return (
        "【小说禁止规则】\n"
        f"{json.dumps(forbidden_rules or [], ensure_ascii=False, indent=2)}\n\n"
        "【小说基本设定】\n"
        f"{json.dumps(basic_settings or {}, ensure_ascii=False, indent=2)}"
    )


def _get_outline_policy_context(db, entity_type: str, payload: Dict[str, Any]) -> str:
    """读取父级大纲内容，供章节大纲审查节点强制校验。"""
    outline_id = payload.get("outline_id")
    target_id = payload.get("target_id")
    outline_doc: Dict[str, Any] = {}
    if not outline_id and entity_type.startswith("chapter") and target_id and db is not None:
        try:
            prose_doc = db["prose"].find_one({"id": target_id}) or db["prose"].find_one({"scene_id": target_id}) or {}
            outline_id = prose_doc.get("outline_id")
        except Exception as e:
            logger.warning(f"Failed to resolve outline_id for review: {e}")
    if outline_id and db is not None:
        try:
            outline_doc = db["outlines"].find_one({"outline_id": outline_id}) or db["outlines"].find_one({"id": outline_id}) or {}
        except Exception as e:
            logger.warning(f"Failed to load outline policy for review: {e}")

    return (
        "【父级大纲】\n"
        f"{json.dumps({k: outline_doc.get(k) for k in ('outline_id', 'id', 'name', 'title', 'summary', 'content') if outline_doc.get(k) is not None}, ensure_ascii=False, indent=2)}"
    )


def _get_previous_chapter_context(db, entity_type: str, payload: Dict[str, Any]) -> str:
    """读取当前章节之前已入库章节，供章节一致性审查强制校验。"""
    if not entity_type.startswith("chapter") or db is None:
        return "非章节审查，不需要读取前置章节。"

    inline_previous = payload.get("previous_chapters") or payload.get("previous_chapter_context")
    if inline_previous:
        return "【用户提供的前置章节上下文】\n" + json.dumps(inline_previous, ensure_ascii=False, indent=2)

    outline_id = payload.get("outline_id")
    novel_id = payload.get("novel_id")
    world_id = payload.get("world_id")
    target_ids = {
        str(value)
        for value in (
            payload.get("target_id"),
            payload.get("chapter_id"),
            payload.get("id"),
            payload.get("scene_id"),
            payload.get("prose_id"),
        )
        if value
    }

    query: Dict[str, Any] = {}
    if outline_id:
        query["outline_id"] = outline_id
    elif novel_id:
        query["novel_id"] = novel_id
    elif world_id:
        query["world_id"] = world_id
    else:
        return "当前 payload 缺少 outline_id/novel_id/world_id，无法可靠读取前置章节。"

    try:
        cursor = (
            db["prose"]
            .find(query)
            .sort([("chapter_index", 1), ("order", 1), ("sequence", 1), ("created_at", 1), ("timestamp", 1)])
            .limit(12)
        )
        chapters = []
        for doc in cursor:
            doc_ids = {str(doc.get(key)) for key in ("id", "scene_id", "prose_id", "chapter_id") if doc.get(key)}
            if target_ids and target_ids.intersection(doc_ids):
                continue
            chapters.append({
                "id": doc.get("id") or doc.get("scene_id") or doc.get("prose_id") or doc.get("chapter_id"),
                "title": doc.get("title") or doc.get("name"),
                "chapter_index": doc.get("chapter_index") or doc.get("order") or doc.get("sequence"),
                "outline_id": doc.get("outline_id"),
                "content": str(doc.get("content") or "")[:3000],
            })
        if not chapters:
            return "未检索到同一 outline/novel/world 下已入库的前置章节；若这是第一章，可通过审查。"
        return "【前置章节内容】\n" + json.dumps(chapters, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Failed to load previous chapters for review: {e}")
        return f"读取前置章节失败：{e}"


def get_review_prompt(entity_type: str) -> str:
    """根据实体类型返回专门的系统提示词"""
    base_prompt = (
        "你是一个极其严格的小说设定审查专家（Review Agent）。\n"
        "你的任务是审查输入的 JSON 业务内容，找出其中可能存在的逻辑漏洞、设定冲突（反吃设定）和规范问题。\n"
        "审查结束后，你必须返回一个合法的 JSON，格式如下：\n"
        "{\n"
        '  "passed": true 或 false,\n'
        '  "errors": ["错误描述1", "错误建议2"] // 如果 passed 为 true，可返回空数组\n'
        "}\n\n"
    )

    if entity_type == "worldview_world_rules":
        base_prompt += (
            "【Worldview World Rules Review (世界观-世界规则审查) 审查重点】\n"
            "1. 必须逐条检查当前世界观是否违反所属世界的 forbidden_rules（世界禁止规则）。\n"
            "2. 必须检查当前世界观是否破坏 basic_settings（世界基本设定），包括时代、力量体系、地理边界、组织结构、资源机制和基础禁令。\n"
            "3. 只判断世界根规则冲突；如果违反禁止规则或基本设定，passed 必须为 false，并指出具体冲突字段与修改方向。\n"
        )
    elif entity_type == "worldview_consistency":
        base_prompt += (
            "【Worldview Consistency Review (世界观-既有设定一致性审查) 审查重点】\n"
            "1. 检查新增或修改后的世界观条目是否与同一 world_id 下已有世界观设定冲突。\n"
            "2. 重点审查历史、地理、规则、势力、人物常识、资源机制和前后 Canon 是否自洽。\n"
            "3. 若与已存在世界观设定冲突，passed 必须为 false，并说明冲突对象、冲突原因和修正建议。\n"
        )
    elif entity_type == "novel_world_rules":
        base_prompt += (
            "【Novel World Rules Review (小说-世界规则审查) 审查重点】\n"
            "1. 必须检查小说项目是否违反所属世界 forbidden_rules（世界禁止规则）。\n"
            "2. 必须检查小说项目是否偏离 basic_settings（世界基本设定），包括时代背景、力量体系、世界边界、资源约束和基础禁令。\n"
            "3. 必须检查小说自身 forbidden_rules 与 basic_settings 是否自洽，且不能与父级世界规则冲突。\n"
            "4. 如关联 worldview_id，还要检查小说设定是否与该世界观约束矛盾。\n"
            "5. 发现反吃设定、绕开禁令、破坏基本设定时，passed 必须为 false。\n"
        )
    elif entity_type == "outline_world_rules":
        base_prompt += (
            "【Outline World Review (大纲-世界审查) 审查重点】\n"
            "1. 必须检查大纲是否违反所属世界 forbidden_rules（世界禁止规则）。\n"
            "2. 必须检查大纲是否偏离所属世界 basic_settings（世界基本设定），包括时代、力量体系、地理边界、组织结构、资源机制和基础禁令。\n"
            "3. 发现大纲绕开世界禁令、改变世界底层规则、引入不属于该世界的能力或资源时，passed 必须为 false。\n"
        )
    elif entity_type == "outline_worldview_rules":
        base_prompt += (
            "【Outline Worldview Review (大纲-世界观审查) 审查重点】\n"
            "1. 必须检查大纲是否违反关联 worldview_id 的世界观设定。\n"
            "2. 必须检查大纲是否与同一 world_id 下已有 Canon 设定冲突，包括历史、地理、规则、势力、人物常识和资源机制。\n"
            "3. 发现大纲误用 Lore、改写已有世界观规则或制造 Canon 前后矛盾时，passed 必须为 false。\n"
        )
    elif entity_type == "outline_novel_rules":
        base_prompt += (
            "【Outline Novel Review (大纲-小说审查) 审查重点】\n"
            "1. 必须检查大纲是否违反所属小说 forbidden_rules（小说禁止规则）。\n"
            "2. 必须检查大纲是否偏离所属小说 basic_settings（小说基本设定），包括主角底线、主线冲突、叙事基调、时间线、人物关系规则和剧情约束。\n"
            "3. 必须检查剧情推进、冲突升级、高潮安排是否服务于小说主线，不能喧宾夺主或重写小说核心方向。\n"
            "4. 发现大纲偏离小说主旨、破坏主角设定、违背时间线或人物关系规则时，passed 必须为 false。\n"
        )
    elif entity_type == "chapter_world_rules":
        base_prompt += (
            "【Chapter World Review (章节-世界审查) 审查重点】\n"
            "1. 必须检查章节正文是否违反所属世界 forbidden_rules（世界禁止规则）。\n"
            "2. 必须检查章节正文是否偏离所属世界 basic_settings（世界基本设定），包括时代、力量体系、地理边界、组织结构、资源机制和基础禁令。\n"
            "3. 发现正文绕开世界禁令、改变世界底层规则、引入不属于该世界的能力或资源时，passed 必须为 false。\n"
        )
    elif entity_type == "chapter_worldview_rules":
        base_prompt += (
            "【Chapter Worldview Review (章节-世界观审查) 审查重点】\n"
            "1. 必须检查章节正文是否违反关联 worldview_id 的世界观设定。\n"
            "2. 必须检查章节正文是否与同一 world_id 下已有 Canon 设定冲突，包括历史、地理、规则、势力、人物常识和资源机制。\n"
            "3. 发现正文误用 Lore、改写已有世界观规则或制造 Canon 前后矛盾时，passed 必须为 false。\n"
        )
    elif entity_type == "chapter_novel_rules":
        base_prompt += (
            "【Chapter Novel Review (章节-小说审查) 审查重点】\n"
            "1. 必须检查章节正文是否违反所属小说 forbidden_rules（小说禁止规则）。\n"
            "2. 必须检查章节正文是否偏离所属小说 basic_settings（小说基本设定），包括主角底线、主线冲突、叙事基调、时间线、人物关系规则和剧情约束。\n"
            "3. 必须检查人物行为、对话、动机是否符合小说主线与角色状态，不能破坏小说核心方向。\n"
            "4. 发现正文偏离小说主旨、破坏主角设定、违背时间线或人物关系规则时，passed 必须为 false。\n"
        )
    elif entity_type == "chapter_outline_rules":
        base_prompt += (
            "【Chapter Outline Review (章节-大纲审查) 审查重点】\n"
            "1. 必须检查章节正文是否严格执行父级 outline_id 对应大纲的剧情任务。\n"
            "2. 必须检查正文是否擅自删除、提前、延后或改写大纲安排的关键事件、转折、冲突升级和结尾任务。\n"
            "3. 必须检查章节收尾是否服务于父级大纲节点，不能自行扩展到未批准的大纲之外。\n"
            "4. 发现正文偏离大纲、删改大纲目标或越权推进后续剧情时，passed 必须为 false。\n"
        )
    elif entity_type == "chapter_consistency":
        base_prompt += (
            "【Chapter Consistency Review (章节-前文一致性审查) 审查重点】\n"
            "1. 必须检查当前章节与此前已入库章节在剧情承接、时间线、地点变化、人物状态、人物关系、伤势/装备/资源和伏笔回收上是否一致。\n"
            "2. 必须检查是否出现前一章结尾尚未解决、当前章却跳过解释的断裂；是否出现人物突然知道未知信息、道具凭空出现、情绪状态无过渡改变。\n"
            "3. 必须检查叙事视角、语气、章节标题和正文内容是否延续同一作品的连续性。\n"
            "4. 如果当前章节是第一章或没有可用前置章节，可通过审查，但必须只基于当前 payload 判断是否自洽。\n"
            "5. 发现与前置章节冲突或承接断裂时，passed 必须为 false，并指出冲突章节、冲突点和修正方向。\n"
        )
    elif entity_type == "worldview":
        base_prompt += (
            "【Worldview (世界观) 审查重点】\n"
            "1. 内容格式是否规范：名称与摘要/详情是否匹配。\n"
            "2. 逻辑漏洞：设定的内部机制能否自洽（例如说‘人人平等’但又设定了‘天生贵族’）。\n"
            "3. 设定冲突：新增设定是否与背景上下文中已有核心设定（历史、地理、规则等）存在直接矛盾。\n"
        )
    elif entity_type == "novel":
        base_prompt += (
            "【Novel (小说项目) 审查重点】\n"
            "1. 故事背景是否契合世界观约束：不能出现超出该世界当前科技/魔法水平的事物。\n"
            "2. 主角设定与核心主线是否符合逻辑：动机是否明确，故事目标是否清晰。\n"
            "3. 是否存在破坏世界基础规则的设定（反吃设定）。\n"
        )
    elif entity_type == "outline":
        base_prompt += (
            "【Outline (大纲节点) 审查重点】\n"
            "1. 上下文节点剧情逻辑是否连贯：没有突兀的转折或未交代的跳跃。\n"
            "2. 故事发展是否偏离小说主旨：支线是否喧宾夺主。\n"
            "3. 核心冲突与高潮安排是否合理。\n"
            "4. 是否违反小说禁止规则与小说基本设定，包括主角底线、主线冲突、叙事基调、时间线和人物关系规则。\n"
            "5. 设定冲突：是否出现与前面剧情或已有世界观设定矛盾的情节。\n"
        )
    elif entity_type == "chapter":
        base_prompt += (
            "【Chapter (正文章节) 审查重点】\n"
            "1. 人物行为动机与对话是否符合已有的人设模板（OOC检查）。\n"
            "2. 场景与道具描写是否符合世界观物理法则。\n"
            "3. 剧情推进与章节收尾是否严格遵循大纲约束，不能自行删改大纲布置的任务。\n"
            "4. 是否违反小说禁止规则与小说基本设定，包括主角底线、主线冲突、叙事基调、时间线和人物关系规则。\n"
            "5. 文字风格与视角是否存在突兀变化。\n"
        )
    else:
        base_prompt += "【综合审查】请检查逻辑连贯性和设定冲突。"

    return base_prompt

def execute_llm_review(db, entity_type: str, payload: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    调用大模型对 payload 进行深度逻辑与设定审查。
    
    Returns:
        (passed: bool, errors: list[str])
    """
    logger.info(f"Executing LLM review for {entity_type}")
    
    try:
        # 获取上下文设定
        context_text = _get_context_for_review(entity_type, payload)
        world_policy_context = _get_world_policy_context(db, entity_type, payload)
        novel_policy_context = _get_novel_policy_context(db, entity_type, payload)
        outline_policy_context = _get_outline_policy_context(db, entity_type, payload)
        previous_chapter_context = _get_previous_chapter_context(db, entity_type, payload)
        
        # 构建消息
        system_prompt = get_review_prompt(entity_type)
        user_message = (
            f"以下是世界禁止规则与基本设定（必须优先遵守）：\n{world_policy_context}\n\n"
            f"以下是小说禁止规则与基本设定（大纲和章节必须遵守）：\n{novel_policy_context}\n\n"
            f"以下是父级大纲约束（章节必须遵守）：\n{outline_policy_context}\n\n"
            f"以下是前置章节上下文（章节一致性审查必须遵守）：\n{previous_chapter_context}\n\n"
            f"以下是世界观和背景设定参考（如果有）：\n{context_text}\n\n"
            f"以下是需要你审查的当前 {entity_type} 业务内容（JSON格式）：\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
            "请严格按照要求审查，并仅输出符合要求的 JSON 格式结果。"
        )

        llm = get_llm(json_mode=True, agent_name=f"{entity_type}_review_agent")
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message)
        ]
        
        response = llm.invoke(messages)
        content = response.content
        logger.debug(f"Review Agent Raw Response: {content}")
        
        result = parse_json_safely(content)
        if isinstance(result, dict) and "passed" in result:
            passed = bool(result.get("passed", False))
            errors = result.get("errors", [])
            if not isinstance(errors, list):
                errors = [str(errors)]
            
            # 如果判定为 failed 但没有给理由，强制补充
            if not passed and not errors:
                errors = ["LLM 审查未通过，但未提供具体原因。"]
                
            return passed, errors
        else:
            logger.warning(f"Review Agent returned malformed JSON: {content}")
            return False, ["审查模型返回了无效的格式，无法解析判定结果。"]
            
    except Exception as e:
        logger.error(f"Error in execute_llm_review for {entity_type}: {e}", exc_info=True)
        return False, [f"执行大模型审查时发生异常: {str(e)}"]
