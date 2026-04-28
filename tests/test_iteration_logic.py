import os
import sys
import unittest
import uuid
from unittest.mock import patch

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.novel.writing_execution_agent_langgraph import write_draft_func, WritingState

class TestIterationLogicClinical(unittest.TestCase):
    """迭代逻辑临床级物理测试：验证 Patch 与 Rewrite 模式的真实有效性"""

    def setUp(self):
        self.test_scene_id = f"iter_test_{uuid.uuid4().hex[:8]}"
        self.original_content = "夕阳洒在破碎的舷窗上，林越抹去脸上的血迹，看着引擎冒出的黑烟，心中一片死寂。这是他最后的机会。"

    def test_patch_mode_preservation(self):
        """验证 Patch 模式是否真实保留了原文内容"""
        print("\n[Clinical Test] 验证 Patch 模式 (局部修订) 的保留率")
        
        state: WritingState = {
            "draft_content": self.original_content,
            "user_feedback": "微调：林越不是死寂，而是充满了愤怒",
            "novel_summary": "星际末世背景",
            "outline_content": "林越逃出生天",
            "active_scene_index": 0,
            "scene_list": [{"title": "坠毁", "description": "林越在废墟中醒来"}],
            "context_data": "林越是一名退役机师",
            "retry_count": 0
        }
        
        # 执行写节点
        # 注意：这里会真实调用 LLM
        print("  - Step 1: 调用 LLM 进行 Patch 模式修订...")
        result = write_draft_func(state, config={})
        new_content = result.get("draft_content", "")
        
        # 物理检查：原文中的核心词汇（如“舷窗”、“血迹”、“黑烟”）是否还在？
        print("  - Step 2: 检查原文核心片段保留情况")
        keywords = ["舷窗", "血迹", "黑烟"]
        found_count = sum(1 for k in keywords if k in new_content)
        
        print(f"    [数据] 原文核心词保留数: {found_count}/{len(keywords)}")
        self.assertGreaterEqual(found_count, 2, "Patch 模式失败：原文核心描写被大范围重写")
        self.assertIn("怒", new_content, "Patch 模式失败：用户修改建议未被采纳")

    def test_rewrite_mode_flexibility(self):
        """验证 Rewrite 模式是否真实执行了全量重写"""
        print("\n[Clinical Test] 验证 Rewrite 模式 (全量重写) 的自由度")
        
        state: WritingState = {
            "draft_content": self.original_content,
            "user_feedback": "全部重写：把场景换成清晨的森林，林越在水边醒来",
            "novel_summary": "奇幻背景",
            "outline_content": "林越的新生",
            "active_scene_index": 0,
            "scene_list": [{"title": "苏醒", "description": "林越在河边醒来"}],
            "context_data": "林越是一名精灵",
            "retry_count": 0
        }
        
        # 执行写节点
        print("  - Step 1: 调用 LLM 进行 Rewrite 模式重写...")
        result = write_draft_func(state, config={})
        new_content = result.get("draft_content", "")
        
        # 物理检查：原文中的“舷窗”、“引擎”等词汇是否已经消失？
        print("  - Step 2: 检查内容偏移度")
        forbidden_keywords = ["舷窗", "引擎", "黑烟"]
        found_count = sum(1 for k in forbidden_keywords if k in new_content)
        
        print(f"    [数据] 残留旧词数: {found_count}")
        self.assertLessEqual(found_count, 0, "Rewrite 模式失败：内容仍残留在旧版本的语境中")
        self.assertIn("森林", new_content, "Rewrite 模式失败：新需求未被执行")

if __name__ == "__main__":
    unittest.main()
