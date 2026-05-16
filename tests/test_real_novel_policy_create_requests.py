import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from real_request_test_utils import cleanup_world, create_novel, create_world, get_novel, unique_suffix


def test_real_novel_policy_create_requests():
    suffix = unique_suffix("novel_policy_create")
    world_id = f"world_{suffix}"
    novel_id = f"novel_{suffix}"
    forbidden_rules = ["主角不能无证调用禁航舰队", "不能跳过灯塔登记制度"]
    basic_settings = {"protagonist_rule": "依靠航图破局", "tone": "克制悬疑", "timeline": "北港事件后一周"}
    try:
        create_world(world_id=world_id, name=f"World {suffix}", summary="小说规则字段父级世界")
        create_novel(world_id=world_id, novel_id=novel_id, name=f"Novel {suffix}", summary="小说规则字段创建", forbidden_rules=forbidden_rules, basic_settings=basic_settings)
        queried = get_novel(novel_id)
        assert queried is not None, novel_id
        assert queried.get("forbidden_rules") == forbidden_rules, queried
        assert queried.get("basic_settings") == basic_settings, queried
    finally:
        cleanup_world(world_id)
