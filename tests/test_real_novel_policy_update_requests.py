import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from real_request_test_utils import cleanup_world, create_novel, create_world, get_novel, request_json, unique_suffix


def test_real_novel_policy_update_requests():
    suffix = unique_suffix("novel_policy_update")
    world_id = f"world_{suffix}"
    novel_id = f"novel_{suffix}"
    updated_rules = ["主角不能绕过证据直接定罪", "反派不能凭空获得潮汐水晶"]
    updated_settings = {"protagonist_rule": "必须用登记簿和航图推理", "tone": "调查悬疑", "timeline": "三日内"}
    try:
        create_world(world_id=world_id, name=f"World {suffix}", summary="小说规则字段更新父级世界")
        create_novel(world_id=world_id, novel_id=novel_id, name=f"Novel {suffix}", summary="原始小说")
        response = request_json(
            "POST",
            "/api/novels/update",
            json={"novel_id": novel_id, "name": f"Novel Updated {suffix}", "summary": "已更新小说", "forbidden_rules": updated_rules, "basic_settings": updated_settings},
        )
        assert response.get("status") == "success", response
        queried = get_novel(novel_id)
        assert queried is not None, novel_id
        assert queried.get("name") == f"Novel Updated {suffix}", queried
        assert queried.get("forbidden_rules") == updated_rules, queried
        assert queried.get("basic_settings") == updated_settings, queried
    finally:
        cleanup_world(world_id)
