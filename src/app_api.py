"""Flask API backend for Novel Agent.

This file is the real HTTP entrypoint expected by the Makefile, README, and
generated API docs. It uses MongoDB through the project helper and calls the
existing agent node functions directly for hierarchy workflows.
"""

from __future__ import annotations

import copy
import os
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from bson import ObjectId
from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

from src.agents import chapter_agent, novel_agent, outline_agent, worldview_agent, world_agent
from src.common.lore_utils import get_mongodb_db


app = Flask(__name__)
CORS(app)


AGENT_MODULES = {
    "world": world_agent,
    "worldview": worldview_agent,
    "novel": novel_agent,
    "outline": outline_agent,
    "chapter": chapter_agent,
}

AGENT_CAPABILITIES = {
    "world": {
        "label": "世界 Agent",
        "description": "创建或修改顶层世界、世界禁止规则与世界基础设定。",
        "required_context": [],
        "id_fields": ["world_id", "target_id"],
        "content_fields": ["name", "summary", "forbidden_rules", "basic_settings"],
    },
    "worldview": {
        "label": "世界观 Agent",
        "description": "创建或修改世界下的世界观容器与世界观设定。",
        "required_context": ["world_id"],
        "id_fields": ["worldview_id", "target_id"],
        "content_fields": ["name", "summary", "forbidden_rules", "basic_settings"],
    },
    "novel": {
        "label": "小说 Agent",
        "description": "创建或修改小说项目、小说介绍、小说简介与小说级规则。",
        "required_context": ["world_id"],
        "id_fields": ["novel_id", "target_id"],
        "content_fields": ["name", "introduction", "summary", "forbidden_rules", "basic_settings"],
    },
    "outline": {
        "label": "大纲 Agent",
        "description": "创建或修改小说下的大纲，并执行世界、世界观和小说约束审查。",
        "required_context": ["novel_id"],
        "id_fields": ["outline_id", "id", "target_id"],
        "content_fields": ["name", "summary", "worldview_id"],
    },
    "chapter": {
        "label": "章节 Agent",
        "description": "创建或修改大纲下的章节正文，并执行全链路约束审查。",
        "required_context": ["outline_id"],
        "id_fields": ["chapter_id", "scene_id", "prose_id", "id", "target_id"],
        "content_fields": ["name", "content"],
    },
}

AGENT_ALIASES = {
    "world": "world",
    "world_agent": "world",
    "世界": "world",
    "worldview": "worldview",
    "worldview_agent": "worldview",
    "世界观": "worldview",
    "设定": "worldview",
    "novel": "novel",
    "novel_agent": "novel",
    "小说": "novel",
    "outline": "outline",
    "outline_agent": "outline",
    "大纲": "outline",
    "chapter": "chapter",
    "chapter_agent": "chapter",
    "章节": "chapter",
    "正文": "chapter",
}

ACTION_ALIASES = {
    "create": "create",
    "new": "create",
    "add": "create",
    "新增": "create",
    "创建": "create",
    "update": "update",
    "modify": "update",
    "edit": "update",
    "修改": "update",
    "更新": "update",
}

AGENT_KEYWORDS = [
    ("chapter", ["chapter", "章节", "正文", "scene", "prose"]),
    ("outline", ["outline", "大纲"]),
    ("novel", ["novel", "小说"]),
    ("worldview", ["worldview", "世界观", "设定"]),
    ("world", ["world", "世界"]),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, list):
        return [_clean(item) for item in value]
    if isinstance(value, dict):
        return {key: _clean(item) for key, item in value.items() if key != "_id"}
    return value


def _json(data: Any, status: int = 200):
    return jsonify(_clean(data)), status


def _body() -> dict[str, Any]:
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        raise ValueError("JSON body must be an object")
    return data


def _db():
    return get_mongodb_db()


def _find_one(collection: str, query: dict[str, Any]) -> dict[str, Any] | None:
    return _db()[collection].find_one(query)


def _require(value: Any, message: str) -> Any:
    if value in (None, ""):
        raise ValueError(message)
    return value


def _new_api_key() -> str:
    return f"na_{secrets.token_urlsafe(32)}"


def _public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_id": user.get("user_id"),
        "username": user.get("username"),
        "display_name": user.get("display_name") or user.get("username"),
        "email": user.get("email", ""),
        "api_key": user.get("api_key"),
        "created_at": user.get("created_at"),
        "updated_at": user.get("updated_at"),
        "last_login_at": user.get("last_login_at"),
    }


def _auth_token() -> str:
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header.split(" ", 1)[1].strip()
    return request.args.get("token", "").strip()


def _request_api_key() -> str:
    header = request.headers.get("X-API-Key") or request.headers.get("X-Api-Key") or ""
    if header:
        return header.strip()
    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("apikey "):
        return authorization.split(" ", 1)[1].strip()
    return request.args.get("api_key", "").strip()


def _current_user() -> dict[str, Any]:
    token = _auth_token()
    api_key = _request_api_key()
    if token:
        session = _find_one("auth_sessions", {"token": token})
        if session:
            user = _find_one("users", {"user_id": session.get("user_id")})
            if not user:
                raise PermissionError("User not found")
            return user

        if not api_key:
            raise PermissionError("Invalid auth token")

    if api_key:
        user = _find_one("users", {"api_key": api_key})
        if not user:
            raise PermissionError("Invalid API key")
        return user

    raise PermissionError("Missing auth token or API key")


def _list_collection(collection: str, query: dict[str, Any], *, sort_field: str = "created_at") -> list[dict[str, Any]]:
    page = max(int(request.args.get("page", 1)), 1)
    page_size = min(max(int(request.args.get("page_size", 100)), 1), 200)
    cursor = _db()[collection].find(query).sort(sort_field, -1).skip((page - 1) * page_size).limit(page_size)
    items = [_clean(doc) for doc in cursor]
    for item in items:
        if "name" not in item and item.get("title"):
            item["name"] = item["title"]
        if "title" not in item and item.get("name"):
            item["title"] = item["name"]
    return items


def _resolve_novel_context(payload: dict[str, Any]) -> dict[str, Any]:
    novel_id = payload.get("novel_id")
    if novel_id:
        novel = _find_one("novels", {"novel_id": novel_id}) or {}
        payload.setdefault("world_id", novel.get("world_id"))
    return payload


def _resolve_outline_context(payload: dict[str, Any]) -> dict[str, Any]:
    outline_id = payload.get("outline_id")
    if outline_id:
        outline = _find_one("outlines", {"$or": [{"outline_id": outline_id}, {"id": outline_id}]}) or {}
        payload.setdefault("novel_id", outline.get("novel_id"))
        payload.setdefault("world_id", outline.get("world_id"))
        payload.setdefault("worldview_id", outline.get("worldview_id"))
    return payload


def _enrich_payload(agent_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    payload = dict(payload or {})
    if agent_type == "outline":
        _resolve_novel_context(payload)
    if agent_type == "chapter":
        _resolve_outline_context(payload)
        _resolve_novel_context(payload)
    if agent_type == "worldview" and payload.get("target_id"):
        doc = _find_one("worldviews", {"worldview_id": payload["target_id"]}) or {}
        payload.setdefault("world_id", doc.get("world_id"))
    if agent_type == "novel" and payload.get("target_id"):
        doc = _find_one("novels", {"novel_id": payload["target_id"]}) or {}
        payload.setdefault("world_id", doc.get("world_id"))
    return payload


def _run_node(module: Any, node_name: str, state: dict[str, Any]) -> dict[str, Any]:
    result = getattr(module, node_name)(state)
    if result:
        state.update(result)
    return state


def _run_until_human(agent_type: str, action: str, payload: dict[str, Any], message: str) -> dict[str, Any]:
    module = AGENT_MODULES[agent_type]
    state: dict[str, Any] = {
        "action": action,
        "payload": _enrich_payload(agent_type, payload),
        "message": message,
        "nodes": [],
        "conversation": [{"role": "user", "content": message, "created_at": _now()}],
        "iterations": 0,
        "committed": False,
    }
    _run_node(module, "input_node", state)
    _run_node(module, "initial_expansion_node", state)

    review_sequences = {
        "world": [],
        "worldview": ["world_rule_review_node", "worldview_consistency_review_node"],
        "novel": ["review_node"],
        "outline": ["world_review_node", "worldview_review_node", "novel_review_node"],
        "chapter": ["world_review_node", "worldview_review_node", "novel_review_node", "outline_review_node", "chapter_review_node"],
    }
    for node_name in review_sequences[agent_type]:
        _run_node(module, node_name, state)
        if state.get("current_node") == "modify_content":
            state["status"] = "review_failed"
            break

    if state.get("current_node") not in {"modify_content", "human"}:
        state["current_node"] = "human"
    state.setdefault("status", "waiting_human")
    return state


def _save_run(run: dict[str, Any]) -> dict[str, Any]:
    db = _db()
    run = copy.deepcopy(run)
    run.setdefault("run_id", f"run_{uuid.uuid4().hex[:12]}")
    run["updated_at"] = _now()
    run.setdefault("created_at", run["updated_at"])
    db["hierarchy_agent_runs"].update_one({"run_id": run["run_id"]}, {"$set": _clean(run)}, upsert=True)
    return _clean(run)


def _load_run(run_id: str) -> dict[str, Any]:
    run = _find_one("hierarchy_agent_runs", {"run_id": run_id})
    if not run:
        raise ValueError(f"Run not found: {run_id}")
    return _clean(run)


def _commit_run(run: dict[str, Any]) -> dict[str, Any]:
    module = AGENT_MODULES[run["agent_type"]]
    state = dict(run)
    state["decision"] = "approve"
    result = module.commit_node(state)
    state.update(result or {})
    state["status"] = "completed"
    state["committed"] = True
    return _save_run(state)


def _normalize_agent_type(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return AGENT_ALIASES.get(str(value).strip().lower()) or AGENT_ALIASES.get(str(value).strip())


def _normalize_action(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return ACTION_ALIASES.get(str(value).strip().lower()) or ACTION_ALIASES.get(str(value).strip())


def _infer_agent_type(data: dict[str, Any], payload: dict[str, Any], message: str) -> tuple[str, str]:
    explicit = (
        data.get("agent_type")
        or data.get("agent")
        or data.get("target_agent")
        or data.get("entity")
        or data.get("entity_type")
        or data.get("type")
        or payload.get("agent_type")
        or payload.get("entity_type")
        or payload.get("type")
    )
    agent_type = _normalize_agent_type(explicit)
    if agent_type:
        return agent_type, "explicit"

    if payload.get("outline_id") or payload.get("chapter_id") or payload.get("scene_id") or payload.get("prose_id"):
        return "chapter", "payload_context"
    if payload.get("novel_id"):
        return "outline", "payload_context"
    if payload.get("worldview_id"):
        return "worldview", "payload_context"

    text = f"{data.get('title', '')} {message}".lower()
    for candidate, keywords in AGENT_KEYWORDS:
        if any(keyword.lower() in text for keyword in keywords):
            return candidate, "message_keyword"

    raise ValueError("Cannot infer agent_type. Provide one of: world, worldview, novel, outline, chapter")


def _infer_action(data: dict[str, Any], payload: dict[str, Any], agent_type: str, message: str) -> tuple[str, str]:
    explicit = data.get("action") or payload.get("action")
    action = _normalize_action(explicit)
    if action:
        return action, "explicit"

    id_fields = AGENT_CAPABILITIES[agent_type]["id_fields"]
    if payload.get("target_id") or any(payload.get(field) for field in id_fields):
        return "update", "payload_id"

    text = f"{data.get('title', '')} {message}".lower()
    for raw, normalized in ACTION_ALIASES.items():
        if raw.lower() in text:
            return normalized, "message_keyword"

    return "create", "default"


def _normalize_dispatch_payload(agent_type: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
    payload = dict(payload or {})
    if action == "update" and not payload.get("target_id"):
        for field in AGENT_CAPABILITIES[agent_type]["id_fields"]:
            if field != "target_id" and payload.get(field):
                payload["target_id"] = payload[field]
                break
    return payload


def _validate_dispatch(agent_type: str, action: str, payload: dict[str, Any]) -> None:
    if agent_type not in AGENT_MODULES:
        raise ValueError(f"Unsupported agent_type: {agent_type}")
    if action not in {"create", "update"}:
        raise ValueError(f"Unsupported action for router dispatch: {action}. Supported actions: create, update")
    if action == "update" and not payload.get("target_id"):
        raise ValueError(f"Update dispatch for {agent_type} requires target_id or one of {AGENT_CAPABILITIES[agent_type]['id_fields']}")
    missing = [field for field in AGENT_CAPABILITIES[agent_type]["required_context"] if not payload.get(field)]
    if missing and action == "create":
        raise ValueError(f"{agent_type} dispatch missing required context: {', '.join(missing)}")


def _save_dispatch(dispatch: dict[str, Any]) -> dict[str, Any]:
    dispatch = copy.deepcopy(dispatch)
    dispatch.setdefault("dispatch_id", f"dispatch_{uuid.uuid4().hex[:12]}")
    dispatch["updated_at"] = _now()
    dispatch.setdefault("created_at", dispatch["updated_at"])
    _db()["agent_dispatch_requests"].update_one(
        {"dispatch_id": dispatch["dispatch_id"]},
        {"$set": _clean(dispatch)},
        upsert=True,
    )
    return _clean(dispatch)


def _load_dispatch(dispatch_id: str) -> dict[str, Any]:
    dispatch = _find_one("agent_dispatch_requests", {"dispatch_id": dispatch_id})
    if not dispatch:
        raise ValueError(f"Dispatch not found: {dispatch_id}")
    return _clean(dispatch)


def _load_dispatch_by_task_ref(task_ref: str) -> dict[str, Any]:
    dispatch = _find_one("agent_dispatch_requests", {"external_task_ref": task_ref})
    if not dispatch:
        raise ValueError(f"Dispatch not found for task_ref: {task_ref}")
    return _clean(dispatch)


def _dispatch_response(dispatch: dict[str, Any], route: dict[str, Any], run: dict[str, Any] | None = None) -> dict[str, Any]:
    response: dict[str, Any] = {"status": "success", "dispatch": dispatch, "route": route}
    if dispatch.get("external_task_ref"):
        response["task_ref"] = dispatch["external_task_ref"]
        response["external_task_ref"] = dispatch["external_task_ref"]
    if run is not None:
        response["run"] = run
    return response


def _start_agent_run(agent_type: str, action: str, payload: dict[str, Any], message: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    state = _run_until_human(agent_type, action, payload, message)
    run = {
        **state,
        "run_id": f"run_{uuid.uuid4().hex[:12]}",
        "agent_type": agent_type,
        "action": action,
        "review_required": agent_type != "world",
        "status": state.get("status", "waiting_human"),
        "current_node": state.get("current_node", "human"),
        "committed": False,
    }
    if metadata:
        run["dispatch"] = metadata
    return _save_run(run)


@app.errorhandler(Exception)
def handle_error(exc: Exception):
    status = 500
    if isinstance(exc, HTTPException):
        status = exc.code or 500
    if isinstance(exc, PermissionError):
        status = 401
    if isinstance(exc, ValueError):
        status = 400
    return _json({"status": "error", "error": str(exc)}, status)


@app.get("/")
def index():
    return _json({"status": "success", "service": "novel_agent"})


@app.post("/api/auth/register")
def register_user():
    data = _body()
    username = str(_require(data.get("username"), "Missing username")).strip()
    password = str(_require(data.get("password"), "Missing password"))
    display_name = str(data.get("display_name") or username).strip()
    email = str(data.get("email") or "").strip()
    if len(username) < 3:
        return _json({"status": "error", "error": "Username must be at least 3 characters"}, 400)
    if len(password) < 6:
        return _json({"status": "error", "error": "Password must be at least 6 characters"}, 400)
    if _find_one("users", {"username": username}):
        return _json({"status": "error", "error": f"Username already exists: {username}"}, 409)
    now = _now()
    user = {
        "user_id": f"user_{uuid.uuid4().hex[:12]}",
        "username": username,
        "display_name": display_name,
        "email": email,
        "api_key": _new_api_key(),
        "password_hash": generate_password_hash(password),
        "created_at": now,
        "updated_at": now,
        "last_login_at": now,
    }
    _db()["users"].insert_one(user)
    token = secrets.token_urlsafe(32)
    _db()["auth_sessions"].insert_one(
        {
            "token": token,
            "user_id": user["user_id"],
            "username": username,
            "created_at": now,
            "updated_at": now,
        }
    )
    return _json({"status": "success", "token": token, "api_key": user["api_key"], "user": _public_user(user)})


@app.post("/api/auth/login")
def login_user():
    data = _body()
    username = str(_require(data.get("username"), "Missing username")).strip()
    password = str(_require(data.get("password"), "Missing password"))
    user = _find_one("users", {"username": username})
    if not user or not check_password_hash(user.get("password_hash", ""), password):
        return _json({"status": "error", "error": "Invalid username or password"}, 401)
    token = secrets.token_urlsafe(32)
    now = _now()
    api_key = user.get("api_key") or _new_api_key()
    session = {
        "token": token,
        "user_id": user["user_id"],
        "username": username,
        "created_at": now,
        "updated_at": now,
    }
    _db()["auth_sessions"].insert_one(session)
    _db()["users"].update_one(
        {"user_id": user["user_id"]},
        {"$set": {"api_key": api_key, "last_login_at": now, "updated_at": now}},
    )
    user["api_key"] = api_key
    user["last_login_at"] = now
    user["updated_at"] = now
    return _json({"status": "success", "token": token, "api_key": api_key, "user": _public_user(user)})


@app.get("/api/auth/me")
def get_current_user():
    return _json({"status": "success", "user": _public_user(_current_user())})


@app.post("/api/auth/logout")
def logout_user():
    token = _auth_token()
    if token:
        _db()["auth_sessions"].delete_many({"token": token})
    return _json({"status": "success"})


@app.post("/api/worlds/create")
def create_world():
    data = _body()
    world_id = data.get("world_id") or f"world_{uuid.uuid4().hex[:8]}"
    if not data.get("name"):
        return _json({"status": "error", "error": "Missing world name"}, 400)
    if _find_one("worlds", {"world_id": world_id}):
        return _json({"status": "error", "error": f"World already exists: {world_id}"}, 409)
    doc = {
        "world_id": world_id,
        "name": data["name"],
        "summary": data.get("summary", ""),
        "forbidden_rules": data.get("forbidden_rules", []),
        "basic_settings": data.get("basic_settings", {}),
        "created_at": _now(),
        "updated_at": _now(),
    }
    _db()["worlds"].insert_one(doc)
    return _json({"status": "success", "world_id": world_id})


@app.post("/api/worlds/update")
def update_world():
    data = _body()
    world_id = _require(data.get("world_id") or data.get("target_id"), "Missing world_id")
    if not _find_one("worlds", {"world_id": world_id}):
        return _json({"status": "error", "error": f"World not found: {world_id}"}, 404)
    update = {key: data[key] for key in ("name", "summary", "forbidden_rules", "basic_settings") if key in data}
    update["updated_at"] = _now()
    _db()["worlds"].update_one({"world_id": world_id}, {"$set": update})
    return _json({"status": "success", "world_id": world_id})


@app.delete("/api/worlds/delete")
def delete_world():
    data = _body()
    world_id = _require(data.get("world_id"), "Missing world_id")
    db = _db()
    if not data.get("cascade", False):
        if db["worldviews"].count_documents({"world_id": world_id}) > 0 or db["novels"].count_documents({"world_id": world_id}) > 0:
            return _json({"status": "error", "error": "Conflict: World has children. Use cascade=True to delete."}, 409)
    db["worlds"].delete_many({"world_id": world_id})
    if data.get("cascade", True):
        db["worldviews"].delete_many({"world_id": world_id})
        db["novels"].delete_many({"world_id": world_id})
        db["outlines"].delete_many({"world_id": world_id})
        db["prose"].delete_many({"world_id": world_id})
        db["lore"].delete_many({"world_id": world_id})
    return _json({"status": "success", "world_id": world_id})


@app.get("/api/worlds/list")
def list_worlds():
    return _json(_list_collection("worlds", {}))


@app.get("/api/worlds/get")
def get_world():
    world_id = _require(request.args.get("world_id"), "Missing world_id")
    world = _find_one("worlds", {"world_id": world_id})
    if not world:
        return _json({"status": "error", "error": f"World not found: {world_id}"}, 404)
    return _json({"status": "success", "world": world})


@app.post("/api/worldviews/create")
def create_worldview():
    data = _body()
    world_id = _require(data.get("world_id"), "Missing world_id")
    if not _find_one("worlds", {"world_id": world_id}):
        return _json({"status": "error", "error": f"Parent World {world_id} not found"}, 404)
    worldview_id = data.get("worldview_id") or f"wv_{uuid.uuid4().hex[:8]}"
    doc = {
        "worldview_id": worldview_id,
        "world_id": world_id,
        "name": _require(data.get("name"), "Missing worldview name"),
        "summary": data.get("summary", ""),
        "forbidden_rules": data.get("forbidden_rules", []),
        "basic_settings": data.get("basic_settings", {}),
        "created_at": _now(),
        "updated_at": _now(),
    }
    _db()["worldviews"].update_one({"worldview_id": worldview_id}, {"$set": doc}, upsert=True)
    return _json({"status": "success", "worldview_id": worldview_id})


@app.post("/api/worldviews/update")
def update_worldview():
    data = _body()
    worldview_id = _require(data.get("worldview_id") or data.get("target_id"), "Missing worldview_id")
    update = {key: data[key] for key in ("name", "summary", "forbidden_rules", "basic_settings") if key in data}
    update["updated_at"] = _now()
    _db()["worldviews"].update_one({"worldview_id": worldview_id}, {"$set": update})
    return _json({"status": "success", "worldview_id": worldview_id})


@app.delete("/api/worldviews/delete")
def delete_worldview():
    data = _body()
    worldview_id = _require(data.get("worldview_id"), "Missing worldview_id")
    db = _db()
    db["worldviews"].delete_many({"worldview_id": worldview_id})
    if data.get("cascade", True):
        db["lore"].delete_many({"worldview_id": worldview_id})
    return _json({"status": "success", "worldview_id": worldview_id})


@app.get("/api/worldviews/list")
def list_worldviews():
    query = {key: request.args[key] for key in ("world_id", "worldview_id") if request.args.get(key)}
    if not query:
        return _json({"status": "error", "error": "Missing required query condition"}, 400)
    if not request.args.get("page"):
        return _json({"status": "error", "error": "Missing pagination"}, 400)
    return _json(_list_collection("worldviews", query))


@app.post("/api/novels/create")
def create_novel():
    data = _body()
    world_id = _require(data.get("world_id"), "Missing world_id")
    if not _find_one("worlds", {"world_id": world_id}):
        return _json({"status": "error", "error": f"Parent World {world_id} not found"}, 404)
    novel_id = data.get("novel_id") or f"novel_{uuid.uuid4().hex[:8]}"
    if _find_one("novels", {"novel_id": novel_id}):
        return _json({"status": "error", "error": f"Novel already exists: {novel_id}"}, 409)
    doc = {
        "novel_id": novel_id,
        "world_id": world_id,
        "name": _require(data.get("name"), "Missing novel name"),
        "introduction": data.get("introduction", ""),
        "summary": data.get("summary", ""),
        "forbidden_rules": data.get("forbidden_rules", []),
        "basic_settings": data.get("basic_settings", {}),
        "created_at": _now(),
        "updated_at": _now(),
    }
    _db()["novels"].insert_one(doc)
    return _json({"status": "success", "novel_id": novel_id})


@app.post("/api/novels/update")
def update_novel():
    data = _body()
    novel_id = _require(data.get("novel_id") or data.get("target_id"), "Missing novel_id")
    novel = _find_one("novels", {"novel_id": novel_id})
    if not novel:
        return _json({"status": "error", "error": f"Novel not found: {novel_id}"}, 404)
    if data.get("world_id") and not _find_one("worlds", {"world_id": data["world_id"]}):
        return _json({"status": "error", "error": f"Parent World {data['world_id']} not found"}, 404)
    update = {key: data[key] for key in ("name", "introduction", "summary", "world_id", "worldview_id", "forbidden_rules", "basic_settings") if key in data}
    update["updated_at"] = _now()
    _db()["novels"].update_one({"novel_id": novel_id}, {"$set": update})
    return _json({"status": "success", "novel_id": novel_id})


@app.delete("/api/novels/delete")
def delete_novel():
    data = _body()
    novel_id = _require(data.get("novel_id"), "Missing novel_id")
    db = _db()
    if not _find_one("novels", {"novel_id": novel_id}):
        return _json({"status": "error", "error": f"Novel not found: {novel_id}"}, 404)
    if not data.get("cascade", False):
        if db["outlines"].count_documents({"novel_id": novel_id}) > 0:
            return _json({"status": "error", "error": "Conflict: Novel has children. Use cascade=True to delete."}, 409)
    db["novels"].delete_many({"novel_id": novel_id})
    if data.get("cascade", True):
        db["outlines"].delete_many({"novel_id": novel_id})
        db["prose"].delete_many({"novel_id": novel_id})
    return _json({"status": "success", "novel_id": novel_id})


@app.get("/api/novels/list")
def list_novels():
    query = {key: request.args[key] for key in ("world_id", "novel_id") if request.args.get(key)}
    if request.args.get("query"):
        text = request.args["query"]
        query["$or"] = [
            {"novel_id": {"$regex": text, "$options": "i"}},
            {"name": {"$regex": text, "$options": "i"}},
            {"introduction": {"$regex": text, "$options": "i"}},
            {"summary": {"$regex": text, "$options": "i"}},
        ]
    if not query:
        return _json({"status": "error", "error": "Missing required query condition"}, 400)
    if not request.args.get("page"):
        return _json({"status": "error", "error": "Missing pagination"}, 400)
    return _json(_list_collection("novels", query))


@app.get("/api/novels/get")
def get_novel():
    novel_id = _require(request.args.get("novel_id"), "Missing novel_id")
    novel = _find_one("novels", {"novel_id": novel_id})
    if not novel:
        return _json({"status": "error", "error": f"Novel not found: {novel_id}"}, 404)
    return _json({"status": "success", "novel": novel})


@app.post("/api/outlines/create")
def create_outline():
    data = _body()
    payload = _resolve_novel_context(dict(data))
    novel_id = _require(payload.get("novel_id"), "Missing novel_id")
    if not _find_one("novels", {"novel_id": novel_id}):
        return _json({"status": "error", "error": f"Parent Novel {novel_id} not found"}, 404)
    outline_id = payload.get("outline_id") or payload.get("id") or f"outline_{uuid.uuid4().hex[:8]}"
    doc = {
        "outline_id": outline_id,
        "id": outline_id,
        "novel_id": novel_id,
        "world_id": payload.get("world_id"),
        "worldview_id": payload.get("worldview_id"),
        "name": _require(payload.get("name"), "Missing outline name"),
        "summary": payload.get("summary", ""),
        "created_at": _now(),
        "updated_at": _now(),
    }
    _db()["outlines"].update_one({"outline_id": outline_id}, {"$set": doc}, upsert=True)
    return _json({"status": "success", "outline_id": outline_id})


@app.post("/api/outlines/update")
def update_outline():
    data = _body()
    outline_id = _require(data.get("outline_id") or data.get("target_id"), "Missing outline_id")
    update = {key: data[key] for key in ("name", "summary", "worldview_id") if key in data}
    update["updated_at"] = _now()
    _db()["outlines"].update_one({"$or": [{"outline_id": outline_id}, {"id": outline_id}]}, {"$set": update})
    return _json({"status": "success", "outline_id": outline_id})


@app.get("/api/outlines/list")
def list_outlines():
    query = {key: request.args[key] for key in ("world_id", "worldview_id", "novel_id", "outline_id", "id") if request.args.get(key)}
    if request.args.get("query"):
        text = request.args["query"]
        query["$or"] = [
            {"outline_id": {"$regex": text, "$options": "i"}},
            {"id": {"$regex": text, "$options": "i"}},
            {"name": {"$regex": text, "$options": "i"}},
            {"title": {"$regex": text, "$options": "i"}},
            {"summary": {"$regex": text, "$options": "i"}},
        ]
    if not query:
        return _json({"status": "error", "error": "Missing required query condition"}, 400)
    if not request.args.get("page"):
        return _json({"status": "error", "error": "Missing pagination"}, 400)
    return _json(_list_collection("outlines", query))


@app.post("/api/archive/update")
def update_archive():
    data = _body()
    item_type = _require(data.get("type"), "Missing type")
    item_id = _require(data.get("id"), "Missing id")
    db = _db()
    
    update_fields = {"updated_at": _now()}
    if item_type == "prose":
        update_fields.update({
            "id": item_id, "scene_id": item_id, "type": "prose"
        })
        name = data.get("name") or data.get("title")
        if name: update_fields["name"] = update_fields["title"] = name
        for key in ("content", "outline_id", "novel_id", "worldview_id", "world_id"):
            if key in data: update_fields[key] = data[key]
        db["prose"].update_one({"id": item_id}, {"$set": update_fields}, upsert=True)
    elif item_type == "worldview":
        update_fields.update({"id": item_id, "type": "worldview"})
        if "name" in data: update_fields["name"] = data["name"]
        if "content" in data: update_fields["content"] = data["content"]
        for key in ("category", "world_id", "worldview_id"):
            if key in data: update_fields[key] = data[key]
        db["lore"].update_one({"id": item_id}, {"$set": update_fields}, upsert=True)
    elif item_type == "outline":
        update_fields.update({"outline_id": item_id, "id": item_id})
        if "name" in data: update_fields["name"] = data["name"]
        summary = data.get("content") or data.get("summary")
        if summary: update_fields["summary"] = summary
        if "worldview_id" in data: update_fields["worldview_id"] = data["worldview_id"]
        db["outlines"].update_one({"outline_id": item_id}, {"$set": update_fields}, upsert=True)
    else:
        raise ValueError(f"Invalid type: {item_type}")
    return _json({"status": "success", "id": item_id})


@app.delete("/api/archive/delete")
def delete_archive():
    data = _body()
    item_type = _require(data.get("type"), "Missing type")
    item_id = _require(data.get("id"), "Missing id")
    if item_type == "prose":
        _db()["prose"].delete_many({"$or": [{"id": item_id}, {"scene_id": item_id}, {"prose_id": item_id}]})
    elif item_type == "worldview":
        _db()["lore"].delete_many({"id": item_id})
    elif item_type == "outline":
        _db()["outlines"].delete_many({"$or": [{"outline_id": item_id}, {"id": item_id}]})
    else:
        raise ValueError(f"Invalid type: {item_type}")
    return _json({"status": "success", "id": item_id})


@app.get("/api/lore/list")
def list_lore():
    query: dict[str, Any] = {}
    for key in ("world_id", "worldview_id", "novel_id", "outline_id", "type"):
        if request.args.get(key):
            query[key] = request.args[key]
    if not query:
        return _json({"status": "error", "error": "Missing required query condition"}, 400)
    if not request.args.get("page"):
        return _json({"status": "error", "error": "Missing pagination"}, 400)
    if request.args.get("query"):
        text = request.args["query"]
        query["$or"] = [{"name": {"$regex": text, "$options": "i"}}, {"title": {"$regex": text, "$options": "i"}}, {"content": {"$regex": text, "$options": "i"}}]
    items = _list_collection("prose", query) + _list_collection("lore", query)
    return _json(items)


def _entry_tree_path(entry: dict[str, Any]) -> list[str]:
    raw_path = entry.get("path") or entry.get("category") or entry.get("type") or "未分类"
    parts = [part.strip() for part in str(raw_path).replace("/", ">").split(">") if part.strip()]
    return parts or ["未分类"]


def _insert_tree_entry(node: dict[str, Any], path: list[str], entry: dict[str, Any]) -> None:
    if not path:
        node["entries"].append(entry)
        return
    child_name = path[0]
    child = next((item for item in node["children"] if item["name"] == child_name), None)
    if child is None:
        child = {"name": child_name, "children": [], "entries": []}
        node["children"].append(child)
    _insert_tree_entry(child, path[1:], entry)


@app.get("/api/lore/tree")
def get_lore_tree():
    world_id = _require(request.args.get("world_id"), "world_id is required")
    if not request.args.get("page"):
        return _json({"status": "error", "error": "Missing pagination"}, 400)
    world = _find_one("worlds", {"world_id": world_id})
    if not world:
        return _json({"status": "error", "error": "World not found"}, 404)

    query = {"world_id": world_id}
    entries = _list_collection("lore", query) + _list_collection("prose", query)
    root = {"name": world.get("name") or world_id, "children": [], "entries": []}
    for entry in entries:
        _insert_tree_entry(root, _entry_tree_path(entry), entry)
    return _json(root)


@app.get("/api/world-hierarchy/tree")
def get_world_hierarchy_tree():
    world_id = _require(request.args.get("world_id"), "world_id is required")
    if not request.args.get("page"):
        return _json({"status": "error", "error": "Missing pagination"}, 400)
    db = _db()
    world = _find_one("worlds", {"world_id": world_id})
    if not world:
        return _json({"status": "error", "error": "World not found"}, 404)

    world["worldviews"] = _list_collection("worldviews", {"world_id": world_id})
    for wv in world["worldviews"]:
        wv["lore"] = _list_collection("lore", {"worldview_id": wv["worldview_id"]})

    world["novels"] = _list_collection("novels", {"world_id": world_id})
    for novel in world["novels"]:
        novel["outlines"] = _list_collection("outlines", {"novel_id": novel.get("novel_id")})
        for outline in novel["outlines"]:
            outline["chapters"] = _list_collection("prose", {"outline_id": outline.get("outline_id")})

    return _json({"status": "success", "worlds": [world]})


@app.get("/api/workflow/outline-chapter/state")
def get_outline_chapter_state():
    if not request.args.get("page") or not request.args.get("page_size"):
        return _json({"status": "error", "error": "Missing pagination"}, 400)

    query = {key: request.args[key] for key in ("world_id", "worldview_id", "novel_id", "outline_id") if request.args.get(key)}
    if not query:
        return _json({"status": "error", "error": "Missing required query condition"}, 400)

    world_id = query.get("world_id")
    worldview_id = query.get("worldview_id")
    novel_id = query.get("novel_id")
    outline_id = query.get("outline_id")

    if world_id and not _find_one("worlds", {"world_id": world_id}):
        return _json({"status": "error", "error": f"World not found: {world_id}"}, 404)
    if worldview_id:
        worldview_query = {"worldview_id": worldview_id}
        if world_id:
            worldview_query["world_id"] = world_id
        if not _find_one("worldviews", worldview_query):
            return _json({"status": "error", "error": f"Worldview not found: {worldview_id}"}, 404)
    if novel_id:
        novel_query = {"novel_id": novel_id}
        if world_id:
            novel_query["world_id"] = world_id
        if not _find_one("novels", novel_query):
            return _json({"status": "error", "error": f"Novel not found: {novel_id}"}, 404)
    if outline_id:
        outline_query: dict[str, Any] = {"$or": [{"outline_id": outline_id}, {"id": outline_id}]}
        outline = _find_one("outlines", outline_query)
        if not outline:
            return _json({"status": "error", "error": f"Outline not found: {outline_id}"}, 404)
        if world_id and outline.get("world_id") and outline.get("world_id") != world_id:
            return _json({"status": "error", "error": f"Outline {outline_id} does not belong to world {world_id}"}, 409)
        if worldview_id and outline.get("worldview_id") and outline.get("worldview_id") != worldview_id:
            return _json({"status": "error", "error": f"Outline {outline_id} does not belong to worldview {worldview_id}"}, 409)

    chapters = _list_collection("prose", query)
    for chapter in chapters:
        chapter.setdefault("type", "prose")
        if not chapter.get("id"):
            chapter["id"] = chapter.get("scene_id") or chapter.get("prose_id")
        if not chapter.get("name") and chapter.get("title"):
            chapter["name"] = chapter["title"]
        if not chapter.get("title") and chapter.get("name"):
            chapter["title"] = chapter["name"]

    return _json({
        "status": "success",
        "world_id": world_id,
        "worldview_id": worldview_id,
        "novel_id": novel_id,
        "outline_id": outline_id,
        "chapters": chapters,
    })


@app.get("/api/router/agents")
def list_router_agents():
    return _json({
        "status": "success",
        "agents": [
            {"agent_type": agent_type, **capability}
            for agent_type, capability in AGENT_CAPABILITIES.items()
        ],
        "actions": sorted(set(ACTION_ALIASES.values())),
        "dispatch_endpoint": "/api/router/dispatch",
    })


@app.post("/api/router/dispatch")
def dispatch_agent_request():
    data = _body()
    payload = data.get("payload") or {}
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    invocation = data.get("invocation") or {}
    if invocation and not isinstance(invocation, dict):
        raise ValueError("invocation must be an object")

    message = data.get("message") or data.get("task") or data.get("prompt") or ""
    agent_type, agent_reason = _infer_agent_type(data, payload, str(message))
    action, action_reason = _infer_action(data, payload, agent_type, str(message))
    payload = _normalize_dispatch_payload(agent_type, action, payload)
    _validate_dispatch(agent_type, action, payload)

    dispatch_id = data.get("dispatch_id") or f"dispatch_{uuid.uuid4().hex[:12]}"
    external_task_ref = (
        data.get("external_task_ref")
        or data.get("task_ref")
        or invocation.get("external_task_ref")
        or invocation.get("task_ref")
    )
    route = {
        "agent_type": agent_type,
        "agent_reason": agent_reason,
        "action": action,
        "action_reason": action_reason,
        "requires_human_approval": not bool(data.get("auto_approve", False)),
    }
    dispatch = {
        "dispatch_id": dispatch_id,
        "status": "planned" if data.get("dry_run") else "started",
        "message": message,
        "payload": payload,
        "route": route,
        "source": data.get("source", "external"),
        "external_request_id": data.get("external_request_id"),
        "external_task_ref": external_task_ref,
        "zentex_task_id": data.get("zentex_task_id") or invocation.get("zentex_task_id"),
        "callback_url": data.get("callback_url") or invocation.get("callback_url"),
    }

    if data.get("dry_run"):
        saved_dispatch = _save_dispatch(dispatch)
        return _json(_dispatch_response(saved_dispatch, route))

    run = _start_agent_run(
        agent_type,
        action,
        payload,
        str(message),
        metadata={
            "dispatch_id": dispatch_id,
            "source": dispatch["source"],
            "external_request_id": dispatch.get("external_request_id"),
            "external_task_ref": dispatch.get("external_task_ref"),
            "zentex_task_id": dispatch.get("zentex_task_id"),
        },
    )
    dispatch["run_id"] = run["run_id"]
    dispatch["status"] = "waiting_human" if run.get("status") == "waiting_human" else run.get("status", "started")

    if data.get("auto_approve") and run.get("status") == "waiting_human":
        run = _commit_run(run)
        dispatch["status"] = "completed"
        dispatch["auto_approved"] = True
    elif data.get("auto_approve"):
        dispatch["auto_approved"] = False
        dispatch["auto_approve_blocked_reason"] = f"Run status is {run.get('status')}; only waiting_human runs can be auto-approved."

    saved_dispatch = _save_dispatch(dispatch)
    return _json(_dispatch_response(saved_dispatch, route, run))


@app.get("/api/router/dispatch/get")
def get_dispatch_request():
    dispatch_id = request.args.get("dispatch_id")
    task_ref = request.args.get("external_task_ref") or request.args.get("task_ref")
    if dispatch_id:
        dispatch = _load_dispatch(dispatch_id)
    elif task_ref:
        dispatch = _load_dispatch_by_task_ref(task_ref)
    else:
        raise ValueError("Missing dispatch_id or task_ref")
    response: dict[str, Any] = {"status": "success", "dispatch": dispatch}
    if dispatch.get("external_task_ref"):
        response["task_ref"] = dispatch["external_task_ref"]
        response["external_task_ref"] = dispatch["external_task_ref"]
    if dispatch.get("run_id"):
        response["run"] = _load_run(dispatch["run_id"])
    return _json(response)


@app.get("/api/router/dispatch/list")
def list_dispatch_requests():
    query = {
        key: request.args[key]
        for key in ("dispatch_id", "status", "source", "external_request_id", "external_task_ref", "run_id")
        if request.args.get(key)
    }
    if request.args.get("agent_type"):
        query["route.agent_type"] = request.args["agent_type"]
    if request.args.get("action"):
        query["route.action"] = request.args["action"]
    if not query:
        return _json({"status": "error", "error": "Missing required query condition"}, 400)
    return _json({"status": "success", "dispatches": _list_collection("agent_dispatch_requests", query)})


@app.post("/api/hierarchy-agent/start")
def start_hierarchy_agent():
    data = _body()
    agent_type = _require(data.get("agent_type"), "Missing agent_type")
    action = data.get("action", "create")
    if agent_type not in AGENT_MODULES:
        raise ValueError(f"Unsupported agent_type: {agent_type}")
    run = _start_agent_run(agent_type, action, data.get("payload") or {}, data.get("message", ""))
    return _json({"status": "success", "run": run})


@app.post("/api/hierarchy-agent/respond")
def respond_hierarchy_agent():
    data = _body()
    run_id = _require(data.get("run_id"), "Missing run_id")
    decision = data.get("decision")
    run = _load_run(run_id)
    if decision == "approve":
        run = _commit_run(run)
    else:
        raise ValueError(f"Unsupported decision in minimal backend: {decision}")
    return _json({"status": "success", "run": run})


@app.get("/api/hierarchy-agent/list")
def list_hierarchy_agents():
    query = {key: request.args[key] for key in ("agent_type", "run_id", "world_id") if request.args.get(key)}
    if not query:
        return _json({"status": "error", "error": "Missing required query condition"}, 400)
    return _json({"status": "success", "runs": _list_collection("hierarchy_agent_runs", query)})


@app.get("/api/hierarchy-agent/get")
def get_hierarchy_agent():
    run_id = _require(request.args.get("run_id"), "Missing run_id")
    return _json({"status": "success", "run": _load_run(run_id)})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", os.environ.get("BACKEND_PORT", "5006")))
    app.run(host="127.0.0.1", port=port, debug=False)
