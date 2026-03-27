import os
import json
from dify_sync_utils import get_dify_client
from sillytavern_export import convert_to_st_lorebook

class SyncProbe:
    def __init__(self, db_path: str = "worldview_db.json"):
        self.db_path = db_path

    def run_all(self) -> dict:
        results = {
            "dify_config": self.test_dify_config(),
            "st_export": self.test_st_export_dry_run()
        }
        return results

    def test_dify_config(self) -> dict:
        try:
            client = get_dify_client()
            if client:
                return {"status": "PASS", "msg": "Dify API Key is configured"}
            return {"status": "WARN", "msg": "Dify API Key is missing, skipping cloud sync tests"}
        except Exception as e:
            return {"status": "ERROR", "msg": str(e)}

    def test_st_export_dry_run(self) -> dict:
        output_path = "/tmp/test_st_probe.json"
        try:
            if not os.path.exists(self.db_path):
                return {"status": "FAIL", "msg": f"{self.db_path} not found"}
            
            # Use convert_to_st_lorebook logic for a small slice
            # To avoid slow export of 1800 entries every time
            convert_to_st_lorebook(self.db_path, output_path, "Probe Test")
            
            if os.path.exists(output_path):
                file_size = os.path.getsize(output_path)
                os.remove(output_path)
                return {"status": "PASS", "msg": f"Lorebook export logic works, generated {file_size} bytes"}
            return {"status": "FAIL", "msg": "Exported file not found"}
        except Exception as e:
            return {"status": "ERROR", "msg": str(e)}
