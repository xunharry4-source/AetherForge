import os
import sys
import unittest
import uuid
import requests

BASE_URL = "http://localhost:5006"

class TestOutlineClinicalAPI(unittest.TestCase):
    """大纲内容功能临床级物理测试 (纯 API 流)"""

    def setUp(self):
        self.test_world_id = f"test_world_{uuid.uuid4().hex[:6]}"
        self.test_novel_id = f"novel_test_{uuid.uuid4().hex[:8]}"
        self.test_outline_id = f"outline_detail_{uuid.uuid4().hex[:8]}"
        
        # 预先创建一个世界和小说
        res_world = requests.post(f"{BASE_URL}/api/worlds/create", json={
            "world_id": self.test_world_id,
            "name": "For Outline Test World",
            "summary": "Summary"
        })
        if res_world.status_code == 200 and "world_id" in res_world.json():
            self.test_world_id = res_world.json()["world_id"]
            
        res_novel = requests.post(f"{BASE_URL}/api/novels/create", json={
            "novel_id": self.test_novel_id,
            "world_id": self.test_world_id,
            "name": "For Outline Test Novel"
        })
        if res_novel.status_code == 200 and "novel_id" in res_novel.json():
            self.test_novel_id = res_novel.json()["novel_id"]

    def tearDown(self):
        requests.delete(f"{BASE_URL}/api/worlds/delete", json={"world_id": self.test_world_id, "cascade": True})

    def test_outline_content_roundtrip(self):
        """验证大纲详细内容的物理 CRUD 回路 (纯 API 流)"""
        print(f"\n[Clinical API Test] 验证大纲内容物理回路: {self.test_outline_id}")
        
        # 1. Add (API Post)
        print("  - Step 1: 通过 API 创建大纲至数据库")
        res_create = requests.post(f"{BASE_URL}/api/outlines/create", json={
            "novel_id": self.test_novel_id,
            "worldview_id": "default_wv",
            "name": "测试大纲详情",
            "summary": "这是初始的大纲内容。"
        })
        self.assertEqual(res_create.status_code, 200, f"创建大纲失败: {res_create.text}")
        if "outline_id" in res_create.json():
            self.test_outline_id = res_create.json()["outline_id"]
        
        # 2. Query Verify (API Request)
        print("  - Step 2: GET API 查询验证大纲")
        res_list = requests.get(f"{BASE_URL}/api/outlines/list", params={"outline_id": self.test_outline_id, "page": 1, "page_size": 50})
        self.assertEqual(res_list.status_code, 200)
        data = next((o for o in res_list.json() if o.get("outline_id") == self.test_outline_id), None)
        self.assertIsNotNone(data, "API 未查询到物理记录")
        self.assertEqual(data["summary"].strip("。"), "这是初始的大纲内容")
        
        # 3. Update
        print("  - Step 3: API 更新大纲内容")
        res_update = requests.post(f"{BASE_URL}/api/archive/update", json={
            "id": self.test_outline_id,
            "type": "outline",
            "name": "测试大纲详情",
            "content": "这是更新后的大纲内容",
            "worldview_id": "default_wv"
        })
        self.assertEqual(res_update.status_code, 200, f"更新大纲失败: {res_update.text}")
        
        # 4. Query Check
        print("  - Step 4: 物理验证更新是否生效")
        res_list_after = requests.get(f"{BASE_URL}/api/outlines/list", params={"outline_id": self.test_outline_id, "page": 1, "page_size": 50})
        data_after = next((o for o in res_list_after.json() if o.get("outline_id") == self.test_outline_id), None)
        self.assertEqual(data_after["summary"], "这是更新后的大纲内容")
        
        # 5. Delete
        print("  - Step 5: 物理删除大纲记录")
        res_del = requests.delete(f"{BASE_URL}/api/archive/delete", json={
            "id": self.test_outline_id,
            "type": "outline",
            "worldview_id": "default_wv"
        })
        self.assertEqual(res_del.status_code, 200)
        res_list_final = requests.get(f"{BASE_URL}/api/outlines/list", params={"outline_id": self.test_outline_id, "page": 1, "page_size": 50})
        data_final = next((o for o in res_list_final.json() if o.get("outline_id") == self.test_outline_id), None)
        self.assertIsNone(data_final, "物理删除后大纲记录未被清除")

if __name__ == "__main__":
    unittest.main()
