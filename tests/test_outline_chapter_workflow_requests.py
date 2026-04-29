import os
import sys
import uuid

import requests


BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:5006")
API_PREFIX = f"{BASE_URL}/api"
TIMEOUT = 10


def assert_json_response(response: requests.Response, expected_status: int = 200) -> dict | list:
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


def get_outlines(params: dict) -> list[dict]:
    next_params = {"page": 1, "page_size": 50, **params}
    data = assert_json_response(requests.get(f"{API_PREFIX}/outlines/list", params=next_params, timeout=TIMEOUT))
    assert isinstance(data, list), f"outlines/list must return a list, got {type(data)}"
    return data


def get_lore(params: dict) -> list[dict]:
    next_params = {"page": 1, "page_size": 50, **params}
    data = assert_json_response(requests.get(f"{API_PREFIX}/lore/list", params=next_params, timeout=TIMEOUT))
    assert isinstance(data, list), f"lore/list must return a list, got {type(data)}"
    return data


def find_outline(outline_id: str) -> dict | None:
    return next((item for item in get_outlines({"outline_id": outline_id}) if item.get("outline_id") == outline_id), None)


def find_lore_item(item_id: str, params: dict) -> dict | None:
    return next((item for item in get_lore(params) if item.get("id") == item_id), None)


def test_outline_and_chapter_workflow_lifecycle():
    suffix = uuid.uuid4().hex[:10]
    worldview_id = "default_wv"
    outline_name = f"Workflow Strict Outline {suffix}"
    outline_summary = f"初始大纲摘要 {suffix}"
    outline_id = None
    chapter_id = f"chapter_{suffix}"

    try:
        create_outline = assert_json_response(
            requests.post(
                f"{API_PREFIX}/outlines/create",
                json={"name": outline_name, "summary": outline_summary, "worldview_id": worldview_id},
                timeout=TIMEOUT,
            )
        )
        assert create_outline.get("status") == "success", create_outline
        outline_id = create_outline.get("outline_id")
        assert outline_id, f"create outline response missing outline_id: {create_outline}"

        created_outline = find_outline(outline_id)
        assert created_outline is not None, f"created outline {outline_id} not found by query"
        assert created_outline.get("title") == outline_name, created_outline
        assert created_outline.get("summary") == outline_summary, created_outline

        updated_outline_name = f"Workflow Strict Outline Updated {suffix}"
        updated_outline_content = f"严格修改后的大纲内容 {suffix}"
        update_outline = assert_json_response(
            requests.post(
                f"{API_PREFIX}/archive/update",
                json={
                    "id": outline_id,
                    "type": "outline",
                    "name": updated_outline_name,
                    "content": updated_outline_content,
                    "worldview_id": worldview_id,
                },
                timeout=TIMEOUT,
            )
        )
        assert update_outline.get("status") == "success", update_outline
        modified_outline = find_outline(outline_id)
        assert modified_outline is not None, f"updated outline {outline_id} not found by query"
        assert modified_outline.get("title") == updated_outline_name, modified_outline
        assert modified_outline.get("summary") == updated_outline_content, modified_outline

        chapter_title = f"Workflow Strict Chapter {suffix}"
        chapter_content = f"章节正文唯一内容 {suffix}"
        save_chapter = assert_json_response(
            requests.post(
                f"{API_PREFIX}/archive/update",
                json={
                    "id": chapter_id,
                    "type": "prose",
                    "name": chapter_title,
                    "content": chapter_content,
                    "outline_id": outline_id,
                    "worldview_id": worldview_id,
                },
                timeout=TIMEOUT,
            )
        )
        assert save_chapter.get("status") == "success", save_chapter
        created_chapter = find_lore_item(chapter_id, {"outline_id": outline_id, "worldview_id": worldview_id})
        assert created_chapter is not None, f"created chapter {chapter_id} not found by query"
        assert created_chapter.get("type") == "prose", created_chapter
        assert created_chapter.get("name") == chapter_title, created_chapter
        assert created_chapter.get("content") == chapter_content, created_chapter

        queried = get_lore({"outline_id": outline_id, "worldview_id": worldview_id, "query": suffix})
        assert any(item.get("id") == chapter_id for item in queried), (
            f"keyword query did not return created chapter {chapter_id}: {queried}"
        )

        state = assert_json_response(
            requests.get(
                f"{API_PREFIX}/workflow/outline-chapter/state",
                params={"outline_id": outline_id, "worldview_id": worldview_id, "page": 1, "page_size": 50},
                timeout=TIMEOUT,
            )
        )
        assert state.get("status") == "success", state
        assert any(item.get("id") == chapter_id for item in state.get("chapters", [])), state
        unfiltered_state = assert_json_response(
            requests.get(f"{API_PREFIX}/workflow/outline-chapter/state", timeout=TIMEOUT),
            expected_status=400,
        )
        assert "Missing required query condition" in unfiltered_state["error"], unfiltered_state
        unpaginated_state = assert_json_response(
            requests.get(
                f"{API_PREFIX}/workflow/outline-chapter/state",
                params={"outline_id": outline_id, "worldview_id": worldview_id},
                timeout=TIMEOUT,
            ),
            expected_status=400,
        )
        assert "Missing required pagination" in unpaginated_state["error"], unpaginated_state

        updated_chapter_title = f"Workflow Strict Chapter Updated {suffix}"
        updated_chapter_content = f"章节正文修改后唯一内容 {suffix}"
        update_chapter = assert_json_response(
            requests.post(
                f"{API_PREFIX}/archive/update",
                json={
                    "id": chapter_id,
                    "type": "prose",
                    "name": updated_chapter_title,
                    "content": updated_chapter_content,
                    "outline_id": outline_id,
                    "worldview_id": worldview_id,
                },
                timeout=TIMEOUT,
            )
        )
        assert update_chapter.get("status") == "success", update_chapter
        modified_chapter = find_lore_item(chapter_id, {"outline_id": outline_id, "worldview_id": worldview_id})
        assert modified_chapter is not None, f"updated chapter {chapter_id} not found by query"
        assert modified_chapter.get("name") == updated_chapter_title, modified_chapter
        assert modified_chapter.get("content") == updated_chapter_content, modified_chapter

        delete_chapter = assert_json_response(
            requests.delete(
                f"{API_PREFIX}/archive/delete",
                json={
                    "id": chapter_id,
                    "type": "prose",
                    "outline_id": outline_id,
                    "worldview_id": worldview_id,
                    "reason": f"strict test cleanup {suffix}",
                },
                timeout=TIMEOUT,
            )
        )
        assert delete_chapter.get("status") == "success", delete_chapter
        assert find_lore_item(chapter_id, {"outline_id": outline_id, "worldview_id": worldview_id}) is None

        delete_outline = assert_json_response(
            requests.delete(
                f"{API_PREFIX}/archive/delete",
                json={
                    "id": outline_id,
                    "type": "outline",
                    "worldview_id": worldview_id,
                    "reason": f"strict test cleanup {suffix}",
                },
                timeout=TIMEOUT,
            )
        )
        assert delete_outline.get("status") == "success", delete_outline
        assert find_outline(outline_id) is None, f"deleted outline {outline_id} still appears in query"
        outline_id = None

    finally:
        if chapter_id and outline_id:
            requests.delete(
                f"{API_PREFIX}/archive/delete",
                json={"id": chapter_id, "type": "prose", "outline_id": outline_id, "worldview_id": worldview_id},
                timeout=TIMEOUT,
            )
        if outline_id:
            requests.delete(
                f"{API_PREFIX}/archive/delete",
                json={"id": outline_id, "type": "outline", "worldview_id": worldview_id},
                timeout=TIMEOUT,
            )


if __name__ == "__main__":
    try:
        test_outline_and_chapter_workflow_lifecycle()
        print("outline/chapter workflow requests test passed")
    except Exception as exc:
        print(f"outline/chapter workflow requests test failed: {exc}")
        raise
