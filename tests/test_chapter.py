import os
import sys
import unittest
import uuid
from unittest.mock import patch

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.common.lore_utils import get_mongodb_db

class TestChapterClinical(unittest.TestCase):
    """章节功能 (Prose) 临床级物理测试"""

    def setUp(self):
        self.db = get_mongodb_db()
        self.test_scene_id = f"scene_test_{uuid.uuid4().hex[:8]}"

    def test_chapter_prose_roundtrip(self):
        """验证章节内容的物理 CRUD 回路"""
        print(f"\n[Clinical Test] 验证章节内容物理回路: {self.test_scene_id}")
        
        chapter_data = {
            "scene_id": self.test_scene_id,
            "outline_id": "test_novel",
            "title": "第100章 物理测试",
            "content": "这是章节的物理测试正文内容。",
            "timestamp": "2026-04-28T12:00:00"
        }
        
        # 1. Add
        print("  - Step 1: 物理同步章节正文至 MongoDB")
        self.db["prose"].insert_one(chapter_data)
        
        # 2. Query Verify
        print("  - Step 2: 物理查询验证正文是否入库")
        doc = self.db["prose"].find_one({"scene_id": self.test_scene_id})
        self.assertIsNotNone(doc, "物理数据库中未找到章节记录")
        self.assertEqual(doc["title"], "第100章 物理测试")
        
        # 3. Update
        print("  - Step 3: 物理修改正文内容")
        self.db["prose"].update_one(
            {"scene_id": self.test_scene_id},
            {"$set": {"content": "修改后的物理正文内容"}}
        )
        
        # 4. Verify Update
        print("  - Step 4: 物理验证内容更新")
        doc = self.db["prose"].find_one({"scene_id": self.test_scene_id})
        self.assertEqual(doc["content"], "修改后的物理正文内容")
        
        # 5. Delete
        print("  - Step 5: 物理删除章节")
        self.db["prose"].delete_one({"scene_id": self.test_scene_id})
        doc = self.db["prose"].find_one({"scene_id": self.test_scene_id})
        self.assertIsNone(doc, "物理删除后章节记录未被清除")

if __name__ == "__main__":
    unittest.main()
