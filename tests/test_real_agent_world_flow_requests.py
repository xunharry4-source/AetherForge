import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from real_request_test_utils import approve_agent, cleanup_world, get_world, start_agent, unique_suffix


def test_real_agent_world_flow_requests():
    suffix = unique_suffix("agent_world")
    world_id = f"world_{suffix}"
    try:
        run = start_agent("world", "create", {"world_id": world_id, "name": f"Agent World {suffix}", "summary": "短草案：潮汐群岛。"}, "真实测试世界 Agent 流程")
        assert run["review_required"] is False, run
        assert all(node["node_id"] != "review" for node in run["nodes"]), run
        approved = approve_agent(run["run_id"])
        queried = get_world(world_id)
        assert queried is not None, approved
        assert queried["world_id"] == world_id, queried
        assert queried["name"] == approved["pending_payload"]["name"], queried
        assert queried["summary"] == approved["pending_payload"]["summary"], queried
        assert "forbidden_rules" in queried, queried
        assert "basic_settings" in queried, queried
    finally:
        cleanup_world(world_id)
