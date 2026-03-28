"""
Worldview Agent (世界观 Agent) - PGA 0-4 协议小说创作引擎核心组件

本模块实现了基于 LangGraph 的世界观管理工作流。它采用 "生成-审计-人工确认-同步" 的闭环模式，
确保创意产出符合“万象星际”底层物理规则（PGA 0-4 架构）。

设计思路 (Design Philosophy):
1. 0-4 逻辑架构: 强制将设定拆分为 定义(0)、入场(1)、冲突(2)、优先级(3) 和 独立性(4) 五个维度。
2. 逻辑隔离: 严禁不同类别的设定（如物理机制与地缘政治）在同一节点中混淆。
3. 人机协作 (Human-in-the-loop): 使用 LangGraph 的 interrupt 机制，在核心设定入库前强制人工审核。
4. RAG 驱动: 每次生成都会从 MongoDB (全文) 和 ChromaDB (向量) 检索相关上下文。
"""
import os
import json
import datetime
from typing import Annotated, TypedDict, List, Union
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Command

# Import shared utilities
from lore_utils import (
    get_llm, 
    get_vector_store, 
    get_prohibited_rules, 
    get_worldview_context_by_category, 
    get_unified_context,
    get_category_template,
    upsert_category_template,
    parse_json_safely,
    get_category_template,
    upsert_category_template,
    parse_json_safely,
    get_evolution_rules,
    get_db_path,
    dispatch_log
)

# ==========================================
# 0. State Definition
# ==========================================
class AgentState(TypedDict):
    """
    Agent 运行时的状态机上下文。
    
    Attributes:
        query: 用户的原始输入请求。
        context: 检索到的相关背景知识。
        proposal: Agent 生成的当前草案/提案（通常为 JSON 格式）。
        review_log: 审计节点生成的逻辑一致性报告。
        user_feedback: 用户在中断节点输入的反馈或指令。
        iterations: 当前任务经历的生成迭代次数。
        audit_count: 当前草案经历的自审修正次数。
        is_approved: 标记当前提案是否已被审计通过或人类批准。
        category: 识别出的设定分类（如 race, faction 等）。
        doc_id: 关联的文档 ID。
        status_message: 用于 UI 显示的实时状态描述。
    """
    query: str
    worldview_id: str      # 所属世界观 ID
    outline_id: Optional[str] # 关联的大纲/小说 ID (可选)
    context: str
    proposal: str
    review_log: str
    user_feedback: str
    iterations: int        # 总生成次数
    audit_count: int       # 当前自审重试次数
    category: str 
    doc_id: str
    scratchpad: List[str]  # Autoresearch 草稿本，用于内部推演
    defense_log: str       # 防御节点产生的错误信息
    research_confidence: float # 当前设定的内部自信度 (0.0 - 1.0)
    extracted_facts: str   # 研究所得的关键推演事实
    llm_interactions: dict  # [诊断] 存储各节点的 LLM 入参与原始出参

# ==========================================
# 0-4 Architecture & Category Specific Logic
# ==========================================
PGA_0_4_ARCHITECTURE = """
[0. Definitions] PGA protocols, star sector ecological niches, thermodynamics-based lore.
[1. Entry Logic] New elements must pass 'Entry Validation' (fit for star sector ecology).
[2. Conflict Logic] Modifications must resolve contradictions with primary lore (Thermodynamics).
[3. Priority Check] Rule Hierarchy (Thermodynamics > PGA Protocol > Regional Lore).
[4. Independence] Multi-dataset updates (Race, Faction, Mechanism) must remain modular.
"""

CATEGORY_LOGIC_TEMPLATES = {
    "race": {
        "title": "种族逻辑 (Races)",
        "logic": """
        1. 生物/机械结构：必须描述能量摄取方式、转化为熵的效率、以及抗熵变异特征。
        2. 生态位：在所属星区的物理环境下（如高引力、强辐射）的生存地位。
        3. 进化导向：对热力学第二定律的屈服或“局部逆熵”补偿机制。
        4. 隔离原则：严禁描述政治关系或国家边界，专注于生命体本身的演化与物理特性。
        """
    },
    "faction": {
        "title": "势力逻辑 (Factions)",
        "logic": """
        1. 政治与主权：组织架构、核心纲领（如何理解PGA协议）、星区势力范围（Territory）。
        2. 资源控制：对恒星能、零点能或特定星矿的配额管理与分配方式。
        3. 外交与冲突：与其他势力的条约约束力、利益纠葛、以及在星际政治中的生态位。
        4. 隔离原则：严禁描述物种演化或生理结构，专注于组织行为、权力结构与地缘政治。
        """
    },
    "geography": {
        "title": "地理逻辑 (Geographies)",
        "logic": """
        1. 物理环境：天体运行规律、重力梯度、辐射能级、空间曲率异常。
        2. 局部熵场：划分热力学有序区（低熵区）与混沌区（高熵区）的物理分布。
        3. 承载力：该区域能支持的最大能量级别 or 文明载荷量。
        4. 隔离原则：严禁描述居民的政治斗争，专注于空间本身的物理参数。
        """
    },
    "mechanism_tech": {
        "title": "机制/科技逻辑 (Mechanisms & Tech)",
        "logic": """
        1. 物理实现：技术如何通过控制局部熵增来实现功能（严禁违反能量守恒）。
        2. 协议合规：确认科技是否触及了PGA协议禁止的“时间操纵”等红线技术。
        3. 热机效率：该技术在热力学系统中的能量转化率与废热处理机制。
        4. 隔离原则：专注于技术底层逻辑，而非使用该技术的政治组织。
        """
    },
    "history": {
        "title": "历史逻辑 (History)",
        "logic": """
        1. 线性一致性：按时间轴顺序确定的因果链条，严禁出现时间旅行 or 溯因性修改.
        2. 熵增叙事：重大事件如何导致星区能量分布的彻底改变。
        3. 记录差异：不同势力对同一事件的不同热力学记录。
        4. 隔离原则：专注于事件的宏观影响，而非单一实体的设定细节。
        """
    }
}

# ==========================================
# Nodes Implementation
# ==========================================

import pydantic
from typing import Optional

class ResearchReflectionSchema(pydantic.BaseModel):
    confidence_score: float = pydantic.Field(description="对当前信息掌握程度的自信度 (0.0 到 1.0)")
    reflection_notes: str = pydantic.Field(description="本轮反思的思考过程与后续还需要推演的疑问点")
    extracted_facts: str = pydantic.Field(description="截至目前推演出的所有确定性关键事实结论")

def autoresearch_node(state: AgentState, config: dict):
    """
    自主研究循环节点 (Autoresearch Core)。
    职责：
    1. 不直接生成设定，而是进行深度推演和假设。
    2. 判断当前背景信息是否足以构建一个无懈可击的 PGA 设定。
    3. 将推演轨迹写入 scratchpad，将确定的事实写入 extracted_facts。
    """
    dispatch_log(config, "启动 Autoresearch 深度推演引擎...")
    print(f"\n[DEBUG] autoresearch_node entry. State keys: {list(state.keys())}")
    query = state.get('query', '')
    worldview_id = state.get('worldview_id', 'default_wv')
    rag_context = get_unified_context(query, worldview_id=worldview_id)
    prohibited_items = get_prohibited_rules()
    
    current_scratchpad = state.get('scratchpad', [])
    past_reflections = "\n".join(current_scratchpad) if current_scratchpad else "这是第一次推演。"
    
    prompt = f"""你是一个运行在后台的“隐形研究引擎 (Autoresearch)”。
你的任务是根据用户需求，在脑内进行多轮推理、反思和纠错，而不是立刻给出最终答案。
请遵循 PGA 世界观的【底层原则】：热力学第二定律和能量守恒。

【用户需求】：{query}
【现有文献知识库】：{rag_context}
【绝对禁令】：{prohibited_items}

【系统跨次元进化记忆 (极为重要)】：
此记忆包含了你甚至其他 Agent 过去犯下的致命错误与总结出的防腐规则。你必须绝对遵守，不要重蹈覆辙！
{get_evolution_rules()}

【过去的思考轨迹 (Scratchpad)】：
{past_reflections}

TASK:
基于过去的思考轨迹和现有文献，请进一步推演这个设定的合理性。
如果还有逻辑漏洞（例如：能量来源不明，违反禁令），请在 reflection_notes 中指出，并给出一个较低的 confidence_score（如 0.4）。
如果逻辑已经完美闭环，请总结所有确定的硬核设定放入 extracted_facts，赋予 confidence_score > 0.9。

必须输出为 JSON，匹配以下 Schema：
{{"confidence_score": float, "reflection_notes": "...", "extracted_facts": "..."}}
"""
    res = get_llm(json_mode=True, agent_name="worldview").invoke(prompt)
    dispatch_log(config, f"Autoresearch 完成一轮推演，置信度评价中...")
    try:
        data = parse_json_safely(res.content)
        validated = ResearchReflectionSchema(**data)
        
        new_scratchpad = current_scratchpad + [f"推演结论 (Confidence: {validated.confidence_score}): {validated.reflection_notes}"]
        
        return {
            "research_confidence": validated.confidence_score,
            "extracted_facts": validated.extracted_facts,
            "scratchpad": new_scratchpad[-5:], # 仅保留最近5轮思考避免上下文爆炸
            "status_message": f"🧠 Autoresearch 深度推演中 (置信度: {validated.confidence_score})... 正在搜根据逻辑边界推演底层事实。",
            "llm_interactions": {
                "autoresearch": {
                    "prompt": prompt,
                    "raw_output": res.content
                }
            }
        }

    except Exception as e:
        print(f"[Autoresearch] 解析失败: {e}")
        return {
            "research_confidence": 0.5,
            "scratchpad": current_scratchpad + ["推演遇到格式异常，进行快速妥协。"],
            "status_message": "Autoresearch 遭遇解析乱流，强制推进。"
        }

def generator_node(state: AgentState, config: dict):
    """
    生成节点 (Proposal Generator)。
    责任:
    1. 分类识别: 根据用户 query 自动判定所属世界观维度 (race, faction, etc.)。
    2. 上下文组装: 调用 RAG 检索文献库 (MongoDB) 和向量库 (ChromaDB) 中的相关冲突/背景。
    3. 模板注入: 获取对应分类的 JSON 模板，确保输出格式合规。
    4. 创作生成: 调用 LLM 生成符合 PGA 0-4 逻辑的设定提案。
    """
    dispatch_log(config, "正在识别设定分类并加载 RAG 上下文...")
    print(f"\n[DEBUG] generator_node entry. State keys: {list(state.keys())}")
    query = state.get('query', '')
    if not query:
        print("[WARNING] 'query' is missing in state at generator_node! Using empty string.")
        
    query_lower = query.lower()
    category = state.get('category', 'general')
    if not category or category == "general":
        # 如果尚未分类，执行关键词分类
        if any(k in query_lower for k in ["势力", "阵营", "国家", "派系", "帝国", "联邦", "军团", "公约", "盟友"]):
            category = "faction"
        elif any(k in query_lower for k in ["种族", "机器人", "机械族", "生命", "进化", "族群", "演化", "物种"]):
            category = "race"
        elif any(k in query_lower for k in ["宗教", "信仰", "教会", "神说", "崇拜"]):
            category = "religion"
        elif any(k in query_lower for k in ["地理", "地形", "环境", "星域", "坐标"]):
            category = "geography"
        elif any(k in query_lower for k in ["星球", "行星", "恒星"]):
            category = "planet"
        elif any(k in query_lower for k in ["危机", "灾难", "变故", "事故"]):
            category = "crisis"
        elif any(k in query_lower for k in ["武器", "装备", "战机", "母舰"]):
            category = "weapon"
        elif any(k in query_lower for k in ["生物", "野兽", "怪物", "掠食者"]):
            category = "creature"
        elif any(k in query_lower for k in ["组织", "协会", "学术", "联盟", "公司"]):
            category = "organization"
        elif any(k in query_lower for k in ["机制", "科技", "武器", "引擎", "原理", "技术", "装置", "协议", "热力学", "物理", "发动机", "驱动"]):
            category = "mechanism_tech"
        elif any(k in query_lower for k in ["历史", "纪元", "事件", "变迁", "战争", "编年史", "记录"]):
            category = "history"
        else:
            category = "general"

    category_info = CATEGORY_LOGIC_TEMPLATES.get(category, {"title": "一般世界观", "logic": "遵循PGA底层物理与逻辑。"})
    
    # 2. 获取分类模板 (MongoDB/Local Fallback)
    template_data = get_category_template(category)
    if not template_data and category != "general":
        # 如果模板不存在，先生成一个
        meta_prompt = f"你是一个世界观架构师。请为【{category}】这个分类创建一个标准的 JSON 模板和参考例子。必须输出合法有效 JSON。"
        meta_res = get_llm(json_mode=True, agent_name="worldview").invoke(meta_prompt)
        try:
            template_data = parse_json_safely(meta_res.content)
            if template_data:
                upsert_category_template(category, template_data)
        except Exception:
            template_data = {"template": "基础文本描述", "example": "无"}

    # 3. 获取上下文 (Namespaced)
    worldview_id = state.get('worldview_id', 'default_wv')
    rag_context = get_unified_context(query, worldview_id=worldview_id)
    prohibited_items = get_prohibited_rules()
    worldview_rules = get_worldview_context_by_category(query, worldview_id=worldview_id)
    
    template_str = json.dumps(template_data.get("template", {}), ensure_ascii=False, indent=2) if template_data else "自由发挥"
    example_str = json.dumps(template_data.get("example", {}), ensure_ascii=False, indent=2) if template_data else "无"

    feedback_section = ""
    user_feedback = state.get('user_feedback', '')
    if user_feedback:
        feedback_section = f"""
【！！！当前核心修改需求 - 必须首先满足！！！】
用户提出以下问题或要求：
>>> {user_feedback} <<<
你必须在本次生成中优先解决上述反馈。
"""

    full_prompt = f"""你是一个专精于“万象星际协议体 (PGA)”世界观的资深创作专家。
你的任务是根据用户的查询扩展或修改世界观设定。

{feedback_section}

【当前逻辑分类：{category_info['title']}】
本类别必须严格遵守以下逻辑边界，绝不能越界：
{category_info['logic']}

【最高禁令 - 必须绝对遵循】
{prohibited_items}

【系统跨次元进化记忆 (血的教训) - 必须绝对遵循】
{get_evolution_rules()}

【官方核心规则】
{worldview_rules}
1. 热力学第二定律：熵增不可逆，能量转换必有损耗。
2. 能量守恒：任何现象必须有物理层面的能量输入。

【PGA 0-4 架构约束】
{PGA_0_4_ARCHITECTURE}

【输出格式要求：JSON】
你必须基于以下“分类模板”进行创作，并参考其“示例”。
分类模板:
{template_str}

参考示例:
{example_str}

【生成内容】
现有背景资料: {rag_context}
用户当前需求：{query}
(之前的审计逻辑建议: {state.get('review_log', '无')})

TASK: 请完成设定提案。必须输出为 JSON 格式。
"""
    
    res = get_llm(json_mode=True, agent_name="worldview").invoke(full_prompt)
    dispatch_log(config, "设定提案初稿已生成。")
    _iter_val = state.get('iterations', 0)
    curr_iterations = int(_iter_val) if isinstance(_iter_val, (int, str)) else 0
    
    # 将当前的思考过程推入草稿本
    current_scratchpad = state.get('scratchpad', [])
    current_scratchpad.append(f"Iteration {curr_iterations}: Generated proposal for {category}")
    
    return {
        "proposal": res.content, 
        "category": category,
        "iterations": curr_iterations + 1, 
        "scratchpad": current_scratchpad,
        "status_message": f"📝 [{category_info['title']}] 设定提案已生成，正在进入结构化防御层 (Defense) 审计...",
        "llm_interactions": {
            "generator": {
                "prompt": full_prompt,
                "raw_output": res.content
            }
        }
    }



import pydantic
from typing import Optional

class WorldviewDefenseSchema(pydantic.BaseModel):
    """用于 Cookbook 结构化防御的底层契约"""
    name: Optional[str] = pydantic.Field(default=None, description="实体的核心名称")
    content: str = pydantic.Field(..., description="设定的详细文本描述")
    
    class Config:
        extra = 'allow'  # 允许由动态模板引入的额外字段

def defense_node(state: AgentState, config: dict):
    """
    防线节点 (Cookbook Structured Defense Validator)。
    将由 generator 产出的非结构化或格式损坏的 JSON 进行强制拦截。
    如果遭遇 Pydantic 解析失败，或者检测到明显的幻觉格式，立刻抛弃并回炉。
    """
    dispatch_log(config, "正在执行结构化防御检查 (Cookbook Defense)...")
    print(f"\n[DEBUG] defense_node entry. State keys: {list(state.keys())}")
    proposal = state.get('proposal', '')
    
    try:
        # 第一层防护：JSON 解析抗干扰
        parsed_data = parse_json_safely(proposal)
        if not parsed_data:
            raise ValueError("Proposal is not valid JSON.")
            
        # 第二层防护：Pydantic 强制模式校验
        if isinstance(parsed_data, dict):
            validated_model = WorldviewDefenseSchema(**parsed_data)
        else:
            raise ValueError("Proposal JSON is not an object/dictionary.")
            
        # 此时数据合法，允许通过防爆门
        return {
            "defense_log": "通过了 Cookbook 结构化防御检查。",
            "status_message": "🛡️ 结构格式合法，正在由逻辑专家执行 0-4 协议一致性审计..."
        }

    except Exception as e:
        error_msg = f"防御层拦截了污染数据: {str(e)}"
        print(f"[DEFENSE BLOCK] {error_msg}")
        
        # 触发自我进化学习
        try:
            from evolution_sentinel_node import trigger_evolution_learning
            trigger_evolution_learning(proposal, str(e), "Worldview Agent Defense")
        except Exception as ex:
            print(f"[EVOLUTION] Sentinel trigger failed: {ex}")
            
        return {
            "defense_log": error_msg,
            "status_message": "⚠️ 生成格式失效，已被防御门拦截，正在自动回溯修正..."
        }



def reviewer_node(state: AgentState, config: dict):
    """
    审计节点 (Logic Reviewer)。
    
    责任:
    1. 一致性检查: 验证提案是否违反 PGA 底层物理规则 (如能量守恒)。
    2. 隔离性审计: 检查提案是否跨越了逻辑边界 (如在种族设定中讨论地缘政治)。
    3. 逻辑闭环: 如果审计不通过，将 is_approved 设为 False，触发图回到 generator_node 进行修正。
    """
    dispatch_log(config, "开始执行 0-4 协议逻辑一致性审计...")
    print(f"\n[DEBUG] reviewer_node entry. State keys: {list(state.keys())}")
    query = state.get('query', '')
    proposal = str(state.get('proposal') or '')
    print(f"[DEBUG] Entering reviewer_node (proposal length: {len(proposal)})")
    category = state.get('category', 'general')
    category_info = CATEGORY_LOGIC_TEMPLATES.get(category, {"title": "一般世界观", "logic": "遵循PGA底层物理与逻辑。"})
    
    prohibited_items = get_prohibited_rules()
    worldview_rules = get_worldview_context_by_category(query, worldview_id=state.get('worldview_id', 'default_wv'))
    
    full_prompt = f"""你是一个专精于“万象星际协议体 (PGA)”的逻辑审核官。
必须输出 JSON 格式。

【审核标准：{category_info['title']}】
{category_info['logic']}

禁令: {prohibited_items}

待审核提案：
{proposal}

请根据规则审核，输出 JSON: {{"status": "合理/不合理", "audit_log": "...", "category_purity": "纯粹/混淆"}}
"""
    _count_val = state.get('audit_count', 0)
    count = int(_count_val) if isinstance(_count_val, (int, str)) else 0
    res = get_llm(json_mode=True, agent_name="worldview").invoke(full_prompt)
    try:
        audit_data = parse_json_safely(res.content)
        if not audit_data:
            raise ValueError("Invalid audit JSON")
        is_purity_ok = audit_data.get("category_purity") == "纯粹"
        is_logical_ok = audit_data.get("status") == "合理"
        is_ok = is_purity_ok and is_logical_ok
        
        msg = f"完成审计：{'✅ 通过' if is_ok else '❌ 检测到逻辑混淆，正在重试'}"
        print(f"[DEBUG] Reviewer result: {msg}, is_approved: {is_ok}")
        return {
            "review_log": audit_data.get("audit_log", res.content), 
            "is_approved": is_ok,
            "audit_count": count + 1,
            "status_message": f"{msg}。正在准备人工核核准对话框...",
            "llm_interactions": {
                "reviewer": {
                    "prompt": full_prompt,
                    "raw_output": res.content
                }
            }
        }

    except Exception as e:

        print(f"[DEBUG] Reviewer parsing error: {e}")
        return {"review_log": res.content, "is_approved": False, "audit_count": count + 1, "status_message": "审核解析异常"}

def human_node(state: AgentState):
    """
    人工节点 (Human-in-the-loop Gate)。
    
    责任:
    1. 中断执行: 在 Web 模式下发出 interrupt 信号，挂起当前线程，等待 UI 层的 Command(resume=...) 指令。
    2. 交互入口: 允许人类创作者对 Agent 的提案进行最终核准或提出修改意见。
    """
    print(f"\n[DEBUG] human_node entry. State keys: {list(state.keys())}")
    proposal = str(state.get('proposal') or '')
    category = str(state.get('category') or 'general')
    print(f"[DEBUG] Entering human_node (category: {category})")
    
    if os.getenv("AGENT_MODE") == "CLI":
        print(f"\n--- [Agent {category.upper()} 提议] ---\n{proposal}")
        choice = input("\n[a]批准 [f]反馈 [q]退出: ").strip().lower()
        if choice == 'a': return {"is_approved": True, "user_feedback": "批准"}
        if choice == 'f': return {"is_approved": False, "user_feedback": input("意见: ")}
        exit()
        
    # Web 模式：使用 interrupt 暂停图，等待用户反馈
    print(f"[DEBUG] human_node: Interrupting for '{category}' (thread={os.getenv('LANGGRAPH_THREAD_ID', 'N/A')})")
    user_input = interrupt({"status_message": f"{category.upper()} 设定已就绪，等待核准...", "proposal": proposal})
    print(f"[DEBUG] human_node: Resumed. Received feedback: '{user_input}'")
    is_approved = any(word in str(user_input) for word in ["批准", "通过", "OK", "yes", "保存"])
    return {"user_feedback": str(user_input), "is_approved": is_approved, "status_message": "正在处理您的反馈..."}

def saver_node(state: AgentState, config: dict):
    """
    存储节点 (Sync Committer)。
    职责:
    1. 事务写入: 将最终获批的设定同步写入本地磁盘 (worldview_db.json) 和向量库 (ChromaDB)。
    2. 状态收尾: 清理会话状态，准备进入下一个创作循环。
    """
    print(f"\n[DEBUG] saver_node entry. State keys: {list(state.keys())}")
    outline_id = state.get('outline_id', 'default')
    doc_id = state.get('doc_id') or f"wv_{datetime.datetime.now().strftime('%H%M%S')}"
    
    doc = {
        "doc_id": doc_id,
        "category": state.get('category', 'general'),
        "content": state.get('proposal',''),
        "iterations": state.get('iterations', 0),
        "query": state.get('query',''),
        "timestamp": str(datetime.datetime.now().isoformat())
    }
    
    # 1. 写入本地 JSON 存档 (Namespaced)
    worldview_id = state.get('worldview_id', 'default_wv')
    print(f"[DEBUG] saver_node: Attempting to save to worldview_db.json for {worldview_id}...")
    db_path = get_db_path("worldview_db.json", worldview_id=worldview_id)
    try:
        with open(db_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")
        print(f"[DEBUG] saver_node: Save successful.")
    except Exception as e:
        print(f"[DEBUG] saver_node: Save failed: {e}")
        return {"is_approved": False, "status_message": f"存储失败: {e}"}
        
    # 2. 同步到向量库 (Namespaced)
    try:
        v_store = get_vector_store(worldview_id=worldview_id)
        if v_store:
            v_store.add_texts(
                texts=[state.get('proposal','')], 
                metadatas=[{"doc_id": doc_id, "name": state.get('query', ''), "category": state.get('category', 'general')}]
            )
            print(f"[DEBUG] saver_node: Sync to Vector Store successful.")
    except Exception as e:
        print(f"[DEBUG] saver_node: Sync to Vector Store failed: {e}")

    return {"is_approved": True, "status_message": "✨ 设定已通过审计并成功同步至 PGA 核心数据库。"}


# ==========================================
# Graph Definition
# ==========================================
workflow = StateGraph(AgentState)
workflow.add_node("autoresearch", autoresearch_node)
workflow.add_node("generator", generator_node)
workflow.add_node("defense", defense_node)
workflow.add_node("reviewer", reviewer_node)
workflow.add_node("human", human_node)
workflow.add_node("saver", saver_node)

# START 接入 Autoresearch
workflow.add_edge(START, "autoresearch")

def route_after_research(state: AgentState):
    conf = float(state.get("research_confidence", 0.0))
    iters = len(state.get("scratchpad", []))
    if conf > 0.85 or iters >= 4:
        return "generator"
    return "autoresearch"

workflow.add_conditional_edges("autoresearch", route_after_research, {"generator": "generator", "autoresearch": "autoresearch"})
workflow.add_edge("generator", "defense")

def route_after_defense(state: AgentState):
    log = str(state.get("defense_log") or "")
    if "拦截" in log or "失效" in log:
        if int(state.get("iterations") or 0) >= 3:
            return "human" # 多次失败后降级交给人类
        return "generator"
    return "reviewer"

workflow.add_conditional_edges("defense", route_after_defense, {"human": "human", "generator": "generator", "reviewer": "reviewer"})

def route_after_review(state: AgentState):
    if state.get("is_approved") or int(state.get("audit_count", 0)) >= 3: return "human"
    return "generator"

workflow.add_conditional_edges("reviewer", route_after_review, {"human": "human", "generator": "generator"})

def route_after_human(state: AgentState):
    fb = state.get("user_feedback", "").strip()
    is_approved = state.get("is_approved", False)
    print(f"[DEBUG] route_after_human: fb='{fb}', is_approved={is_approved}")
    if is_approved or any(word in fb for word in ["批准", "通过", "OK", "yes", "保存"]): 
        print(f"[DEBUG] route_after_human: routing to 'saver'")
        return "saver"
    if fb == "终止": return END
    if fb: 
        print(f"[DEBUG] route_after_human: routing to 'generator'")
        return "generator"
    return END

workflow.add_conditional_edges("human", route_after_human, {"saver": "saver", "generator": "generator", END: END})
workflow.add_edge("saver", END)

app = workflow.compile(checkpointer=MemorySaver())
