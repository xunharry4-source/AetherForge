#!/usr/bin/env python3
"""Real requests test for router dispatch planning.

This test exercises the external scheduling interface without mocks. It uses
dry_run dispatches so the router can be validated without invoking LLM agents.
"""

from __future__ import annotations

from real_request_test_utils import assert_success, request_json, unique_suffix


def main() -> None:
    suffix = unique_suffix("router")

    agents_payload = assert_success(request_json("GET", "/api/router/agents"))
    agent_types = {item["agent_type"] for item in agents_payload["agents"]}
    assert {"world", "worldview", "novel", "outline", "chapter"}.issubset(agent_types), agents_payload

    chapter_dispatch = assert_success(
        request_json(
            "POST",
            "/api/router/dispatch",
            json={
                "dry_run": True,
                "source": "router-test",
                "external_request_id": suffix,
                "message": "新增章节正文",
                "payload": {
                    "outline_id": f"outline_{suffix}",
                    "name": "调度测试章节",
                    "content": "调度测试章节正文。",
                },
            },
        )
    )
    assert chapter_dispatch["route"]["agent_type"] == "chapter", chapter_dispatch
    assert chapter_dispatch["route"]["agent_reason"] == "payload_context", chapter_dispatch
    assert chapter_dispatch["route"]["action"] == "create", chapter_dispatch
    assert chapter_dispatch["dispatch"]["status"] == "planned", chapter_dispatch
    dispatch_id = chapter_dispatch["dispatch"]["dispatch_id"]

    fetched = assert_success(request_json("GET", "/api/router/dispatch/get", params={"dispatch_id": dispatch_id}))
    assert fetched["dispatch"]["dispatch_id"] == dispatch_id, fetched
    assert fetched["dispatch"]["route"]["agent_type"] == "chapter", fetched

    explicit_update = assert_success(
        request_json(
            "POST",
            "/api/router/dispatch",
            json={
                "dry_run": True,
                "agent_type": "小说",
                "action": "修改",
                "message": "修改小说简介",
                "payload": {
                    "novel_id": f"novel_{suffix}",
                    "name": "调度测试小说",
                    "summary": "调度测试小说简介。",
                },
            },
        )
    )
    assert explicit_update["route"]["agent_type"] == "novel", explicit_update
    assert explicit_update["route"]["agent_reason"] == "explicit", explicit_update
    assert explicit_update["route"]["action"] == "update", explicit_update
    assert explicit_update["dispatch"]["payload"]["target_id"] == f"novel_{suffix}", explicit_update

    listed = assert_success(
        request_json(
            "GET",
            "/api/router/dispatch/list",
            params={"source": "router-test", "page": 1, "page_size": 20},
        )
    )
    assert any(item["dispatch_id"] == dispatch_id for item in listed["dispatches"]), listed


if __name__ == "__main__":
    main()

