import unittest
import uuid
import requests

BASE_URL = "http://localhost:5006"
API = f"{BASE_URL}/api"

class ClinicalAPITest(unittest.TestCase):
    """纯 API 流临床测试：全程禁止 Mock、禁止假库、禁止 test_client 内部调用"""

    def test_physical_delete_worldview(self):
        """[临床 API 测试] 世界观条目物理删除验证：先 API 建，再 API 删，再 GET 确认消失"""
        print("\n🧪 正在执行 Case 1: 世界观物理删除...")
        test_id = f"test_lore_{uuid.uuid4().hex[:6]}"

        # 1. 通过 API 插入（前门进入）
        res_create = requests.post(f"{API}/archive/update", json={
            "id": test_id, "type": "worldview",
            "name": "待删除条目", "content": "物理删除测试内容",
            "worldview_id": "default_wv"
        })
        self.assertEqual(res_create.status_code, 200, f"前置创建失败: {res_create.text}")

        # 2. 真实 DELETE 请求
        response = requests.delete(f"{API}/archive/delete", json={
            "id": test_id, "type": "worldview", "worldview_id": "default_wv"
        })
        print(f"  - 响应码: {response.status_code}")
        print(f"  - 响应内容: {response.json()}")
        self.assertEqual(response.status_code, 200)

        # 3. 物理断言：通过 GET 确认查不到
        res_list = requests.get(f"{API}/lore/list", params={
            "worldview_id": "default_wv", "page": 1, "page_size": 50
        })
        doc_after = next((i for i in res_list.json() if i.get("id") == test_id), None)
        self.assertIsNone(doc_after, f"物理删除后 {test_id} 仍可 GET 查到！")
        print("  ✅ 物理删除成功证明完成。")

    def test_physical_delete_novel(self):
        """[临床 API 测试] 小说项目物理删除验证：先 API 建，再 API 删，再 GET 确认消失"""
        print("\n🧪 正在执行 Case 2: 小说项目物理删除...")
        world_id = f"world_{uuid.uuid4().hex[:6]}"
        novel_id = None

        # 创建父 World
        res_world = requests.post(f"{API}/worlds/create", json={
            "world_id": world_id, "name": "Clinical Test World", "summary": "s"
        })
        if res_world.status_code == 200 and "world_id" in res_world.json():
            world_id = res_world.json()["world_id"]

        try:
            # 创建 Novel
            res_novel = requests.post(f"{API}/novels/create", json={
                "world_id": world_id, "name": "待删除项目"
            })
            self.assertEqual(res_novel.status_code, 200, f"Novel 创建失败: {res_novel.text}")
            novel_id = res_novel.json()["novel_id"]

            # DELETE
            response = requests.delete(f"{API}/novels/delete", json={
                "novel_id": novel_id, "cascade": True
            })
            print(f"  - 响应码: {response.status_code}")
            self.assertEqual(response.status_code, 200)

            # GET 确认消失
            res_list = requests.get(f"{API}/novels/list", params={
                "world_id": world_id, "page": 1, "page_size": 50
            })
            doc_after = next((n for n in res_list.json() if n.get("novel_id") == novel_id), None)
            self.assertIsNone(doc_after, f"物理删除后 Novel {novel_id} 仍可 GET 查到！")
            print("  ✅ 小说项目物理删除证明完成。")
        finally:
            requests.delete(f"{API}/worlds/delete", json={"world_id": world_id, "cascade": True})

    def test_error_handling_missing_type(self):
        """[临床 API 测试] 缺少 type 参数时应返回 400"""
        print("\n🧪 正在执行 Case 3: 异常路径校验（缺少 type）...")
        response = requests.delete(f"{API}/archive/delete", json={"id": "only_id"})
        print(f"  - 响应码 (预期 400): {response.status_code}")
        self.assertEqual(response.status_code, 400, f"缺少 type 参数应返回 400, 实际: {response.status_code}")
        print("  ✅ 异常处理正确证明完成。")

if __name__ == "__main__":
    unittest.main()
