import unittest
import uuid
import requests

BASE_URL = "http://localhost:5006"

class TestWorldviewClinicalAPI(unittest.TestCase):
    """世界观功能临床级物理测试：严禁 MOCK，严禁降级，必须通过 API 闭环验证"""

    def setUp(self):
        self.test_world_id = f"world_test_{uuid.uuid4().hex[:6]}"
        self.test_wv_id = f"wv_test_{uuid.uuid4().hex[:8]}"

        # 先建一个 World
        res = requests.post(f"{BASE_URL}/api/worlds/create", json={
            "world_id": self.test_world_id, "name": "Worldview Test World", "summary": "s"
        })
        if res.status_code == 200 and "world_id" in res.json():
            self.test_world_id = res.json()["world_id"]

        # 再建一个 Worldview
        res = requests.post(f"{BASE_URL}/api/worldviews/create", json={
            "world_id": self.test_world_id,
            "worldview_id": self.test_wv_id,
            "name": "Test Worldview Container",
            "summary": "For clinical test"
        })
        if res.status_code == 200 and "worldview_id" in res.json():
            self.test_wv_id = res.json()["worldview_id"]

    def tearDown(self):
        requests.delete(f"{BASE_URL}/api/worldviews/delete", json={
            "worldview_id": self.test_wv_id, "cascade": True
        })
        requests.delete(f"{BASE_URL}/api/worlds/delete", json={
            "world_id": self.test_world_id, "cascade": True
        })

    def test_worldview_lore_roundtrip(self):
        """验证世界观设定 (Lore) 的 API CRUD 回路"""
        test_id = f"lore_{uuid.uuid4().hex[:8]}"
        print(f"\n[Clinical API Test] 验证世界观设定回路: {test_id}")

        # 1. Create via API
        print("  - Step 1: API 写入 Lore 设定")
        res_create = requests.post(f"{BASE_URL}/api/archive/update", json={
            "id": test_id,
            "type": "worldview",
            "name": "测试世界观条目",
            "content": "物理测试内容",
            "category": "TestCategory",
            "world_id": self.test_world_id,
            "worldview_id": self.test_wv_id
        })
        self.assertEqual(res_create.status_code, 200, f"Lore 创建失败: {res_create.text}")

        # 2. Query Check via GET
        print("  - Step 2: GET 验证 Lore 是否入库")
        res_list = requests.get(f"{BASE_URL}/api/lore/list", params={
            "world_id": self.test_world_id,
            "worldview_id": self.test_wv_id,
            "page": 1, "page_size": 50
        })
        self.assertEqual(res_list.status_code, 200)
        doc = next((i for i in res_list.json() if i.get("id") == test_id), None)
        self.assertIsNotNone(doc, "物理数据库中未找到同步的 Lore 记录")
        self.assertEqual(doc["content"], "物理测试内容", "业务返回与写入内容不一致")

        # 3. Category filter check
        print("  - Step 3: 带 category 条件 GET 查询验证")
        res_cat = requests.get(f"{BASE_URL}/api/lore/list", params={
            "world_id": self.test_world_id,
            "worldview_id": self.test_wv_id,
            "query": "测试世界观条目",
            "page": 1, "page_size": 50
        })
        matched = [i for i in res_cat.json() if i.get("id") == test_id and i.get("category") == "TestCategory"]
        self.assertTrue(len(matched) > 0, "带条件查询未返回新增的 Lore 记录")
        self.assertEqual(matched[0]["name"], "测试世界观条目")

        # 4. Delete and verify gone
        print("  - Step 4: API 删除并 GET 确认消失")
        res_del = requests.delete(f"{BASE_URL}/api/archive/delete", json={
            "id": test_id, "type": "worldview",
            "world_id": self.test_world_id, "worldview_id": self.test_wv_id
        })
        self.assertEqual(res_del.status_code, 200)
        res_final = requests.get(f"{BASE_URL}/api/lore/list", params={
            "world_id": self.test_world_id, "worldview_id": self.test_wv_id,
            "page": 1, "page_size": 50
        })
        doc_final = next((i for i in res_final.json() if i.get("id") == test_id), None)
        self.assertIsNone(doc_final, "物理删除后 Lore 记录仍残留")

    def test_worldview_container_lifecycle(self):
        """验证 Worldview 容器本身的 CRUD（创建/查列表/删除）"""
        wv2_id = f"wv_extra_{uuid.uuid4().hex[:6]}"
        print(f"\n[Clinical API Test] 验证 Worldview 容器生命周期: {wv2_id}")

        # Create
        res = requests.post(f"{BASE_URL}/api/worldviews/create", json={
            "world_id": self.test_world_id,
            "worldview_id": wv2_id,
            "name": "临时测试世界观容器",
            "summary": "lifecycle test"
        })
        self.assertEqual(res.status_code, 200, f"Worldview 容器创建失败: {res.text}")
        actual_wv2_id = res.json().get("worldview_id", wv2_id)

        # Verify exists in list
        res_list = requests.get(f"{BASE_URL}/api/worldviews/list", params={
            "world_id": self.test_world_id, "page": 1, "page_size": 50
        })
        found = next((w for w in res_list.json() if w.get("worldview_id") == actual_wv2_id), None)
        self.assertIsNotNone(found, "Worldview 容器未出现在列表中")

        # Delete
        res_del = requests.delete(f"{BASE_URL}/api/worldviews/delete", json={
            "worldview_id": actual_wv2_id, "cascade": True
        })
        self.assertEqual(res_del.status_code, 200)

        # Verify gone
        res_list_after = requests.get(f"{BASE_URL}/api/worldviews/list", params={
            "world_id": self.test_world_id, "page": 1, "page_size": 50
        })
        gone = next((w for w in res_list_after.json() if w.get("worldview_id") == actual_wv2_id), None)
        self.assertIsNone(gone, "Worldview 容器删除后仍残留在列表中")

if __name__ == "__main__":
    unittest.main()
