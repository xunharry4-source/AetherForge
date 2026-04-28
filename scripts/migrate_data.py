import os
import json
import pymongo
from src.common.lore_utils import get_mongodb_db, get_db_path

def migrate():
    db = get_mongodb_db()
    
    # 1. Migrate Lore (Worldview)
    print("Migrating Worldview Lore...")
    # Lore is now mandatory in MongoDB. We will read from DB_PATH (default 'data/')
    wv_path = get_db_path("worldview_db.json", worldview_id="default_wv")
    if os.path.exists(wv_path):
        with open(wv_path, 'r', encoding='utf-8') as f:
            count = 0
            for line in f:
                if not line.strip(): continue
                item = json.loads(line)
                item['worldview_id'] = "default_wv"
                db["lore"].update_one({"doc_id": item.get("doc_id")}, {"$set": item}, upsert=True)
                count += 1
            print(f"Migrated {count} lore items.")
    else:
        print(f"No lore file found at {wv_path}")

    # 2. Migrate Outlines
    print("Migrating Outlines...")
    outlines_path = get_db_path("outlines_db.json")
    if os.path.exists(outlines_path):
        with open(outlines_path, 'r', encoding='utf-8') as f:
            count = 0
            for line in f:
                if not line.strip(): continue
                item = json.loads(line)
                # Map 'id' to 'outline_id' if needed
                oid = item.get("id") or item.get("outline_id")
                db["outlines"].update_one({"id": oid}, {"$set": item}, upsert=True)
                count += 1
            print(f"Migrated {count} outlines.")
    
    # 3. Migrate Prose
    # (Note: This might need to iterate through all worldview/outline combinations)
    print("Note: Prose and Drafts migration might be partial. Please sync manually if needed.")

if __name__ == "__main__":
    try:
        migrate()
        print("Migration completed successfully.")
    except Exception as e:
        print(f"Migration failed: {e}")
        print("Please ensure MongoDB is running.")
