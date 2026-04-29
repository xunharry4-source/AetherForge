import os
import sys
import unittest
import uuid
import requests

BASE_URL = "http://localhost:5006"

class TestNovelClinicalAPI(unittest.TestCase):
    """小说项目功能临床级物理测试 (纯 API 流)"""

    def setUp(self):
        self.test_world_id = f"test_world_{uuid.uuid4().hex[:6]}"
        self.test_novel_id = f"novel_test_{uuid.uuid4().hex[:8]}"
        
        # 预先创建一个世界
        res = requests.post(f"{BASE_URL}/api/worlds/create", json={
            "world_id": self.test_world_id,
            "name": "For Novel Test World",
            "summary": "Summary"
        })
        if res.status_code == 200 and "world_id" in res.json():
            self.test_world_id = res.json()["world_id"]

    def tearDown(self):
        requests.delete(f"{BASE_URL}/api/worlds/delete", json={"world_id": self.test_world_id, "cascade": True})

    def test_novel_project_roundtrip(self):
        """验证小说项目 (Novel Project) 的真实 API CRUD 回路"""
        print(f"\n[Clinical API Test] 验证小说项目回路: {self.test_novel_id}")
        
        # 1. Add (API Post)
        print("  - Step 1: 通过 API 创建小说项目")
        res_create = requests.post(f"{BASE_URL}/api/novels/create", json={
            "novel_id": self.test_novel_id,
            "world_id": self.test_world_id,
            "name": "测试小说项目",
            "summary": "这是一个物理测试小说项目摘要"
        })
        self.assertEqual(res_create.status_code, 200, f"创建失败: {res_create.text}")
        
        if "novel_id" in res_create.json():
            self.test_novel_id = res_create.json()["novel_id"]
        
        # 2. Query Check (Physical Verification)
        print("  - Step 2: 物理查询验证项目是否存在")
        res_list = requests.get(f"{BASE_URL}/api/novels/list", params={"world_id": self.test_world_id, "page": 1, "page_size": 50})
        self.assertEqual(res_list.status_code, 200)
        novels = res_list.json()
        doc = next((n for n in novels if n.get("novel_id") == self.test_novel_id), None)
        self.assertIsNotNone(doc, "物理数据库中未找到新增的小说项目")
        self.assertEqual(doc["name"], "测试小说项目")
        
        # 3. Update Check (Modification Side Effect)
        print("  - Step 3: 通过 API 修改项目名称")
        res_update = requests.post(f"{BASE_URL}/api/novels/update", json={
            "novel_id": self.test_novel_id,
            "name": "已修改小说项目"
        })
        self.assertEqual(res_update.status_code, 200)
        
        # 4. Verify Update
        print("  - Step 4: 物理查询验证修改是否成功")
        res_list_after = requests.get(f"{BASE_URL}/api/novels/list", params={"world_id": self.test_world_id, "page": 1, "page_size": 50})
        novels_after = res_list_after.json()
        doc_after = next((n for n in novels_after if n.get("novel_id") == self.test_novel_id), None)
        self.assertIsNotNone(doc_after)
        self.assertEqual(doc_after["name"], "已修改小说项目", "物理数据库中的更新未生效")
        
        # 5. Delete Check (Final Cleanup)
        print("  - Step 5: 物理删除项目")
        res_del = requests.delete(f"{BASE_URL}/api/novels/delete", json={"novel_id": self.test_novel_id, "cascade": True})
        self.assertEqual(res_del.status_code, 200)
        
        res_list_final = requests.get(f"{BASE_URL}/api/novels/list", params={"world_id": self.test_world_id, "page": 1, "page_size": 50})
        doc_final = next((n for n in res_list_final.json() if n.get("novel_id") == self.test_novel_id), None)
        self.assertIsNone(doc_final, "物理删除后项目记录仍残留在数据库中")

if __name__ == "__main__":
    unittest.main()
