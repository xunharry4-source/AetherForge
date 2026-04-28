import json
from typing import List, Dict, Any
from .lore_utils import get_llm

def summarize_project_context(worldview_id: str, outline_id: str = None) -> Dict[str, str]:
    """
    聚合全量背景并生成摘要，供大脑 Agent 进行高维审计。
    """
    from .lore_utils import get_all_lore_items
    
    items = get_all_lore_items(outline_id=outline_id, worldview_id=worldview_id)
    
    wv_content = []
    outline_content = []
    prose_content = []
    
    for item in items:
        content_snippet = f"- {item['name']}: {item['content'][:300]}..."
        if item['type'] == 'worldview':
            wv_content.append(content_snippet)
        elif item['type'] == 'outline':
            outline_content.append(content_snippet)
        elif item['type'] == 'prose':
            prose_content.append(content_snippet)
            
    # 使用 LLM 进行初步摘要提取
    llm = get_llm(agent_name="brain_summarizer")
    
    def _safe_summarize(title, data_list):
        if not data_list: return f"暂无{title}数据。"
        text = "\n".join(data_list[:20]) # 限制数量防止 context 溢出
        prompt = f"请简要总结以下小说项目的{title}核心要素（保持在 500 字以内）：\n\n{text}"
        try:
            res = llm.invoke(prompt)
            return res.content
        except Exception as e:
            return f"摘要生成失败: {e}"

    return {
        "worldview_summary": _safe_summarize("世界观设定", wv_content),
        "outline_summary": _safe_summarize("大纲脉络", outline_content),
        "prose_summary": _safe_summarize("正文现状", prose_content)
    }

def format_command_for_agent(target_agent: str, query: str, context: str = "") -> str:
    """
    格式化大脑下达给子 Agent 的指令。
    """
    return f"【大脑指令】 {query}\n\n参考上下文: {context}"
