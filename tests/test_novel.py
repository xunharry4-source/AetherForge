import os
import sys
import unittest
import uuid
import json
from unittest.mock import patch

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.common.lore_utils import get_mongodb_db

class TestNovelClinical(unittest.TestCase):
    """小说项目功能临床级物理测试"""

    def setUp(self):
        self.db = get_mongodb_db()
        self.test_novel_id = f"novel_test_{uuid.uuid4().hex[:8]}"

    def test_novel_project_roundtrip(self):
        """验证小说项目 (Novel Project) 的物理 CRUD 回路"""
        print(f"\n[Clinical Test] 验证小说项目物理回路: {self.test_novel_id}")
        
        new_novel = {
            "outline_id": self.test_novel_id,
            "worldview_id": "test_wv",
            "name": "测试小说项目",
            "summary": "这是一个物理测试小说项目摘要",
            "timestamp": "2026-04-28T12:00:00"
        }
        
        # 1. Add (Physical Insert)
        print("  - Step 1: 物理插入小说项目至 MongoDB")
        self.db["outlines"].insert_one(new_novel)
        
        # 2. Query Check (Physical Verification)
        print("  - Step 2: 物理查询验证项目是否存在")
        doc = self.db["outlines"].find_one({"outline_id": self.test_novel_id})
        self.assertIsNotNone(doc, "物理数据库中未找到新增的小说项目")
        self.assertEqual(doc["name"], "测试小说项目")
        
        # 3. Update Check (Modification Side Effect)
        print("  - Step 3: 物理修改项目名称")
        self.db["outlines"].update_one(
            {"outline_id": self.test_novel_id}, 
            {"$set": {"name": "已修改小说项目"}}
        )
        
        # 4. Verify Update
        print("  - Step 4: 物理查询验证修改是否成功")
        doc = self.db["outlines"].find_one({"outline_id": self.test_novel_id})
        self.assertEqual(doc["name"], "已修改小说项目", "物理数据库中的更新未生效")
        
        # 5. Delete Check (Final Cleanup)
        print("  - Step 5: 物理删除项目")
        self.db["outlines"].delete_one({"outline_id": self.test_novel_id})
        doc = self.db["outlines"].find_one({"outline_id": self.test_novel_id})
        self.assertIsNone(doc, "物理删除后项目记录仍残留在数据库中")

if __name__ == "__main__":
    unittest.main()
