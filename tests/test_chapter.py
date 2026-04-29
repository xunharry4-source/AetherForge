import unittest
import uuid
import requests

BASE_URL = "http://localhost:5006"

class TestChapterClinicalAPI(unittest.TestCase):
    """章节功能 (Prose) 临床级物理测试 (纯 API 流)"""

    def setUp(self):
        self.test_world_id = f"test_world_{uuid.uuid4().hex[:6]}"
        self.test_novel_id = f"novel_test_{uuid.uuid4().hex[:6]}"
        self.test_outline_id = f"outline_test_{uuid.uuid4().hex[:6]}"
        self.test_chapter_id = f"chapter_test_{uuid.uuid4().hex[:8]}"

        res = requests.post(f"{BASE_URL}/api/worlds/create", json={
            "world_id": self.test_world_id, "name": "Chapter Test World", "summary": "s"
        })
        if res.status_code == 200 and "world_id" in res.json():
            self.test_world_id = res.json()["world_id"]

        res = requests.post(f"{BASE_URL}/api/novels/create", json={
            "novel_id": self.test_novel_id, "world_id": self.test_world_id, "name": "Chapter Test Novel"
        })
        if res.status_code == 200 and "novel_id" in res.json():
            self.test_novel_id = res.json()["novel_id"]

        res = requests.post(f"{BASE_URL}/api/outlines/create", json={
            "outline_id": self.test_outline_id, "novel_id": self.test_novel_id,
            "worldview_id": "default_wv", "name": "Chapter Test Outline", "summary": "s"
        })
        if res.status_code == 200 and "outline_id" in res.json():
            self.test_outline_id = res.json()["outline_id"]

    def tearDown(self):
        requests.delete(f"{BASE_URL}/api/worlds/delete", json={"world_id": self.test_world_id, "cascade": True})

    def test_chapter_prose_roundtrip(self):
        """验证章节内容的真实 API CRUD 回路"""
        print(f"\n[Clinical API Test] 验证章节内容回路: {self.test_chapter_id}")

        # 1. Create via API
        print("  - Step 1: 通过 API 写入章节正文")
        res_create = requests.post(f"{BASE_URL}/api/archive/update", json={
            "id": self.test_chapter_id,
            "type": "prose",
            "name": "第100章 物理测试",
            "content": "这是章节的物理测试正文内容。",
            "outline_id": self.test_outline_id,
            "worldview_id": "default_wv"
        })
        self.assertEqual(res_create.status_code, 200, f"章节写入失败: {res_create.text}")

        # 2. Query Verify via GET
        print("  - Step 2: GET 查询验证章节是否入库")
        res_list = requests.get(f"{BASE_URL}/api/lore/list", params={
            "outline_id": self.test_outline_id, "worldview_id": "default_wv",
            "page": 1, "page_size": 50
        })
        self.assertEqual(res_list.status_code, 200)
        doc = next((i for i in res_list.json() if i.get("id") == self.test_chapter_id), None)
        self.assertIsNotNone(doc, "数据库中未找到章节记录")
        self.assertEqual(doc["name"], "第100章 物理测试")
        self.assertEqual(doc["content"], "这是章节的物理测试正文内容。")

        # 3. Update via API
        print("  - Step 3: 通过 API 修改正文内容")
        res_update = requests.post(f"{BASE_URL}/api/archive/update", json={
            "id": self.test_chapter_id,
            "type": "prose",
            "name": "第100章 物理测试",
            "content": "修改后的物理正文内容",
            "outline_id": self.test_outline_id,
            "worldview_id": "default_wv"
        })
        self.assertEqual(res_update.status_code, 200, f"章节更新失败: {res_update.text}")

        # 4. Verify Update via GET
        print("  - Step 4: GET 验证内容更新是否生效")
        res_after = requests.get(f"{BASE_URL}/api/lore/list", params={
            "outline_id": self.test_outline_id, "worldview_id": "default_wv",
            "page": 1, "page_size": 50
        })
        doc_after = next((i for i in res_after.json() if i.get("id") == self.test_chapter_id), None)
        self.assertIsNotNone(doc_after)
        self.assertEqual(doc_after["content"], "修改后的物理正文内容", "更新后内容不一致")

        # 5. Delete via API + verify
        print("  - Step 5: API 删除章节并 GET 确认消失")
        res_del = requests.delete(f"{BASE_URL}/api/archive/delete", json={
            "id": self.test_chapter_id, "type": "prose",
            "outline_id": self.test_outline_id, "worldview_id": "default_wv"
        })
        self.assertEqual(res_del.status_code, 200)
        res_final = requests.get(f"{BASE_URL}/api/lore/list", params={
            "outline_id": self.test_outline_id, "worldview_id": "default_wv",
            "page": 1, "page_size": 50
        })
        doc_final = next((i for i in res_final.json() if i.get("id") == self.test_chapter_id), None)
        self.assertIsNone(doc_final, "物理删除后章节记录仍存在")

if __name__ == "__main__":
    unittest.main()
