import os
import sys
import unittest
import uuid
import json
from unittest.mock import patch

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.common.lore_utils import (
    get_mongodb_db, 
    get_all_lore_items, 
    sync_lore_to_db,
    upsert_category_template,
    delete_category_template
)

class TestWorldviewClinical(unittest.TestCase):
    """世界观功能临床级物理测试：严禁 MOCK，严禁降级，必须物理回路验证"""

    def setUp(self):
        self.db = get_mongodb_db()
        self.test_id = f"wv_test_{uuid.uuid4().hex[:8]}"

    def test_worldview_lore_roundtrip(self):
        """验证世界观设定 (Lore) 的物理 CRUD 回路"""
        print(f"\n[Clinical Test] 验证世界观设定物理回路: {self.test_id}")
        
        entity = {
            "doc_id": self.test_id,
            "name": "测试世界观条目",
            "content": "物理测试内容",
            "category": "TestCategory",
            "type": "worldview"
        }
        
        # 1. Add (Physically)
        print("  - Step 1: 物理同步设定至 MongoDB")
        try:
            sync_lore_to_db(entity)
        except Exception as e:
            print(f"    [SYNC WARN] {e}")
        
        # 2. Query Check (Physical Verification)
        print("  - Step 2: 物理查询验证设定是否入库")
        doc = self.db["lore"].find_one({"doc_id": self.test_id})
        self.assertIsNotNone(doc, "物理数据库中未找到同步的 Lore 记录")
        self.assertEqual(doc["content"], "物理测试内容", "业务返回与物理存储不一致")
        
        # 3. Aggregation Check (Business Requirements)
        print("  - Step 3: 业务聚合器查询验证")
        all_items = get_all_lore_items()
        found = any(item.get("id") == self.test_id for item in all_items)
        self.assertTrue(found, "业务聚合器未返回新增的物理记录")

    def test_category_template_transparency(self):
        """验证分类模板的物理透明度"""
        print("\n[Clinical Test] 验证分类模板物理回路")
        cat = f"cat_{uuid.uuid4().hex[:6]}"
        data = {"name_zh": "测试分类", "fields": ["f1"]}
        
        # 1. Upsert
        print(f"  - Step 1: 更新模板 {cat}")
        upsert_category_template(cat, data)
        
        # 2. Query Verify
        print("  - Step 2: 物理验证模板记录")
        doc = self.db["worldview_templates"].find_one({"category": cat})
        self.assertIsNotNone(doc, "物理数据库未记录模板")
        
        # 3. Delete & Verify
        print("  - Step 3: 物理删除并验证")
        delete_category_template(cat)
        doc = self.db["worldview_templates"].find_one({"category": cat})
        self.assertIsNone(doc, "物理删除后记录仍残留在数据库中")

if __name__ == "__main__":
    unittest.main()
