import requests
import json
import uuid
import time
import sys

BASE_URL = "http://127.0.0.1:5005"

def test_system_health():
    print("\n--- Testing GET /api/system/health ---")
    try:
        response = requests.get(f"{BASE_URL}/api/system/health")
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
        assert response.status_code == 200
        assert "status" in response.json()
        print("✅ Success: System health check passed.")
        return "PASS"
    except Exception as e:
        print(f"❌ Failed: {e}")
        return f"FAIL: {e}"

def test_list_worldviews():
    print("\n--- Testing GET /api/worldviews/list ---")
    try:
        response = requests.get(f"{BASE_URL}/api/worldviews/list")
        print(f"Status Code: {response.status_code}")
        data = response.json()
        print(f"Found {len(data)} worldviews.")
        assert response.status_code == 200
        assert isinstance(data, list)
        print("✅ Success: Worldview list check passed.")
        return "PASS"
    except Exception as e:
        print(f"❌ Failed: {e}")
        return f"FAIL: {e}"

def test_list_outlines():
    print("\n--- Testing GET /api/outlines/list ---")
    try:
        response = requests.get(f"{BASE_URL}/api/outlines/list")
        print(f"Status Code: {response.status_code}")
        data = response.json()
        print(f"Found {len(data)} outlines.")
        assert response.status_code == 200
        assert isinstance(data, list)
        print("✅ Success: Outline list check passed.")
        return "PASS"
    except Exception as e:
        print(f"❌ Failed: {e}")
        return f"FAIL: {e}"

def test_archive_lifecycle():
    print("\n--- Testing Archive Lifecycle (CRUD) ---")
    item_id = f"test_item_{uuid.uuid4().hex[:8]}"
    item_type = "worldview"
    
    # 1. Create/Update
    print(f"Step 1: Creating item {item_id}...")
    payload = {
        "id": item_id,
        "type": item_type,
        "name": "Clinical Test Entity",
        "content": "This is a test entity created by clinical requests test.",
        "category": "Test > Clinical"
    }
    try:
        resp = requests.post(f"{BASE_URL}/api/archive/update", json=payload)
        print(f"Create Status: {resp.status_code}, Body: {resp.text}")
        assert resp.status_code == 200
        assert resp.json().get("status") == "success"
        
        # 2. Verify in list
        print("Step 2: Verifying item in list...")
        resp_list = requests.get(f"{BASE_URL}/api/lore/list?worldview_id=default_wv")
        items = resp_list.json()
        found = any(item.get("id") == item_id for item in items)
        # Note: If database is large, this might not be the best way, but for tests it's okay
        print(f"Item found in lore list: {found}")
        
        # 3. Delete
        print(f"Step 3: Deleting item {item_id}...")
        del_payload = {"id": item_id, "type": item_type}
        resp_del = requests.delete(f"{BASE_URL}/api/archive/delete", json=del_payload)
        print(f"Delete Status: {resp_del.status_code}, Body: {resp_del.text}")
        assert resp_del.status_code == 200
        
        # 4. Verify deletion (Negative test)
        print("Step 4: Verifying deletion...")
        resp_del_verify = requests.delete(f"{BASE_URL}/api/archive/delete", json=del_payload)
        print(f"Re-delete Status (expect 404): {resp_del_verify.status_code}")
        assert resp_del_verify.status_code == 404
        
        print("✅ Success: Archive lifecycle test passed.")
        return "PASS"
    except Exception as e:
        print(f"❌ Failed: {e}")
        return f"FAIL: {e}"

def test_search():
    print("\n--- Testing POST /api/search ---")
    try:
        # Search for something that likely exists or just an empty search
        payload = {"query": "test"}
        response = requests.post(f"{BASE_URL}/api/search", json=payload)
        print(f"Status Code: {response.status_code}")
        data = response.json()
        print(f"Search results count: {len(data)}")
        assert response.status_code == 200
        assert isinstance(data, list)
        
        # Special case: empty query
        print("Step: Testing empty query...")
        resp_empty = requests.post(f"{BASE_URL}/api/search", json={"query": ""})
        assert resp_empty.status_code == 200
        assert resp_empty.json() == []
        
        print("✅ Success: Search API check passed.")
        return "PASS"
    except Exception as e:
        print(f"❌ Failed: {e}")
        return f"FAIL: {e}"

def test_errors():
    print("\n--- Testing Error Handling (Exception Cases) ---")
    try:
        # 1. Missing ID in delete
        print("Step 1: Delete without ID...")
        resp1 = requests.delete(f"{BASE_URL}/api/archive/delete", json={"type": "worldview"})
        print(f"Status (expect 400): {resp1.status_code}")
        assert resp1.status_code == 400
        
        # 2. Invalid type in update
        print("Step 2: Update with invalid type...")
        resp2 = requests.post(f"{BASE_URL}/api/archive/update", json={"id": "foo", "type": "invalid_type"})
        print(f"Status (expect 400): {resp2.status_code}")
        assert resp2.status_code == 400
        
        print("✅ Success: Error handling tests passed.")
        return "PASS"
    except Exception as e:
        print(f"❌ Failed: {e}")
        return f"FAIL: {e}"

if __name__ == "__main__":
    results = {}
    results["API-001 (Health)"] = test_system_health()
    results["API-002 (Lists)"] = test_list_worldviews()
    results["API-002 (Outlines)"] = test_list_outlines()
    results["API-003 (CRUD)"] = test_archive_lifecycle()
    results["API-004 (Search)"] = test_search()
    results["API-ERR (Errors)"] = test_errors()
    
    print("\n" + "="*30)
    print("FINAL TEST SUMMARY")
    print("="*30)
    all_pass = True
    for test, result in results.items():
        print(f"{test}: {result}")
        if result != "PASS":
            all_pass = False
    
    if all_pass:
        print("\n🏆 ALL CLINICAL TESTS PASSED")
        sys.exit(0)
    else:
        print("\n⚠️ SOME TESTS FAILED")
        sys.exit(1)
