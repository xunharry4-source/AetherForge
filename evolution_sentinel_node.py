"""
Evolution Sentinel Node (自主进化旁路审计节点)

该模块负责监听系统中的拦截事件（如 DefenseNode 的格式拦截、ReviewNode 的逻辑拦截）。
当错误发生时，分析失败的设定和错误日志，提取出避免复发的“通用规则”，
并动态写入 `.gemini/skills/evolution/SKILL.md` 文件中，实现永久的知识进化。
"""

import os
import datetime
from lore_utils import get_llm

EVOLUTION_FILE_PATH = os.path.join(os.path.dirname(__file__), ".gemini", "skills", "evolution", "SKILL.md")

def trigger_evolution_learning(failed_proposal: str, error_log: str, agent_source: str):
    """
    当任务被拦截时，触动学习引擎抽象通用规律。
    
    Args:
        failed_proposal (str): 被拦截的提案或推演过程。
        error_log (str): 防御节点或审核节点给出的具体报错原因。
        agent_source (str): 是哪个 Agent 触发的 (Worldview / Outline)。
    """
    print(f"\n[EVOLUTION ENGINE] Triggered by {agent_source}. Analyzing failure reason...")
    
    prompt = f"""你是一个高级 AI 认知工程师。
你的一个下属 Agent 刚刚在创作小说设定时因为犯了常识性错误/格式错误而被“结构化防御验证器”拦截了。

【被拦截的失败草案片段】：
{failed_proposal[:2000]}

【系统的报错日志 / 拦截原因】：
{error_log}

TASK:
请作为一位严厉的导师，从这次失败中提取出 **1-2条极其凝练的通用法则**，防止未来的 Agent 再犯同样的错误。
每条法则必须具有普适性和可操作性（例如：“当描述碳基生命时，绝对禁止让其直接肉身免疫上万度的高温，必须提供明确的能量护盾机制”）。

只需输出法则本身，不要任何客套话。每条法则以星号 `*` 开头。
"""
    try:
        res = get_llm().invoke(prompt)
        lessons = res.content.strip()
        if lessons:
            _append_lesson_to_skill_file(lessons, agent_source)
    except Exception as e:
        print(f"[EVOLUTION ENGINE] Failed to abstract lesson: {e}")

def _append_lesson_to_skill_file(lessons: str, source: str):
    """内部方法：将提取的教训刺入到 SKILL.md 文档中"""
    if not os.path.exists(EVOLUTION_FILE_PATH):
        # 防御性回退：如果文件夹不存在就跳过
        try:
            os.makedirs(os.path.dirname(EVOLUTION_FILE_PATH), exist_ok=True)
        except Exception:
            return
            
    try:
        with open(EVOLUTION_FILE_PATH, "r", encoding="utf-8") as f:
            content = f.read()
            
        # 寻找锚点
        start_tag = "<!-- EVOLUTION_RECORDS_START -->"
        end_tag = "<!-- EVOLUTION_RECORDS_END -->"
        
        if start_tag in content and end_tag in content:
            before = content.split(start_tag)[0]
            middle = content.split(start_tag)[1].split(end_tag)[0]
            after = content.split(end_tag)[1]
            
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            new_record = f"\n### [{timestamp}] 来自 {source} 崩溃的启示:\n{lessons}\n"
            
            new_content = before + start_tag + middle + new_record + "\n" + end_tag + after
            
            with open(EVOLUTION_FILE_PATH, "w", encoding="utf-8") as f:
                f.write(new_content)
                
            print(f"[EVOLUTION ENGINE] Successfully recorded new lesson into SKILL.md")
    except Exception as e:
        print(f"[EVOLUTION ENGINE] Error appending to SKILL file: {e}")
