import requests
import json
import os
import uuid
import time
import sys

BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:5006")
API_PREFIX = f"{BASE_URL}/api"

def assert_response(response, expected_status=200, message="Request failed"):
    if response.status_code != expected_status:
        print(f"❌ {message}")
        print(f"  Status: {response.status_code}")
        print(f"  Response: {response.text}")
        sys.exit(1)

def test_system_health():
    print("\n[Step 1] 验证系统健康状态...")
    url = f"{API_PREFIX}/system/health"
    res = requests.get(url, timeout=5)
    assert_response(res, 200, "系统健康检查未通过")
    data = res.json()
    assert data.get("status") == "healthy", f"系统状态异常: {data}"
    print("  ✅ 系统健康状况良好")

def test_worldview_lifecycle():
    print("\n[Step 2] 验证世界观全生命周期 (创建 -> 校验 -> 更新 -> 搜索 -> 删除 -> 校验)...")
    
    # 1. 创建世界观容器
    unique_suffix = uuid.uuid4().hex[:8]
    wv_name = f"Strict Test Worldview {unique_suffix}"
    create_wv_url = f"{API_PREFIX}/worldviews/create"
    res = requests.post(create_wv_url, json={"name": wv_name, "summary": "测试容器内容"})
    assert_response(res, 200, "创建世界观容器失败")
    wv_id = res.json()["worldview_id"]
    print(f"  - 已创建世界观容器: {wv_id}")

    # 2. 验证容器是否存在于列表
    list_wv_url = f"{API_PREFIX}/worldviews/list"
    res = requests.get(list_wv_url, params={"worldview_id": wv_id, "page": 1, "page_size": 10})
    assert_response(res, 200, "获取世界观列表失败")
    wvs = res.json()
    assert any(w["worldview_id"] == wv_id for w in wvs), f"创建的容器 {wv_id} 不在列表中"
    print("  - 容器列表校验通过")

    # 3. 在容器内创建条目 (Archive Update)
    entry_id = f"entry_{unique_suffix}"
    entry_name = f"Strict Entry {unique_suffix}"
    update_url = f"{API_PREFIX}/archive/update"
    payload = {
        "id": entry_id,
        "type": "worldview",
        "name": entry_name,
        "content": f"这是一段非常独特的测试内容: {unique_suffix}",
        "category": "测试分类",
        "worldview_id": wv_id
    }
    res = requests.post(update_url, json=payload)
    assert_response(res, 200, "创建条目失败")
    print(f"  - 已创建条目: {entry_id}")

    # 4. 验证条目内容 (List Lore + Keyword Query)
    list_lore_url = f"{API_PREFIX}/lore/list"
    # 同时测试新增加的 query 关键字过滤功能
    res = requests.get(list_lore_url, params={"worldview_id": wv_id, "query": unique_suffix, "page": 1, "page_size": 20})
    assert_response(res, 200, "获取条目列表失败")
    items = res.json()
    assert len(items) > 0, f"关键字查询 {unique_suffix} 未能返回结果"
    match = next((i for i in items if i["id"] == entry_id), None)
    assert match is not None, f"条目 {entry_id} 未能出现在关键字查询结果中"
    assert match["name"] == entry_name, "条目名称不一致"
    print("  - 条目物理写入 & 关键字过滤校验通过")
    
    # 5. 搜索验证 (RAG 向量同步校验 + worldview_id 隔离校验)
    search_url = f"{API_PREFIX}/search"
    # 现在支持传入 worldview_id 进行隔离搜索
    search_payload = {"query": unique_suffix, "worldview_id": wv_id}
    res = requests.post(search_url, json=search_payload)
    assert_response(res, 200, "搜索接口失败")
    results = res.json()
    
    found = False
    for r in results:
        # 严格检查返回结果中的 ID 和内容
        if r.get("id") == entry_id and unique_suffix in r.get("content", ""):
            found = True
            break
    
    assert found, f"向量搜索无法在 worldview {wv_id} 中找到包含 {unique_suffix} 的条目"
    print("  - 向量化搜索 & 隔离校验通过")

    # 6. 删除条目
    delete_url = f"{API_PREFIX}/archive/delete"
    res = requests.delete(delete_url, json={"id": entry_id, "type": "worldview", "worldview_id": wv_id})
    assert_response(res, 200, "删除条目失败")
    print(f"  - 已发送删除请求: {entry_id}")

    # 7. 验证条目已消失
    res = requests.get(list_lore_url, params={"worldview_id": wv_id, "page": 1, "page_size": 20})
    items = res.json()
    assert not any(i["id"] == entry_id for i in items), f"条目 {entry_id} 在删除后仍然存在"
    print("  - 条目物理删除校验通过")

def test_outline_lifecycle():
    print("\n[Step 3] 验证小说项目全生命周期 (创建 -> 查询 -> 修改 -> 查询 -> 删除 -> 查询)...")
    unique_suffix = uuid.uuid4().hex[:8]
    name = f"Strict Novel {unique_suffix}"
    updated_name = f"Strict Novel Updated {unique_suffix}"
    updated_content = f"严格测试修改后的大纲内容 {unique_suffix}"
    
    # 1. 创建
    res = requests.post(f"{API_PREFIX}/outlines/create", json={"name": name, "summary": "测试大纲"})
    assert_response(res, 200, "创建小说项目失败")
    outline_id = res.json()["outline_id"]
    print(f"  - 已创建小说项目: {outline_id}")

    # 2. 校验
    res = requests.get(f"{API_PREFIX}/outlines/list", params={"outline_id": outline_id, "page": 1, "page_size": 10})
    outlines = res.json()
    assert any(o["outline_id"] == outline_id for o in outlines), "小说项目不在列表中"
    print("  - 列表展示校验通过")

    # 3. 修改后严格查询验证
    res = requests.post(f"{API_PREFIX}/archive/update", json={
        "id": outline_id,
        "type": "outline",
        "name": updated_name,
        "content": updated_content,
        "worldview_id": "default_wv"
    })
    assert_response(res, 200, "修改小说项目失败")
    res = requests.get(f"{API_PREFIX}/outlines/list", params={"outline_id": outline_id, "page": 1, "page_size": 10})
    assert_response(res, 200, "修改后查询小说项目失败")
    outlines = res.json()
    match = next((o for o in outlines if o["outline_id"] == outline_id), None)
    assert match is not None, "修改后小说项目不在列表中"
    assert match["title"] == updated_name, f"小说项目标题未真实修改: {match}"
    assert match["summary"] == updated_content, f"小说项目内容未真实修改: {match}"
    print("  - 修改后查询校验通过")

    # 4. 删除
    res = requests.delete(f"{API_PREFIX}/archive/delete", json={"id": outline_id, "type": "outline"})
    assert_response(res, 200, "删除小说项目失败")
    
    # 5. 校验消失
    res = requests.get(f"{API_PREFIX}/outlines/list", params={"outline_id": outline_id, "page": 1, "page_size": 10})
    assert_response(res, 200, "删除后查询小说项目失败")
    outlines = res.json()
    assert not any(o["outline_id"] == outline_id for o in outlines), "小说项目删除后依然存在"
    print("  - 物理删除校验通过")

def test_chapter_lifecycle():
    print("\n[Step 4] 验证章节正文全生命周期 (创建 -> 查询 -> 修改 -> 查询 -> 删除 -> 查询)...")
    unique_suffix = uuid.uuid4().hex[:8]
    outline_name = f"Strict Chapter Project {unique_suffix}"
    chapter_id = f"strict_chapter_{unique_suffix}"
    chapter_title = f"Strict Chapter {unique_suffix}"
    chapter_content = f"严格章节正文唯一内容 {unique_suffix}"
    updated_title = f"Strict Chapter Updated {unique_suffix}"
    updated_content = f"严格章节正文修改内容 {unique_suffix}"

    res = requests.post(f"{API_PREFIX}/outlines/create", json={"name": outline_name, "summary": "章节测试大纲", "worldview_id": "default_wv"})
    assert_response(res, 200, "创建章节测试项目失败")
    outline_id = res.json()["outline_id"]

    try:
        res = requests.post(f"{API_PREFIX}/archive/update", json={
            "id": chapter_id,
            "type": "prose",
            "name": chapter_title,
            "content": chapter_content,
            "outline_id": outline_id,
            "worldview_id": "default_wv"
        })
        assert_response(res, 200, "创建章节失败")

        res = requests.get(f"{API_PREFIX}/lore/list", params={"outline_id": outline_id, "worldview_id": "default_wv", "page": 1, "page_size": 20})
        assert_response(res, 200, "查询章节列表失败")
        items = res.json()
        match = next((i for i in items if i.get("id") == chapter_id), None)
        assert match is not None, f"章节 {chapter_id} 创建后查询不到"
        assert match.get("type") == "prose", match
        assert match.get("name") == chapter_title, match
        assert match.get("content") == chapter_content, match
        print("  - 章节创建后查询校验通过")

        res = requests.post(f"{API_PREFIX}/archive/update", json={
            "id": chapter_id,
            "type": "prose",
            "name": updated_title,
            "content": updated_content,
            "outline_id": outline_id,
            "worldview_id": "default_wv"
        })
        assert_response(res, 200, "修改章节失败")

        res = requests.get(f"{API_PREFIX}/lore/list", params={"outline_id": outline_id, "worldview_id": "default_wv", "query": unique_suffix, "page": 1, "page_size": 20})
        assert_response(res, 200, "修改后查询章节失败")
        items = res.json()
        match = next((i for i in items if i.get("id") == chapter_id), None)
        assert match is not None, f"章节 {chapter_id} 修改后查询不到"
        assert match.get("name") == updated_title, match
        assert match.get("content") == updated_content, match
        print("  - 章节修改后查询校验通过")

        res = requests.delete(f"{API_PREFIX}/archive/delete", json={"id": chapter_id, "type": "prose", "outline_id": outline_id, "worldview_id": "default_wv"})
        assert_response(res, 200, "删除章节失败")

        res = requests.get(f"{API_PREFIX}/lore/list", params={"outline_id": outline_id, "worldview_id": "default_wv", "page": 1, "page_size": 20})
        assert_response(res, 200, "删除后查询章节失败")
        items = res.json()
        assert not any(i.get("id") == chapter_id for i in items), f"章节 {chapter_id} 删除后仍然存在"
        print("  - 章节物理删除校验通过")
    finally:
        requests.delete(f"{API_PREFIX}/archive/delete", json={"id": chapter_id, "type": "prose", "outline_id": outline_id, "worldview_id": "default_wv"})
        requests.delete(f"{API_PREFIX}/archive/delete", json={"id": outline_id, "type": "outline", "worldview_id": "default_wv"})

def test_config_persistence():
    print("\n[Step 5] 验证配置持久化...")
    # 1. 读取原始配置
    res = requests.get(f"{API_PREFIX}/config")
    assert_response(res, 200, "读取配置失败")
    orig_config = res.json()
    
    # 2. 修改 (使用一个不在 .env 中的字段，避免被环境变量覆盖)
    test_val = "strict-test-value-" + uuid.uuid4().hex[:4]
    res = requests.post(f"{API_PREFIX}/config", json={"STRICT_TEST_FIELD": test_val})
    assert_response(res, 200, "更新配置失败")
    
    # 3. 再次读取并校验
    res = requests.get(f"{API_PREFIX}/config")
    new_config = res.json()
    assert new_config.get("STRICT_TEST_FIELD") == test_val, f"配置未持久化: 预期 {test_val}, 实际 {new_config.get('STRICT_TEST_FIELD')}"
    print(f"  - 配置修改并持久化校验通过 ({test_val})")
    
    # 4. 恢复配置 (可选)
    requests.post(f"{API_PREFIX}/config", json={"DEFAULT_MODEL": orig_config.get("DEFAULT_MODEL")})

def test_agent_stream():
    print("\n[Step 6] 验证 Agent 异步流式输出 (NDJSON)...")
    query_payload = {
        "query": "请帮我分析一下这个星系的势力分布",
        "agent_type": "worldview",
        "worldview_id": "default_wv",
        "thread_id": "test_thread_" + uuid.uuid4().hex[:8]
    }
    res = requests.post(f"{API_PREFIX}/agent/query", json=query_payload, stream=True)
    assert_response(res, 200, "Agent 启动失败")
    
    has_node_update = False
    has_final_state = False
    
    print("  - 正在解析实时流...")
    for line in res.iter_lines():
        if not line: continue
        msg = json.loads(line.decode('utf-8'))
        msg_type = msg.get("type")
        if msg_type == "node_update":
            has_node_update = True
        elif msg_type == "final_state":
            has_final_state = True
            break
        elif msg_type == "error":
            print(f"❌ 流中检测到错误: {msg}")
            sys.exit(1)

    assert has_node_update, "流中未检测到 node_update 过程消息"
    assert has_final_state, "流中未检测到 final_state 结束标记"
    print("  - 流式协议校验通过 (真实调用 + 实时反馈)")

def test_world_hierarchy_lifecycle_bridge():
    print("\n[Step 7] 验证世界层级全生命周期真实 requests 测试...")
    from tests.test_world_hierarchy_requests import (
        test_world_hierarchy_invalid_inputs,
        test_world_hierarchy_lifecycle,
    )
    test_world_hierarchy_lifecycle()
    test_world_hierarchy_invalid_inputs()
    print("  - 世界 -> 世界观 -> 小说 -> 大纲 -> 章节层级校验通过")

def test_hierarchy_agent_workflow_bridge():
    print("\n[Step 8] 验证世界层级独立 Agent 工作流真实 requests 测试...")
    from tests.test_hierarchy_agent_workflow_requests import test_hierarchy_agent_workflow_lifecycle
    test_hierarchy_agent_workflow_lifecycle()
    print("  - 独立 Agent、审查、人工介入、迭代与真实写库校验通过")

if __name__ == "__main__":
    print("🚀 开始执行最严格业务逻辑测试套件...")
    start_time = time.time()
    
    try:
        test_system_health()
        test_worldview_lifecycle()
        test_outline_lifecycle()
        test_chapter_lifecycle()
        test_world_hierarchy_lifecycle_bridge()
        test_hierarchy_agent_workflow_bridge()
        test_config_persistence()
        test_agent_stream()
        
        duration = time.time() - start_time
        print(f"\n🎉 测试全部通过！耗时: {duration:.2f}s")
        print("物理副作用已核实，业务逻辑闭环，无 MOCK，无虚假降级。")
    except Exception as e:
        print(f"\n💥 测试过程中发生未捕获异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
