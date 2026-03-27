import json
import os
import argparse
from typing import Dict, List, Any

def convert_to_st_lorebook(input_path: str, output_path: str, book_name: str = "PGA Worldview"):
    """
    Converts worldview_db.json (JSONL format) to SillyTavern World Info JSON format.
    """
    if not os.path.exists(input_path):
        print(f"Error: Input file {input_path} does not exist.")
        return

    entries = {}
    uid_counter = 0

    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip(): continue
            try:
                entity = json.loads(line)
                name = entity.get("name", "Unknown")
                content = entity.get("content", "")
                category = entity.get("category", "General")
                
                # Create ST entry
                entry = {
                    "uid": uid_counter,
                    "key": [name],
                    "keysecondary": [category],
                    "comment": f"Category: {category}",
                    "content": content,
                    "constant": False,
                    "selective": False,
                    "selectiveLogic": 0,
                    "add_to_chat_continuity": False,
                    "order": 100,
                    "enabled": True,
                    "exclude_recursion": False,
                    "display_index": uid_counter,
                    "probability": 100,
                    "use_regex": False,
                    "group_ids": []
                }
                
                # Add synonyms or common keywords if available in future
                # For now, just the name and category
                
                entries[str(uid_counter)] = entry
                uid_counter += 1
            except Exception as e:
                print(f"Skip invalid line: {e}")

    lorebook = {
        "entries": entries,
        "name": book_name,
        "description": f"Exported from Novel Agent Worldview Database. Total entries: {len(entries)}",
        "scan_depth": 50,
        "token_budget": 500,
        "recursive_scanning": True,
        "extensions": {}
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(lorebook, f, ensure_ascii=False, indent=2)
    
    print(f"Successfully exported {len(entries)} entries to {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export Worldview DB to SillyTavern Lorebook")
    parser.add_argument("--input", default="worldview_db.json", help="Path to worldview_db.json")
    parser.add_argument("--output", default="pga_lorebook_st.json", help="Output path for ST Lorebook")
    parser.add_argument("--name", default="万象星际 (PGA) 设定集", help="Lorebook name")
    
    args = parser.parse_args()
    convert_to_st_lorebook(args.input, args.output, args.name)
