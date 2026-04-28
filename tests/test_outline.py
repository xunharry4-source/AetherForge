import os
import sys
import unittest
import uuid
import json
from unittest.mock import patch

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.common.lore_utils import get_mongodb_db, get_outline_by_id

class TestOutlineClinical(unittest.TestCase):
    """大纲内容功能临床级物理测试"""

    def setUp(self):
        self.db = get_mongodb_db()
        self.test_outline_id = f"outline_detail_{uuid.uuid4().hex[:8]}"

    def test_outline_content_roundtrip(self):
        """验证大纲详细内容的物理 CRUD 回路"""
        print(f"\n[Clinical Test] 验证大纲内容物理回路: {self.test_outline_id}")
        
        outline_doc = {
            "outline_id": self.test_outline_id,
            "name": "测试大纲详情",
            "content": "这是初始的大纲内容。",
            "timestamp": "2026-04-28T12:00:00"
        }
        
        # 1. Add
        print("  - Step 1: 物理同步大纲至 MongoDB")
        self.db["outlines"].insert_one(outline_doc)
        
        # 2. Query Verify (Business Function)
        print("  - Step 2: 业务函数查询验证")
        data = get_outline_by_id(self.test_outline_id)
        self.assertIsNotNone(data, "业务函数未查询到物理记录")
        self.assertEqual(data["content"].strip("。"), "这是初始的大纲内容")
        
        # 3. Update
        print("  - Step 3: 物理更新大纲内容")
        self.db["outlines"].update_one(
            {"outline_id": self.test_outline_id},
            {"$set": {"content": "这是更新后的大纲内容"}}
        )
        
        # 4. Query Check
        print("  - Step 4: 物理验证更新是否生效")
        data = get_outline_by_id(self.test_outline_id)
        self.assertEqual(data["content"], "这是更新后的大纲内容")
        
        # 5. Delete
        print("  - Step 5: 物理删除大纲记录")
        self.db["outlines"].delete_one({"outline_id": self.test_outline_id})
        data = get_outline_by_id(self.test_outline_id)
        self.assertIsNone(data, "物理删除后大纲记录未被清除")

if __name__ == "__main__":
    unittest.main()
