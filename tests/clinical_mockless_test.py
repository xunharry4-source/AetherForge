import unittest
import json
import uuid
import sys
import os

# 确保能引用到 src 和 app_api
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app_api import app
from src.common.lore_utils import get_mongodb_db

class ClinicalAPITest(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True
        self.db = get_mongodb_db()

    def test_physical_delete_worldview(self):
        """[临床测试] 世界观条目物理删除验证"""
        print("\n🧪 正在执行 Case 1: 世界观物理删除...")
        test_id = f"test_lore_{uuid.uuid4().hex[:6]}"
        self.db["lore"].insert_one({"doc_id": test_id, "name": "待删除条目", "content": "物理删除测试内容"})
        
        # 模拟真实 DELETE 请求
        response = self.app.delete('/api/archive/delete', 
                                 data=json.dumps({"id": test_id, "type": "worldview"}),
                                 content_type='application/json')
        
        data = response.get_json()
        print(f"  - 响应码: {response.status_code}")
        print(f"  - 响应内容: {data}")
        
        # 物理断言
        doc_after = self.db["lore"].find_one({"doc_id": test_id})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(doc_after)
        print("  ✅ 物理删除成功证明完成。")

    def test_physical_delete_novel(self):
        """[临床测试] 小说项目物理删除验证"""
        print("\n🧪 正在执行 Case 2: 小说项目物理删除...")
        novel_id = f"test_novel_{uuid.uuid4().hex[:6]}"
        self.db["novels"].insert_one({"id": novel_id, "title": "待删除项目"})
        
        response = self.app.delete('/api/archive/delete', 
                                 data=json.dumps({"id": novel_id, "type": "novel"}),
                                 content_type='application/json')
        
        print(f"  - 响应码: {response.status_code}")
        doc_after = self.db["novels"].find_one({"id": novel_id})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(doc_after)
        print("  ✅ 小说项目物理删除证明完成。")

    def test_error_handling(self):
        """[临床测试] 异常路径验证"""
        print("\n🧪 正在执行 Case 3: 异常路径校验...")
        # 缺少参数
        response = self.app.delete('/api/archive/delete', 
                                 data=json.dumps({"id": "only_id"}),
                                 content_type='application/json')
        print(f"  - 响应码 (预期 400): {response.status_code}")
        self.assertEqual(response.status_code, 400)
        print("  ✅ 异常处理正确证明完成。")

if __name__ == "__main__":
    unittest.main()
