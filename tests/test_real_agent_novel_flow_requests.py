import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from real_request_test_utils import approve_agent, cleanup_world, create_world, get_novel, start_agent, unique_suffix


def test_real_agent_novel_flow_requests():
    suffix = unique_suffix("agent_novel")
    world_id = f"world_{suffix}"
    try:
        create_world(world_id=world_id, name=f"World {suffix}", summary="小说 Agent 父级世界")
        run = start_agent("novel", "create", {"world_id": world_id, "name": f"Agent Novel {suffix}", "summary": "航图师追查灯塔异常。"}, "真实测试小说 Agent 流程")
        assert run["review_required"] is True, run
        assert any(node["node_id"] == "review" for node in run["nodes"]), run
        approved = approve_agent(run["run_id"])
        novel_id = approved["commit_result"]["novel_id"]
        queried = get_novel(novel_id)
        assert queried is not None, approved
        assert queried["world_id"] == world_id, queried
        assert queried["name"] == approved["pending_payload"]["name"], queried
        assert queried["summary"] == approved["pending_payload"]["summary"], queried
        assert "forbidden_rules" in queried, queried
        assert "basic_settings" in queried, queried
    finally:
        cleanup_world(world_id)
