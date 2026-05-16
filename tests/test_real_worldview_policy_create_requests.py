import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from real_request_test_utils import cleanup_world, create_world, get_worldview, request_json, unique_suffix


def test_real_worldview_policy_create_requests():
    suffix = unique_suffix("worldview_policy_create")
    world_id = f"world_{suffix}"
    worldview_id = f"wv_{suffix}"
    forbidden_rules = ["禁止世界观条目改写世界根规则"]
    basic_settings = {"canon_scope": "灯塔公会", "resource_rule": "潮汐水晶登记制"}
    try:
        create_world(world_id=world_id, name=f"World {suffix}", summary="世界观规则字段父级世界")
        response = request_json(
            "POST",
            "/api/worldviews/create",
            json={"world_id": world_id, "worldview_id": worldview_id, "name": f"Worldview {suffix}", "summary": "世界观规则字段创建", "forbidden_rules": forbidden_rules, "basic_settings": basic_settings},
        )
        assert response.get("status") == "success", response
        queried = get_worldview(response.get("worldview_id", worldview_id))
        assert queried is not None, response
        assert queried.get("world_id") == world_id, queried
        assert queried.get("forbidden_rules") == forbidden_rules, queried
        assert queried.get("basic_settings") == basic_settings, queried
    finally:
        cleanup_world(world_id)
