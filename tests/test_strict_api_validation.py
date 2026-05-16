import unittest
import requests
import uuid
import os

BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:5006")
API_PREFIX = f"{BASE_URL}/api"

class TestStrictApiValidation(unittest.TestCase):
    """
    最严格、最真实的 API 边界与一致性测试。
    验证为什么之前的测试没发现 UI 中的 400 错误，并补全边界测试。
    """

    def test_outline_list_no_params_fails(self):
        """
        [分析发现] 之前的测试总是带参数，而 UI 在某些页面加载时可能不带参数。
        验证：不带参数调用 /api/outlines/list 应该返回 400。
        """
        print("\n🧪 验证 /api/outlines/list 无参数时的 400 返回...")
        res = requests.get(f"{API_PREFIX}/outlines/list")
        self.assertEqual(res.status_code, 400, "API 应该拒绝无参数的列表查询")
        data = res.json()
        self.assertIn("error", data)
        self.assertIn("Missing required query condition", data["error"])
        print(f"  ✅ 验证成功: API 返回了预期的 400 错误: {data['error']}")

    def test_outline_list_missing_pagination_fails(self):
        """
        验证：带了过滤参数但没带分页参数也应该返回 400。
        """
        print("\n🧪 验证 /api/outlines/list 缺少分页参数时的 400 返回...")
        res = requests.get(f"{API_PREFIX}/outlines/list", params={"world_id": "test_world"})
        self.assertEqual(res.status_code, 400)
        data = res.json()
        self.assertIn("pagination", data["error"])
        print(f"  ✅ 验证成功: API 返回了预期的分页缺失错误: {data['error']}")

    def test_full_crud_cycle_with_strict_verification(self):
        """
        执行完整 CRUD 循环，并在每一步执行物理查询验证。
        禁止 MOCK，禁止虚假实现。
        """
        suffix = uuid.uuid4().hex[:6]
        world_name = f"Strict_World_{suffix}"
        novel_name = f"Strict_Novel_{suffix}"
        
        print(f"\n🧪 启动全链路严格 CRUD 验证: {suffix}")

        # 1. Create World
        print("  - Step 1: 创建世界...")
        res = requests.post(f"{API_PREFIX}/worlds/create", json={"name": world_name, "summary": "Strict Test"})
        self.assertEqual(res.status_code, 200)
        world_id = res.json()["world_id"]
        
        # 验证写入：直接查列表看能不能查到
        res = requests.get(f"{API_PREFIX}/worlds/list")
        worlds = res.json()
        found = next((w for w in worlds if w["world_id"] == world_id), None)
        self.assertIsNotNone(found, "世界创建后在列表中不可见")
        self.assertEqual(found["name"], world_name)

        # 2. Create Novel
        print("  - Step 2: 创建小说项目...")
        res = requests.post(f"{API_PREFIX}/novels/create", json={"name": novel_name, "world_id": world_id})
        self.assertEqual(res.status_code, 200)
        novel_id = res.json()["novel_id"]
        
        # 验证写入：用过滤参数查列表
        res = requests.get(f"{API_PREFIX}/novels/list", params={"world_id": world_id, "page": 1, "page_size": 10})
        novels = res.json()
        found_n = next((n for n in novels if n["novel_id"] == novel_id), None)
        self.assertIsNotNone(found_n, "小说创建后在过滤列表中不可见")
        self.assertEqual(found_n["name"], novel_name)

        # 3. Update Novel
        print("  - Step 3: 修改小说项目...")
        new_name = f"Updated_{novel_name}"
        res = requests.post(f"{API_PREFIX}/archive/update", json={
            "id": novel_id,
            "type": "novel",
            "name": new_name,
            "world_id": world_id
        })
        self.assertEqual(res.status_code, 200)
        
        # 验证修改：再次查询并对比内容
        res = requests.get(f"{API_PREFIX}/novels/list", params={"novel_id": novel_id, "page": 1, "page_size": 10})
        updated_novels = res.json()
        self.assertEqual(updated_novels[0]["name"], new_name, "小说名称更新未生效")

        # 4. Delete Novel
        print("  - Step 4: 删除小说项目...")
        res = requests.delete(f"{API_PREFIX}/novels/delete", json={"novel_id": novel_id, "cascade": True})
        self.assertEqual(res.status_code, 200)
        
        # 验证删除：查询确认已消失
        res = requests.get(f"{API_PREFIX}/novels/list", params={"world_id": world_id, "page": 1, "page_size": 10})
        after_del = res.json()
        found_after = next((n for n in after_del if n["novel_id"] == novel_id), None)
        self.assertIsNone(found_after, "小说删除后依然存在于列表中")

        # 5. Cleanup World
        print("  - Step 5: 清理世界...")
        requests.delete(f"{API_PREFIX}/worlds/delete", json={"world_id": world_id, "cascade": True})
        print(f"  ✅ 全链路严格验证完成: {suffix}")

if __name__ == "__main__":
    unittest.main()
