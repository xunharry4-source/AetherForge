#!/usr/bin/env python3
"""Generate backend API documentation from Flask route decorators.

The generator parses src/app_api.py with Python's AST instead of importing the
Flask app, so it does not start the server, connect to MongoDB, or run agent
initialization code.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = REPO_ROOT / "src" / "app_api.py"
DEFAULT_OPENAPI = REPO_ROOT / "docs" / "openapi.json"
DEFAULT_MARKDOWN = REPO_ROOT / "docs" / "api.md"

AUTH_REQUIRED_ENDPOINTS = {"get_current_user", "logout_user"}

AUTH_ROUTE_NOTES = {
    "register_user": [
        "Creates a user, stores a hashed password, generates a user API Key, creates a login session, and returns `token`, `api_key`, and `user`.",
        "API Key generation: `na_` prefix plus `secrets.token_urlsafe(32)`, stored on the user document as `users.api_key`.",
        "Required JSON fields: `username`, `password`. Optional JSON fields: `display_name`, `email`.",
    ],
    "login_user": [
        "Authenticates with `username` and `password`, then returns `token`, `api_key`, and `user`.",
        "If an existing user has no `api_key`, login generates one with the same `na_` + `secrets.token_urlsafe(32)` format and persists it.",
        "Required JSON fields: `username`, `password`.",
    ],
    "get_current_user": [
        "Requires either a login token or a user API Key.",
        "Accepted headers: `Authorization: Bearer <token>`, `X-API-Key: <api_key>`, or `Authorization: ApiKey <api_key>`.",
    ],
    "logout_user": [
        "Invalidates the login token passed as `Authorization: Bearer <token>`.",
        "API Key access does not depend on login sessions and remains valid after logout.",
    ],
}


@dataclass(frozen=True)
class RouteDoc:
    path: str
    openapi_path: str
    methods: list[str]
    endpoint: str
    summary: str
    path_params: list[str]
    uses_files: bool
    uses_json: bool
    uses_args: bool


def _literal_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _literal_string_list(node: ast.AST) -> list[str]:
    if not isinstance(node, (ast.List, ast.Tuple)):
        return []
    values: list[str] = []
    for item in node.elts:
        value = _literal_string(item)
        if value:
            values.append(value.upper())
    return values


def _route_path_to_openapi(path: str) -> tuple[str, list[str]]:
    params: list[str] = []

    def replace(match: re.Match[str]) -> str:
        raw = match.group(1)
        name = raw.split(":", 1)[-1]
        params.append(name)
        return "{" + name + "}"

    return re.sub(r"<([^>]+)>", replace, path), params


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Attribute):
        base = _call_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _uses_request_attr(function: ast.FunctionDef, attr_name: str) -> bool:
    for node in ast.walk(function):
        if isinstance(node, ast.Attribute) and node.attr == attr_name:
            if _call_name(node.value) == "request":
                return True
    return False


def _uses_request_get_json(function: ast.FunctionDef) -> bool:
    for node in ast.walk(function):
        if isinstance(node, ast.Call) and _call_name(node.func) == "request.get_json":
            return True
    return False


def _extract_route(function: ast.FunctionDef) -> RouteDoc | None:
    for decorator in function.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        decorator_name = _call_name(decorator.func)
        if decorator_name not in {"app.route", "app.get", "app.post", "app.put", "app.patch", "app.delete"}:
            continue
        if not decorator.args:
            continue
        path = _literal_string(decorator.args[0])
        if not path:
            continue
        methods = [decorator_name.rsplit(".", 1)[1].upper()]
        if decorator_name == "app.route":
            methods = ["GET"]
            for keyword in decorator.keywords:
                if keyword.arg == "methods":
                    methods = _literal_string_list(keyword.value) or methods
        openapi_path, path_params = _route_path_to_openapi(path)
        summary = ast.get_docstring(function) or function.name.replace("_", " ")
        return RouteDoc(
            path=path,
            openapi_path=openapi_path,
            methods=sorted(set(methods)),
            endpoint=function.name,
            summary=summary.strip().splitlines()[0],
            path_params=path_params,
            uses_files=_uses_request_attr(function, "files"),
            uses_json=_uses_request_get_json(function),
            uses_args=_uses_request_attr(function, "args"),
        )
    return None


def collect_routes(source_path: Path = DEFAULT_SOURCE) -> list[RouteDoc]:
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    routes: list[RouteDoc] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            route = _extract_route(node)
            if route:
                routes.append(route)
    routes.sort(key=lambda item: (item.openapi_path, item.methods, item.endpoint))
    return routes


def _tag_for_path(path: str) -> str:
    if path == "/":
        return "frontend"
    parts = [part for part in path.split("/") if part]
    if not parts:
        return "frontend"
    if parts[0] != "api":
        return "static"
    return parts[1] if len(parts) > 1 else "api"


def _path_parameters(route: RouteDoc) -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "in": "path",
            "required": True,
            "schema": {"type": "string"},
        }
        for name in route.path_params
    ]


def _request_body(route: RouteDoc, method: str) -> dict[str, Any] | None:
    if method == "GET":
        return None
    if route.uses_files:
        return {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "additionalProperties": True,
                        "description": "Inferred from request.files; see endpoint tests and product docs for required fields.",
                    }
                }
            },
        }
    return {
        "required": False,
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "additionalProperties": True,
                    "description": "Route accepts JSON or query parameters depending on endpoint implementation.",
                }
            }
        },
    }


def build_openapi(routes: list[RouteDoc]) -> dict[str, Any]:
    paths: dict[str, Any] = {}
    for route in routes:
        path_item = paths.setdefault(route.openapi_path, {})
        for method in route.methods:
            operation: dict[str, Any] = {
                "operationId": route.endpoint,
                "summary": route.summary,
                "tags": [_tag_for_path(route.path)],
                "parameters": _path_parameters(route),
                "responses": {
                    "200": {
                        "description": "Successful response. Response shape is generated by the live Flask endpoint.",
                        "content": {"application/json": {"schema": {"type": "object", "additionalProperties": True}}},
                    },
                    "400": {"description": "Bad request or missing required business parameters."},
                    "404": {"description": "Resource not found."},
                    "409": {"description": "Conflict, usually non-empty parent without cascade confirmation."},
                    "500": {"description": "Server error. Errors must not be swallowed or converted to fake success."},
                },
                "x-source": {"file": "src/app_api.py", "endpoint": route.endpoint, "route": route.path},
            }
            if route.endpoint in AUTH_REQUIRED_ENDPOINTS:
                operation["security"] = [
                    {"bearerAuth": []},
                    {"apiKeyAuth": []},
                    {"authorizationApiKey": []},
                ]
                operation["responses"]["401"] = {"description": "Missing or invalid login token / API Key."}
            if route.endpoint in AUTH_ROUTE_NOTES:
                operation["description"] = "\n".join(AUTH_ROUTE_NOTES[route.endpoint])
            request_body = _request_body(route, method)
            if request_body:
                operation["requestBody"] = request_body
            if route.uses_args and method == "GET":
                operation["parameters"].append(
                    {
                        "name": "query parameters",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "object", "additionalProperties": True},
                        "description": "Endpoint reads request.args; see tests and product docs for required query fields.",
                    }
                )
            path_item[method.lower()] = operation
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Novel Agent Backend API",
            "version": "1.0.0",
            "description": "Generated from Flask @app.route decorators in src/app_api.py.",
        },
        "servers": [{"url": "http://127.0.0.1:5006"}],
        "components": {
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "description": "Login session token returned by `/api/auth/login` or `/api/auth/register`.",
                },
                "apiKeyAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-API-Key",
                    "description": "User API Key returned by `/api/auth/login` or `/api/auth/register`.",
                },
                "authorizationApiKey": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "Authorization",
                    "description": "Alternative API Key format: `Authorization: ApiKey <api_key>`.",
                },
            }
        },
        "paths": paths,
    }


def build_markdown(routes: list[RouteDoc]) -> str:
    lines = [
        "# Backend API Documentation",
        "",
        "Generated by: `scripts/generate_api_docs.py`",
        "",
        "Source: `src/app_api.py` Flask `@app.route` decorators.",
        "",
        "This file is generated. Update route code first, then run:",
        "",
        "```bash",
        ".venv/bin/python scripts/generate_api_docs.py",
        "```",
        "",
        "The generator does not import the Flask app, does not connect to MongoDB, and does not execute API handlers.",
        "",
        "Business validation details are enforced by the real requests tests and product requirements document.",
        "",
        "## Summary",
        "",
        f"- Routes: `{len(routes)}`",
        f"- OpenAPI JSON: `docs/openapi.json`",
        "",
        "## Authentication",
        "",
        "Register and login return both a login token and a user API Key:",
        "",
        "- Login token: generated with `secrets.token_urlsafe(32)` and stored in `auth_sessions.token`.",
        "- User API Key: generated with `na_` prefix plus `secrets.token_urlsafe(32)` and stored in `users.api_key`.",
        "- New users receive an API Key during `POST /api/auth/register`.",
        "- Existing users without an API Key receive one during their next successful `POST /api/auth/login`.",
        "- API Keys are returned as both top-level `api_key` and `user.api_key` in register/login responses.",
        "",
        "```http",
        "Authorization: Bearer <token>",
        "```",
        "",
        "External callers can skip login and access protected user endpoints with the user's API Key:",
        "",
        "```http",
        "X-API-Key: <api_key>",
        "```",
        "",
        "Alternative API Key header:",
        "",
        "```http",
        "Authorization: ApiKey <api_key>",
        "```",
        "",
        "Protected endpoints currently include `GET /api/auth/me`. `POST /api/auth/logout` only invalidates login tokens; API Keys remain valid after logout.",
        "",
    ]
    current_tag = None
    for route in routes:
        tag = _tag_for_path(route.path)
        if tag != current_tag:
            lines.extend([f"## {tag}", ""])
            current_tag = tag
        method_text = ", ".join(route.methods)
        lines.extend(
            [
                f"### `{method_text} {route.path}`",
                "",
                f"- Endpoint: `{route.endpoint}`",
                f"- Summary: {route.summary}",
                f"- OpenAPI path: `{route.openapi_path}`",
            ]
        )
        if route.path_params:
            lines.append(f"- Path params: `{', '.join(route.path_params)}`")
        if route.uses_args:
            lines.append("- Reads query parameters: yes")
        if route.uses_json:
            lines.append("- Reads JSON body: yes")
        if route.uses_files:
            lines.append("- Reads multipart files: yes")
        for note in AUTH_ROUTE_NOTES.get(route.endpoint, []):
            lines.append(f"- Auth note: {note}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    routes = collect_routes()
    DEFAULT_OPENAPI.write_text(
        json.dumps(build_openapi(routes), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    DEFAULT_MARKDOWN.write_text(build_markdown(routes), encoding="utf-8")
    print(f"Generated {DEFAULT_MARKDOWN.relative_to(REPO_ROOT)}")
    print(f"Generated {DEFAULT_OPENAPI.relative_to(REPO_ROOT)}")
    print(f"Routes: {len(routes)}")


if __name__ == "__main__":
    main()
