import pymongo
import uuid
import sys
import os

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.common.lore_utils import get_mongodb_db

def test_physical_delete():
    print("🚀 Starting Physical Delete Verification...")
    db = get_mongodb_db()
    test_id = f"del_test_{uuid.uuid4().hex[:8]}"
    
    # 1. Prepare data
    print(f"  - Step 1: Inserting dummy lore {test_id}")
    db["lore"].insert_one({
        "doc_id": test_id,
        "name": "To Be Deleted",
        "content": "Delete me"
    })
    
    # 2. Verify existence
    doc = db["lore"].find_one({"doc_id": test_id})
    if not doc:
        print("  ❌ Insert failed!")
        return
    
    # 3. Perform delete (via the same query logic as API)
    print("  - Step 2: Executing physical delete query")
    query = {
        "$or": [
            {"id": test_id},
            {"doc_id": test_id}
        ]
    }
    res = db["lore"].delete_one(query)
    print(f"  - Deleted count: {res.deleted_count}")
    
    # 4. Final check
    doc_after = db["lore"].find_one({"doc_id": test_id})
    if doc_after is None and res.deleted_count == 1:
        print("  ✅ SUCCESS: Physical deletion confirmed in MongoDB.")
    else:
        print("  ❌ FAILURE: Record still exists or delete_one failed.")

if __name__ == "__main__":
    test_physical_deal() if hasattr(sys, 'frozen') else test_physical_delete()
