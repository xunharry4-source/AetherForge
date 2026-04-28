"""
API 入口模块 (App API) - PGA 小说创作引擎后端服务

本模块提供了基于 Flask 的 RESTful API 接口，负责连接前端 UI 与后端的 LangGraph Agents。
其核心职责包括：
1. 状态装载与持久化: 维护会话线程 (thread_id)，通过 LangGraph Checkpointer 实现状态恢复。
2. 异常处理与自愈: 捕获 API 限制错误 (429)，并自动触发 API Key 旋转机制。
3. 文献检索与管理: 提供统一的资料搜索和模板存取接口。
4. 人机交互路由: 将用户反馈正确引导至对应的 Agent 暂停点。
"""
from flask import Flask, request, jsonify, render_template, send_from_directory, send_file, Response
import os
import json
import re
import uuid
import time
import traceback
import shutil
from typing import Any, Dict, List, Optional, Union
import threading
import queue
from langgraph.types import Command
from flask_cors import CORS
from src.common.logger_utils import get_logger

logger = get_logger("novel_agent.api")
# 尝试导入观测与监控插件 (Graceful Observability Imports)
HAS_SENTRY = False
try:
    import sentry_sdk
    from sentry_sdk.integrations.flask import FlaskIntegration
    HAS_SENTRY = True
    logger.info("sentry-sdk initialized successfully.")
except ImportError:
    logger.warning("sentry-sdk not installed, error tracking disabled.")

HAS_PROMETHEUS = False
try:
    from prometheus_flask_exporter import PrometheusMetrics
    import prometheus_client
    HAS_PROMETHEUS = True
    logger.info("prometheus-flask-exporter initialized.")
except ImportError:
    logger.warning("prometheus-flask-exporter not installed, metrics disabled.")

# Import shared utilities
from src.common.lore_utils import (
    AtomicLogHandler,
    add_new_category,
    approve_draft_entity,
    batch_approve_draft_entities,
    batch_reject_draft_entities,
    delete_category_template,
    get_db_path,
    get_all_templates,
    delete_lore_vector,
    get_all_lore_items,
    get_draft_entities,
    get_langfuse_callback,
    get_lore_by_doc_id,
    get_mongodb_db,
    get_prohibited_rules,
    get_vector_store,
    report_token_usage,
    rotate_api_key,
    sync_archive_to_all_stores,
    upsert_category_template,
)
from src.worldview.worldview_agent_langgraph import app as worldview_app
from src.outline.novel_outline_agent_langgraph import app as outline_app
from src.novel.writing_execution_agent_langgraph import app as writing_app
from src.router_agent_langgraph import app as router_app
from src.worldview.worldview_import_agent import app as import_app
from src.cosmos_brain_agent import app as brain_app
from src.common.config_utils import get_config
from src.novel.batch_writer_utils import BatchWriter

# Load configuration for observability
CONFIG = get_config()

# --- Initialize Observability Stack ---

app = Flask(__name__, static_folder='static', static_url_path='/static')
CORS(app)  # Enable CORS for all routes securely

# 初始化 Sentry
if HAS_SENTRY and CONFIG.get("SENTRY_DSN"):
    sentry_sdk.init(
        dsn=CONFIG["SENTRY_DSN"],
        integrations=[FlaskIntegration()],
        traces_sample_rate=1.0,
        profiles_sample_rate=1.0,
    )
    print("[INFO] Sentry initialized.")

# 初始化 Prometheus 指标
metrics = None
if HAS_PROMETHEUS:
    metrics = PrometheusMetrics(app)
    metrics.info('app_info', 'Novel Agent API info', version='1.0.0')

    # 定义自定义指标
    TOKEN_USAGE_COUNTER = prometheus_client.Counter(
        'llm_token_usage_total',
        'Total LLM token usage',
        ['model', 'token_type', 'agent_name']
    )
    LLM_REQUEST_COUNTER = prometheus_client.Counter(
        'llm_requests_total',
        'Total LLM requests count',
        ['model', 'agent_name']
    )
    print("[INFO] Prometheus metrics enabled.")
else:
    # 如果没有安装 prometheus，定义一个 Mock 计数器避免代码崩溃
    class MockCounter:
        def labels(self, *args, **kwargs): return self
        def inc(self, amount=1): pass
        def collect(self): 
            return [type('obj', (), {'samples': []})]
    TOKEN_USAGE_COUNTER: Any = MockCounter()
    LLM_REQUEST_COUNTER: Any = MockCounter()
# token_type: prompt / completion


# Agent Mapping
AGENTS = {
    "worldview": worldview_app,
    "outline": outline_app,
    "writing": writing_app,
    "router": router_app,
    "import": import_app,
    "brain": brain_app
}

@app.route('/favicon.ico')
def favicon():
    return '', 204

# --- Shared Error Handler to prevent HTML responses ---
@app.errorhandler(Exception)
def handle_exception(e):
    """确保所有未捕获的异常都以 JSON 形式返回，而不是 HTML 错误页面"""
    # 如果是 404 且不是 API 路径，且不是 favicon，则静默处理
    if hasattr(e, 'code') and e.code == 404:
        return jsonify({"error": "Not Found"}), 404

    err_msg = str(e)
    print(f"[API GLOBAL ERROR]: {err_msg}")
    traceback.print_exc()
    
    return jsonify({
        "error": "Internal Server Error",
        "details": err_msg,
        "status_message": "系统后端发生异常，请检查控制台日志。"
    }), 500


# --- Template Management Endpoints ---
@app.route('/api/worldview/templates', methods=['GET'])
def get_templates():
    """获取所有世界观模板"""
    try:
        templates = get_all_templates()
        return jsonify(templates)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/worldview/templates', methods=['POST'])
def update_template():
    """更新或创建世界观模板"""
    data = request.json
    category = data.get('category')
    template_data = data.get('template_data')
    if not category or not template_data:
        return jsonify({"error": "缺少分类或模板数据"}), 400
    try:
        success = upsert_category_template(category, template_data)
        if success:
            return jsonify({"message": f"模板 '{category}' 更新成功"})
        else:
            return jsonify({"error": "模板更新失败"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/worldview/templates', methods=['DELETE'])
def delete_template():
    """删除指定分类模板"""
    data = request.json
    category = data.get('category')
    if not category:
        return jsonify({"error": "缺少分类名称"}), 400
    try:
        success = delete_category_template(category)
        if success:
            return jsonify({"message": f"分类 '{category}' 已删除"})
        else:
            return jsonify({"error": f"分类 '{category}' 不存在"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/worldview/templates/new-category', methods=['POST'])
def create_new_category():
    """创建新的分类模板"""
    data = request.json
    category = data.get('category')
    name_zh = data.get('name_zh')
    template_fields = data.get('template')
    example_fields = data.get('example')
    
    if not category or not name_zh:
        return jsonify({"error": "缺少分类标识(category)或中文名(name_zh)"}), 400
    
    try:
        success, msg = add_new_category(category, name_zh, template_fields, example_fields)
        if success:
            return jsonify({"message": msg})
        else:
            return jsonify({"error": msg}), 409
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# 用于存储大纲以便写作 Agent 使用 (模拟 MongoDB)
def get_outline_by_id(outline_id: str) -> Optional[Dict[str, Any]]:
    """获取大纲及其关联的世界观信息。"""
    db_path = get_db_path("outlines_db.json")
    if not os.path.exists(db_path):
        return None
    try:
        with open(db_path, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    if data.get('id') == outline_id:
                        return data # 返回完整记录，包含 worldview_id
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.error(f"Error reading outlines DB: {e}")
    return None

@app.route('/')
def index():
    from flask import make_response
    response = make_response(send_file('dashboard.html'))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/assets/<path:filename>')
def serve_assets(filename):
    return send_from_directory('assets', filename)

@app.route('/api/lore/all', methods=['GET'])
def api_get_all_lore():
    outline_id = request.args.get('outline_id')
    worldview_id = request.args.get('worldview_id')
    return jsonify(get_all_lore_items(outline_id=outline_id, worldview_id=worldview_id))

@app.route('/api/lore/list', methods=['GET'])
def api_list_lore():
    """Route to list all lore items, supporting filtering."""
    oid = request.args.get('outline_id')
    wid = request.args.get('worldview_id')
    items = get_all_lore_items(outline_id=oid, worldview_id=wid)
    return jsonify(items)

@app.route('/api/lore', methods=['GET'])
def get_lore():
    outline_id = request.args.get('outline_id')
    worldview_id = request.args.get('worldview_id')
    return jsonify(get_all_lore_items(outline_id=outline_id, worldview_id=worldview_id))

@app.route('/api/lore/tree', methods=['GET'])
def get_lore_tree():
    """Returns lore organized in a tree structure by category."""
    outline_id = request.args.get('outline_id')
    worldview_id = request.args.get('worldview_id')
    all_docs = get_all_lore_items(outline_id=outline_id, worldview_id=worldview_id)
    # Type hint for Pyre
    tree_data: Dict[str, Any] = {"name": "Root", "children": {}, "entries": []}
    
    for doc in all_docs:
        cat_path = doc.get("category", "Uncategorized")
        parts = [p.strip() for p in cat_path.split(">")]
        
        curr = tree_data
        for part in parts:
            children: Dict[str, Any] = curr["children"]
            if part not in children:
                children[part] = {"name": part, "children": {}, "entries": []}
            curr = children[part]
        
        curr["entries"].append(doc)
    
    def format_node(node):
        return {
            "name": node["name"],
            "children": [format_node(c) for c in node["children"].values()],
            "entries": node["entries"]
        }
    
    return jsonify(format_node(tree_data))
@app.route('/api/lore/mindmap', methods=['GET'])
def get_lore_mindmap():
    """Returns lore in Markdown format for mindmap visualization."""
    outline_id = request.args.get('outline_id')
    worldview_id = request.args.get('worldview_id')
    all_docs = get_all_lore_items(outline_id=outline_id, worldview_id=worldview_id)
    # Build internal tree first
    tree_data: Dict[str, Any] = {"name": "PGA 万象星际全息关系图", "children": {}, "entries": []}
    for doc in all_docs:
        cat_path = doc.get("category", "Uncategorized")
        # Split by > or /
        parts = [p.strip() for p in re.split(r'[>/]', cat_path)]
        curr = tree_data
        for part in parts:
            children: Dict[str, Any] = curr["children"]
            if part not in children:
                children[part] = {"name": part, "children": {}, "entries": []}
            curr = children[part]
        curr["entries"].append(doc)

    def to_markdown(node, level=0):
        # Use # hierarchy for better markmap rendering
        prefix = "#" * (level + 1)
        md = f"{prefix} {node['name']}\n\n"
        for child in node["children"].values():
            md += to_markdown(child, level + 1)
        for entry in node["entries"]:
            # Sanitize name
            name = entry['name'].replace('\\', '').replace('`', '')
            md += f"{'#' * (level + 2)} {name}\n\n"
        return md

    return to_markdown(tree_data)

@app.route('/api/lore/entity-graph/<doc_id>', methods=['GET'])
def get_entity_graph(doc_id):
    """Returns a local or global relationship graph around entities."""
    outline_id = request.args.get('outline_id')
    worldview_id = request.args.get('worldview_id')
    all_docs = get_all_lore_items(outline_id=outline_id, worldview_id=worldview_id)
    
    if doc_id == "all":
        # Global graph mode
        nodes = []
        links = []
        seen_ids = set()
        
        # Limit to 50 nodes for performance in global view
        limited_docs = all_docs[:50]
        
        for doc in limited_docs:
            nodes.append({
                "id": doc['id'], 
                "name": doc['name'], 
                "type": doc['type'], 
                "val": 20 if doc['type'] == 'entity' else 10
            })
            seen_ids.add(doc['id'])
            
        # Discover links between all nodes in the limited set
        for i in range(len(limited_docs)):
            for j in range(i + 1, len(limited_docs)):
                d1 = limited_docs[i]
                d2 = limited_docs[j]
                
                # Check for mutual mentions
                d1_content = (d1.get('content') or "").lower()
                d2_content = (d2.get('content') or "").lower()
                d1_name = d1['name'].lower()
                d2_name = d2['name'].lower()
                
                if d1_name in d2_content or d2_name in d1_content:
                    links.append({
                        "source": d1['id'],
                        "target": d2['id'],
                        "type": "mention",
                        "value": 1
                    })
        
        return jsonify({"nodes": nodes, "links": links})

    # Local graph mode (original logic)
    target = next((d for d in all_docs if d['id'] == doc_id), None)
    if not target:
        target = next((d for d in all_docs if d['name'] == doc_id), None)
        
    if not target:
        return jsonify({"nodes": [], "links": []}), 404
    
    nodes = [{"id": target['id'], "name": target['name'], "type": target['type'], "val": 30}]
    links = []
    seen_nodes = {target['id']}
    
    target_name = target['name'].lower()
    for doc in all_docs:
        if doc['id'] == target['id']: continue
        
        doc_content = (doc.get('content') or "").lower()
        doc_name = doc['name'].lower()
        
        is_linked = False
        if target_name in doc_content or target_name in doc_name:
            is_linked = True
        elif doc_name in (target.get('content') or "").lower():
            is_linked = True
            
        if is_linked:
            if doc['id'] not in seen_nodes:
                nodes.append({"id": doc['id'], "name": doc['name'], "type": doc['type'], "val": 15})
                seen_nodes.add(doc['id'])
            
            links.append({
                "source": target['id'], 
                "target": doc['id'], 
                "type": "mention",
                "value": 2
            })
            
    if len(nodes) > 30: # Slightly increased limit
        nodes = nodes[:30]
    
    valid_node_ids = {n['id'] for n in nodes}
    links = [l for l in links if l['source'] in valid_node_ids and l['target'] in valid_node_ids]

    return jsonify({"nodes": nodes, "links": links})

@app.route('/api/lore/export/opml', methods=['GET'])
def export_lore_opml():
    """Exports all lore as an OPML file."""
    outline_id = request.args.get('outline_id')
    worldview_id = request.args.get('worldview_id')
    all_docs = get_all_lore_items(outline_id=outline_id, worldview_id=worldview_id)
    tree_data = {"name": "PGA Worldview", "children": {}, "entries": []}
    for doc in all_docs:
        cat_path = doc.get("category", "Uncategorized")
        parts = [p.strip() for p in cat_path.split(">")]
        curr = tree_data
        for part in parts:
            if part not in curr["children"]:
                curr["children"][part] = {"name": part, "children": {}, "entries": []}
            curr = curr["children"][part]
        curr["entries"].append(doc)

    def to_opml_outline(node):
        safe_name = node["name"].replace('"', '&quot;').replace('<', '&lt;').replace('>', '&gt;')
        res = f'<outline text="{safe_name}">\n'
        for child in node["children"].values():
            res += to_opml_outline(child)
        for entry in node["entries"]:
            safe_entry_name = entry["name"].replace('"', '&quot;').replace('<', '&lt;').replace('>', '&gt;')
            # We can put content in _note or as a child node
            res += f'  <outline text="{safe_entry_name}" />\n'
        res += '</outline>\n'
        return res

    opml_head = '<?xml version="1.0" encoding="UTF-8"?>\n<opml version="2.0">\n  <head><title>PGA Worldview Export</title></head>\n  <body>\n'
    opml_body = to_opml_outline(tree_data)
    opml_foot = '  </body>\n</opml>'
    
    from flask import Response
    return Response(
        opml_head + opml_body + opml_foot,
        mimetype='text/xml',
        headers={'Content-Disposition': 'attachment;filename=worldview_export.opml'}
    )

@app.route('/api/archive/update', methods=['POST'])
def update_archive():
    """更新或创建存档条目 (Worldview, Outline, Prose) - MongoDB 物理写入"""
    data = request.json or {}
    item_id = data.get('id')
    item_type = data.get('type')
    new_content = data.get('content')
    new_name = data.get('name')
    category = data.get('category')
    outline_id = data.get('outline_id')
    worldview_id = data.get('worldview_id')
            
    # MongoDB 物理写入
    try:
        db = get_mongodb_db()
        collection_map = {
            'worldview': 'lore',
            'outline': 'outlines',
            'prose': 'prose',
            'novel': 'novels',
            'entity-draft': 'entity_drafts'
        }
        coll_name = collection_map.get(str(item_type))
        if not coll_name:
            return jsonify({"error": f"Invalid type: {item_type}"}), 400
            
        coll = db[coll_name]
        
        # 准备数据对象
        import datetime
        now = datetime.datetime.now().isoformat()
        
        # 确定查询和更新字段
        if item_type == 'worldview':
            query = {"doc_id": item_id}
            update_data = {"content": new_content, "name": new_name, "timestamp": now}
            if category: update_data["category"] = category
        elif item_type == 'prose':
            query = {"$or": [{"scene_id": item_id}, {"id": item_id}]}
            update_data = {"content": new_content, "title": new_name, "timestamp": now}
        elif item_type == 'outline':
            query = {"$or": [{"outline_id": item_id}, {"id": item_id}]}
            update_data = {"content": new_content, "name": new_name, "timestamp": now}
        elif item_type == 'entity-draft':
            query = {"id": item_id}
            update_data = {"status": "pending", "timestamp": now} # 草稿通常只更新状态或内容
        
        # 执行更新 (物理副作用)
        res = coll.update_one(query, {"$set": update_data}, upsert=True)
        
        # 同步到 ChromaDB (仅限 worldview 和 outline)
        if item_type in ['worldview', 'outline']:
            from src.common.lore_utils import sync_archive_to_all_stores
            sync_archive_to_all_stores(item_id, item_type, new_content, new_name, outline_id)
            
        return jsonify({"status": "success", "id": item_id, "type": item_type, "modified": res.modified_count})
    except Exception as e:
        logger.error(f"Failed to update archive: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/archive/delete', methods=['DELETE'])
def delete_archive():
    """从 MongoDB 数据库中永久删除条目，并同步清理向量索引。"""
    data = request.json or {}
    logger.info(f"[API] Delete request received: {data}")
    item_id = data.get('id')
    item_type = data.get('type')
    outline_id = data.get('outline_id')
    worldview_id = data.get('worldview_id')
    
    if not item_id or not item_type:
        logger.warning(f"[API] Delete 400: Missing id({item_id}) or type({item_type})")
        return jsonify({"error": "Missing id or type"}), 400
        
    try:
        db = get_mongodb_db()
        collection_map = {
            'worldview': 'lore',
            'outline': 'outlines',
            'prose': 'prose',
            'novel': 'novels',
            'entity-draft': 'entity_drafts'
        }
        coll_name = collection_map.get(str(item_type))
        if not coll_name:
            return jsonify({"error": f"Invalid type: {item_type}"}), 400
            
        coll = db[coll_name]
        
        # 构造多键名兼容的查询
        query = {
            "$or": [
                {"id": item_id},
                {"doc_id": item_id},
                {"scene_id": item_id},
                {"outline_id": item_id}
            ]
        }
        
        # 1. 物理执行 MongoDB 删除
        res = coll.delete_one(query)
        
        if res.deleted_count > 0:
            # 2. 同步清理向量库 (ChromaDB)
            try:
                # 某些类型可能没有向量索引，静默处理
                delete_lore_vector(item_id, outline_id=outline_id, worldview_id=worldview_id)
            except Exception as ve:
                logger.warning(f"Vector delete skipped or failed: {ve}")
                
            return jsonify({
                "status": "success", 
                "message": f"Item {item_id} of type {item_type} deleted from {coll_name}",
                "deleted_count": res.deleted_count
            })
        else:
            return jsonify({"error": f"Item {item_id} not found in {coll_name}"}), 404
            
    except Exception as e:
        logger.error(f"Deletion failed: {e}")
        return jsonify({"error": f"Deletion failed: {e}"}), 500


@app.route('/api/agent/brain', methods=['POST'])
def run_brain():
    """运行万象大脑 Agent 进行自主审计与想法扩张。"""
    data = request.json
    worldview_id = data.get('worldview_id', 'default_wv')
    outline_id = data.get('outline_id')
    thread_id = data.get('thread_id', f"brain_{uuid.uuid4().hex[:8]}")
    
    config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
    initial_state = {
        "worldview_id": worldview_id,
        "outline_id": outline_id,
        "system_rules": get_prohibited_rules(outline_id=outline_id),
        "insights": [],
        "expansion_seeds": [],
        "pending_commands": [],
        "status_message": "🧠 大脑正在启动..."
    }
    
    # 同步返回结果
    state = brain_app.invoke(initial_state, config)
    return jsonify(state)


@app.route('/api/agent/query', methods=['POST'])
def agent_query():
    data = request.json
    query = data.get('query', '')
    thread_id = data.get('thread_id', 'default_user')
    agent_type = data.get('agent_type', 'worldview')
    resume_input = data.get('resume_input')

    agent_app = AGENTS.get(agent_type)
    if not agent_app:
        return jsonify({"error": f"Agent '{agent_type}' 未就绪"}), 500
            
    config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
    
    # 1. 自动路由处理 (Router Logic)
    if agent_type == 'router':
        langfuse_handler = get_langfuse_callback()
        if langfuse_handler:
            config["callbacks"] = [langfuse_handler]

        router_state = agent_app.invoke({"query": query}, config=config)
        
        if "metadata" in router_state and "usage_metadata" in router_state["metadata"]:
            usage = router_state["metadata"]["usage_metadata"]
            report_token_usage(
                model=CONFIG.get("DEFAULT_MODEL", "gemini-flash"),
                prompt_tokens=usage.get("prompt_token_count", 0),
                completion_tokens=usage.get("candidates_token_count", 0),
                agent_name="router"
            )
        intent = router_state.get("intent", "unknown")
        
        if intent != 'unknown' and intent in AGENTS:
            agent_type = intent
            agent_app = AGENTS[intent]
        else:
            state_snapshot = agent_app.get_state(config)
            return jsonify(dict(state_snapshot.values))

    # 2. 状态初始化
    current_worldview = data.get('worldview_id') or 'default_wv'
    
    if agent_type == 'writing':
        outline_id = data.get('outline_id') or query
        record = get_outline_by_id(outline_id)
        if not record:
            return jsonify({"error": f"大纲/项目 ID '{outline_id}' 不存在"}), 400
        
        project_meta = record.get('outline', {})
        wv_id = record.get('worldview_id') or current_worldview
        
        novel_summary = project_meta.get('summary') or project_meta.get('content') or ""
        outline_details = project_meta.get('outline') or {}
        
        input_state = {
            "worldview_id": wv_id,
            "outline_id": outline_id,
            "outline_content": json.dumps(outline_details, ensure_ascii=False) if outline_details else novel_summary,
            "novel_summary": novel_summary,
            "current_act": "第一幕",
            "status_message": f"启动中 (世界观: {wv_id})，正在依大纲拆解场次...",
            "active_scene_index": 0,
            "scene_list": [],
            "context_data": "",
            "draft_content": "",
            "audit_feedback": "",
            "user_feedback": "",
            "is_audit_passed": False,
            "is_approved": False,
            "char_status_summary": "",
            "scene_status_summary": "",
            "visual_snapshot_path": "",
            "visual_description_summary": ""
        }
    elif agent_type == 'worldview':
        outline_id = data.get('outline_id', 'default')
        input_state = {
            "query": query, "worldview_id": current_worldview, "outline_id": outline_id, 
            "context": "", "proposal": "", "review_log": "", "user_feedback": "",
            "iterations": 0, "audit_count": 0, "is_approved": False, "category": "", "doc_id": "",
            "status_message": f"正在启动万象星际探查 (Worldview: {current_worldview}, Project: {outline_id})...",
            "autonomy_level": CONFIG.get("AUTONOMY_LEVEL", "safe")
        }
    elif agent_type == 'outline':
        outline_id = data.get('outline_id') or f"pga_{str(uuid.uuid4())[:8]}"
        record = get_outline_by_id(outline_id)
        
        wv_id = current_worldview
        novel_summary = ""
        if record:
            wv_id = record.get('worldview_id') or current_worldview
            novel_summary = record.get('outline', {}).get('summary') or ""
        
        input_state = {
            "query": query, "worldview_id": wv_id, "outline_id": outline_id,
            "context": "", "proposal": "", "review_log": "", "user_feedback": "",
            "iterations": 0, "audit_count": 0, "is_approved": False, "status_message": "构思中...",
            "autonomy_level": CONFIG.get("AUTONOMY_LEVEL", "safe")
        }
    elif agent_type == 'brain':
        input_state = {
            "worldview_id": current_worldview,
            "outline_id": data.get('outline_id'),
            "system_rules": get_prohibited_rules(outline_id=data.get('outline_id')),
            "insights": [],
            "expansion_seeds": [],
            "pending_commands": [],
            "status_message": "🧠 大脑深度思考中..."
        }
    else:
        return jsonify({"error": f"Unknown agent type: {agent_type}"}), 400
    
    stream_input = Command(resume=resume_input) if resume_input else input_state
    q = queue.Queue()

    def worker():
        try:
            q.put({"type": "node_update", "node": "system", "status_message": "后台已接收请求，正在处理工作流..."})
            max_retries = 5
            for attempt in range(max_retries + 1):
                try:
                    langfuse_handler = get_langfuse_callback()
                    atomic_handler = AtomicLogHandler(lambda msg: q.put({"type": "node_update", "node": "atomic", "status_message": msg}))
                    config_callbacks = [langfuse_handler] if langfuse_handler else []
                    config_callbacks.append(atomic_handler)
                    local_config = {**config, "callbacks": config_callbacks}

                    for event in agent_app.stream(stream_input, config=local_config, stream_mode="updates"):
                        for node_name, node_data in event.items():
                            status_msg = node_data.get("status_message")
                            if not status_msg:
                                friendly_names = {
                                    "retriever": "正在从知识库检索背景素材...",
                                    "planner": "正在策划大纲与章节目录...",
                                    "auditor": "正在进行逻辑一致性审计...",
                                    "grounding_audit": "正在执行素材锚定审计...",
                                    "entity_sentinel": "正在执行实体名规范化审计...",
                                    "human": "提案已就绪，等待人工审核...",
                                    "saver": "正在同步分布式存储协议...",
                                    "defense": "内容安全防御检查中...",
                                    "writing_retriever": "正在检索该场次相关的世界观背景...",
                                    "load_context": "正在对齐分布式创作协议 (SKILL)...",
                                    "write_draft": "正在根据当前锚点创作文学正文...",
                                    "audit_logic": "正在执行文学自审与逻辑边界检查...",
                                    "prose_saver": "正文已保存，正在执行向量化同步...",
                                    "snapshot_node": "正在生成场次逻辑快照...",
                                    "parse": "正在解析导入的原始文档...",
                                    "segment": "正在将文档切分为独立的设定实体...",
                                    "categorize": "正在将实体归入 0-4 逻辑架构...",
                                    "sync": "正在将导入的设定同步至数据库..."
                                }
                                status_msg = friendly_names.get(node_name, f"进度: {node_name}")
                            
                            q.put({
                                "type": "node_update", "node": node_name, "status_message": status_msg,
                                "proposal": node_data.get("proposal"), "is_approved": node_data.get("is_approved"),
                                "diagnostics": node_data.get("llm_interactions")
                            })
                    break
                except Exception as e:
                    err_str = str(e)
                    if ("429" in err_str or "RESOURCE_EXHAUSTED" in err_str) and attempt < max_retries:
                        rotate_api_key()
                        q.put({"type": "node_update", "node": "system", "status_message": f"API 配额超限，正在自动切换备用 Key 重试 (第 {attempt+1} 次)..."})
                        continue
                    else:
                        raise e

            final_snapshot = agent_app.get_state(config)
            final_state_data = dict(final_snapshot.values)
            final_state_data["type"] = "final_state"
            final_state_data["thread_id"] = thread_id
            q.put(final_state_data)
        except Exception as e:
            q.put({"type": "error", "error": str(e)})
        finally:
            q.put(None)

    worker_thread = threading.Thread(target=worker)
    worker_thread.daemon = True
    worker_thread.start()

    def generate_stream():
        while True:
            try:
                msg = q.get(timeout=5)
                if msg is None: break
                yield json.dumps(msg, ensure_ascii=False) + "\n"
            except queue.Empty:
                yield json.dumps({"type": "heartbeat", "time": time.time()}) + "\n"

    from flask import stream_with_context
    return Response(stream_with_context(generate_stream()), mimetype='application/x-ndjson')

@app.route('/api/agent/batch-write', methods=['POST'])
def agent_batch_write():
    data = request.json
    outline_id = data.get('outline_id')
    outline_content = data.get('outline_content', '')
    current_act = data.get('current_act', '')
    thread_id = data.get('thread_id', f"batch_{str(uuid.uuid4())[:8]}")
    
    config = {"configurable": {"thread_id": thread_id}}
    input_state = {"outline_id": outline_id, "outline_content": outline_content, "current_act": current_act, "is_batch_mode": True, "retry_count": 0, "status_message": "正在启动批量创作流水线 (Chapter Batch Indexing)..."}
    
    q = queue.Queue()
    def worker():
        try:
            q.put({"type": "node_update", "node": "system", "status_message": "后台已接收批量创作请求，正在初始化流水线..."})
            max_retries = 5
            for attempt in range(max_retries + 1):
                try:
                    langfuse_handler = get_langfuse_callback()
                    atomic_handler = AtomicLogHandler(lambda msg: q.put({"type": "node_update", "node": "atomic", "status_message": msg}))
                    config_callbacks = [langfuse_handler] if langfuse_handler else []
                    config_callbacks.append(atomic_handler)
                    local_config = {**config, "callbacks": config_callbacks}
                    for event in writing_app.stream(input_state, config=local_config, stream_mode="updates"):
                        for node_name, node_data in event.items():
                            status_msg = node_data.get("status_message")
                            if not status_msg:
                                extra_names = {"writing_retriever": "正在检索该场次相关的世界观背景...", "load_context": "正在对齐分布式创作协议 (SKILL)...", "write_draft": "正在根据当前锚点创作文学正文...", "audit_logic": "正在执行文学自审与逻辑边界检查...", "prose_saver": "正文已保存，正在执行向量化同步...", "snapshot_node": "正在生成场次逻辑快照...", "plan_scenes": "正在将大纲细化为具体场次..."}
                                status_msg = extra_names.get(node_name, f"进度: {node_name}")
                            q.put({"type": "node_update", "node": node_name, "status_message": status_msg, "proposal": node_data.get("proposal"), "is_approved": node_data.get("is_approved"), "diagnostics": node_data.get("llm_interactions")})
                    break
                except Exception as e:
                    err_str = str(e)
                    if ("429" in err_str or "RESOURCE_EXHAUSTED" in err_str) and attempt < max_retries:
                        rotate_api_key(); q.put({"type": "node_update", "node": "system", "status_message": f"API 配额超限，正在自动切换备用 Key 重试 (第 {attempt+1} 次)..."}); continue
                    else: raise e
            final_snapshot = writing_app.get_state(config)
            final_state_data = dict(final_snapshot.values)
            final_state_data["type"] = "final_state"
            final_state_data["thread_id"] = thread_id
            q.put(final_state_data)
        except Exception as e: q.put({"type": "error", "error": str(e)})
        finally: q.put(None)
    worker_v = threading.Thread(target=worker); worker_v.daemon = True; worker_v.start()
    def generate_stream():
        while True:
            try:
                msg = q.get(timeout=5)
                if msg is None: break
                yield json.dumps(msg, ensure_ascii=False) + "\n"
            except queue.Empty: yield json.dumps({"type": "heartbeat", "time": time.time()}) + "\n"
    from flask import stream_with_context
    return Response(stream_with_context(generate_stream()), mimetype='application/x-ndjson')

@app.route('/api/agent/feedback', methods=['POST'])
def agent_feedback():
    data = request.json
    feedback = data.get('feedback', '')
    thread_id = data.get('thread_id', 'default_user')
    agent_type = data.get('agent_type', 'worldview')
    
    agent_app = AGENTS.get(agent_type)
    if not agent_app:
        return jsonify({"error": f"Agent '{agent_type}' 未就绪"}), 500
            
    config = {"configurable": {"thread_id": thread_id}}
    print(f"\n[API] Resuming Agent '{agent_type}' for thread '{thread_id}'")
    print(f"[API] Feedback Received: '{feedback}'")
    try:
        # 检查当前状态，看是否真的在等待 interrupt
        state_snapshot = agent_app.get_state(config)
        if not state_snapshot.values:
             return jsonify({"error": "找不到该会话的状态。可能服务器已重启或会话已过期，请重新在大纲/正文 Agent 中发起任务。"}), 400
        
        from langgraph.types import Command
        langfuse_handler = get_langfuse_callback()
        if langfuse_handler:
            config["callbacks"] = [langfuse_handler]

        def generate_feedback():
            try:
                print(f"[API] Resuming Command(resume={feedback[:20]}...)")
                # 使用 Command(resume=...) 配合 stream
                for event in agent_app.stream(Command(resume=feedback), config=config, stream_mode="updates"):
                    for node_name, node_data in event.items():
                        yield json.dumps({
                            "type": "node_update",
                            "node": node_name,
                            "status_message": str(node_data.get("status_message", f"节点 {node_name} 已完成")),
                            "diagnostics": node_data.get("llm_interactions")
                        }) + "\n"
                
                # 最后发送更新后的完整状态
                new_state = agent_app.get_state(config)
                final_state = dict(new_state.values)
                final_state["type"] = "final_state"
                yield json.dumps(final_state) + "\n"
                
            except Exception as e:
                yield json.dumps({"type": "error", "error": str(e)}) + "\n"

        return Response(generate_feedback(), mimetype='application/x-ndjson')
    except Exception as e:
        raise e
        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
             if rotate_api_key():
                 from langgraph.types import Command
                 print("[API] Rotated key and retrying Agent feedback...")
                 output = agent_app.invoke(Command(resume=feedback), config=config)
                 state_snapshot = agent_app.get_state(config)
                 return jsonify(dict(state_snapshot.values))
        raise e

@app.route('/api/search', methods=['POST'])
def search_lore(retry=True):
    data = request.json
    query = data.get('query', '')
    if not query:
        return jsonify([])

    try:
        outline_id = data.get('outline_id')
        vector_store = get_vector_store(outline_id=outline_id)
        if not vector_store:
            print("[SEARCH ERROR] Vector store initialization failed.")
            return jsonify([])
        
        # 1. 初始向量检索 (检索子片段或父节点)
        docs = vector_store.similarity_search(query, k=10)
        print(f"[DEBUG SEARCH] Raw docs found: {len(docs)}")
        
        seen_doc_ids = set()
        formatted = []
        
        for i, d in enumerate(docs):
            doc_type = d.metadata.get('doc_type', 'parent')
            target_id = d.metadata.get('parent_id') if doc_type == 'child' else d.metadata.get('doc_id')
            print(f"  Result {i}: Type={doc_type}, TargetID={target_id}, Content={d.page_content[:30]}...")
            
            if not target_id or target_id in seen_doc_ids:
                continue
                
            # 3. 扩展回 Parent (获取完整设定内容)
            parent_entity = get_lore_by_doc_id(target_id, outline_id=outline_id)
            if parent_entity:
                formatted.append({
                    "id": target_id,
                    "type": parent_entity.get('type') or 'worldview',
                    "name": parent_entity.get('name') or parent_entity.get('query') or '搜索结果',
                    "content": parent_entity.get('content', ''),
                    "category": parent_entity.get('category') or parent_entity.get('path') or 'Search Results',
                    "timestamp": parent_entity.get('timestamp', 'Known'),
                    "match_type": doc_type
                })
                seen_doc_ids.add(target_id)
            else:
                print(f"  WARNING: Could not find parent entity for ID: {target_id}")
                
            # 限制返回数量
            if len(formatted) >= 5:
                break
                
        print(f"[SEARCH SUCCESS] Query: '{query}', Parent Entities Found: {len(formatted)}")
        return jsonify(formatted)
        
    except Exception as e:
        print(f"[SEARCH EXCEPTION] Error: {str(e)}")
        traceback.print_exc()
        if ("429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)) and retry:
             if rotate_api_key():
                 print("[API] Rotated key and retrying Search...")
                 return search_lore(retry=False)
        print(f"[SEARCH ERROR]: {str(e)}")
        return jsonify([]) 

@app.route('/api/snapshots/<outline_id>', methods=['GET'])
def get_snapshots(outline_id):
    snapshots = []
    if os.path.exists('snapshots_db.json'):
        with open('snapshots_db.json', 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line)
                    if data.get('outline_id') == outline_id:
                        snapshots.append(data)
                except: continue
    return jsonify(snapshots)

# ==========================================
# C 层：实体哨兵 API (Entity Sentinel Endpoints)
# ==========================================

@app.route('/api/entity-drafts', methods=['GET'])
def list_entity_drafts():
    """获取待审实体列表"""
    status = request.args.get('status', 'pending')
    outline_id = request.args.get('outline_id')
    drafts = get_draft_entities(status_filter=status if status != 'all' else None, outline_id=outline_id)
    return jsonify(drafts)

@app.route('/api/entity-drafts/approve', methods=['POST'])
def approve_entity():
    """批准待审实体 → 写入正式世界观库"""
    data = request.get_json()
    if not data or 'name' not in data:
        return jsonify({"error": "缺少 name 参数"}), 400
    outline_id = data.get('outline_id')
    success = approve_draft_entity(data['name'], outline_id=outline_id)
    if success:
        return jsonify({"status": "approved", "name": data['name']})
    
    # 更详细的错误提示
    return jsonify({
        "error": f"实体 '{data['name']}' 批准失败",
        "detail": "可能原因：草案不存在、状态非 pending 或数据库写入权限问题。请刷新后重试。"
    }), 404

@app.route('/api/entity-drafts/reject', methods=['POST'])
def reject_entity():
    """拒绝待审实体"""
    data = request.get_json()
    if not data or 'name' not in data:
        return jsonify({"error": "缺少 name 参数"}), 400
    
    outline_id = data.get('outline_id')
    db_path = get_db_path("entity_drafts_db.json", outline_id=outline_id)
    
    # 更新草案库中的状态为 rejected
    if not os.path.exists(db_path):
        return jsonify({"error": "草案库不存在"}), 404
    
    all_drafts = []
    found = False
    with open(db_path, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip(): continue
            d = json.loads(line)
            # 仅拒绝 pending 状态的匹配项 (只匹配第一个)
            if not found and d.get('name') == data['name'] and d.get('status') == 'pending':
                d['status'] = 'rejected'
                found = True
            all_drafts.append(d)
    
    if not found:
        return jsonify({"error": f"实体 '{data['name']}' 未找到或已处理"}), 404
        
    # 重要：必须写回文件
    try:
        with open(db_path, 'w', encoding='utf-8') as f:
            for draft in all_drafts:
                f.write(json.dumps(draft, ensure_ascii=False) + "\n")
        return jsonify({"status": "rejected", "name": data['name']})
    except Exception as e:
        logger.error(f"Reject write failed: {e}")
        return jsonify({"error": "数据库写入失败", "detail": str(e)}), 500

@app.route('/api/entity-drafts/batch-approve', methods=['POST'])
def batch_approve():
    """批量通过实体草案"""
    data = request.get_json()
    if not data or 'names' not in data:
        return jsonify({"error": "缺少 names 参数"}), 400
    
    outline_id = data.get('outline_id')
    results = batch_approve_draft_entities(data['names'], outline_id=outline_id)
    return jsonify(results)

@app.route('/api/entity-drafts/batch-reject', methods=['POST'])
def batch_reject():
    """批量拒绝实体草案"""
    data = request.get_json()
    if not data or 'names' not in data:
        return jsonify({"error": "缺少 names 参数"}), 400
    
    outline_id = data.get('outline_id')
    results = batch_reject_draft_entities(data['names'], outline_id=outline_id)
    return jsonify(results)

@app.route('/api/entity-drafts/refine', methods=['POST'])
def refine_entity():
    """迭代修正实体草案 - 调用 Worldview Agent"""
    data = request.get_json()
    name = data.get('name')
    feedback = data.get('feedback')
    outline_id = data.get('outline_id')
    
    if not name or not feedback:
        return jsonify({"error": "缺少 name 或 feedback 参数"}), 400
    
    # 查找原始草案
    drafts = get_draft_entities(status_filter=None, outline_id=outline_id)
    target_draft = next((d for d in drafts if d['name'] == name), None)
    if not target_draft:
        return jsonify({"error": f"未找到实体草案: {name}"}), 404
        
    thread_id = f"refine_{name}_{int(time.time())}"
    config = {"configurable": {"thread_id": thread_id}}
    
    initial_state = {
        "query": name,
        "proposal": json.dumps(target_draft.get("entity_card", {}), ensure_ascii=False),
        "user_feedback": feedback,
        "category": target_draft.get("type", "general"),
        "iterations": 1,
        "outline_id": outline_id  # Ensure project context for the agent
    }
    
    def generate():
        try:
            # 直接从 generator 开始处理反馈
            for output in worldview_app.stream(initial_state, config, stream_mode="updates"):
                # 包装为 NDJSON 格式
                yield json.dumps(output, ensure_ascii=False) + "\n"
        except Exception as e:
            yield json.dumps({"error": str(e)}, ensure_ascii=False) + "\n"

    return Response(generate(), mimetype='application/x-ndjson')

# --- Import Lore Endpoints ---

# Define UPLOAD_FOLDER if not already defined
import os
UPLOAD_FOLDER = "uploads" # Assuming "uploads" is the folder used by import_upload

@app.route('/api/import/upload', methods=['POST'])
def import_upload():
    """Handles file uploads for worldview ingestion."""
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    # Save to uploads folder
    upload_path = os.path.join("uploads", file.filename)
    file.save(upload_path)
    
    return jsonify({
        "status": "success", 
        "file_path": upload_path,
        "filename": file.filename
    })

@app.route('/api/import/process', methods=['POST'])
def import_process():
    """Triggers the Import Agent for a specific file."""
    data = request.json
    file_path = data.get("file_path")
    
    if not file_path or not os.path.exists(file_path):
        return jsonify({"error": "Invalid file path"}), 400
        
    q = queue.Queue()

    def worker():
        try:
            q.put({
                "type": "node_update",
                "node": "system",
                "status_message": "后台已接收导入请求，正在解析文档..."
            })
            
            outline_id = data.get("outline_id", "default")
            max_retries = 5
            for attempt in range(max_retries + 1):
                try:
                    atomic_handler = AtomicLogHandler(lambda msg: q.put({"type": "node_update", "node": "atomic", "status_message": msg}))
                    local_config = {"callbacks": [atomic_handler]}
                    for output in import_app.stream({"file_path": file_path, "outline_id": outline_id}, config=local_config, stream_mode="updates"):
                        for node_name, node_data in output.items():
                            status_msg = node_data.get("status_message")
                            if not status_msg:
                                extra_names = {
                                    "parse": "正在解析导入的原始文档...",
                                    "segment": "正在将文档切分为独立的设定实体...",
                                    "categorize": "正在将实体归入 0-4 逻辑架构...",
                                    "sync": "正在将导入的设定同步至数据库..."
                                }
                                status_msg = extra_names.get(node_name, f"进度: {node_name}")

                            q.put({
                                "type": "node_update",
                                "node": node_name,
                                "status_message": status_msg,
                                "data": node_data
                            })
                    break
                except Exception as e:
                    err_str = str(e)
                    if ("429" in err_str or "RESOURCE_EXHAUSTED" in err_str) and attempt < max_retries:
                        rotate_api_key()
                        q.put({
                            "type": "node_update",
                            "node": "system",
                            "status_message": f"API 配额超限，正在自动切换备用 Key 重试 (第 {attempt+1} 次)..."
                        })
                        continue
                    else:
                        raise e

            q.put({"type": "final_state", "status": "completed", "file": file_path})
        except Exception as e:
            q.put({"type": "error", "error": str(e)})
        finally:
            q.put(None)

    threading.Thread(target=worker).start()

    def generate_stream():
        while True:
            try:
                msg = q.get(timeout=5)
                if msg is None:
                    break
                yield json.dumps(msg) + "\n"
            except queue.Empty:
                yield json.dumps({"type": "heartbeat", "time": time.time()}) + "\n"

    from flask import stream_with_context
    return Response(stream_with_context(generate_stream()), mimetype='application/x-ndjson')


@app.route('/api/system/health', methods=['GET'])
def system_health():
    """Returns system health metrics."""
    health: Dict[str, Any] = {
        "status": "healthy",
        "timestamp": None,
        "services": {
            "mongodb": "未知",
            "chromadb": "未知",
            "sentry": "可用" if HAS_SENTRY else "未启用",
            "prometheus": "可用" if HAS_PROMETHEUS else "未启用"
        },
        "storage": {
            "total_gb": 0,
            "used_gb": 0,
            "free_gb": 0,
            "percent_used": 0
        },
        "llm": {
            "total_tokens": 0,
            "request_count": 0,
            "estimated_cost_usd": 0.0
        }
    }
    
    import datetime
    health["timestamp"] = datetime.datetime.now().isoformat()
    
    # Check MongoDB
    try:
        db = get_mongodb_db()
        if db is not None:
            # Simple ping
            db.command('ping')
            health["services"]["mongodb"] = "已连接"
        else:
            health["services"]["mongodb"] = "未连接"
    except Exception as e:
        error_msg = str(e)
        if "Connection refused" in error_msg or "ServerSelectionTimeoutError" in error_msg:
             health["services"]["mongodb"] = "断开 (服务未启动)"
        else:
             health["services"]["mongodb"] = f"错误: {error_msg[:30]}..."
        health["status"] = "degraded"
        
    # Check ChromaDB
    try:
        vector_store = get_vector_store()
        if vector_store:
            # Check if we can access collection
            health["services"]["chromadb"] = "已连接"
        else:
            health["services"]["chromadb"] = "未连接 (Key错误)"
    except Exception as e:
        health["services"]["chromadb"] = f"错误: {str(e)[:30]}..."
        health["status"] = "degraded"
        
    # Check Disk Space
    try:
        total, used, free = shutil.disk_usage("/")
        health["storage"]["total_gb"] = round(total / (1024**3), 2)
        health["storage"]["used_gb"] = round(used / (1024**3), 2)
        health["storage"]["free_gb"] = round(free / (1024**3), 2)
        health["storage"]["percent_used"] = round((used / total) * 100, 2)
    except Exception:
        pass
        
    # Check LLM Metrics
    if HAS_PROMETHEUS:
        try:
            # Aggregate token count from samples
            token_samples = TOKEN_USAGE_COUNTER.collect()
            if token_samples:
                for sample in token_samples[0].samples:
                    health["llm"]["total_tokens"] += int(sample.value)
            
            # Aggregate request count
            request_samples = LLM_REQUEST_COUNTER.collect()
            if request_samples:
                for sample in request_samples[0].samples:
                    health["llm"]["request_count"] += int(sample.value)
                
            # Basic cost calculation (Approximate for Gemini 1.5 Flash)
            # Input: $0.075 / 1M tokens, Output: $0.30 / 1M tokens -> Weighted avg approx $0.15/1M
            health["llm"]["estimated_cost_usd"] = round((health["llm"]["total_tokens"] / 1_000_000) * 0.15, 6)
        except Exception:
            pass
            
    return jsonify(health)

@app.route('/api/system/logs', methods=['GET'])
def system_logs() -> Response:
    """Reads the tail of the log file."""
    limit = request.args.get('limit', default=100, type=int)
    log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs', 'novel_agent.log')
    
    if not os.path.exists(log_file):
        return jsonify({"logs": ["Log file not found at " + log_file]})
        
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            # Read all lines then take last N
            lines = f.readlines()
            tail = lines[-limit:] if len(lines) > limit else lines
            return jsonify({"logs": [line.strip() for line in tail]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/system/llm-info', methods=['GET'])
def get_llm_info():
    """Returns metadata about the currently active LLM provider."""
    from src.common.llm_factory import get_provider_info
    return jsonify(get_provider_info())

@app.route('/api/config', methods=['GET'])
def get_full_config():
    """Returns the full configuration for the settings UI."""
    from src.common.config_utils import load_config
    return jsonify(load_config())

@app.route('/api/config', methods=['POST'])
def update_full_config():
    """Updates the config.json file."""
    from src.common.config_utils import save_config
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    success = save_config(data)
    if success:
        return jsonify({"status": "success"})
    else:
        return jsonify({"error": "Failed to save config"}), 500

@app.route('/api/config/usage', methods=['GET'])
def get_usage_stats():
    """Returns the agent usage statistics."""
    from src.common.usage_utils import load_usage
    return jsonify(load_usage())

@app.route('/api/worldviews/list', methods=['GET'])
def list_worldviews():
    """获取所有世界观容器 - MongoDB 物理查询"""
    try:
        db = get_mongodb_db()
        cursor = db["worldviews"].find({})
        worldviews = []
        for wv in cursor:
            if "_id" in wv: wv["_id"] = str(wv["_id"])
            worldviews.append(wv)
        
        # 确保默认项存在
        if not any(w.get('worldview_id') == 'default_wv' for w in worldviews):
            worldviews.insert(0, {
                "worldview_id": "default_wv",
                "name": "默认世界观 (Default Worldview)",
                "summary": "系统的初始宇宙设定。所有未归类的大纲将默认关联至此。",
                "timestamp": "N/A"
            })
            
        return jsonify(worldviews)
    except Exception as e:
        logger.error(f"Failed to list worldviews: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/worldviews/create', methods=['POST'])
def create_worldview():
    """创建新的独立世界观容器 - MongoDB 物理写入"""
    data = request.json or {}
    name = data.get('name', '新世界观')
    summary = data.get('summary', '')
    
    wv_id = f"wv_{uuid.uuid4().hex[:8]}"
    
    import datetime
    new_entry = {
        "worldview_id": wv_id,
        "name": name,
        "summary": summary,
        "timestamp": datetime.datetime.now().isoformat()
    }
    
    try:
        db = get_mongodb_db()
        db["worldviews"].insert_one(new_entry)
        return jsonify({"status": "success", "worldview_id": wv_id, "name": name})
    except Exception as e:
        logger.error(f"Failed to create new worldview: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/outlines/list', methods=['GET'])
def list_outlines():
    """获取所有大纲 (Novels) - MongoDB 物理查询"""
    try:
        db = get_mongodb_db()
        cursor = db["outlines"].find({})
        outlines = []
        for doc in cursor:
            outlines.append({
                "outline_id": doc.get("outline_id") or doc.get("id"),
                "worldview_id": doc.get("worldview_id") or "default_wv",
                "title": doc.get("name") or doc.get("title") or "未命名小说",
                "summary": doc.get("summary") or doc.get("content") or "",
                "timestamp": doc.get("timestamp", "N/A")
            })
        
        # 确保默认项目存在
        if not any(o.get('outline_id') == 'default' for o in outlines):
            outlines.insert(0, {
                "outline_id": "default",
                "worldview_id": "default_wv",
                "title": "默认项目 (Default Project)",
                "summary": "系统的默认工作区。所有未归类或遗留的世界观及剧情资料都将优先保存在此处。",
                "timestamp": "N/A"
            })
            
        return jsonify(outlines)
    except Exception as e:
        logger.error(f"Failed to list outlines: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/outlines/create', methods=['POST'])
def create_outline():
    """创建新小说项目 - MongoDB 物理写入"""
    data = request.json or {}
    name = data.get('name', '新小说')
    summary = data.get('summary', '')
    worldview_id = data.get('worldview_id', 'default_wv')
    
    novel_id = f"novel_{uuid.uuid4().hex[:8]}"
    
    import datetime
    new_entry = {
        "outline_id": novel_id,
        "worldview_id": worldview_id,
        "name": name,
        "summary": summary,
        "timestamp": datetime.datetime.now().isoformat()
    }
    
    try:
        db = get_mongodb_db()
        db["outlines"].insert_one(new_entry)
        return jsonify({"status": "success", "outline_id": novel_id, "worldview_id": worldview_id, "name": name})
    except Exception as e:
        logger.error(f"Failed to create new novel project: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # 启动 5005 端口
    app.run(port=5005, host='localhost', debug=False)
