import requests
import json
from logger_utils import get_logger

logger = get_logger("test.probes.api")

class APIProbe:
    def __init__(self, base_url: str = "http://localhost:5005"):
        self.base_url = base_url.rstrip("/")

    def run_all(self) -> dict:
        results = {
            "system_health": self.test_health(),
            "agent_query_stream": self.test_agent_query_status(),
            "entity_drafts": self.test_entity_drafts_list(),
            "batch_approve": self.test_batch_approve_exists(),
            "batch_reject": self.test_batch_reject_exists(),
            "refine_loop": self.test_refine_endpoint_reachable(),
            "llm_info": self.test_llm_info_exists()
        }
        return results

    def test_health(self) -> dict:
        url = f"{self.base_url}/api/system/health"
        try:
            # Note: Assuming there is a /api/health endpoint, if not we check /
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                return {"status": "PASS", "msg": "API is healthy"}
            return {"status": "FAIL", "msg": f"Status code: {response.status_code}"}
        except Exception as e:
            return {"status": "ERROR", "msg": str(e)}

    def test_agent_query_status(self) -> dict:
        url = f"{self.base_url}/api/agent/query"
        try:
            # Increase timeout to 15s for agent initialization
            response = requests.post(url, json={}, timeout=15)
            if response.status_code in [200, 400]:
                return {"status": "PASS", "msg": "Agent Query endpoint is reachable"}
            return {"status": "FAIL", "msg": f"Unexpected status: {response.status_code}"}
        except Exception as e:
            return {"status": "ERROR", "msg": str(e)}

    def test_entity_drafts_list(self) -> dict:
        url = f"{self.base_url}/api/entity-drafts"
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                # If it's a list, use len(data). if it's a dict with 'drafts', use that.
                count = len(data) if isinstance(data, list) else len(data.get('drafts', []))
                return {"status": "PASS", "msg": f"Found {count} drafts"}
            return {"status": "FAIL", "msg": f"Status code: {response.status_code}"}
        except Exception as e:
            return {"status": "ERROR", "msg": str(e)}

    def test_batch_approve_exists(self) -> dict:
        url = f"{self.base_url}/api/entity-drafts/batch-approve"
        try:
            # Send empty list to check if route exists and handles validation
            response = requests.post(url, json={"names": []}, timeout=5)
            if response.status_code == 200:
                return {"status": "PASS", "msg": "Batch Approve endpoint is active"}
            return {"status": "FAIL", "msg": f"Status code: {response.status_code}"}
        except Exception as e:
            return {"status": "ERROR", "msg": str(e)}

    def test_batch_reject_exists(self) -> dict:
        url = f"{self.base_url}/api/entity-drafts/batch-reject"
        try:
            response = requests.post(url, json={"names": []}, timeout=5)
            if response.status_code == 200:
                return {"status": "PASS", "msg": "Batch Reject endpoint is active"}
            return {"status": "FAIL", "msg": f"Status code: {response.status_code}"}
        except Exception as e:
            return {"status": "ERROR", "msg": str(e)}

    def test_refine_endpoint_reachable(self) -> dict:
        url = f"{self.base_url}/api/entity-drafts/refine"
        try:
            # We don't want to actually start a refinement without a valid name, 
            # but we can check if it returns 400 (Bad Request) instead of 404.
            response = requests.post(url, json={}, timeout=5)
            if response.status_code == 400:
                return {"status": "PASS", "msg": "Refine endpoint is alive (returned 400 as expected)"}
            return {"status": "FAIL", "msg": f"Status code: {response.status_code}"}
        except Exception as e:
            return {"status": "ERROR", "msg": str(e)}

    def test_llm_info_exists(self) -> dict:
        url = f"{self.base_url}/api/system/llm-info"
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                return {"status": "PASS", "msg": f"LLM Provider: {data.get('provider')}, Model: {data.get('model')}"}
            return {"status": "FAIL", "msg": f"Status code: {response.status_code}"}
        except Exception as e:
            return {"status": "ERROR", "msg": str(e)}
