import os
import uuid

import requests


BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:5006")
API_PREFIX = f"{BASE_URL}/api"
TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "180"))


def assert_json_response(response: requests.Response, expected_status: int = 200):
    if response.status_code != expected_status:
        raise AssertionError(
            f"HTTP {response.status_code} != {expected_status}\n"
            f"URL: {response.request.method} {response.url}\n"
            f"Body: {response.text}"
        )
    try:
        return response.json()
    except Exception as exc:
        raise AssertionError(f"Response is not JSON: {response.text}") from exc


def find_by_id(url: str, id_key: str, value: str, params: dict | None = None):
    data = assert_json_response(requests.get(url, params=params or {}, timeout=TIMEOUT))
    assert isinstance(data, list), data
    return next((item for item in data if item.get(id_key) == value), None)


def start_agent(agent_type: str, action: str, payload: dict, message: str = ""):
    data = assert_json_response(
        requests.post(
            f"{API_PREFIX}/hierarchy-agent/start",
            json={"agent_type": agent_type, "action": action, "payload": payload, "message": message},
            timeout=TIMEOUT,
        )
    )
    assert data["status"] == "success", data
    run = data["run"]
    assert run["agent_type"] == agent_type, run
    assert run["action"] == action, run
    assert any(node["node_id"] == "input" and node["input"]["payload"] for node in run["nodes"]), run
    draft_node = next(node for node in run["nodes"] if node["node_id"] == "draft")
    assert draft_node["output"]["payload"], run
    assert draft_node["output"]["llm_invoked"] is True, draft_node
    assert draft_node["output"]["raw_response"], draft_node
    for key, value in draft_node["output"]["payload"].items():
        if key in {"name", "summary", "content", "world_id", "worldview_id", "novel_id", "outline_id", "target_id"}:
            assert run["pending_payload"].get(key) == value, {
                "field": key,
                "draft_payload": draft_node["output"]["payload"],
                "pending_payload": run["pending_payload"],
            }
    return run


def approve(run_id: str):
    data = assert_json_response(
        requests.post(
            f"{API_PREFIX}/hierarchy-agent/respond",
            json={"run_id": run_id, "decision": "approve", "message": "批准写入"},
            timeout=TIMEOUT,
        )
    )
    run = data["run"]
    assert run["status"] == "completed", run
    assert run["committed"] is True, run
    assert any(node["node_id"] == "apply" and node["output"].get("result") for node in run["nodes"]), run
    return run


def request_changes(run_id: str, payload: dict, message: str, revision_mode: str):
    data = assert_json_response(
        requests.post(
            f"{API_PREFIX}/hierarchy-agent/respond",
            json={
                "run_id": run_id,
                "decision": "request_changes",
                "message": message,
                "revision_mode": revision_mode,
                "manual_edit": True,
                "payload": payload,
            },
            timeout=TIMEOUT,
        )
    )
    run = data["run"]
    assert run["iterations"] >= 2, run
    assert run["committed"] is False, run
    revision_node = next(node for node in reversed(run["nodes"]) if node["node_id"] == "revision")
    assert revision_node["input"]["revision_mode"] == revision_mode, revision_node
    assert revision_node["input"]["revision_mode_label"] in {"指定局部重写", "完全重写", "指定内容重写"}, revision_node
    assert revision_node["input"]["manual_edit"] is True, revision_node
    assert "scope_guard" in revision_node["input"], revision_node
    if revision_mode == "partial_rewrite":
        assert "保持未点名内容" in revision_node["input"]["scope_guard"], revision_node
    return run


def test_hierarchy_agent_workflow_lifecycle():
    suffix = uuid.uuid4().hex[:10]
    world_id = None
    worldview_id = None
    novel_id = None
    outline_id = None
    chapter_id = None

    try:
        world_name = f"Agent World {suffix}"
        original_world_summary = "短草案：漂浮群岛。"
        world_run = start_agent("world", "create", {"name": world_name, "summary": original_world_summary}, "创建世界并完善草案")
        assert world_run["review_required"] is False, world_run
        assert all(node["node_id"] != "review" for node in world_run["nodes"]), world_run
        assert world_run["pending_payload"]["summary"] != original_world_summary, world_run
        world_run = approve(world_run["run_id"])
        world_id = world_run["commit_result"]["world_id"]
        queried_world = find_by_id(f"{API_PREFIX}/worlds/list", "world_id", world_id)
        assert queried_world["name"] == world_name, queried_world
        assert queried_world["summary"] == world_run["pending_payload"]["summary"], queried_world

        worldview_run = start_agent(
            "worldview",
            "create",
            {"name": f"Agent Worldview {suffix}", "summary": "rules", "world_id": world_id},
            "创建世界规则",
        )
        assert worldview_run["review_required"] is True, worldview_run
        review = next(node for node in worldview_run["nodes"] if node["node_id"] == "review")
        assert review["output"]["passed"] is True, review
        worldview_run = approve(worldview_run["run_id"])
        worldview_id = worldview_run["commit_result"]["worldview_id"]
        assert find_by_id(f"{API_PREFIX}/worldviews/list", "worldview_id", worldview_id, {"worldview_id": worldview_id, "page": 1, "page_size": 10})["world_id"] == world_id

        novel_run = start_agent(
            "novel",
            "create",
            {"name": f"Agent Novel {suffix}", "summary": "story", "world_id": world_id},
            "创建这个世界发生的故事",
        )
        bad_revision = assert_json_response(
            requests.post(
                f"{API_PREFIX}/hierarchy-agent/respond",
                json={
                    "run_id": novel_run["run_id"],
                    "decision": "request_changes",
                    "message": "缺少修改模式",
                    "payload": {"summary": "should not apply"},
                },
                timeout=TIMEOUT,
            ),
            expected_status=400,
        )
        assert "Invalid revision_mode" in bad_revision["error"], bad_revision

        novel_run = request_changes(novel_run["run_id"], {"summary": "story revised"}, "补充故事基调", "partial_rewrite")
        assert find_by_id(f"{API_PREFIX}/novels/list", "novel_id", novel_run["pending_payload"].get("novel_id", ""), {"world_id": world_id, "page": 1, "page_size": 10}) is None
        novel_run = approve(novel_run["run_id"])
        novel_id = novel_run["commit_result"]["novel_id"]
        queried_novel = find_by_id(f"{API_PREFIX}/novels/list", "novel_id", novel_id, {"novel_id": novel_id, "page": 1, "page_size": 10})
        assert queried_novel["world_id"] == world_id, queried_novel
        assert "worldview_id" not in queried_novel, queried_novel

        outline_run = start_agent(
            "outline",
            "create",
            {"name": f"Agent Outline {suffix}", "summary": "outline", "novel_id": novel_id, "worldview_id": worldview_id},
            "创建小说大纲",
        )
        outline_run = approve(outline_run["run_id"])
        outline_id = outline_run["commit_result"]["outline_id"]
        queried_outline = find_by_id(f"{API_PREFIX}/outlines/list", "outline_id", outline_id, {"outline_id": outline_id, "page": 1, "page_size": 10})
        assert queried_outline["novel_id"] == novel_id, queried_outline
        assert queried_outline["world_id"] == world_id, queried_outline

        chapter_run = start_agent(
            "chapter",
            "create",
            {"name": f"Agent Chapter {suffix}", "content": "chapter content", "outline_id": outline_id},
            "创建章节",
        )
        chapter_run = approve(chapter_run["run_id"])
        chapter_id = chapter_run["commit_result"]["id"]
        chapters = assert_json_response(
            requests.get(
                f"{API_PREFIX}/lore/list",
                params={"outline_id": outline_id, "worldview_id": worldview_id, "page": 1, "page_size": 20},
                timeout=TIMEOUT,
            )
        )
        queried_chapter = next((item for item in chapters if item.get("id") == chapter_id), None)
        assert queried_chapter is not None, chapters
        assert queried_chapter["content"] == "chapter content", queried_chapter

        update_run = start_agent(
            "chapter",
            "update",
            {"target_id": chapter_id, "name": f"Agent Chapter Updated {suffix}", "content": "chapter content updated"},
            "修改章节",
        )
        update_run = approve(update_run["run_id"])
        chapters = assert_json_response(
            requests.get(
                f"{API_PREFIX}/lore/list",
                params={"outline_id": outline_id, "worldview_id": worldview_id, "page": 1, "page_size": 20},
                timeout=TIMEOUT,
            )
        )
        queried_chapter = next((item for item in chapters if item.get("id") == chapter_id), None)
        assert queried_chapter["name"] == f"Agent Chapter Updated {suffix}", queried_chapter
        assert queried_chapter["content"] == "chapter content updated", queried_chapter

        unfiltered_runs = assert_json_response(
            requests.get(f"{API_PREFIX}/hierarchy-agent/list", timeout=TIMEOUT),
            expected_status=400,
        )
        assert "Missing required query condition" in unfiltered_runs["error"], unfiltered_runs
        listed_runs = assert_json_response(
            requests.get(
                f"{API_PREFIX}/hierarchy-agent/list",
                params={"agent_type": "chapter", "page": 1, "page_size": 10},
                timeout=TIMEOUT,
            )
        )
        assert listed_runs["status"] == "success", listed_runs
        assert any(item["run_id"] == update_run["run_id"] for item in listed_runs["runs"]), listed_runs

        tree = assert_json_response(requests.get(f"{API_PREFIX}/world-hierarchy/tree", params={"world_id": world_id, "page": 1, "page_size": 50}, timeout=TIMEOUT))
        world = next(item for item in tree["worlds"] if item["world_id"] == world_id)
        assert next(item for item in world["worldviews"] if item["worldview_id"] == worldview_id)
        novel = next(item for item in world["novels"] if item["novel_id"] == novel_id)
        outline = next(item for item in novel["outlines"] if item["outline_id"] == outline_id)
        assert next(item for item in outline["chapters"] if item["id"] == chapter_id)

        invalid = assert_json_response(
            requests.post(
                f"{API_PREFIX}/hierarchy-agent/start",
                json={"agent_type": "outline", "action": "create", "payload": {"name": "bad", "novel_id": "missing"}},
                timeout=TIMEOUT,
            )
        )
        assert invalid["run"]["status"] == "review_failed", invalid
        failed_review = next(node for node in invalid["run"]["nodes"] if node["node_id"] == "review")
        assert failed_review["status"] == "failed", failed_review
        assert "Parent novel not found" in failed_review["output"]["errors"][0], failed_review
    finally:
        if world_id:
            requests.delete(f"{API_PREFIX}/worlds/delete", json={"world_id": world_id, "cascade": True}, timeout=TIMEOUT)


if __name__ == "__main__":
    test_hierarchy_agent_workflow_lifecycle()
    print("hierarchy agent workflow requests tests passed")
