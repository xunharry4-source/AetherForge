import requests
import json
import time
import sys

BASE_URL = "http://127.0.0.1:5006"
API_PREFIX = f"{BASE_URL}/api"

def print_result(name, url, method, expected_status, res, is_success):
    status_icon = "✅ PASS" if is_success else "❌ FAIL"
    print(f"{status_icon} | {name} | {method} {url} | Expected: {expected_status} | Got: {res.status_code}")
    if not is_success:
        print(f"  Response: {res.text}")

def test_system_health():
    print("\n--- Testing System Health ---")
    url = f"{API_PREFIX}/system/health"
    try:
        res = requests.get(url, timeout=5)
        # Normal
        is_success = res.status_code == 200
        print_result("Health Check Normal", url, "GET", 200, res, is_success)
    except requests.exceptions.ConnectionError:
        print(f"❌ FAIL | Connection Error: Make sure the server is running at {BASE_URL}")
        sys.exit(1)

def test_worldviews_list():
    print("\n--- Testing Worldviews List ---")
    url = f"{API_PREFIX}/worldviews/list"
    res = requests.get(url, params={"world_id": "test_world", "page": 1, "page_size": 10})
    is_success = res.status_code == 200 and isinstance(res.json(), list)
    print_result("List Worldviews Normal", url, "GET", 200, res, is_success)

def test_outlines_list():
    print("\n--- Testing Outlines List ---")
    url = f"{API_PREFIX}/outlines/list"
    res = requests.get(url, params={"world_id": "test_world", "page": 1, "page_size": 10})
    is_success = res.status_code == 200 and isinstance(res.json(), list)
    print_result("List Outlines Normal", url, "GET", 200, res, is_success)

def verify_entity_exists(entity_type, doc_id, expected_fields=None, outline_id=None, worldview_id=None):
    params = {}
    if outline_id: params["outline_id"] = outline_id
    if worldview_id: params["worldview_id"] = worldview_id
    if not outline_id and not worldview_id:
        params["worldview_id"] = "default_wv"
    params["page"] = 1
    params["page_size"] = 50
        
    res = requests.get(f"{API_PREFIX}/lore/list", params=params)
    assert res.status_code == 200, f"Query failed: {res.text}"
    items = res.json()
    
    found = None
    for item in items:
        if item.get("id") == doc_id and item.get("type") == entity_type:
            found = item
            break
            
    assert found is not None, f"Entity {doc_id} (type: {entity_type}) NOT FOUND in DB."
    if expected_fields:
        for k, v in expected_fields.items():
            assert found.get(k) == v, f"Field mismatch: Expected {k}={v}, Got {found.get(k)}"
    return found

def verify_entity_deleted(entity_type, doc_id, outline_id=None, worldview_id=None):
    params = {}
    if outline_id: params["outline_id"] = outline_id
    if worldview_id: params["worldview_id"] = worldview_id
    if not outline_id and not worldview_id:
        params["worldview_id"] = "default_wv"
    params["page"] = 1
    params["page_size"] = 50
        
    res = requests.get(f"{API_PREFIX}/lore/list", params=params)
    assert res.status_code == 200, f"Query failed: {res.text}"
    items = res.json()
    for item in items:
        if item.get("id") == doc_id and item.get("type") == entity_type:
            raise AssertionError(f"Entity {doc_id} WAS NOT DELETED!")

def test_archive_crud():
    print("\n--- Testing Archive CRUD (Strict API Check) ---")
    
    import uuid
    doc_id = f"test_clinical_{uuid.uuid4().hex[:6]}"
    
    # 1. Normal Create
    create_url = f"{API_PREFIX}/archive/update"
    payload = {
        "id": doc_id,
        "type": "worldview",
        "name": "Test Worldview Archive",
        "content": "This is a test content.",
        "worldview_id": "default_wv"
    }
    res_create = requests.post(create_url, json=payload)
    if res_create.status_code != 200:
        print_result("Archive Create Normal", create_url, "POST", 200, res_create, False)
        return
        
    # 强制进行 GET 查询验证
    try:
        verify_entity_exists("worldview", doc_id, expected_fields={"name": "Test Worldview Archive"})
        print_result("Archive Create Normal + Verified", create_url, "POST", 200, res_create, True)
    except AssertionError as e:
        print(f"❌ FAIL | Archive Create Normal | API returned 200 but verification failed: {e}")
        sys.exit(1)

    # 2. Normal Delete
    delete_url = f"{API_PREFIX}/archive/delete"
    res_del = requests.delete(delete_url, json={"id": doc_id, "type": "worldview", "worldview_id": "default_wv"})
    if res_del.status_code != 200:
        print_result("Archive Delete Normal", delete_url, "DELETE", 200, res_del, False)
    else:
        # 强制 GET 确认已经消失
        try:
            verify_entity_deleted("worldview", doc_id)
            print_result("Archive Delete Normal + Verified", delete_url, "DELETE", 200, res_del, True)
        except AssertionError as e:
            print(f"❌ FAIL | Archive Delete Normal | API returned 200 but verification failed: {e}")
            sys.exit(1)

def test_search():
    print("\n--- Testing Search ---")
    url = f"{API_PREFIX}/search"
    payload = {
        "query": "test query",
        "worldview_id": "default_wv"
    }
    res = requests.post(url, json=payload)
    is_success = res.status_code == 200
    print_result("Search Normal", url, "POST", 200, res, is_success)

if __name__ == "__main__":
    print("Starting Strict Clinical API Requests Test...\n")
    test_system_health()
    test_worldviews_list()
    test_outlines_list()
    test_archive_crud()
    test_search()
    print("\nDone.")
