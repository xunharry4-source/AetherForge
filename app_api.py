from flask import Flask, jsonify, request, send_file
import os
import json
from worldview_agent_langgraph import app as worldview_app
from novel_outline_agent_langgraph import app as outline_app
from writing_execution_agent_langgraph import app as writing_app

app = Flask(__name__)

# Agent Mapping
AGENTS = {
    "worldview": worldview_app,
    "outline": outline_app,
    "writing": writing_app
}

# 用于存储大纲以便写作 Agent 使用 (模拟 MongoDB)
def get_outline_by_id(outline_id):
    if not os.path.exists('outlines_db.json'): return None
    with open('outlines_db.json', 'r', encoding='utf-8') as f:
        for line in f:
            data = json.loads(line)
            if data['id'] == outline_id:
                return data['outline']
    return None

# 配置信息加载
from config_utils import CONFIG
GOOGLE_API_KEY = CONFIG.get("GOOGLE_API_KEY")

@app.route('/')
def index():
    return send_file('dashboard.html')

@app.route('/api/lore', methods=['GET'])
def get_lore():
    all_docs = []
    
    # 1. Worldview (JSONL)
    if os.path.exists('worldview_db.json'):
        with open('worldview_db.json', 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip(): continue
                try:
                    item = json.loads(line)
                    all_docs.append({
                        "name": item.get("name") or item.get("query"),
                        "content": item.get("content"),
                        "category": item.get("category", "Worldview"),
                        "timestamp": item.get("timestamp", "N/A")
                    })
                except: pass

    # 2. Outlines (JSONL)
    if os.path.exists('outlines_db.json'):
        with open('outlines_db.json', 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip(): continue
                try:
                    item = json.loads(line)
                    all_docs.append({
                        "name": f"大纲: {item.get('query', '未命名')[:20]}...",
                        "content": f"大纲 ID: {item.get('id')}\n\n{item.get('proposal')}",
                        "category": "Outline",
                        "timestamp": item.get("timestamp", "刚刚")
                    })
                except: pass

    # 3. Prose (JSONL)
    if os.path.exists('prose_db.json'):
        with open('prose_db.json', 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip(): continue
                try:
                    item = json.loads(line)
                    all_docs.append({
                        "name": f"正文: {item.get('scene_title')}",
                        "content": f"场次 ID: {item.get('scene_id', 'N/A')}\n\n{item.get('content')}",
                        "category": "Prose",
                        "timestamp": item.get("timestamp", "刚刚")
                    })
                except: pass

    return jsonify(all_docs[::-1])

@app.route('/api/agent/query', methods=['POST'])
def agent_query():
    try:
        data = request.json
        query = data.get('query', '')
        thread_id = data.get('thread_id', 'default_user')
        agent_type = data.get('agent_type', 'worldview')
        
        agent_app = AGENTS.get(agent_type)
        if not agent_app:
             return jsonify({"error": f"Agent '{agent_type}' 未就绪"}), 500
             
        config = {"configurable": {"thread_id": thread_id}}
        
        # 初始化状态
        if agent_type == 'writing':
            outline_id = query # 初始 query 是大纲 ID
            outline_content = get_outline_by_id(outline_id)
            if not outline_content:
                return jsonify({"error": f"大纲 ID '{outline_id}' 不存在"}), 400
            
            input_state = {
                "outline_id": outline_id,
                "outline_content": json.dumps(outline_content, ensure_ascii=False),
                "current_act": "第一幕", # 默认起点
                "status_message": "启动中，正在拆解场次...",
                "active_scene_index": 0,
                "scene_list": []
            }
        else:
            input_state = {
                "query": query,
                "user_feedback": "",
                "iterations": 0, "audit_count": 0, "is_approved": False,
            }
        
        output = agent_app.invoke(input_state, config=config)
        return jsonify(output)
    except Exception as e:
        print(f"[API ERROR] Query failed: {e}")
        return jsonify({"error": str(e), "status_message": "系统处理异常，请重试。"}), 500

@app.route('/api/agent/feedback', methods=['POST'])
def agent_feedback():
    try:
        data = request.json
        feedback = data.get('feedback', '')
        thread_id = data.get('thread_id', 'default_user')
        agent_type = data.get('agent_type', 'worldview')
        
        agent_app = AGENTS.get(agent_type)
        if not agent_app:
             return jsonify({"error": f"Agent '{agent_type}' 未就绪"}), 500
             
        config = {"configurable": {"thread_id": thread_id}}
        
        # 显式传递反馈给状态机
        output = agent_app.invoke({"user_feedback": feedback}, config=config)
        return jsonify(output)
    except Exception as e:
        print(f"[API ERROR] Feedback failed: {e}")
        return jsonify({"error": str(e), "status_message": "反馈处理异常，请检查网络或会话。"}), 500

@app.route('/api/search', methods=['POST'])
def search_lore():
    try:
        data = request.json
        query = data.get('query', '')
        if not query:
            return jsonify([])

        # 延迟加载 Chroma 以避免不必要的依赖冲突
        from langchain_chroma import Chroma
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        import chromadb
        
        embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001", google_api_key=GOOGLE_API_KEY, task_type="retrieval_document")
        chroma_client = chromadb.PersistentClient(path="./chroma_db")
        
        # 核心：必须使用与 ingest_lore.py 一致的 collection_name
        vector_store = Chroma(client=chroma_client, collection_name="pga_lore", embedding_function=embeddings)
        
        docs = vector_store.similarity_search(query, k=5)
        formatted = []
        for d in docs:
            formatted.append({
                "name": d.metadata.get('name', '搜索结果'),
                "content": d.page_content,
                "category": d.metadata.get('category', 'Search'),
                "timestamp": "检索中"
            })
        print(f"[SEARCH SUCCESS] Query: '{query}', Results: {len(formatted)}")
        return jsonify(formatted)
    except Exception as e:
        print(f"[SEARCH ERROR] {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/snapshots/<outline_id>', methods=['GET'])
def get_snapshots(outline_id):
    snapshots = []
    if os.path.exists('snapshots_db.json'):
        with open('snapshots_db.json', 'r', encoding='utf-8') as f:
            for line in f:
                data = json.loads(line)
                if data.get('outline_id') == outline_id:
                    snapshots.append(data)
    return jsonify(snapshots)

if __name__ == '__main__':
    # 启动 unified 服务
    app.run(port=5005, host='0.0.0.0')
