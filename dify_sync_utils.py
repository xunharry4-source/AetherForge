import requests
import json
from logger_utils import get_logger
from config_utils import load_config

logger = get_logger("novel_agent.dify_sync")

class DifyClient:
    """
    Client for Dify Knowledge Base (Dataset) API.
    Ref: https://docs.dify.ai/v1/api-reference/dataset
    """
    def __init__(self, api_key: str, base_url: str = "https://api.dify.ai/v1"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def upsert_document(self, dataset_id: str, name: str, text: str, document_id: str = None) -> dict:
        """
        Creates or updates a document in the specified dataset.
        If document_id is provided, it updates the existing document.
        """
        if not dataset_id:
            logger.error("Dify Dataset ID is required for synchronization.")
            return {"error": "dataset_id_missing"}

        if document_id:
            return self._update_by_text(dataset_id, document_id, name, text)
        else:
            return self._create_by_text(dataset_id, name, text)

    def _create_by_text(self, dataset_id: str, name: str, text: str) -> dict:
        url = f"{self.base_url}/datasets/{dataset_id}/document/create-by-text"
        payload = {
            "name": name,
            "text": text,
            "indexing_technique": "high_quality",
            "process_rule": {
                "mode": "automatic"
            }
        }
        try:
            logger.info(f"Creating Dify document '{name}' in dataset {dataset_id}")
            response = requests.post(url, headers=self.headers, json=payload, timeout=60)
            response.raise_for_status()
            result = response.json()
            # Extract document ID from response (Dify returns 'document' object or similar)
            doc_id = result.get("document", {}).get("id")
            if not doc_id and "id" in result: doc_id = result["id"]
            
            logger.info(f"Successfully created Dify document: {doc_id}")
            return {"success": True, "document_id": doc_id, "raw": result}
        except Exception as e:
            logger.error(f"Failed to create Dify document: {e}")
            return {"success": False, "error": str(e)}

    def _update_by_text(self, dataset_id: str, document_id: str, name: str, text: str) -> dict:
        url = f"{self.base_url}/datasets/{dataset_id}/documents/{document_id}/update-by-text"
        payload = {
            "name": name,
            "text": text,
            "process_rule": {
                "mode": "automatic"
            }
        }
        try:
            logger.info(f"Updating Dify document '{name}' ({document_id})")
            response = requests.post(url, headers=self.headers, json=payload, timeout=60)
            response.raise_for_status()
            result = response.json()
            
            logger.info(f"Successfully updated Dify document: {document_id}")
            return {"success": True, "document_id": document_id, "raw": result}
        except Exception as e:
            logger.error(f"Failed to update Dify document {document_id}: {e}")
            return {"success": False, "error": str(e)}

def get_dify_client() -> DifyClient:
    config = load_config()
    api_key = config.get("DIFY_API_KEY")
    base_url = config.get("DIFY_BASE_URL", "https://api.dify.ai/v1")
    if not api_key:
        return None
    return DifyClient(api_key, base_url)
