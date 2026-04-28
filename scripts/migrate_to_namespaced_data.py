import os
import shutil
from pathlib import Path

def migrate_legacy_data(project_root: str):
    """
    Moves legacy data files from data/ into data/default/ 
    to support the new multi-novel namespaced architecture.
    """
    data_dir = Path(project_root) / "data"
    default_project_dir = data_dir / "default"
    
    # Files to migrate
    legacy_files = [
        "worldview_db.json",
        "prose_db.json",
        "entity_drafts_db.json"
    ]
    
    if not data_dir.exists():
        print(f"[!] Data directory '{data_dir}' not found. Nothing to migrate.")
        return

    # Create default project directory if it doesn't exist
    if not default_project_dir.exists():
        print(f"[*] Creating default project directory: {default_project_dir}")
        default_project_dir.mkdir(parents=True, exist_ok=True)
    
    migrated_count = 0
    for filename in legacy_files:
        src_path = data_dir / filename
        dst_path = default_project_dir / filename
        
        if src_path.exists():
            if not dst_path.exists():
                print(f"[*] Migrating '{filename}' -> '{dst_path}'")
                shutil.move(str(src_path), str(dst_path))
                migrated_count += 1
            else:
                print(f"[!] '{filename}' already exists in default project. Skipping move to avoid overwrite.")
        else:
            print(f"[.] '{filename}' not found in root data directory. No migration needed.")
            
    if migrated_count > 0:
        print(f"\n[✓] Successfully migrated {migrated_count} files to 'data/default/'.")
    else:
        print("\n[✓] No legacy files required migration.")

if __name__ == "__main__":
    # Assuming the script is run from project root or its path is known
    root = "/Users/harry/Documents/git/novel_agent"
    migrate_legacy_data(root)
