import httpx
import json
import time
import os
import uuid

BASE_URL = "http://localhost:5005"
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

def get_path(filename):
    return os.path.join(DATA_DIR, filename)

def log_step(msg):
    print(f"\n[TEST STEP] {msg}")

def test_worldview_cycle():
    log_step("Testing Worldview CRUD Cycle")
    # 1. Create via API
    doc_id = f"test_wv_{uuid.uuid4().hex[:6]}"
    res = httpx.post(f"{BASE_URL}/api/archive/update", json={
        "id": doc_id,
        "type": "worldview",
        "name": "星际赏金猎人 (E2E Test)",
        "content": "这是一群在银河边境游荡的探索者。",
        "category": "主要人物 > 赏金猎人"
    })
    assert res.status_code == 200, f"Create failed: {res.text}"
    print(f"  Created: {doc_id}")

    # 2. Modify
    res = httpx.post(f"{BASE_URL}/api/archive/update", json={
        "id": doc_id,
        "type": "worldview",
        "name": "星际赏金猎人 (Modified)",
        "content": "修改后的内容：他们现在拥有量子级跳跃设备。"
    })
    assert res.status_code == 200
    print("  Modified successfully.")

    # 3. Delete
    res = httpx.request("DELETE", f"{BASE_URL}/api/archive/delete", json={
        "id": doc_id,
        "type": "worldview"
    })
    assert res.status_code == 200
    print("  Deleted successfully (Vector sync should have run).")

    # 5. Create a draft manually to test the approval flow
    res = httpx.post(f"{BASE_URL}/api/archive/update", json={
        "id": "draft_001", 
        "type": "entity-draft", 
        "name": "Ancient Core", 
        "content": "Test Content", 
        "status": "pending"
    })
    assert res.status_code == 200, f"Manual draft creation failed: {res.text}"
    print("  Manual draft created successfully.")

    # 4. Re-create
    res = httpx.post(f"{BASE_URL}/api/archive/update", json={
        "id": doc_id,
        "type": "worldview",
        "name": "星际赏金猎人 (Re-created)",
        "content": "最终确定的设定内容。"
    })
    assert res.status_code == 200
    print("  Re-created successfully.")
    return doc_id

def test_outline_cycle():
    log_step("Testing Outline CRUD Cycle")
    doc_id = f"test_ot_{uuid.uuid4().hex[:6]}"
    
    # 1. Create
    res = httpx.post(f"{BASE_URL}/api/archive/update", json={
        "id": doc_id,
        "type": "outline",
        "name": "遗迹探索 (E2E Outline)",
        "content": "第一章：发现核心\n第二章：逃离坍塌"
    })
    assert res.status_code == 200
    print(f"  Created Outline: {doc_id}")

    # 2. Modify
    res = httpx.post(f"{BASE_URL}/api/archive/update", json={
        "id": doc_id,
        "type": "outline",
        "name": "遗迹探索 (Modified Outline)",
        "content": "修改后的章节计划..."
    })
    assert res.status_code == 200
    print("  Modified Outline successfully.")

    # 3. Delete
    res = httpx.request("DELETE", f"{BASE_URL}/api/archive/delete", json={
        "id": doc_id,
        "type": "outline"
    })
    assert res.status_code == 200
    print("  Deleted Outline successfully.")

    # 4. Re-create
    res = httpx.post(f"{BASE_URL}/api/archive/update", json={
        "id": doc_id,
        "type": "outline",
        "name": "遗迹探索 (Final Outline)",
        "content": "确定的全书大纲内容。"
    })
    assert res.status_code == 200
    print("  Re-created Outline successfully.")
    return doc_id

def test_chapter_and_propagation(outline_id):
    log_step(f"Testing Chapter Management & Propagation (Outline: {outline_id})")
    
    # 1. Create Chapter
    res = httpx.post(f"{BASE_URL}/api/archive/update", json={
        "id": f"prose_{uuid.uuid4().hex[:6]}",
        "type": "prose",
        "name": "第一章：星云熔炉",
        "content": "主角潜入了 '古文明核心' (Ancient Core)，那里散发着诡异的蓝光。"
    })
    assert res.status_code == 200
    print("  Chapter created.")

    # 2. Simulate Entity Propagation (Manual Draft Creation as if from Agent)
    # We use the internal draft API or direct file write to simulate what the agent would do
    log_step("Simulating entity draft propagation (Ancient Core)...")
    with open(get_path("entity_drafts_db.json"), "a", encoding="utf-8") as f:
        draft = {
            "name": "Ancient Core",
            "type": "Mechanisms",
            "proposal": "古文明的核心动力源，由星云能量驱动。",
            "source_prose": "第一章：星云熔炉",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        f.write(json.dumps(draft, ensure_ascii=False) + "\n")
    
    # 3. Verify in Drafts
    time.sleep(1)
    print("  Draft 'Ancient Core' injected. Verifying...")
    
    # 4. Approve Draft via API
    res = httpx.post(f"{BASE_URL}/api/entity-drafts/approve", json={"name": "Ancient Core"})
    assert res.status_code == 200, f"Draft approval failed: {res.text}"
    print("  Draft 'Ancient Core' approved.")

    # 5. Verify in Worldview
    with open(get_path("worldview_db.json"), "r", encoding="utf-8") as f:
        content = f.read()
        assert "Ancient Core" in content, "Approved entity not found in worldview_db.json"
    print("  Propagation success: 'Ancient Core' is now part of the worldview!")

if __name__ == "__main__":
    print(f"E2E Data Directory: {DATA_DIR}")
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
        
    try:
        test_worldview_cycle()
        outline_id = test_outline_cycle()
        test_chapter_and_propagation(outline_id)
        log_step("ALL E2E WORKFLOW TESTS PASSED!")
    except Exception as e:
        print(f"\n[TEST FAILED] {e}")
        import traceback
        traceback.print_exc()
