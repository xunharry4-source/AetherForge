import httpx
import json
import time
import os
import uuid

BASE_URL = "http://localhost:5006"
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

def get_path(filename):
    return os.path.join(DATA_DIR, filename)

def log_step(msg):
    print(f"\n[TEST STEP] {msg}")

def verify_entity_exists(entity_type, doc_id, expected_fields=None, outline_id=None, worldview_id=None):
    """最严格测试：确保通过 GET 接口能够查询到对应的数据，且字段一致"""
    params = {}
    if outline_id: params["outline_id"] = outline_id
    if worldview_id: params["worldview_id"] = worldview_id
    if not outline_id and not worldview_id:
        params["worldview_id"] = "default_wv"
    
    res = httpx.get(f"{BASE_URL}/api/lore/list", params=params)
    assert res.status_code == 200, f"Query failed: {res.text}"
    items = res.json()
    
    found = None
    for item in items:
        if item.get("id") == doc_id and item.get("type") == entity_type:
            found = item
            break
            
    assert found is not None, f"Entity {doc_id} (type: {entity_type}) NOT FOUND in DB. Database does not reflect the POST action!"
    
    if expected_fields:
        for k, v in expected_fields.items():
            assert found.get(k) == v, f"Field '{k}' mismatch. Expected '{v}', got '{found.get(k)}'"
    return found

def verify_entity_deleted(entity_type, doc_id, outline_id=None, worldview_id=None):
    """最严格测试：确保数据被完全删除"""
    params = {}
    if outline_id: params["outline_id"] = outline_id
    if worldview_id: params["worldview_id"] = worldview_id
    if not outline_id and not worldview_id:
        params["worldview_id"] = "default_wv"
    
    res = httpx.get(f"{BASE_URL}/api/lore/list", params=params)
    assert res.status_code == 200, f"Query failed: {res.text}"
    items = res.json()
    
    for item in items:
        if item.get("id") == doc_id and item.get("type") == entity_type:
            raise AssertionError(f"Entity {doc_id} (type: {entity_type}) WAS NOT DELETED from DB. Fake deletion detected!")

def test_worldview_cycle():
    log_step("Testing Worldview CRUD Cycle (Strict API Verification)")
    doc_id = f"test_wv_{uuid.uuid4().hex[:6]}"
    
    # 1. Create via API
    create_payload = {
        "id": doc_id,
        "type": "worldview",
        "name": "星际赏金猎人 (E2E Test)",
        "content": "这是一群在银河边境游荡的探索者。",
        "category": "主要人物 > 赏金猎人"
    }
    res = httpx.post(f"{BASE_URL}/api/archive/update", json=create_payload)
    assert res.status_code == 200, f"Create failed: {res.text}"
    
    # 验证 1: 确保刚才创建的记录确实存在，绝不被 API 蒙骗
    verify_entity_exists("worldview", doc_id, expected_fields={"name": create_payload["name"], "content": create_payload["content"]})
    print(f"  Created & Verified: {doc_id}")

    # 2. Modify
    modify_payload = {
        "id": doc_id,
        "type": "worldview",
        "name": "星际赏金猎人 (Modified)",
        "content": "修改后的内容：他们现在拥有量子级跳跃设备。"
    }
    res = httpx.post(f"{BASE_URL}/api/archive/update", json=modify_payload)
    assert res.status_code == 200
    
    # 验证 2: 确保修改真的生效
    verify_entity_exists("worldview", doc_id, expected_fields={"name": modify_payload["name"], "content": modify_payload["content"]})
    print("  Modified & Verified successfully.")

    # 3. Delete
    res = httpx.request("DELETE", f"{BASE_URL}/api/archive/delete", json={
        "id": doc_id,
        "type": "worldview"
    })
    assert res.status_code == 200
    
    # 验证 3: 确保真的删除了
    verify_entity_deleted("worldview", doc_id)
    print("  Deleted & Verified successfully.")

    # 4. Create a draft strictly via API (No manual file writes!)
    draft_id = "draft_001"
    res = httpx.post(f"{BASE_URL}/api/archive/update", json={
        "id": draft_id, 
        "type": "entity-draft", 
        "name": "Ancient Core", 
        "content": "Test Content", 
        "status": "pending"
    })
    assert res.status_code == 200, f"Draft creation failed: {res.text}"
    verify_entity_exists("entity-draft", draft_id, expected_fields={"name": "Ancient Core", "status": "pending"})
    print("  API Draft created & Verified successfully.")

    return doc_id

def test_outline_cycle():
    log_step("Testing Outline CRUD Cycle (Strict API Verification)")
    doc_id = f"test_ot_{uuid.uuid4().hex[:6]}"
    
    # 1. Create
    res = httpx.post(f"{BASE_URL}/api/archive/update", json={
        "id": doc_id,
        "type": "outline",
        "name": "遗迹探索 (E2E Outline)",
        "content": "第一章：发现核心\n第二章：逃离坍塌"
    })
    assert res.status_code == 200
    verify_entity_exists("outline", doc_id, expected_fields={"name": "遗迹探索 (E2E Outline)"})
    print(f"  Created & Verified Outline: {doc_id}")

    # 2. Modify
    res = httpx.post(f"{BASE_URL}/api/archive/update", json={
        "id": doc_id,
        "type": "outline",
        "name": "遗迹探索 (Modified Outline)",
        "content": "修改后的章节计划..."
    })
    assert res.status_code == 200
    verify_entity_exists("outline", doc_id, expected_fields={"name": "遗迹探索 (Modified Outline)"})
    print("  Modified & Verified Outline successfully.")

    # 3. Delete
    res = httpx.request("DELETE", f"{BASE_URL}/api/archive/delete", json={
        "id": doc_id,
        "type": "outline"
    })
    assert res.status_code == 200
    verify_entity_deleted("outline", doc_id)
    print("  Deleted & Verified Outline successfully.")

    # 4. Re-create
    res = httpx.post(f"{BASE_URL}/api/archive/update", json={
        "id": doc_id,
        "type": "outline",
        "name": "遗迹探索 (Final Outline)",
        "content": "确定的全书大纲内容。"
    })
    assert res.status_code == 200
    verify_entity_exists("outline", doc_id, expected_fields={"name": "遗迹探索 (Final Outline)"})
    print("  Re-created Outline successfully.")
    
    return doc_id

def test_chapter_and_propagation(outline_id):
    log_step(f"Testing Chapter Management & Propagation (Outline: {outline_id})")
    
    # 1. Create Chapter
    chapter_id = f"prose_{uuid.uuid4().hex[:6]}"
    res = httpx.post(f"{BASE_URL}/api/archive/update", json={
        "id": chapter_id,
        "type": "prose",
        "outline_id": outline_id,
        "name": "第一章：星云熔炉",
        "content": "主角潜入了 '古文明核心' (Ancient Core)，那里散发着诡异的蓝光。"
    })
    assert res.status_code == 200
    verify_entity_exists("prose", chapter_id, expected_fields={"name": "第一章：星云熔炉"}, outline_id=outline_id)
    print("  Chapter created & Verified.")

    # 2. Simulate Entity Propagation via API instead of direct file I/O!
    log_step("Simulating entity draft propagation via API (Ancient Core)...")
    draft_payload = {
        "id": f"draft_{uuid.uuid4().hex[:6]}",
        "type": "entity-draft",
        "name": "Ancient Core",
        "content": "古文明的核心动力源，由星云能量驱动。",
        "status": "pending",
        "outline_id": outline_id
    }
    res = httpx.post(f"{BASE_URL}/api/archive/update", json=draft_payload)
    assert res.status_code == 200, f"Draft insertion failed: {res.text}"
    verify_entity_exists("entity-draft", draft_payload["id"], expected_fields={"name": "Ancient Core"}, outline_id=outline_id)
    print("  Draft 'Ancient Core' injected via API & Verified.")
    
    # 3. Approve Draft via API
    res = httpx.post(f"{BASE_URL}/api/entity-drafts/approve", json={"name": "Ancient Core", "outline_id": outline_id})
    assert res.status_code == 200, f"Draft approval failed: {res.text}"
    print("  Draft 'Ancient Core' approved via API.")

    # 4. Verify the approved draft is now a formal worldview entity!
    # API: /api/lore/list with type=worldview should have it.
    found_approved = False
    items = httpx.get(f"{BASE_URL}/api/lore/list", params={"outline_id": outline_id}).json()
    for item in items:
        if item.get("name") == "Ancient Core" and item.get("type") == "worldview":
            found_approved = True
            break
            
    assert found_approved, "Propagation FAILED! Approved entity 'Ancient Core' was not found in worldview list query."
    print("  Propagation success: 'Ancient Core' is now fully integrated into the DB via API!")

if __name__ == "__main__":
    print(f"E2E Data Directory: {DATA_DIR}")
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
        
    try:
        test_worldview_cycle()
        outline_id = test_outline_cycle()
        test_chapter_and_propagation(outline_id)
        log_step("ALL STRICT E2E WORKFLOW TESTS PASSED!")
    except Exception as e:
        print(f"\n[STRICT TEST FAILED] {e}")
        import traceback
        traceback.print_exc()
        # Non-zero exit code to fail CI
        exit(1)
