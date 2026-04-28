import requests
import pymongo
import uuid
import time
import sys
import os

# 确保能引用到 src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.common.lore_utils import get_mongodb_db

BASE_URL = "http://localhost:5005"

def run_clinical_test():
    print("🧪 启动 API 临床级物理验证...")
    db = get_mongodb_db()
    
    # --- 测试项 1: 物理删除 (Worldview 类型) ---
    print("\n[Case 1] 物理删除验证 (Worldview)")
    test_id = f"test_lore_{uuid.uuid4().hex[:6]}"
    # 预埋数据
    db["lore"].insert_one({"doc_id": test_id, "name": "待删除条目", "content": "物理删除测试内容"})
    print(f"  - 物理准备: 已在 MongoDB 插入条目 {test_id}")
    
    # 发起真实请求
    response = requests.delete(f"{BASE_URL}/api/archive/delete", json={
        "id": test_id,
        "type": "worldview"
    })
    
    # 物理断言
    print(f"  - API 状态码: {response.status_code}")
    print(f"  - API 响应: {response.json()}")
    
    time.sleep(0.5) # 给数据库一点反应时间
    doc_after = db["lore"].find_one({"doc_id": test_id})
    if response.status_code == 200 and doc_after is None:
        print("  ✅ 结果: 物理删除成功，MongoDB 记录已消失。")
    else:
        print("  ❌ 结果: 物理删除失败！记录依然存在。")
        sys.exit(1)

    # --- 测试项 2: 小说项目删除 (Novel 类型) ---
    print("\n[Case 2] 小说项目物理删除验证")
    novel_id = f"test_novel_{uuid.uuid4().hex[:6]}"
    db["novels"].insert_one({"id": novel_id, "title": "待删除小说"})
    
    response = requests.delete(f"{BASE_URL}/api/archive/delete", json={
        "id": novel_id,
        "type": "novel"
    })
    
    print(f"  - API 状态码: {response.status_code}")
    doc_after = db["novels"].find_one({"id": novel_id})
    if response.status_code == 200 and doc_after is None:
        print("  ✅ 结果: 小说项目物理删除成功。")
    else:
        print("  ❌ 结果: 小说项目物理删除失败。")
        sys.exit(1)

    # --- 测试项 3: 异常场景 (不存在的 ID) ---
    print("\n[Case 3] 异常场景验证 (不存在的 ID)")
    response = requests.delete(f"{BASE_URL}/api/archive/delete", json={
        "id": "non_existent_id",
        "type": "worldview"
    })
    print(f"  - API 状态码 (预期 404): {response.status_code}")
    if response.status_code == 404:
        print("  ✅ 结果: 异常处理正确。")
    else:
        print("  ❌ 结果: 异常处理不符合预期。")
        sys.exit(1)

    # --- 测试项 4: 异常场景 (缺少参数) ---
    print("\n[Case 4] 特殊情况验证 (缺少参数)")
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
        print("❌ 错误: 无法连接到服务器。请确保执行了 'make restart' 且服务在 http://localhost:5005 运行。")
        sys.exit(1)
