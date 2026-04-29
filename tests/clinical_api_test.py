import requests
import uuid
import time
import sys
import os

BASE_URL = "http://localhost:5006"

def run_clinical_test():
    print("🧪 启动 API 临床级严格验证 (纯 API 流)...")
    
    # --- 测试项 1: 物理删除 (Worldview 类型) ---
    print("\n[Case 1] 物理删除验证 (Worldview)")
    test_id = f"test_lore_{uuid.uuid4().hex[:6]}"
    # 通过 API 创建数据
    res_create = requests.post(f"{BASE_URL}/api/archive/update", json={
        "id": test_id,
        "type": "worldview",
        "name": "待删除条目",
        "content": "物理删除测试内容",
        "worldview_id": "default_wv"
    })
    if res_create.status_code != 200:
        print(f"  ❌ 结果: API 创建前置数据失败！{res_create.text}")
        sys.exit(1)
    print(f"  - 物理准备: 已通过 API 插入条目 {test_id}")
    
    # 发起真实删除请求
    response = requests.delete(f"{BASE_URL}/api/archive/delete", json={
        "id": test_id,
        "type": "worldview",
        "worldview_id": "default_wv"
    })
    
    # 物理断言：通过 API 查不到
    print(f"  - API 状态码: {response.status_code}")
    print(f"  - API 响应: {response.json()}")
    
    res_list = requests.get(f"{BASE_URL}/api/lore/list", params={"worldview_id": "default_wv", "page": 1, "page_size": 50})
    items = res_list.json()
    doc_after = next((i for i in items if i.get("id") == test_id), None)
    
    if response.status_code == 200 and doc_after is None:
        print("  ✅ 结果: 物理删除成功，API 查询已找不到该记录。")
    else:
        print("  ❌ 结果: 物理删除失败！API 返回 200，但记录依然可查。")
        sys.exit(1)

    # --- 测试项 2: 小说项目删除 (Novel 类型) ---
    print("\n[Case 2] 小说项目物理删除验证")
    
    # 必须先创建一个物理世界，否则小说会报找不到父节点 404
    world_id = f"test_world_{uuid.uuid4().hex[:6]}"
    res_create_world = requests.post(f"{BASE_URL}/api/worlds/create", json={
        "world_id": world_id,
        "name": "待删除小说的父世界",
        "summary": "父世界摘要"
    })
    if res_create_world.status_code == 200 and "world_id" in res_create_world.json():
        world_id = res_create_world.json()["world_id"]
        
    novel_id = f"test_novel_{uuid.uuid4().hex[:6]}"
    res_create_novel = requests.post(f"{BASE_URL}/api/novels/create", json={
        "name": "待删除小说",
        "world_id": world_id,
        "novel_id": novel_id
    })
    
    if res_create_novel.status_code != 200:
        print(f"  ❌ 结果: API 创建前置小说数据失败！{res_create_novel.text}")
        sys.exit(1)
        
    if "novel_id" in res_create_novel.json():
        novel_id = res_create_novel.json()["novel_id"]
    
    response = requests.delete(f"{BASE_URL}/api/novels/delete", json={
        "novel_id": novel_id,
        "cascade": True
    })
    
    print(f"  - API 状态码: {response.status_code}")
    res_list_novel = requests.get(f"{BASE_URL}/api/novels/list", params={"world_id": world_id, "page": 1, "page_size": 50})
    novels = res_list_novel.json()
    doc_after = next((n for n in novels if n.get("novel_id") == novel_id), None)
    
    if response.status_code == 200 and doc_after is None:
        print("  ✅ 结果: 小说项目物理删除成功。")
    else:
        print(f"  ❌ 结果: 小说项目物理删除失败。返回码: {response.status_code}")
        sys.exit(1)
        
    # --- 测试项 3: 列表查询必填项验证 (分析发现 UI 400 错误的根源) ---
    print("\n[Case 3] 列表查询必填项严格验证")
    print("  - 场景 A: 无参数调用 outlines/list")
    res_no_param = requests.get(f"{BASE_URL}/api/outlines/list")
    if res_no_param.status_code == 400:
        print("  ✅ 验证成功: API 正确拒绝了无参数请求 (400)")
    else:
        print(f"  ❌ 验证失败: API 应该返回 400 但返回了 {res_no_param.status_code}")
        sys.exit(1)

    print("  - 场景 B: 仅带过滤参数不带分页参数")
    res_no_page = requests.get(f"{BASE_URL}/api/outlines/list", params={"world_id": world_id})
    if res_no_page.status_code == 400 and "pagination" in res_no_page.json().get("error", ""):
        print("  ✅ 验证成功: API 正确识别分页参数缺失 (400)")
    else:
        print(f"  ❌ 验证失败: API 分页校验逻辑异常 {res_no_page.status_code}")
        sys.exit(1)

    # 顺手删掉父世界
    requests.delete(f"{BASE_URL}/api/worlds/delete", json={"world_id": world_id, "cascade": True})

    # --- 测试项 4: 异常场景 (不存在的 ID) ---
    print("\n[Case 4] 异常场景验证 (不存在的 ID)")
    response = requests.delete(f"{BASE_URL}/api/archive/delete", json={
        "id": "non_existent_id",
        "type": "worldview",
        "worldview_id": "default_wv"
    })
    print(f"  - API 状态码 (预期 404): {response.status_code}")
    if response.status_code == 404:
        print("  ✅ 结果: 异常处理正确。")
    else:
        print("  ❌ 结果: 异常处理不符合预期。")
        sys.exit(1)

    # --- 测试项 5: 异常场景 (缺少参数) ---
    print("\n[Case 5] 特殊情况验证 (缺少参数)")
    response = requests.delete(f"{BASE_URL}/api/archive/delete", json={
        "id": "missing_type"
    })
    print(f"  - API 状态码 (预期 400): {response.status_code}")
    if response.status_code == 400:
        print("  ✅ 结果: 校验逻辑生效。")
    else:
        print("  ❌ 结果: 校验逻辑失效。")
        sys.exit(1)

    print("\n🎉 所有 API 临床级测试通过！系统稳定性与正确性已得到物理证明。")

if __name__ == "__main__":
    try:
        run_clinical_test()
    except requests.exceptions.ConnectionError:
        print("❌ 错误: 无法连接到服务器。请确保执行了 'make restart' 且服务在 http://localhost:5006 运行。")
        sys.exit(1)
