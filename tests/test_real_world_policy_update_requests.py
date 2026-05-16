import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from real_request_test_utils import cleanup_world, create_world, get_world, request_json, unique_suffix


def test_real_world_policy_update_requests():
    suffix = unique_suffix("world_policy_update")
    world_id = f"world_{suffix}"
    original_rules = ["禁止旧规则"]
    original_settings = {"era": "旧时代"}
    updated_rules = ["禁止破坏潮汐水晶守恒", "禁止无代价复活"]
    updated_settings = {"era": "蒸汽航海", "power_system": "潮汐水晶", "boundary": "北港群岛"}
    try:
        create_world(world_id=world_id, name=f"World {suffix}", summary="原始世界", forbidden_rules=original_rules, basic_settings=original_settings)
        response = request_json(
            "POST",
            "/api/worlds/update",
            json={"world_id": world_id, "name": f"World Updated {suffix}", "summary": "更新世界规则", "forbidden_rules": updated_rules, "basic_settings": updated_settings},
        )
        assert response.get("status") == "success", response
        queried = get_world(world_id)
        assert queried is not None, world_id
        assert queried.get("forbidden_rules") == updated_rules, queried
        assert queried.get("basic_settings") == updated_settings, queried
        assert queried.get("forbidden_rules") != original_rules, queried
        assert queried.get("basic_settings") != original_settings, queried
    finally:
        cleanup_world(world_id)
