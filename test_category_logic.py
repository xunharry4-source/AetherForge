import os
import json

# Manual extraction of the logic from worldview_agent_langgraph.py for verification
def detect_category(query):
    query_lower = query.lower()
    # 势力关键词
    if any(k in query_lower for k in ["势力", "组织", "阵营", "国家", "派系", "帝国", "联邦", "军团", "公约"]):
        return "faction"
    # 种族关键词
    elif any(k in query_lower for k in ["种族", "生物", "机器人", "机械族", "生命", "进化", "族群"]):
        return "race"
    # 地理关键词
    elif any(k in query_lower for k in ["地理", "星球", "星系", "地形", "环境", "星域", "戴森球"]):
        return "geography"
    # 科技/机制关键词
    elif any(k in query_lower for k in ["机制", "科技", "武器", "引擎", "原理", "技术", "装置", "协议"]):
        return "mechanism_tech"
    # 历史关键词
    elif any(k in query_lower for k in ["历史", "纪元", "事件", "变迁", "战争", "编年史"]):
        return "history"
    return "general"

test_cases = [
    ("创建一个新的星际势力：极光联邦", "faction"),
    ("描述熵族的生物演化特征", "race"),
    ("分析天琴座星区的地理环境", "geography"),
    ("解释戴森球的能量转化机制", "geography"), # '戴森球' is in geography, but '机制' is in mechanism. Geography has higher priority here? Wait.
    ("开发一种基于热力学第二定律的湮灭发动机", "mechanism_tech"),
    ("记录第三纪元的星际大战争历史", "history"),
    ("创建一个帝国组织", "faction")
]

print("--- Category Detection Verification ---")
for query, expected in test_cases:
    actual = detect_category(query)
    status = "PASS" if actual == expected else "FAIL"
    print(f"Query: {query}")
    print(f"  Expected: {expected}, Actual: {actual} -> {status}")

# Also verify keywords overlap handling (e.g. '戴森球' vs '机制')
# In the code, 'faction' > 'race' > 'geography' > 'mechanism_tech' > 'history'
print("\n--- Priority & Overlap Handling ---")
q2 = "戴森球的运作机制"
print(f"Query: {q2}")
print(f"  Detected: {detect_category(q2)} (Should be 'geography' or 'mechanism_tech' depending on priority)")
