import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from real_request_test_utils import cleanup_world, create_world, get_world, unique_suffix


def test_real_world_policy_create_requests():
    suffix = unique_suffix("world_policy_create")
    world_id = f"world_{suffix}"
    forbidden_rules = ["禁止凭空出现现代枪械", "禁止无代价复活"]
    basic_settings = {"era": "蒸汽航海", "power_system": "潮汐水晶", "boundary": "群岛航线"}
    try:
        create_world(world_id=world_id, name=f"World {suffix}", summary="真实世界规则字段创建测试", forbidden_rules=forbidden_rules, basic_settings=basic_settings)
        queried = get_world(world_id)
        assert queried is not None, world_id
        assert queried.get("forbidden_rules") == forbidden_rules, queried
        assert queried.get("basic_settings") == basic_settings, queried
    finally:
        cleanup_world(world_id)
