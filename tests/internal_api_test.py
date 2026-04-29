
import requests
import uuid
import sys

BASE_URL = "http://localhost:5006"
API = f"{BASE_URL}/api"

def assert_ok(res, label):
    if not res.ok:
        print(f"❌ FAIL | {label} | Got: {res.status_code} | Body: {res.text[:200]}")
        sys.exit(1)

def test_api():
    print("Starting Strict External API Test (Real HTTP via requests)...\n")

    # 1. System Health
    print("--- Testing System Health ---")
    res = requests.get(f"{API}/system/health")
    assert_ok(res, "Health Check")
    data = res.json()
    assert data.get("status") == "healthy", f"status 字段不是 healthy: {data}"
    print(f"✅ PASS | Health Check | status={data['status']}")

    # 2. Worldviews List
    print("\n--- Testing Worldviews List ---")
    res = requests.get(f"{API}/worldviews/list", params={"world_id": "test_world", "page": 1, "page_size": 10})
    assert_ok(res, "Worldviews List")
    assert isinstance(res.json(), list), f"返回值不是列表: {res.text[:100]}"
    print(f"✅ PASS | Worldviews List | count={len(res.json())}")

    # 3. Archive Update (Create) + GET 验证 + Delete + GET 确认消失
    print("\n--- Testing Archive CRUD (Strict Closed-loop) ---")
    doc_id = f"internal_test_{uuid.uuid4().hex[:6]}"
    payload = {
        "id": doc_id,
        "type": "worldview",
        "name": "Internal Test",
        "content": "Testing via real external HTTP",
        "worldview_id": "default_wv"
    }
    res = requests.post(f"{API}/archive/update", json=payload)
    assert_ok(res, "Archive Update (Create)")

    # GET verify
    res_list = requests.get(f"{API}/lore/list", params={"worldview_id": "default_wv", "page": 1, "page_size": 50})
    assert_ok(res_list, "Lore List after Create")
    found = next((i for i in res_list.json() if i.get("id") == doc_id), None)
    assert found is not None, f"创建后 GET 查不到 {doc_id}"
    assert found["content"] == "Testing via real external HTTP", f"content 字段不符: {found}"
    print(f"✅ PASS | Archive Create + Verified via GET | id={doc_id}")

    # Delete
    res_del = requests.delete(f"{API}/archive/delete", json={"id": doc_id, "type": "worldview", "worldview_id": "default_wv"})
    assert_ok(res_del, "Archive Delete")

    # GET confirm gone
    res_final = requests.get(f"{API}/lore/list", params={"worldview_id": "default_wv", "page": 1, "page_size": 50})
    gone = next((i for i in res_final.json() if i.get("id") == doc_id), None)
    assert gone is None, f"删除后 {doc_id} 仍可 GET 查到！"
    print(f"✅ PASS | Archive Delete + Verified via GET | id={doc_id}")

    print("\nInternal Strict Test Done. All assertions passed.")

if __name__ == "__main__":
    test_api()
