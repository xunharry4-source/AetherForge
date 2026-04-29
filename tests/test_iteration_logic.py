import unittest
import uuid
import json
import requests

BASE_URL = "http://localhost:5006"

class TestIterationLogicClinicalAPI(unittest.TestCase):
    """迭代逻辑临床级 API 测试：通过真实接口验证 Patch 与 Rewrite 模式的有效性"""

    def setUp(self):
        self.original_content = "夕阳洒在破碎的舷窗上，林越抹去脸上的血迹，看着引擎冒出的黑烟，心中一片死寂。这是他最后的机会。"

    def _stream_agent_and_get_final(self, payload: dict) -> str:
        """发起流式 Agent 请求，解析 NDJSON 并返回最终草稿内容"""
        res = requests.post(f"{BASE_URL}/api/agent/query", json=payload, stream=True, timeout=120)
        self.assertEqual(res.status_code, 200, f"Agent 启动失败: {res.text[:300]}")

        final_content = ""
        for line in res.iter_lines():
            if not line:
                continue
            try:
                msg = json.loads(line.decode("utf-8"))
            except Exception:
                continue
            msg_type = msg.get("type", "")
            if msg_type == "error":
                self.fail(f"Agent 流中检测到 error: {msg}")
            # 从 final_state 或 node_update 中提取 draft_content
            if msg_type in ("final_state", "node_update"):
                state = msg.get("state") or msg.get("data") or {}
                if isinstance(state, dict) and state.get("draft_content"):
                    final_content = state["draft_content"]
            if msg_type == "final_state":
                break

        self.assertTrue(len(final_content) > 0, "Agent 流中未返回任何 draft_content")
        return final_content

    def test_patch_mode_preservation(self):
        """验证 partial_rewrite 模式是否真实保留了原文核心内容"""
        print("\n[Clinical API Test] 验证 partial_rewrite 模式 (局部修订) 的保留率")
        thread_id = f"patch_test_{uuid.uuid4().hex[:8]}"

        payload = {
            "query": "微调：林越不是死寂，而是充满了愤怒",
            "agent_type": "chapter",
            "thread_id": thread_id,
            "worldview_id": "default_wv",
            "rewrite_mode": "partial_rewrite",
            "draft_content": self.original_content,
            "context_data": "林越是一名退役机师",
            "outline_content": "林越逃出生天"
        }

        print("  - Step 1: 调用 Agent 进行 partial_rewrite 模式修订...")
        new_content = self._stream_agent_and_get_final(payload)

        # 核心词汇保留率检查
        print("  - Step 2: 检查原文核心片段保留情况")
        keywords = ["舷窗", "血迹", "黑烟"]
        found_count = sum(1 for k in keywords if k in new_content)
        print(f"    [数据] 原文核心词保留数: {found_count}/{len(keywords)}")
        self.assertGreaterEqual(found_count, 2, f"partial_rewrite 失败：原文核心描写被大范围重写\n新内容：{new_content[:200]}")
        self.assertIn("怒", new_content, f"partial_rewrite 失败：用户修改建议（愤怒）未被采纳\n新内容：{new_content[:200]}")
        print(f"    ✅ partial_rewrite 保留率通过")

    def test_rewrite_mode_flexibility(self):
        """验证 full_rewrite 模式是否真实执行了全量重写"""
        print("\n[Clinical API Test] 验证 full_rewrite 模式 (全量重写) 的自由度")
        thread_id = f"rewrite_test_{uuid.uuid4().hex[:8]}"

        payload = {
            "query": "全部重写：把场景换成清晨的森林，林越在水边醒来",
            "agent_type": "chapter",
            "thread_id": thread_id,
            "worldview_id": "default_wv",
            "rewrite_mode": "full_rewrite",
            "draft_content": self.original_content,
            "context_data": "林越是一名精灵",
            "outline_content": "林越的新生"
        }

        print("  - Step 1: 调用 Agent 进行 full_rewrite 模式重写...")
        new_content = self._stream_agent_and_get_final(payload)

        # 偏移度检查：原文星际科幻词汇应消失
        print("  - Step 2: 检查内容偏移度（旧词不应残留）")
        forbidden_keywords = ["舷窗", "引擎", "黑烟"]
        found_count = sum(1 for k in forbidden_keywords if k in new_content)
        print(f"    [数据] 残留旧词数: {found_count}")
        self.assertLessEqual(found_count, 0, f"full_rewrite 失败：内容仍残留旧版本语境\n新内容：{new_content[:200]}")
        self.assertIn("森林", new_content, f"full_rewrite 失败：新需求「森林」未被执行\n新内容：{new_content[:200]}")
        print(f"    ✅ full_rewrite 偏移度通过")

if __name__ == "__main__":
    unittest.main()
