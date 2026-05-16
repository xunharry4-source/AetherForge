import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from real_request_test_utils import approve_agent, cleanup_world, create_world, get_worldview, start_agent, unique_suffix


def test_real_agent_worldview_flow_requests():
    suffix = unique_suffix("agent_worldview")
    world_id = f"world_{suffix}"
    try:
        create_world(world_id=world_id, name=f"World {suffix}", summary="世界观 Agent 父级世界")
        run = start_agent("worldview", "create", {"world_id": world_id, "name": f"Agent Worldview {suffix}", "summary": "灯塔公会登记潮汐水晶。"}, "真实测试世界观 Agent 流程")
        assert run["review_required"] is True, run
        assert any(node["node_id"] == "world_rule_review" for node in run["nodes"]), run
        assert any(node["node_id"] == "worldview_consistency_review" for node in run["nodes"]), run
        approved = approve_agent(run["run_id"])
        worldview_id = approved["commit_result"]["worldview_id"]
        queried = get_worldview(worldview_id)
        assert queried is not None, approved
        assert queried["world_id"] == world_id, queried
        assert queried["name"] == approved["pending_payload"]["name"], queried
        assert queried["summary"] == approved["pending_payload"]["summary"], queried
    finally:
        cleanup_world(world_id)
