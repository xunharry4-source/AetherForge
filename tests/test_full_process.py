import httpx
import json
import time
import os
import uuid

BASE_URL = "http://localhost:5005"
NICEGUI_URL = "http://localhost:8090"

def log_step(msg):
    print(f"\n[TEST STEP] {msg}")

def test_worldview_cycle():
    log_step("Testing Worldview CRUD Cycle")
    thread_id = f"test_wv_{uuid.uuid4().hex[:8]}"
    
    # 1. Create
    print(f"Creating Worldview entry for 'The Xylari' (Thread: {thread_id})...")
    with httpx.stream("POST", f"{BASE_URL}/api/agent/query", json={
        "agent_type": "worldview",
        "query": "创建一个名为 'The Xylari' 的种族，他们居住在气态巨行星中，拥有半透明的身体。",
        "thread_id": thread_id
    }, timeout=60.0) as response:
        for line in response.iter_lines():
            if not line: continue
            data = json.loads(line)
            print(f"  [Node] {data.get('node')}: {data.get('status_message')}")
            if data.get('type') == 'final_state':
                break

    # 2. Approve (Simulate user feedback)
    log_step("Approving the Worldview proposal...")
    with httpx.stream("POST", f"{BASE_URL}/api/agent/feedback", json={
        "agent_type": "worldview",
        "feedback": "批准并保存",
        "thread_id": thread_id
    }, timeout=60.0) as response:
        for line in response.iter_lines():
            if not line: continue
            data = json.loads(line)
            print(f"  [Node] {data.get('node')}: {data.get('status_message')}")

    # Verify in DB
    time.sleep(1) # Wait for FS sync
    found = False
    doc_id = None
    if os.path.exists('worldview_db.json'):
        with open('worldview_db.json', 'r', encoding='utf-8') as f:
            for line in f:
                if 'The Xylari' in line:
                    found = True
                    doc_id = json.loads(line).get('doc_id')
                    break
    
    assert found, "Worldview entry 'The Xylari' not found after approval"
    print(f"  Verified: 'The Xylari' created with ID {doc_id}")

    # 3. Modify
    log_step(f"Modifying Worldview entry {doc_id}...")
    res = httpx.post(f"{BASE_URL}/api/archive/update", json={
        "id": doc_id,
        "type": "worldview",
        "name": "The Xylari (Modified)",
        "content": "Updated content: They can also swim in liquid hydrogen."
    })
    assert res.status_code == 200, f"Update failed: {res.text}"
    print("  Modification successful.")

    # 4. Delete
    log_step(f"Deleting Worldview entry {doc_id}...")
    res = httpx.request("DELETE", f"{BASE_URL}/api/archive/delete", json={
        "id": doc_id,
        "type": "worldview"
    })
    assert res.status_code == 200, f"Delete failed: {res.text}"
    print("  Deletion successful.")

def test_outline_cycle():
    log_step("Testing Outline CRUD Cycle")
    thread_id = f"test_ot_{uuid.uuid4().hex[:8]}"
    
    # 1. Create
    print(f"Creating Outline for 'Starry Silence'...")
    outline_id = None
    with httpx.stream("POST", f"{BASE_URL}/api/agent/query", json={
        "agent_type": "outline",
        "query": "为一部科幻小说《星际沉默》创作大纲。",
        "thread_id": thread_id
    }, timeout=60.0) as response:
        for line in response.iter_lines():
            if not line: continue
            data = json.loads(line)
            if data.get('type') == 'final_state':
                outline_id = data.get('doc_id')
                break
    
    # 2. Approve
    log_step("Approving the Outline proposal...")
    with httpx.stream("POST", f"{BASE_URL}/api/agent/feedback", json={
        "agent_type": "outline",
        "feedback": "批准",
        "thread_id": thread_id
    }, timeout=60.0) as response:
        for line in response.iter_lines():
            if not line: continue
            data = json.loads(line)
            if data.get('type') == 'final_state':
                outline_id = data.get('id') or data.get('outline_id')

    assert outline_id, "Failed to get outline ID"
    print(f"  Verified: Outline created with ID {outline_id}")

    # 3. Modify
    log_step(f"Modifying Outline {outline_id}...")
    res = httpx.post(f"{BASE_URL}/api/archive/update", json={
        "id": outline_id,
        "type": "outline",
        "content": "{\"title\": \"星际沉默 (修改版)\", \"summary\": \"新的大纲内容...\"}" 
    })
    assert res.status_code == 200, f"Update outline failed: {res.text}"

    # 4. Delete
    log_step(f"Deleting Outline {outline_id}...")
    res = httpx.request("DELETE", f"{BASE_URL}/api/archive/delete", json={
        "id": outline_id,
        "type": "outline"
    })
    assert res.status_code == 200, "Delete outline failed"

    # 5. Re-create
    log_step("Re-creating the Outline...")
    with httpx.stream("POST", f"{BASE_URL}/api/agent/query", json={
        "agent_type": "outline",
        "query": "重新为《星际沉默》创作大纲。",
        "thread_id": thread_id + "_v2"
    }, timeout=60.0) as response:
        for line in response.iter_lines():
            if not line: continue
            data = json.loads(line)
            if data.get('type') == 'final_state':
                outline_id = data.get('id') or data.get('outline_id')
                break
    
    # Approve v2
    httpx.stream("POST", f"{BASE_URL}/api/agent/feedback", json={
        "agent_type": "outline",
        "feedback": "直接保存",
        "thread_id": thread_id + "_v2"
    }).close()
    
    print(f"  Re-created Outline ID: {outline_id}")
    return outline_id

def test_chapter_and_propagation(outline_id):
    log_step(f"Testing Chapter Generation & Entity Propagation for Outline {outline_id}")
    thread_id = f"test_ch_{uuid.uuid4().hex[:8]}"
    
    # 1. Create Chapter with target entity propagation
    # We ask it to write a scene about a specific NEW entity to force a draft creation
    print("Generating chapter and forcing propagation of 'Nebula Forge'...")
    with httpx.stream("POST", f"{BASE_URL}/api/agent/query", json={
        "agent_type": "writing",
        "query": outline_id, # First move is always identifying scenes or taking outline ID
        "thread_id": thread_id
    }, timeout=120.0) as response:
        for line in response.iter_lines():
            if not line: continue
            # This triggers scene indexing...
            pass

    # Now we need to actually trigger the writing node with feedback if it paused for scene list approval
    log_step("Providing feedback to start writing Chapter 1 involving 'Nebula Forge'...")
    with httpx.stream("POST", f"{BASE_URL}/api/agent/feedback", json={
        "agent_type": "writing",
        "feedback": "开始创作第一场，并确保场景发生在 'Nebula Forge'（这一设定目前缺失，请自动生成草案）。",
        "thread_id": thread_id
    }, timeout=120.0) as response:
        for line in response.iter_lines():
            if not line: continue
            data = json.loads(line)
            print(f"  [Node] {data.get('node')}: {data.get('status_message')}")
            if data.get('type') == 'final_state':
                break

    # 2. Verify Entity Draft Creation
    log_step("Checking for 'Nebula Forge' in entity drafts...")
    time.sleep(2)
    draft_found = False
    if os.path.exists('entity_drafts_db.json'):
        with open('entity_drafts_db.json', 'r', encoding='utf-8') as f:
            for line in f:
                if 'Nebula Forge' in line:
                    draft_found = True
                    break
    
    assert draft_found, "'Nebula Forge' draft was not created as expected"
    print("  Entity propagation verified: 'Nebula Forge' draft created.")

    # 3. Approve Draft via NiceGUI API
    log_step("Approving 'Nebula Forge' draft...")
    res = httpx.post(f"{BASE_URL}/api/entity-drafts/approve", json={"name": "Nebula Forge"})
    assert res.status_code == 200, "Draft approval failed"
    
    # 4. Verify in Worldview
    wv_found = False
    with open('worldview_db.json', 'r', encoding='utf-8') as f:
        for line in f:
            if 'Nebula Forge' in line:
                wv_found = True
                break
    assert wv_found, "'Nebula Forge' not found in worldview after approval"
    print("  Draft promotion to Worldview verified.")

if __name__ == "__main__":
    print("Waiting for server to stabilize...")
    time.sleep(3)
    try:
        test_worldview_cycle()
        outline_id = test_outline_cycle()
        if outline_id:
            test_chapter_and_propagation(outline_id)
        log_step("FULL PROCESS TEST COMPLETED SUCCESSFULLY!")
    except Exception as e:
        print(f"\n[TEST FAILED] {e}")
        import traceback
        traceback.print_exc()
