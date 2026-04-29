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
import datetime
import hashlib
import xml.etree.ElementTree as ET
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
from src.world.world_agent_langgraph import app as world_app
from src.novel_meta.novel_agent_langgraph import app as novel_app
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
    # Prometheus 未安装时禁用指标上报；业务接口不使用替代数据。
    class OptionalMetricsCounter:
        def labels(self, *args, **kwargs): return self
        def inc(self, amount=1): pass
        def collect(self): 
            return [type('obj', (), {'samples': []})]
    TOKEN_USAGE_COUNTER: Any = OptionalMetricsCounter()
    LLM_REQUEST_COUNTER: Any = OptionalMetricsCounter()
# token_type: prompt / completion


# Agent Mapping
AGENTS = {
    "world": world_app,
    "worldview": worldview_app,
    "novel": novel_app,
    "outline": outline_app,
    "writing": writing_app,
    "router": router_app,
    "import": import_app,
    "brain": brain_app
}

DEFAULT_WORLD_ID = "world_default"
DEFAULT_WORLDVIEW_ID = "default_wv"

def _now_iso() -> str:
    return datetime.datetime.now().isoformat()

def _mongo_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    next_doc = dict(doc)
    if "_id" in next_doc:
        next_doc["_id"] = str(next_doc["_id"])
    return next_doc

def _json_or_args() -> Dict[str, Any]:
    data = request.get_json(silent=True) or {}
    merged = dict(request.args)
    merged.update(data)
    return merged

def _wants_cascade(data: Dict[str, Any]) -> bool:
    value = data.get("cascade")
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "y"}
    return False

def _default_world_doc() -> Dict[str, Any]:
    return {
        "world_id": DEFAULT_WORLD_ID,
        "name": "默认世界",
        "summary": "系统默认世界。迁移前的世界观、小说、大纲和章节默认归属到这里。",
        "timestamp": _now_iso(),
    }

def _default_worldview_doc() -> Dict[str, Any]:
    return {
        "worldview_id": DEFAULT_WORLDVIEW_ID,
        "world_id": DEFAULT_WORLD_ID,
        "name": "默认世界观 (Default Worldview)",
        "summary": "系统的初始宇宙设定。所有未归类的大纲将默认关联至此。",
        "timestamp": _now_iso(),
    }

def _ensure_default_hierarchy(db):
    db["worlds"].update_one(
        {"world_id": DEFAULT_WORLD_ID},
        {"$setOnInsert": _default_world_doc()},
        upsert=True,
    )
    db["worldviews"].update_one(
        {"worldview_id": DEFAULT_WORLDVIEW_ID},
        {"$setOnInsert": _default_worldview_doc()},
        upsert=True,
    )

def _get_world_or_error(db, world_id: str) -> Optional[Dict[str, Any]]:
    if world_id == DEFAULT_WORLD_ID:
        _ensure_default_hierarchy(db)
    return db["worlds"].find_one({"world_id": world_id})

def _get_worldview_or_error(db, worldview_id: str) -> Optional[Dict[str, Any]]:
    if worldview_id == DEFAULT_WORLDVIEW_ID:
        _ensure_default_hierarchy(db)
    return db["worldviews"].find_one({"worldview_id": worldview_id})

def _get_novel_or_error(db, novel_id: str) -> Optional[Dict[str, Any]]:
    return db["novels"].find_one({"novel_id": novel_id})

def _get_outline_or_error(db, outline_id: str) -> Optional[Dict[str, Any]]:
    return db["outlines"].find_one({"$or": [{"outline_id": outline_id}, {"id": outline_id}]})

def _require_field(data: Dict[str, Any], field: str):
    value = data.get(field)
    if value is None or value == "":
        return None, (jsonify({"error": f"Missing required field: {field}"}), 400)
    return value, None

def _pagination_params(max_page_size: int = 100):
    page_raw = request.args.get("page")
    page_size_raw = request.args.get("page_size")
    if page_raw is None or page_size_raw is None:
        return None, None, (jsonify({"error": "Missing required pagination: page and page_size"}), 400)
    try:
        page = int(page_raw)
        page_size = int(page_size_raw)
    except ValueError:
        return None, None, (jsonify({"error": "page and page_size must be integers"}), 400)
    if page < 1:
        return None, None, (jsonify({"error": "page must be >= 1"}), 400)
    if page_size < 1 or page_size > max_page_size:
        return None, None, (jsonify({"error": f"page_size must be between 1 and {max_page_size}"}), 400)
    return (page - 1) * page_size, page_size, None

def _require_query_condition(*fields: str):
    if any(request.args.get(field) for field in fields):
        return None
    return jsonify({"error": f"Missing required query condition: one of {', '.join(fields)}"}), 400

def _novel_payload_from_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "novel_id": doc.get("novel_id") or doc.get("id"),
        "world_id": doc.get("world_id") or DEFAULT_WORLD_ID,
        "name": doc.get("name") or doc.get("title") or "",
        "summary": doc.get("summary") or doc.get("content") or "",
        "timestamp": doc.get("timestamp"),
    }

def _outline_payload_from_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "outline_id": doc.get("outline_id") or doc.get("id"),
        "novel_id": doc.get("novel_id"),
        "world_id": doc.get("world_id") or DEFAULT_WORLD_ID,
        "worldview_id": doc.get("worldview_id") or DEFAULT_WORLDVIEW_ID,
        "title": doc.get("name") or doc.get("title") or "",
        "summary": doc.get("summary") or doc.get("content") or "",
        "timestamp": doc.get("timestamp"),
    }

def _chapter_payload_from_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": doc.get("prose_id") or doc.get("scene_id") or doc.get("id"),
        "type": "prose",
        "name": doc.get("title") or doc.get("scene_title") or doc.get("name") or "",
        "content": doc.get("content"),
        "outline_id": doc.get("outline_id"),
        "novel_id": doc.get("novel_id"),
        "worldview_id": doc.get("worldview_id") or DEFAULT_WORLDVIEW_ID,
        "world_id": doc.get("world_id") or DEFAULT_WORLD_ID,
        "timestamp": doc.get("timestamp"),
    }

def _import_doc_id(worldview_id: str, source_name: str, path: str) -> str:
    digest = hashlib.sha1(f"{worldview_id}|{source_name}|{path}".encode("utf-8")).hexdigest()[:16]
    return f"import_{digest}"

def _normalize_import_entry(name: str, content: str, path_parts: List[str], order: int) -> Dict[str, Any]:
    clean_parts = [str(part).strip() for part in path_parts if str(part).strip()]
    clean_name = str(name or (clean_parts[-1] if clean_parts else "未命名")).strip()
    full_path = " > ".join(clean_parts or [clean_name])
    clean_content = str(content or "").strip() or f"层级节点：{full_path}"
    return {
        "name": clean_name,
        "content": clean_content,
        "path": full_path,
        "category": full_path,
        "order": order,
    }

def _parse_import_json(raw_text: str) -> List[Dict[str, Any]]:
    data = json.loads(raw_text)
    entries: List[Dict[str, Any]] = []
    order = 0
    name_keys = ("name", "title", "text", "label", "heading")
    content_keys = ("content", "summary", "description", "body", "note", "_note", "value")
    child_keys = ("children", "items", "entries", "nodes", "outline", "outlines")

    def next_order() -> int:
        nonlocal order
        order += 1
        return order

    def scalar(value: Any) -> bool:
        return isinstance(value, (str, int, float, bool)) or value is None

    def walk(value: Any, path: List[str], fallback_name: str = "") -> None:
        if isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, path, f"条目 {index + 1}")
            return

        if isinstance(value, dict):
            explicit_name = next((value.get(key) for key in name_keys if value.get(key)), None)
            children = next((value.get(key) for key in child_keys if isinstance(value.get(key), list)), None)
            content_parts = [str(value.get(key)).strip() for key in content_keys if scalar(value.get(key)) and str(value.get(key) or "").strip()]

            if explicit_name:
                node_name = str(explicit_name).strip()
                current_path = path + [node_name]
                entries.append(_normalize_import_entry(node_name, "\n\n".join(content_parts), current_path, next_order()))
                if children:
                    walk(children, current_path)
                nested_child_keys = set(name_keys) | set(content_keys) | set(child_keys)
                for key, child in value.items():
                    if key in nested_child_keys or scalar(child):
                        continue
                    walk(child, current_path + [str(key)])
                return

            for key, child in value.items():
                key_name = str(key).strip()
                if scalar(child):
                    entries.append(_normalize_import_entry(key_name, str(child or ""), path + [key_name], next_order()))
                else:
                    walk(child, path + [key_name], key_name)
            return

        node_name = fallback_name or (path[-1] if path else "导入内容")
        entries.append(_normalize_import_entry(node_name, str(value or ""), path or [node_name], next_order()))

    walk(data, [])
    return entries

def _parse_import_markdown(raw_text: str) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    sections: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    preface: List[str] = []

    for line in raw_text.splitlines():
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if match:
            if current:
                sections.append(current)
            level = len(match.group(1))
            title = match.group(2).strip()
            current = {"level": level, "title": title, "lines": []}
        elif current:
            current["lines"].append(line)
        else:
            preface.append(line)

    if current:
        sections.append(current)

    order = 0
    if preface and "\n".join(preface).strip():
        order += 1
        entries.append(_normalize_import_entry("导入内容", "\n".join(preface), ["导入内容"], order))

    if not sections and raw_text.strip():
        return [_normalize_import_entry("导入内容", raw_text, ["导入内容"], 1)]

    stack: List[Dict[str, Any]] = []
    for section in sections:
        while stack and int(stack[-1]["level"]) >= int(section["level"]):
            stack.pop()
        stack.append(section)
        path = [str(item["title"]) for item in stack]
        order += 1
        entries.append(_normalize_import_entry(str(section["title"]), "\n".join(section["lines"]), path, order))

    return entries

def _parse_import_opml(raw_text: str) -> List[Dict[str, Any]]:
    root = ET.fromstring(raw_text)
    body = root.find("body")
    if body is None:
        raise ValueError("Invalid OPML: missing body")
    entries: List[Dict[str, Any]] = []
    order = 0

    def walk(node: ET.Element, path: List[str]) -> None:
        nonlocal order
        name = (node.get("text") or node.get("title") or "").strip()
        if not name:
            return
        current_path = path + [name]
        content = node.get("_note") or node.get("note") or node.get("description") or name
        order += 1
        entries.append(_normalize_import_entry(name, content, current_path, order))
        for child in list(node):
            if child.tag.lower().endswith("outline"):
                walk(child, current_path)

    for child in list(body):
        if child.tag.lower().endswith("outline"):
            walk(child, [])
    return entries

def _parse_worldview_import(filename: str, raw_text: str) -> List[Dict[str, Any]]:
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".json":
        return _parse_import_json(raw_text)
    if ext in {".md", ".markdown"}:
        return _parse_import_markdown(raw_text)
    if ext == ".opml":
        return _parse_import_opml(raw_text)
    raise ValueError("Unsupported import format. Only json, md, and opml are supported.")

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

# 用于写作 Agent 的大纲缓存；正式业务数据以 MongoDB 集合为准。
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
    return api_list_lore()

@app.route('/api/lore/list', methods=['GET'])
def api_list_lore():
    """Route to list paginated, filtered lore items. Full scans are forbidden."""
    condition_error = _require_query_condition("outline_id", "worldview_id", "novel_id", "world_id", "query")
    if condition_error:
        return condition_error
    skip, limit, pagination_error = _pagination_params()
    if pagination_error:
        return pagination_error
    oid = request.args.get('outline_id')
    wid = request.args.get('worldview_id')
    nid = request.args.get('novel_id')
    world_id = request.args.get('world_id')
    keyword = request.args.get('query')
    try:
        db = get_mongodb_db()
        text_filter = None
        if keyword:
            text_filter = {"$regex": keyword, "$options": "i"}

        lore_query: Dict[str, Any] = {}
        outline_query: Dict[str, Any] = {}
        prose_query: Dict[str, Any] = {}
        if oid:
            lore_query["outline_id"] = oid
            outline_query["$or"] = [{"outline_id": oid}, {"id": oid}]
            prose_query["outline_id"] = oid
        if wid:
            lore_query["worldview_id"] = wid
            outline_query["worldview_id"] = wid
            prose_query["worldview_id"] = wid
        if nid:
            lore_query["novel_id"] = nid
            outline_query["novel_id"] = nid
            prose_query["novel_id"] = nid
        if world_id:
            lore_query["world_id"] = world_id
            outline_query["world_id"] = world_id
            prose_query["world_id"] = world_id
        if text_filter:
            lore_query["$or"] = [{"name": text_filter}, {"content": text_filter}, {"query": text_filter}, {"category": text_filter}, {"path": text_filter}]
            outline_text_or = [{"name": text_filter}, {"title": text_filter}, {"summary": text_filter}, {"content": text_filter}]
            if "$or" in outline_query:
                outline_query = {"$and": [outline_query, {"$or": outline_text_or}]}
            else:
                outline_query["$or"] = outline_text_or
            prose_query["$or"] = [{"title": text_filter}, {"scene_title": text_filter}, {"name": text_filter}, {"content": text_filter}]

        items: List[Dict[str, Any]] = []
        for item in db["lore"].find(lore_query).sort("timestamp", -1).skip(skip).limit(limit):
            items.append({
                "id": item.get("doc_id") or str(item.get("_id")),
                "type": "worldview",
                "name": item.get("name") or item.get("query") or "",
                "content": item.get("content"),
                "category": item.get("path") or item.get("category", "Worldview"),
                "timestamp": item.get("timestamp"),
                "outline_id": item.get("outline_id"),
                "novel_id": item.get("novel_id"),
                "worldview_id": item.get("worldview_id"),
                "world_id": item.get("world_id"),
            })
        for item in db["outlines"].find(outline_query).sort("timestamp", -1).skip(skip).limit(limit):
            outline = _outline_payload_from_doc(item)
            items.append({
                "id": outline["outline_id"],
                "type": "outline",
                "name": outline["title"],
                "content": outline.get("summary"),
                "category": "Outlines",
                **outline,
            })
        for item in db["prose"].find(prose_query).sort("timestamp", -1).skip(skip).limit(limit):
            items.append(_chapter_payload_from_doc(item))
        return jsonify(items[:limit])
    except Exception as e:
        logger.error(f"Failed to list lore: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/lore', methods=['GET'])
def get_lore():
    return api_list_lore()

@app.route('/api/lore/tree', methods=['GET'])
def get_lore_tree():
    """Returns lore organized in a tree structure by category."""
    condition_error = _require_query_condition("outline_id", "worldview_id", "novel_id", "world_id", "query")
    if condition_error:
        return condition_error
    skip, limit, pagination_error = _pagination_params()
    if pagination_error:
        return pagination_error
    outline_id = request.args.get('outline_id')
    worldview_id = request.args.get('worldview_id')
    novel_id = request.args.get('novel_id')
    world_id = request.args.get('world_id')
    keyword = request.args.get('query')
    with app.test_request_context(
        f"/api/lore/list?outline_id={outline_id or ''}&worldview_id={worldview_id or ''}&novel_id={novel_id or ''}&world_id={world_id or ''}&query={keyword or ''}&page={request.args.get('page')}&page_size={request.args.get('page_size')}"
    ):
        response = api_list_lore()
        if isinstance(response, tuple):
            return response
        all_docs = response.get_json()
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
    condition_error = _require_query_condition("outline_id", "worldview_id", "novel_id", "world_id", "query")
    if condition_error:
        return condition_error
    skip, limit, pagination_error = _pagination_params()
    if pagination_error:
        return pagination_error
    outline_id = request.args.get('outline_id')
    worldview_id = request.args.get('worldview_id')
    novel_id = request.args.get('novel_id')
    world_id = request.args.get('world_id')
    keyword = request.args.get('query')
    with app.test_request_context(
        f"/api/lore/list?outline_id={outline_id or ''}&worldview_id={worldview_id or ''}&novel_id={novel_id or ''}&world_id={world_id or ''}&query={keyword or ''}&page={request.args.get('page')}&page_size={request.args.get('page_size')}"
    ):
        response = api_list_lore()
        if isinstance(response, tuple):
            return response
        all_docs = response.get_json()
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
    condition_error = _require_query_condition("outline_id", "worldview_id", "novel_id", "world_id", "query")
    if condition_error:
        return condition_error
    skip, limit, pagination_error = _pagination_params()
    if pagination_error:
        return pagination_error
    lore_response = api_list_lore()
    if isinstance(lore_response, tuple):
        return lore_response
    all_docs = lore_response.get_json() or []
    
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
    """Exports a paginated, filtered lore slice as an OPML file."""
    condition_error = _require_query_condition("outline_id", "worldview_id", "novel_id", "world_id", "query")
    if condition_error:
        return condition_error
    skip, limit, pagination_error = _pagination_params()
    if pagination_error:
        return pagination_error
    lore_response = api_list_lore()
    if isinstance(lore_response, tuple):
        return lore_response
    all_docs = lore_response.get_json() or []
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
    novel_id = data.get('novel_id')
    world_id = data.get('world_id')

    if not item_id or not item_type:
        return jsonify({"error": "Missing id or type"}), 400
            
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
        now = _now_iso()
        
        # 确定查询和更新字段
        if item_type == 'worldview':
            query = {"doc_id": item_id}
            update_data = {"doc_id": item_id, "content": new_content, "name": new_name, "timestamp": now}
            if category: update_data["category"] = category
            if outline_id:
                outline = _get_outline_or_error(db, outline_id)
                if not outline:
                    return jsonify({"error": f"Parent outline not found: {outline_id}"}), 404
                novel_id = outline.get("novel_id") or novel_id
                worldview_id = outline.get("worldview_id") or worldview_id
                world_id = outline.get("world_id") or world_id
            if worldview_id:
                worldview = _get_worldview_or_error(db, worldview_id)
                if not worldview:
                    return jsonify({"error": f"Parent worldview not found: {worldview_id}"}), 404
                world_id = world_id or worldview.get("world_id") or DEFAULT_WORLD_ID
                update_data["worldview_id"] = worldview_id
            if world_id:
                if not _get_world_or_error(db, world_id):
                    return jsonify({"error": f"Parent world not found: {world_id}"}), 404
                update_data["world_id"] = world_id
            if novel_id: update_data["novel_id"] = novel_id
            if outline_id: update_data["outline_id"] = outline_id
        elif item_type == 'prose':
            if not outline_id:
                return jsonify({"error": "Missing required field: outline_id"}), 400
            outline = _get_outline_or_error(db, outline_id)
            if not outline:
                return jsonify({"error": f"Parent outline not found: {outline_id}"}), 404
            novel_id = outline.get("novel_id") or novel_id
            worldview_id = outline.get("worldview_id") or worldview_id or DEFAULT_WORLDVIEW_ID
            world_id = outline.get("world_id") or world_id or DEFAULT_WORLD_ID
            query = {"$or": [{"scene_id": item_id}, {"id": item_id}]}
            update_data = {
                "id": item_id,
                "scene_id": item_id,
                "content": new_content,
                "title": new_name,
                "timestamp": now,
                "outline_id": outline_id,
                "novel_id": novel_id,
                "worldview_id": worldview_id,
                "world_id": world_id,
            }
        elif item_type == 'outline':
            query = {"$or": [{"outline_id": item_id}, {"id": item_id}]}
            existing_outline = _get_outline_or_error(db, item_id)
            if novel_id:
                novel = _get_novel_or_error(db, novel_id)
                if not novel:
                    return jsonify({"error": f"Parent novel not found: {novel_id}"}), 404
                if existing_outline:
                    worldview_id = worldview_id or existing_outline.get("worldview_id")
                world_id = novel.get("world_id") or world_id
            elif existing_outline:
                novel_id = existing_outline.get("novel_id")
                worldview_id = existing_outline.get("worldview_id") or worldview_id
                world_id = existing_outline.get("world_id") or world_id
            else:
                return jsonify({"error": "Missing required field: novel_id"}), 400
            update_data = {
                "id": item_id,
                "outline_id": item_id,
                "content": new_content,
                "summary": new_content,
                "name": new_name,
                "timestamp": now,
                "novel_id": novel_id,
                "worldview_id": worldview_id or DEFAULT_WORLDVIEW_ID,
                "world_id": world_id or DEFAULT_WORLD_ID,
            }
        elif item_type == 'novel':
            query = {"$or": [{"novel_id": item_id}, {"id": item_id}]}
            existing_novel = _get_novel_or_error(db, item_id)
            world_id = world_id or (existing_novel or {}).get("world_id")
            if not world_id:
                return jsonify({"error": "Missing required field: world_id"}), 400
            if not _get_world_or_error(db, world_id):
                return jsonify({"error": f"Parent world not found: {world_id}"}), 404
            update_data = {
                "id": item_id,
                "novel_id": item_id,
                "name": new_name,
                "summary": new_content,
                "content": new_content,
                "timestamp": now,
                "world_id": world_id,
            }
        elif item_type == 'entity-draft':
            query = {"id": item_id}
            update_data = {"status": "pending", "timestamp": now} 
            if worldview_id: update_data["worldview_id"] = worldview_id
            if outline_id: update_data["outline_id"] = outline_id
        
        # 执行更新 (物理副作用)
        res = coll.update_one(query, {"$set": update_data}, upsert=True)
        
        # 同步到 ChromaDB (仅限 worldview 和 outline)
        if item_type in ['worldview', 'outline']:
            from src.common.lore_utils import sync_archive_to_all_stores
            sync_archive_to_all_stores(item_id, item_type, new_content, new_name, outline_id, worldview_id)
            
        return jsonify({"status": "success", "id": item_id, "type": item_type, "modified": res.modified_count})
    except Exception as e:
        logger.error(f"Failed to update archive: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/archive/delete', methods=['DELETE'])
def delete_archive():
    """从 MongoDB 数据库中永久删除条目，并同步清理向量索引。"""
    data = _json_or_args()
    logger.info(f"[API] Delete request received: {data}")
    item_id = data.get('id')
    item_type = data.get('type')
    outline_id = data.get('outline_id')
    worldview_id = data.get('worldview_id')
    cascade = _wants_cascade(data)
    
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

        if item_type == "outline":
            child_count = db["prose"].count_documents({"outline_id": item_id})
            if child_count and not cascade:
                return jsonify({"error": "Outline is not empty", "child_count": child_count}), 409
            if cascade:
                db["prose"].delete_many({"outline_id": item_id})
        elif item_type == "novel":
            child_count = (
                db["outlines"].count_documents({"novel_id": item_id})
                + db["prose"].count_documents({"novel_id": item_id})
            )
            if child_count and not cascade:
                return jsonify({"error": "Novel is not empty", "child_count": child_count}), 409
            if cascade:
                db["prose"].delete_many({"novel_id": item_id})
                db["outlines"].delete_many({"novel_id": item_id})
        
        # 构造多键名兼容的查询
        query = {
            "$or": [
                {"id": item_id},
                {"doc_id": item_id},
                {"scene_id": item_id},
                {"outline_id": item_id},
                {"novel_id": item_id}
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
    elif agent_type == 'world':
        input_state = {
            "query": query,
            "world_id": data.get("world_id") or DEFAULT_WORLD_ID,
            "context": "",
            "proposal": "",
            "user_feedback": "",
            "iterations": 0,
            "is_approved": False,
            "status_message": "世界 Agent 启动中，等待创世草案生成...",
        }
    elif agent_type == 'novel':
        input_state = {
            "query": query,
            "worldview_id": current_worldview,
            "outline_id": data.get("outline_id") or "default_novel",
            "context": "",
            "proposal": "",
            "review_log": "",
            "user_feedback": "",
            "iterations": 0,
            "is_approved": False,
            "status_message": "小说 Agent 启动中，正在构思故事元数据...",
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
                            # Safely handle non-dict node_data (tuples, Interrupts, etc.)
                            if isinstance(node_data, tuple) and len(node_data) > 0:
                                node_data = node_data[0]
                            
                            status_msg = None
                            if isinstance(node_data, dict):
                                status_msg = node_data.get("status_message")
                            elif hasattr(node_data, "__class__") and "Interrupt" in node_data.__class__.__name__:
                                status_msg = "等待人工干预/审核 (Human-in-the-loop Interrupt)"
                            
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
                                "proposal": node_data.get("proposal") if isinstance(node_data, dict) else None,
                                "is_approved": node_data.get("is_approved") if isinstance(node_data, dict) else None,
                                "diagnostics": node_data.get("llm_interactions") if isinstance(node_data, dict) else None
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
        worldview_id = data.get('worldview_id')
        vector_store = get_vector_store(worldview_id=worldview_id, outline_id=outline_id)
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

@app.route('/api/workflow/outline-chapter/state', methods=['GET'])
def get_outline_chapter_workflow_state():
    """Return a query-only snapshot for the outline/chapter iteration UI."""
    outline_id = request.args.get('outline_id')
    worldview_id = request.args.get('worldview_id')
    world_id = request.args.get('world_id')
    condition_error = _require_query_condition("world_id", "outline_id", "worldview_id")
    if condition_error:
        return condition_error
    skip, limit, pagination_error = _pagination_params()
    if pagination_error:
        return pagination_error
    try:
        outlines_response = list_outlines()
        if isinstance(outlines_response, tuple):
            return outlines_response
        outlines = outlines_response.get_json() if hasattr(outlines_response, "get_json") else []
        lore_response = api_list_lore()
        if isinstance(lore_response, tuple):
            return lore_response
        items = lore_response.get_json() if hasattr(lore_response, "get_json") else []
        chapters = [item for item in items if item.get("type") == "prose"]
        outline_items = [item for item in items if item.get("type") == "outline"]
        snapshots = []
        if outline_id:
            snapshots_response = get_snapshots(outline_id)
            snapshots = snapshots_response.get_json() if hasattr(snapshots_response, "get_json") else []
        return jsonify({
            "status": "success",
            "world_id": world_id,
            "outline_id": outline_id,
            "worldview_id": worldview_id,
            "outlines": outlines,
            "outline_items": outline_items,
            "chapters": chapters,
            "snapshots": snapshots,
        })
    except Exception as e:
        logger.error(f"Failed to load outline/chapter workflow state: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

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

@app.route('/api/worldviews/import', methods=['POST'])
def import_worldview_hierarchy():
    """Import hierarchical worldview lore from JSON, Markdown, or OPML without flattening paths."""
    world_id = request.form.get("world_id")
    worldview_id = request.form.get("worldview_id")
    upload = request.files.get("file")

    if not world_id:
        return jsonify({"error": "Missing required field: world_id"}), 400
    if not worldview_id:
        return jsonify({"error": "Missing required field: worldview_id"}), 400
    if upload is None or not upload.filename:
        return jsonify({"error": "Missing required file"}), 400

    filename = os.path.basename(upload.filename)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in {".json", ".md", ".markdown", ".opml"}:
        return jsonify({"error": "Unsupported import format. Only json, md, and opml are supported."}), 400

    try:
        db = get_mongodb_db()
        world = _get_world_or_error(db, world_id)
        if not world:
            return jsonify({"error": f"Parent world not found: {world_id}"}), 404
        worldview = _get_worldview_or_error(db, worldview_id)
        if not worldview:
            return jsonify({"error": f"Worldview not found: {worldview_id}"}), 404
        if (worldview.get("world_id") or DEFAULT_WORLD_ID) != world_id:
            return jsonify({"error": f"Worldview {worldview_id} does not belong to world {world_id}"}), 400

        raw_text = upload.read().decode("utf-8-sig")
        parsed_entries = _parse_worldview_import(filename, raw_text)
        if not parsed_entries:
            return jsonify({"error": "No importable hierarchy entries found"}), 400

        now = _now_iso()
        imported_entries = []
        for entry in parsed_entries:
            doc_id = _import_doc_id(worldview_id, filename, entry["path"])
            doc = {
                "doc_id": doc_id,
                "type": "worldview",
                "name": entry["name"],
                "content": entry["content"],
                "category": entry["category"],
                "path": entry["path"],
                "hierarchy_path": entry["path"].split(" > "),
                "hierarchy_order": entry["order"],
                "world_id": world_id,
                "worldview_id": worldview_id,
                "source_file": filename,
                "source_format": ext.lstrip("."),
                "timestamp": now,
            }
            db["lore"].update_one({"doc_id": doc_id}, {"$set": doc}, upsert=True)
            imported_entries.append({
                "id": doc_id,
                "name": doc["name"],
                "path": doc["path"],
                "category": doc["category"],
                "world_id": world_id,
                "worldview_id": worldview_id,
            })

        return jsonify({
            "status": "success",
            "world_id": world_id,
            "worldview_id": worldview_id,
            "source_file": filename,
            "source_format": ext.lstrip("."),
            "imported_count": len(imported_entries),
            "entries": imported_entries,
        })
    except json.JSONDecodeError as e:
        return jsonify({"error": f"Invalid JSON: {e}"}), 400
    except ET.ParseError as e:
        return jsonify({"error": f"Invalid OPML/XML: {e}"}), 400
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Failed to import worldview hierarchy: {e}")
        return jsonify({"error": str(e)}), 500

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
    from src.common.lore_utils import get_embedding_provider_info
    info = get_provider_info()
    info["embedding"] = get_embedding_provider_info()
    return jsonify(info)

@app.route('/api/config', methods=['GET'])
def get_full_config():
    """Returns the full configuration for the settings UI."""
    from src.common.config_utils import load_config
    return jsonify(load_config())

@app.route('/api/config', methods=['POST'])
def update_full_config():
    """Updates the module-scoped YAML config files."""
    from src.common.config_utils import load_config, save_config
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    current_config = load_config()
    merged_config = {**current_config, **data}

    if "LLM_MODEL" in merged_config and "DEFAULT_MODEL" not in data:
        merged_config["DEFAULT_MODEL"] = merged_config.pop("LLM_MODEL")
    else:
        merged_config.pop("LLM_MODEL", None)

    provider = (merged_config.get("LLM_PROVIDER") or "").lower()
    if provider == "google":
        provider = "gemini"
        merged_config["LLM_PROVIDER"] = provider
    default_model = merged_config.get("DEFAULT_MODEL")
    if provider and default_model:
        model_map = merged_config.get("DEFAULT_MODEL_MAP") or {}
        model_map[provider] = default_model
        merged_config["DEFAULT_MODEL_MAP"] = model_map
        llm_models = merged_config.get("LLM_MODELS") or {}
        provider_models = llm_models.get(provider) or {}
        if not isinstance(provider_models, dict):
            provider_models = {"models": provider_models if isinstance(provider_models, list) else []}
        provider_models["default"] = default_model
        models = provider_models.get("models") or []
        if default_model not in models:
            models.insert(0, default_model)
        provider_models["models"] = models
        if provider == "ollama":
            provider_models["base_url"] = merged_config.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        llm_models[provider] = provider_models
        merged_config["LLM_MODELS"] = llm_models

    embedding_provider = (merged_config.get("EMBEDDING_PROVIDER") or "ollama").lower()
    default_embedding_model = (
        merged_config.get("DEFAULT_EMBEDDING_MODEL")
        or merged_config.get("OLLAMA_EMBEDDING_MODEL")
        or "embeddinggemma"
    )
    merged_config["DEFAULT_EMBEDDING_MODEL"] = default_embedding_model
    if embedding_provider == "ollama":
        merged_config["OLLAMA_EMBEDDING_MODEL"] = default_embedding_model
    embedding_models = merged_config.get("EMBEDDING_MODELS") or {}
    provider_embeddings = embedding_models.get(embedding_provider) or {}
    if not isinstance(provider_embeddings, dict):
        provider_embeddings = {"models": provider_embeddings if isinstance(provider_embeddings, list) else []}
    provider_embeddings["default"] = default_embedding_model
    models = provider_embeddings.get("models") or []
    if default_embedding_model not in models:
        models.insert(0, default_embedding_model)
    provider_embeddings["models"] = models
    if embedding_provider == "ollama":
        provider_embeddings["base_url"] = merged_config.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    embedding_models[embedding_provider] = provider_embeddings
    merged_config["EMBEDDING_MODELS"] = embedding_models
    
    success = save_config(merged_config)
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
    """获取分页世界观容器；禁止无条件全量查询。"""
    condition_error = _require_query_condition("world_id", "worldview_id", "query")
    if condition_error:
        return condition_error
    skip, limit, pagination_error = _pagination_params()
    if pagination_error:
        return pagination_error
    try:
        db = get_mongodb_db()
        _ensure_default_hierarchy(db)
        query: Dict[str, Any] = {}
        world_id = request.args.get("world_id")
        if world_id:
            query["world_id"] = world_id
        worldview_id = request.args.get("worldview_id")
        if worldview_id:
            query["worldview_id"] = worldview_id
        keyword = request.args.get("query")
        if keyword:
            text_filter = {"$regex": keyword, "$options": "i"}
            query["$or"] = [{"name": text_filter}, {"summary": text_filter}, {"worldview_id": text_filter}]
        cursor = db["worldviews"].find(query).sort("timestamp", -1).skip(skip).limit(limit)
        worldviews = []
        for wv in cursor:
            wv.setdefault("world_id", DEFAULT_WORLD_ID)
            worldviews.append(_mongo_doc(wv))
            
        return jsonify(worldviews)
    except Exception as e:
        logger.error(f"Failed to list worldviews: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/worldviews/create', methods=['POST'])
def create_worldview():
    """创建新的独立世界观容器 - MongoDB 物理写入"""
    data = request.json or {}
    name = data.get('name')
    if not name:
        return jsonify({"error": "Missing required field: name"}), 400
    summary = data.get('summary', '')
    world_id = data.get("world_id") or DEFAULT_WORLD_ID
    
    wv_id = f"wv_{uuid.uuid4().hex[:8]}"
    new_entry = {
        "worldview_id": wv_id,
        "world_id": world_id,
        "name": name,
        "summary": summary,
        "timestamp": _now_iso()
    }
    
    try:
        db = get_mongodb_db()
        if not _get_world_or_error(db, world_id):
            return jsonify({"error": f"Parent world not found: {world_id}"}), 404
        db["worldviews"].insert_one(new_entry)
        return jsonify({"status": "success", "worldview_id": wv_id, "world_id": world_id, "name": name})
    except Exception as e:
        logger.error(f"Failed to create new worldview: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/worldviews/update', methods=['POST'])
def update_worldview_container():
    data = request.json or {}
    worldview_id, error = _require_field(data, "worldview_id")
    if error:
        return error
    try:
        db = get_mongodb_db()
        existing = _get_worldview_or_error(db, worldview_id)
        if not existing:
            return jsonify({"error": f"Worldview not found: {worldview_id}"}), 404
        update_data = {"timestamp": _now_iso()}
        if "name" in data:
            if not data.get("name"):
                return jsonify({"error": "Missing required field: name"}), 400
            update_data["name"] = data["name"]
        if "summary" in data:
            update_data["summary"] = data.get("summary", "")
        if "world_id" in data:
            if not _get_world_or_error(db, data["world_id"]):
                return jsonify({"error": f"Parent world not found: {data['world_id']}"}), 404
            update_data["world_id"] = data["world_id"]
        db["worldviews"].update_one({"worldview_id": worldview_id}, {"$set": update_data})
        return jsonify({"status": "success", "worldview_id": worldview_id, **update_data})
    except Exception as e:
        logger.error(f"Failed to update worldview: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/worldviews/delete', methods=['DELETE'])
def delete_worldview_container():
    data = _json_or_args()
    worldview_id, error = _require_field(data, "worldview_id")
    if error:
        return error
    cascade = _wants_cascade(data)
    try:
        db = get_mongodb_db()
        if not _get_worldview_or_error(db, worldview_id):
            return jsonify({"error": f"Worldview not found: {worldview_id}"}), 404
        child_count = db["lore"].count_documents({"worldview_id": worldview_id})
        if child_count and not cascade:
            return jsonify({"error": "Worldview is not empty", "child_count": child_count}), 409
        deleted = {
            "lore": db["lore"].delete_many({"worldview_id": worldview_id}).deleted_count if cascade else 0,
            "worldviews": db["worldviews"].delete_one({"worldview_id": worldview_id}).deleted_count,
        }
        return jsonify({"status": "success", "deleted": deleted})
    except Exception as e:
        logger.error(f"Failed to delete worldview: {e}")
        return jsonify({"error": str(e)}), 500

HIERARCHY_AGENT_TYPES = {"world", "worldview", "novel", "outline", "chapter"}
HIERARCHY_AGENT_ACTIONS = {"create", "update", "delete"}
HIERARCHY_AGENT_REVIEW_REQUIRED = {
    "world": False,
    "worldview": True,
    "novel": True,
    "outline": True,
    "chapter": True,
}
HIERARCHY_REVISION_MODES = {
    "partial_rewrite": "指定局部重写",
    "full_rewrite": "完全重写",
    "content_rewrite": "指定内容重写",
}
HIERARCHY_REVISION_GUARDS = {
    "partial_rewrite": "只重写用户指出的局部段落或字段，保持未点名内容、命名、结构和父级关系不变。",
    "full_rewrite": "允许完整重写当前草案，但必须保留业务父级关系和用户明确要求保留的命名。",
    "content_rewrite": "只做小范围措辞、命名或字段修正，不得改动主体结构和大部分内容。",
}

def _node_time() -> str:
    return _now_iso()

def _agent_node(node_id: str, label: str, status: str, node_input: Dict[str, Any], output: Dict[str, Any]) -> Dict[str, Any]:
    now = _node_time()
    return {
        "node_id": node_id,
        "label": label,
        "status": status,
        "input": node_input,
        "output": output,
        "started_at": now,
        "completed_at": now if status in {"completed", "skipped", "failed"} else None,
    }

def _hierarchy_run_payload(doc: Dict[str, Any]) -> Dict[str, Any]:
    return _mongo_doc(doc)

def _get_hierarchy_agent_run(db, run_id: str) -> Optional[Dict[str, Any]]:
    return db["hierarchy_agent_runs"].find_one({"run_id": run_id})

def _validate_hierarchy_agent_payload(db, entity_type: str, action: str, payload: Dict[str, Any]) -> tuple[bool, List[str], Dict[str, Any]]:
    errors: List[str] = []
    normalized = dict(payload or {})

    def require(field: str):
        if normalized.get(field) in (None, ""):
            errors.append(f"Missing required field: {field}")

    if action == "create":
        require("name")
        if entity_type == "worldview":
            require("world_id")
        if entity_type == "novel":
            require("world_id")
        if entity_type == "outline":
            require("novel_id")
        if entity_type == "chapter":
            require("outline_id")
            if not normalized.get("content") and not normalized.get("summary"):
                errors.append("Missing required field: content")
    elif action == "update":
        require("target_id")
        if not any(normalized.get(field) not in (None, "") for field in ("name", "summary", "content")):
            errors.append("At least one of name, summary, content is required")
    elif action == "delete":
        require("target_id")

    if errors:
        return False, errors, normalized

    if entity_type == "world":
        if action in {"update", "delete"} and not _get_world_or_error(db, normalized["target_id"]):
            errors.append(f"World not found: {normalized['target_id']}")
    elif entity_type == "worldview":
        if action == "create":
            if not _get_world_or_error(db, normalized["world_id"]):
                errors.append(f"Parent world not found: {normalized['world_id']}")
        elif not _get_worldview_or_error(db, normalized["target_id"]):
            errors.append(f"Worldview not found: {normalized['target_id']}")
    elif entity_type == "novel":
        if action == "create":
            if not _get_world_or_error(db, normalized["world_id"]):
                errors.append(f"Parent world not found: {normalized['world_id']}")
        else:
            existing = _get_novel_or_error(db, normalized["target_id"])
            if not existing:
                errors.append(f"Novel not found: {normalized['target_id']}")
            elif normalized.get("world_id") and not _get_world_or_error(db, normalized["world_id"]):
                errors.append(f"Parent world not found: {normalized['world_id']}")
    elif entity_type == "outline":
        if action == "create":
            novel = _get_novel_or_error(db, normalized["novel_id"])
            if not novel:
                errors.append(f"Parent novel not found: {normalized['novel_id']}")
            else:
                normalized["world_id"] = novel.get("world_id") or normalized.get("world_id") or DEFAULT_WORLD_ID
            if normalized.get("worldview_id") and not _get_worldview_or_error(db, normalized["worldview_id"]):
                errors.append(f"Parent worldview not found: {normalized['worldview_id']}")
        else:
            existing = _get_outline_or_error(db, normalized["target_id"])
            if not existing:
                errors.append(f"Outline not found: {normalized['target_id']}")
            elif normalized.get("novel_id") and not _get_novel_or_error(db, normalized["novel_id"]):
                errors.append(f"Parent novel not found: {normalized['novel_id']}")
    elif entity_type == "chapter":
        if action == "create":
            outline = _get_outline_or_error(db, normalized["outline_id"])
            if not outline:
                errors.append(f"Parent outline not found: {normalized['outline_id']}")
            else:
                normalized["novel_id"] = outline.get("novel_id")
                normalized["worldview_id"] = outline.get("worldview_id") or DEFAULT_WORLDVIEW_ID
                normalized["world_id"] = outline.get("world_id") or DEFAULT_WORLD_ID
        else:
            target_id = normalized["target_id"]
            existing = db["prose"].find_one({"$or": [{"id": target_id}, {"scene_id": target_id}, {"prose_id": target_id}]})
            if not existing:
                errors.append(f"Chapter not found: {target_id}")

    return not errors, errors, normalized

def _apply_hierarchy_agent_operation(db, entity_type: str, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    now = _now_iso()
    if entity_type == "world":
        if action == "create":
            world_id = payload.get("world_id") or f"world_{uuid.uuid4().hex[:8]}"
            if db["worlds"].find_one({"world_id": world_id}):
                raise ValueError(f"World already exists: {world_id}")
            doc = {"world_id": world_id, "name": payload["name"], "summary": payload.get("summary", ""), "timestamp": now}
            db["worlds"].insert_one(doc)
            return {"world_id": world_id, **_mongo_doc(doc)}
        if action == "update":
            update_data = {"timestamp": now}
            if "name" in payload:
                update_data["name"] = payload.get("name", "")
            if "summary" in payload:
                update_data["summary"] = payload.get("summary", "")
            db["worlds"].update_one({"world_id": payload["target_id"]}, {"$set": update_data})
            return {"world_id": payload["target_id"], **update_data}
        if action == "delete":
            child_count = (
                db["worldviews"].count_documents({"world_id": payload["target_id"]})
                + db["novels"].count_documents({"world_id": payload["target_id"]})
                + db["outlines"].count_documents({"world_id": payload["target_id"]})
                + db["prose"].count_documents({"world_id": payload["target_id"]})
                + db["lore"].count_documents({"world_id": payload["target_id"]})
            )
            if child_count and not payload.get("cascade"):
                raise ValueError(f"World is not empty: {child_count}")
            deleted = {
                "lore": db["lore"].delete_many({"world_id": payload["target_id"]}).deleted_count if payload.get("cascade") else 0,
                "prose": db["prose"].delete_many({"world_id": payload["target_id"]}).deleted_count if payload.get("cascade") else 0,
                "outlines": db["outlines"].delete_many({"world_id": payload["target_id"]}).deleted_count if payload.get("cascade") else 0,
                "novels": db["novels"].delete_many({"world_id": payload["target_id"]}).deleted_count if payload.get("cascade") else 0,
                "worldviews": db["worldviews"].delete_many({"world_id": payload["target_id"]}).deleted_count if payload.get("cascade") else 0,
                "worlds": db["worlds"].delete_one({"world_id": payload["target_id"]}).deleted_count,
            }
            return {"deleted": deleted}

    if entity_type == "worldview":
        if action == "create":
            worldview_id = payload.get("worldview_id") or f"wv_{uuid.uuid4().hex[:8]}"
            doc = {"worldview_id": worldview_id, "world_id": payload["world_id"], "name": payload["name"], "summary": payload.get("summary", ""), "timestamp": now}
            db["worldviews"].insert_one(doc)
            return _mongo_doc(doc)
        if action == "update":
            update_data = {"timestamp": now}
            if "name" in payload:
                update_data["name"] = payload.get("name", "")
            if "summary" in payload:
                update_data["summary"] = payload.get("summary", "")
            db["worldviews"].update_one({"worldview_id": payload["target_id"]}, {"$set": update_data})
            return {"worldview_id": payload["target_id"], **update_data}
        if action == "delete":
            lore_count = db["lore"].count_documents({"worldview_id": payload["target_id"]})
            if lore_count and not payload.get("cascade"):
                raise ValueError(f"Worldview is not empty: {lore_count}")
            deleted = {
                "lore": db["lore"].delete_many({"worldview_id": payload["target_id"]}).deleted_count if payload.get("cascade") else 0,
                "worldviews": db["worldviews"].delete_one({"worldview_id": payload["target_id"]}).deleted_count,
            }
            return {"deleted": deleted}

    if entity_type == "novel":
        if action == "create":
            novel_id = payload.get("novel_id") or f"novel_{uuid.uuid4().hex[:8]}"
            doc = {"novel_id": novel_id, "world_id": payload["world_id"], "name": payload["name"], "summary": payload.get("summary", ""), "timestamp": now}
            db["novels"].insert_one(doc)
            return _novel_payload_from_doc(doc)
        if action == "update":
            update_data = {"timestamp": now}
            if "name" in payload:
                update_data["name"] = payload.get("name", "")
            if "summary" in payload:
                update_data["summary"] = payload.get("summary", "")
            if "world_id" in payload:
                update_data["world_id"] = payload.get("world_id")
            db["novels"].update_one({"novel_id": payload["target_id"]}, {"$set": update_data})
            return {"novel_id": payload["target_id"], **update_data}
        if action == "delete":
            child_count = db["outlines"].count_documents({"novel_id": payload["target_id"]}) + db["prose"].count_documents({"novel_id": payload["target_id"]})
            if child_count and not payload.get("cascade"):
                raise ValueError(f"Novel is not empty: {child_count}")
            deleted = {
                "prose": db["prose"].delete_many({"novel_id": payload["target_id"]}).deleted_count if payload.get("cascade") else 0,
                "outlines": db["outlines"].delete_many({"novel_id": payload["target_id"]}).deleted_count if payload.get("cascade") else 0,
                "novels": db["novels"].delete_one({"novel_id": payload["target_id"]}).deleted_count,
            }
            return {"deleted": deleted}

    if entity_type == "outline":
        if action == "create":
            outline_id = payload.get("outline_id") or f"outline_{uuid.uuid4().hex[:8]}"
            doc = {
                "outline_id": outline_id,
                "id": outline_id,
                "novel_id": payload["novel_id"],
                "world_id": payload.get("world_id") or DEFAULT_WORLD_ID,
                "worldview_id": payload.get("worldview_id") or DEFAULT_WORLDVIEW_ID,
                "name": payload["name"],
                "summary": payload.get("summary", ""),
                "timestamp": now,
            }
            db["outlines"].insert_one(doc)
            return _outline_payload_from_doc(doc)
        if action == "update":
            existing = _get_outline_or_error(db, payload["target_id"])
            update_data = {"timestamp": now}
            if "name" in payload:
                update_data["name"] = payload.get("name", "")
            if "summary" in payload:
                update_data["summary"] = payload.get("summary", "")
                update_data["content"] = payload.get("summary", "")
            if "novel_id" in payload:
                novel = _get_novel_or_error(db, payload["novel_id"])
                update_data["novel_id"] = payload.get("novel_id")
                update_data["world_id"] = (novel or {}).get("world_id") or existing.get("world_id")
            db["outlines"].update_one({"_id": existing["_id"]}, {"$set": update_data})
            return {"outline_id": payload["target_id"], **update_data}
        if action == "delete":
            child_count = db["prose"].count_documents({"outline_id": payload["target_id"]})
            if child_count and not payload.get("cascade"):
                raise ValueError(f"Outline is not empty: {child_count}")
            deleted = {
                "prose": db["prose"].delete_many({"outline_id": payload["target_id"]}).deleted_count if payload.get("cascade") else 0,
                "outlines": db["outlines"].delete_one({"$or": [{"outline_id": payload["target_id"]}, {"id": payload["target_id"]}]}).deleted_count,
            }
            return {"deleted": deleted}

    if entity_type == "chapter":
        if action == "create":
            chapter_id = payload.get("chapter_id") or payload.get("id") or f"chapter_{uuid.uuid4().hex[:8]}"
            doc = {
                "id": chapter_id,
                "scene_id": chapter_id,
                "type": "prose",
                "title": payload["name"],
                "content": payload.get("content") or payload.get("summary") or "",
                "outline_id": payload["outline_id"],
                "novel_id": payload.get("novel_id"),
                "worldview_id": payload.get("worldview_id") or DEFAULT_WORLDVIEW_ID,
                "world_id": payload.get("world_id") or DEFAULT_WORLD_ID,
                "timestamp": now,
            }
            db["prose"].insert_one(doc)
            return _chapter_payload_from_doc(doc)
        if action == "update":
            update_data = {"timestamp": now}
            if "name" in payload:
                update_data["title"] = payload.get("name", "")
            if "content" in payload:
                update_data["content"] = payload.get("content", "")
            elif "summary" in payload:
                update_data["content"] = payload.get("summary", "")
            db["prose"].update_one({"$or": [{"id": payload["target_id"]}, {"scene_id": payload["target_id"]}, {"prose_id": payload["target_id"]}]}, {"$set": update_data})
            return {"id": payload["target_id"], **update_data}
        if action == "delete":
            deleted = db["prose"].delete_one({"$or": [{"id": payload["target_id"]}, {"scene_id": payload["target_id"]}, {"prose_id": payload["target_id"]}]}).deleted_count
            return {"deleted": {"prose": deleted}}

    raise ValueError(f"Unsupported operation: {entity_type}/{action}")

def _create_hierarchy_agent_run(db, entity_type: str, action: str, payload: Dict[str, Any], message: str) -> Dict[str, Any]:
    run_id = f"hwf_{uuid.uuid4().hex[:10]}"
    agent_name = f"{entity_type}_agent"
    nodes = [
        _agent_node("input", "对话输入", "completed", {"message": message, "payload": payload}, {"accepted": True}),
        _agent_node("draft", f"{agent_name} 草案", "completed", {"action": action, "entity_type": entity_type}, {"payload": payload, "iteration": 1}),
    ]
    review_required = HIERARCHY_AGENT_REVIEW_REQUIRED[entity_type]
    ok, review_errors, normalized = _validate_hierarchy_agent_payload(db, entity_type, action, payload)
    if review_required:
        if ok:
            from src.agents.review_agent import execute_llm_review
            ok, review_errors = execute_llm_review(db, entity_type, normalized)
        nodes.append(_agent_node("review", f"{entity_type}_review_agent 审查", "completed" if ok else "failed", {"payload": normalized}, {"passed": ok, "errors": review_errors}))
    else:
        nodes.append(_agent_node("review", "审查节点", "skipped", {"entity_type": entity_type}, {"reason": "world 不需要审查"}))
    status = "waiting_human" if ok else "review_failed"
    nodes.append(_agent_node("human", "人工介入", "waiting" if ok else "blocked", {"review_passed": ok}, {"required": True}))
    doc = {
        "run_id": run_id,
        "agent_type": entity_type,
        "agent_name": agent_name,
        "action": action,
        "status": status,
        "iterations": 1,
        "review_required": review_required,
        "pending_payload": normalized,
        "message": message,
        "nodes": nodes,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "committed": False,
    }
    db["hierarchy_agent_runs"].insert_one(doc)
    return _hierarchy_run_payload(doc)

@app.route('/api/hierarchy-agent/start', methods=['POST'])
def start_hierarchy_agent():
    data = request.json or {}
    entity_type = data.get("agent_type") or data.get("entity_type")
    action = data.get("action")
    payload = data.get("payload") or {}
    message = data.get("message") or ""
    if entity_type not in HIERARCHY_AGENT_TYPES:
        return jsonify({"error": f"Invalid hierarchy agent type: {entity_type}"}), 400
    if action not in HIERARCHY_AGENT_ACTIONS:
        return jsonify({"error": f"Invalid hierarchy action: {action}"}), 400
    try:
        db = get_mongodb_db()
        run = _create_hierarchy_agent_run(db, entity_type, action, payload, message)
        return jsonify({"status": "success", "run": run})
    except Exception as e:
        logger.error(f"Failed to start hierarchy agent: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/hierarchy-agent/respond', methods=['POST'])
def respond_hierarchy_agent():
    data = request.json or {}
    run_id, error = _require_field(data, "run_id")
    if error:
        return error
    decision = data.get("decision")
    if decision not in {"approve", "request_changes", "reject"}:
        return jsonify({"error": f"Invalid decision: {decision}"}), 400
    try:
        db = get_mongodb_db()
        run = _get_hierarchy_agent_run(db, run_id)
        if not run:
            return jsonify({"error": f"Hierarchy agent run not found: {run_id}"}), 404
        if run.get("committed"):
            return jsonify({"error": f"Hierarchy agent run already committed: {run_id}"}), 409

        nodes = run.get("nodes", [])
        nodes.append(_agent_node("human_response", "人工反馈", "completed", {
            "decision": decision,
            "message": data.get("message", ""),
            "revision_mode": data.get("revision_mode"),
            "manual_edit": bool(data.get("manual_edit")),
        }, {"received": True}))

        if decision == "reject":
            update = {"status": "rejected", "nodes": nodes, "updated_at": _now_iso()}
            db["hierarchy_agent_runs"].update_one({"run_id": run_id}, {"$set": update})
            run.update(update)
            return jsonify({"status": "success", "run": _hierarchy_run_payload(run)})

        if decision == "request_changes":
            revision_mode = data.get("revision_mode")
            if revision_mode not in HIERARCHY_REVISION_MODES:
                return jsonify({"error": f"Invalid revision_mode: {revision_mode}"}), 400
            manual_edit = bool(data.get("manual_edit"))
            next_payload = {**(run.get("pending_payload") or {}), **(data.get("payload") or {})}
            next_iterations = int(run.get("iterations", 1)) + 1
            nodes.append(_agent_node(
                "revision",
                f"{run['agent_name']} 迭代",
                "completed",
                {
                    "feedback": data.get("message", ""),
                    "revision_mode": revision_mode,
                    "revision_mode_label": HIERARCHY_REVISION_MODES[revision_mode],
                    "scope_guard": HIERARCHY_REVISION_GUARDS[revision_mode],
                    "manual_edit": manual_edit,
                    "payload": next_payload,
                },
                {"payload": next_payload, "iteration": next_iterations, "manual_edit": manual_edit},
            ))
            ok, review_errors, normalized = _validate_hierarchy_agent_payload(db, run["agent_type"], run["action"], next_payload)
            if run.get("review_required"):
                if ok:
                    from src.agents.review_agent import execute_llm_review
                    ok, review_errors = execute_llm_review(db, run["agent_type"], normalized)
                nodes.append(_agent_node("review", f"{run['agent_type']}_review_agent 审查", "completed" if ok else "failed", {"payload": normalized}, {"passed": ok, "errors": review_errors}))
            else:
                nodes.append(_agent_node("review", "审查节点", "skipped", {"entity_type": run["agent_type"]}, {"reason": "world 不需要审查"}))
            nodes.append(_agent_node("human", "人工介入", "waiting" if ok else "blocked", {"review_passed": ok}, {"required": True}))
            update = {
                "status": "waiting_human" if ok else "review_failed",
                "pending_payload": normalized,
                "iterations": next_iterations,
                "last_revision_mode": revision_mode,
                "nodes": nodes,
                "updated_at": _now_iso(),
            }
            db["hierarchy_agent_runs"].update_one({"run_id": run_id}, {"$set": update})
            run.update(update)
            return jsonify({"status": "success", "run": _hierarchy_run_payload(run)})

        if run.get("status") != "waiting_human":
            return jsonify({"error": f"Run is not ready for approval: {run.get('status')}"}), 409
        result = _apply_hierarchy_agent_operation(db, run["agent_type"], run["action"], run.get("pending_payload") or {})
        nodes.append(_agent_node("apply", "真实写库", "completed", {"payload": run.get("pending_payload")}, {"result": result}))
        update = {
            "status": "completed",
            "committed": True,
            "commit_result": result,
            "nodes": nodes,
            "updated_at": _now_iso(),
        }
        db["hierarchy_agent_runs"].update_one({"run_id": run_id}, {"$set": update})
        run.update(update)
        return jsonify({"status": "success", "run": _hierarchy_run_payload(run)})
    except ValueError as e:
        return jsonify({"error": str(e)}), 409
    except Exception as e:
        logger.error(f"Failed to respond hierarchy agent: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/hierarchy-agent/get', methods=['GET'])
def get_hierarchy_agent():
    run_id = request.args.get("run_id")
    if not run_id:
        return jsonify({"error": "Missing required field: run_id"}), 400
    try:
        db = get_mongodb_db()
        run = _get_hierarchy_agent_run(db, run_id)
        if not run:
            return jsonify({"error": f"Hierarchy agent run not found: {run_id}"}), 404
        return jsonify({"status": "success", "run": _hierarchy_run_payload(run)})
    except Exception as e:
        logger.error(f"Failed to get hierarchy agent: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/hierarchy-agent/list', methods=['GET'])
def list_hierarchy_agents():
    condition_error = _require_query_condition("agent_type", "status", "run_id")
    if condition_error:
        return condition_error
    skip, limit, pagination_error = _pagination_params()
    if pagination_error:
        return pagination_error
    try:
        db = get_mongodb_db()
        query: Dict[str, Any] = {}
        if request.args.get("agent_type"):
            query["agent_type"] = request.args.get("agent_type")
        if request.args.get("status"):
            query["status"] = request.args.get("status")
        if request.args.get("run_id"):
            query["run_id"] = request.args.get("run_id")
        runs = [
            _hierarchy_run_payload(item)
            for item in db["hierarchy_agent_runs"].find(query).sort("created_at", -1).skip(skip).limit(limit)
        ]
        return jsonify({"status": "success", "runs": runs})
    except Exception as e:
        logger.error(f"Failed to list hierarchy agents: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/worlds/list', methods=['GET'])
def list_worlds():
    try:
        db = get_mongodb_db()
        _ensure_default_hierarchy(db)
        worlds = [_mongo_doc(item) for item in db["worlds"].find({})]
        return jsonify(worlds)
    except Exception as e:
        logger.error(f"Failed to list worlds: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/worlds/create', methods=['POST'])
def create_world():
    data = request.json or {}
    name = data.get("name")
    if not name:
        return jsonify({"error": "Missing required field: name"}), 400
    world_id = data.get("world_id") or f"world_{uuid.uuid4().hex[:8]}"
    doc = {
        "world_id": world_id,
        "name": name,
        "summary": data.get("summary", ""),
        "timestamp": _now_iso(),
    }
    try:
        db = get_mongodb_db()
        if db["worlds"].find_one({"world_id": world_id}):
            return jsonify({"error": f"World already exists: {world_id}"}), 409
        db["worlds"].insert_one(doc)
        return jsonify({"status": "success", "world_id": world_id, "name": name, "summary": doc["summary"]})
    except Exception as e:
        logger.error(f"Failed to create world: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/worlds/update', methods=['POST'])
def update_world():
    data = request.json or {}
    world_id, error = _require_field(data, "world_id")
    if error:
        return error
    try:
        db = get_mongodb_db()
        if not _get_world_or_error(db, world_id):
            return jsonify({"error": f"World not found: {world_id}"}), 404
        update_data = {"timestamp": _now_iso()}
        if "name" in data:
            if not data.get("name"):
                return jsonify({"error": "Missing required field: name"}), 400
            update_data["name"] = data["name"]
        if "summary" in data:
            update_data["summary"] = data.get("summary", "")
        db["worlds"].update_one({"world_id": world_id}, {"$set": update_data})
        return jsonify({"status": "success", "world_id": world_id, **update_data})
    except Exception as e:
        logger.error(f"Failed to update world: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/worlds/delete', methods=['DELETE'])
def delete_world():
    data = _json_or_args()
    world_id, error = _require_field(data, "world_id")
    if error:
        return error
    cascade = _wants_cascade(data)
    try:
        db = get_mongodb_db()
        if not _get_world_or_error(db, world_id):
            return jsonify({"error": f"World not found: {world_id}"}), 404
        child_count = (
            db["worldviews"].count_documents({"world_id": world_id})
            + db["novels"].count_documents({"world_id": world_id})
            + db["outlines"].count_documents({"world_id": world_id})
            + db["prose"].count_documents({"world_id": world_id})
            + db["lore"].count_documents({"world_id": world_id})
        )
        if child_count and not cascade:
            return jsonify({"error": "World is not empty", "child_count": child_count}), 409
        deleted = {
            "lore": db["lore"].delete_many({"world_id": world_id}).deleted_count if cascade else 0,
            "prose": db["prose"].delete_many({"world_id": world_id}).deleted_count if cascade else 0,
            "outlines": db["outlines"].delete_many({"world_id": world_id}).deleted_count if cascade else 0,
            "novels": db["novels"].delete_many({"world_id": world_id}).deleted_count if cascade else 0,
            "worldviews": db["worldviews"].delete_many({"world_id": world_id}).deleted_count if cascade else 0,
            "worlds": db["worlds"].delete_one({"world_id": world_id}).deleted_count,
        }
        return jsonify({"status": "success", "deleted": deleted})
    except Exception as e:
        logger.error(f"Failed to delete world: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/outlines/list', methods=['GET'])
def list_outlines():
    """获取分页大纲；禁止无条件全量查询。"""
    condition_error = _require_query_condition("world_id", "worldview_id", "novel_id", "outline_id", "query")
    if condition_error:
        return condition_error
    skip, limit, pagination_error = _pagination_params()
    if pagination_error:
        return pagination_error
    try:
        db = get_mongodb_db()
        query: Dict[str, Any] = {}
        if request.args.get("world_id"):
            query["world_id"] = request.args.get("world_id")
        if request.args.get("worldview_id"):
            query["worldview_id"] = request.args.get("worldview_id")
        if request.args.get("novel_id"):
            query["novel_id"] = request.args.get("novel_id")
        if request.args.get("outline_id"):
            query["$or"] = [{"outline_id": request.args.get("outline_id")}, {"id": request.args.get("outline_id")}]
        if request.args.get("query"):
            text_filter = {"$regex": request.args.get("query"), "$options": "i"}
            text_or = [{"name": text_filter}, {"title": text_filter}, {"summary": text_filter}, {"content": text_filter}, {"outline_id": text_filter}]
            if "$or" in query:
                query = {"$and": [query, {"$or": text_or}]}
            else:
                query["$or"] = text_or
        cursor = db["outlines"].find(query).sort("timestamp", -1).skip(skip).limit(limit)
        outlines = []
        for doc in cursor:
            outlines.append(_outline_payload_from_doc(doc))
        
        return jsonify(outlines)
    except Exception as e:
        logger.error(f"Failed to list outlines: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/outlines/create', methods=['POST'])
def create_outline():
    """创建新大纲 - MongoDB 物理写入。兼容旧客户端：未传 novel_id 时自动创建同名小说容器。"""
    data = request.json or {}
    name = data.get('name')
    if not name:
        return jsonify({"error": "Missing required field: name"}), 400
    summary = data.get('summary', '')
    worldview_id = data.get('worldview_id') or DEFAULT_WORLDVIEW_ID
    novel_id = data.get("novel_id")
    world_id = data.get("world_id")

    outline_id = data.get("outline_id") or f"outline_{uuid.uuid4().hex[:8]}"

    try:
        db = get_mongodb_db()
        worldview = _get_worldview_or_error(db, worldview_id)
        if not worldview:
            return jsonify({"error": f"Parent worldview not found: {worldview_id}"}), 404

        if novel_id:
            novel = _get_novel_or_error(db, novel_id)
            if not novel:
                return jsonify({"error": f"Parent novel not found: {novel_id}"}), 404
            world_id = novel.get("world_id") or worldview.get("world_id") or DEFAULT_WORLD_ID
        else:
            world_id = world_id or worldview.get("world_id") or DEFAULT_WORLD_ID
            novel_id = f"novel_{uuid.uuid4().hex[:8]}"
            db["novels"].insert_one({
                "novel_id": novel_id,
                "world_id": world_id,
                "name": name,
                "summary": summary,
                "timestamp": _now_iso(),
            })

        new_entry = {
        "outline_id": outline_id,
        "novel_id": novel_id,
        "world_id": world_id,
        "worldview_id": worldview_id,
        "name": name,
        "summary": summary,
        "timestamp": _now_iso()
        }
        db["outlines"].insert_one(new_entry)
        return jsonify({
            "status": "success",
            "outline_id": outline_id,
            "novel_id": novel_id,
            "world_id": world_id,
            "worldview_id": worldview_id,
            "name": name
        })
    except Exception as e:
        logger.error(f"Failed to create new novel project: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/novels/list', methods=['GET'])
def list_novels():
    condition_error = _require_query_condition("world_id", "novel_id", "query")
    if condition_error:
        return condition_error
    skip, limit, pagination_error = _pagination_params()
    if pagination_error:
        return pagination_error
    try:
        db = get_mongodb_db()
        query: Dict[str, Any] = {}
        if request.args.get("world_id"):
            query["world_id"] = request.args.get("world_id")
        if request.args.get("novel_id"):
            query["novel_id"] = request.args.get("novel_id")
        if request.args.get("query"):
            text_filter = {"$regex": request.args.get("query"), "$options": "i"}
            query["$or"] = [{"name": text_filter}, {"summary": text_filter}, {"novel_id": text_filter}]
        novels = [_novel_payload_from_doc(item) for item in db["novels"].find(query).sort("timestamp", -1).skip(skip).limit(limit)]
        return jsonify(novels)
    except Exception as e:
        logger.error(f"Failed to list novels: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/novels/create', methods=['POST'])
def create_novel():
    data = request.json or {}
    name = data.get("name")
    if not name:
        return jsonify({"error": "Missing required field: name"}), 400
    world_id = data.get("world_id")
    if not world_id:
        return jsonify({"error": "Missing required field: world_id"}), 400
    try:
        db = get_mongodb_db()
        if not _get_world_or_error(db, world_id):
            return jsonify({"error": f"Parent world not found: {world_id}"}), 404
        novel_id = data.get("novel_id") or f"novel_{uuid.uuid4().hex[:8]}"
        if db["novels"].find_one({"novel_id": novel_id}):
            return jsonify({"error": f"Novel already exists: {novel_id}"}), 409
        doc = {
            "novel_id": novel_id,
            "world_id": world_id,
            "name": name,
            "summary": data.get("summary", ""),
            "timestamp": _now_iso(),
        }
        db["novels"].insert_one(doc)
        return jsonify({"status": "success", **_novel_payload_from_doc(doc)})
    except Exception as e:
        logger.error(f"Failed to create novel: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/novels/update', methods=['POST'])
def update_novel():
    data = request.json or {}
    novel_id, error = _require_field(data, "novel_id")
    if error:
        return error
    try:
        db = get_mongodb_db()
        existing = _get_novel_or_error(db, novel_id)
        if not existing:
            return jsonify({"error": f"Novel not found: {novel_id}"}), 404
        update_data = {"timestamp": _now_iso()}
        if "name" in data:
            if not data.get("name"):
                return jsonify({"error": "Missing required field: name"}), 400
            update_data["name"] = data["name"]
        if "summary" in data:
            update_data["summary"] = data.get("summary", "")
        if "world_id" in data:
            if not _get_world_or_error(db, data["world_id"]):
                return jsonify({"error": f"Parent world not found: {data['world_id']}"}), 404
            update_data["world_id"] = data["world_id"]
        db["novels"].update_one({"novel_id": novel_id}, {"$set": update_data})
        return jsonify({"status": "success", "novel_id": novel_id, **update_data})
    except Exception as e:
        logger.error(f"Failed to update novel: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/novels/delete', methods=['DELETE'])
def delete_novel():
    data = _json_or_args()
    novel_id, error = _require_field(data, "novel_id")
    if error:
        return error
    cascade = _wants_cascade(data)
    try:
        db = get_mongodb_db()
        if not _get_novel_or_error(db, novel_id):
            return jsonify({"error": f"Novel not found: {novel_id}"}), 404
        child_count = (
            db["outlines"].count_documents({"novel_id": novel_id})
            + db["prose"].count_documents({"novel_id": novel_id})
        )
        if child_count and not cascade:
            return jsonify({"error": "Novel is not empty", "child_count": child_count}), 409
        deleted = {
            "prose": db["prose"].delete_many({"novel_id": novel_id}).deleted_count if cascade else 0,
            "outlines": db["outlines"].delete_many({"novel_id": novel_id}).deleted_count if cascade else 0,
            "novels": db["novels"].delete_one({"novel_id": novel_id}).deleted_count,
        }
        return jsonify({"status": "success", "deleted": deleted})
    except Exception as e:
        logger.error(f"Failed to delete novel: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/world-hierarchy/tree', methods=['GET'])
def get_world_hierarchy_tree():
    """返回指定世界的分页业务层级: 世界 -> [世界观, 小说] -> 大纲 -> 章节。"""
    if not request.args.get("world_id"):
        return jsonify({"error": "Missing required query condition: world_id"}), 400
    skip, limit, pagination_error = _pagination_params()
    if pagination_error:
        return pagination_error
    try:
        db = get_mongodb_db()
        _ensure_default_hierarchy(db)
        world_filter = request.args.get("world_id")
        worldview_filter = request.args.get("worldview_id")
        novel_filter = request.args.get("novel_id")
        outline_filter = request.args.get("outline_id")

        world_query = {"world_id": world_filter} if world_filter else {}
        worlds = [_mongo_doc(item) for item in db["worlds"].find(world_query)]
        world_nodes: Dict[str, Dict[str, Any]] = {
            item["world_id"]: {
                "world_id": item["world_id"],
                "name": item.get("name") or "",
                "summary": item.get("summary", ""),
                "timestamp": item.get("timestamp"),
                "worldviews": [],
                "novels": [],
            }
            for item in worlds
        }

        worldview_query: Dict[str, Any] = {}
        if world_filter:
            worldview_query["world_id"] = world_filter
        if worldview_filter:
            worldview_query["worldview_id"] = worldview_filter
        worldviews = list(db["worldviews"].find(worldview_query).sort("timestamp", -1).skip(skip).limit(limit))
        worldview_nodes: Dict[str, Dict[str, Any]] = {}
        for item in worldviews:
            world_id = item.get("world_id") or DEFAULT_WORLD_ID
            if world_id not in world_nodes:
                continue
            node = {
                "worldview_id": item.get("worldview_id"),
                "world_id": world_id,
                "name": item.get("name") or "",
                "summary": item.get("summary", ""),
                "timestamp": item.get("timestamp"),
            }
            worldview_nodes[node["worldview_id"]] = node
            world_nodes[world_id]["worldviews"].append(node)

        novel_query: Dict[str, Any] = {}
        if world_filter:
            novel_query["world_id"] = world_filter
        if novel_filter:
            novel_query["novel_id"] = novel_filter
        novel_nodes: Dict[str, Dict[str, Any]] = {}
        for item in db["novels"].find(novel_query).sort("timestamp", -1).skip(skip).limit(limit):
            novel = _novel_payload_from_doc(item)
            node = {**novel, "outlines": []}
            novel_nodes[node["novel_id"]] = node
            
            # 挂载到 World 级别而非 Worldview 级别
            world_id = node.get("world_id") or DEFAULT_WORLD_ID
            if world_id in world_nodes:
                if "novels" not in world_nodes[world_id]:
                    world_nodes[world_id]["novels"] = []
                world_nodes[world_id]["novels"].append(node)

        outline_query: Dict[str, Any] = {}
        if world_filter:
            outline_query["world_id"] = world_filter
        if worldview_filter:
            outline_query["worldview_id"] = worldview_filter
        if novel_filter:
            outline_query["novel_id"] = novel_filter
        if outline_filter:
            outline_query["$or"] = [{"outline_id": outline_filter}, {"id": outline_filter}]
        outline_nodes: Dict[str, Dict[str, Any]] = {}
        for item in db["outlines"].find(outline_query).sort("timestamp", -1).skip(skip).limit(limit):
            outline = _outline_payload_from_doc(item)
            node = {**outline, "chapters": []}
            outline_nodes[node["outline_id"]] = node
            parent = novel_nodes.get(node.get("novel_id"))
            if parent:
                parent["outlines"].append(node)

        prose_query: Dict[str, Any] = {}
        if world_filter:
            prose_query["world_id"] = world_filter
        if worldview_filter:
            prose_query["worldview_id"] = worldview_filter
        if novel_filter:
            prose_query["novel_id"] = novel_filter
        if outline_filter:
            prose_query["outline_id"] = outline_filter
        for item in db["prose"].find(prose_query).sort("timestamp", -1).skip(skip).limit(limit):
            chapter = _chapter_payload_from_doc(item)
            parent = outline_nodes.get(chapter.get("outline_id"))
            if parent:
                parent["chapters"].append(chapter)

        for world in world_nodes.values():
            world["worldviews"].sort(key=lambda item: item.get("name", ""))
            world.setdefault("novels", []).sort(key=lambda item: item.get("name", ""))
            for novel in world.get("novels", []):
                novel["outlines"].sort(key=lambda item: item.get("title", ""))
                for outline in novel["outlines"]:
                    outline["chapters"].sort(key=lambda item: item.get("name", ""))

        return jsonify({"status": "success", "worlds": list(world_nodes.values())})
    except Exception as e:
        logger.error(f"Failed to load world hierarchy tree: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # 启动 5006 端口 (避开死锁的 5005)
    app.run(port=5006, host='localhost', debug=False)
