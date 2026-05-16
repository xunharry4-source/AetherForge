import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from real_request_test_utils import approve_agent, cleanup_world, get_outline, make_full_chain, start_agent


def test_real_agent_outline_flow_requests():
    chain = make_full_chain("agent_outline")
    try:
        run = start_agent(
            "outline",
            "create",
            {"world_id": chain["world_id"], "worldview_id": chain["worldview_id"], "novel_id": chain["novel_id"], "name": f"Agent Outline {chain['suffix']}", "summary": "发现北港灯塔潮汐刻度异常。"},
            "真实测试大纲 Agent 流程",
        )
        assert run["review_required"] is True, run
        for node_id in ("world_review", "worldview_review", "novel_review"):
            assert any(node["node_id"] == node_id for node in run["nodes"]), run
        approved = approve_agent(run["run_id"])
        outline_id = approved["commit_result"]["outline_id"]
        queried = get_outline(outline_id)
        assert queried is not None, approved
        assert queried["novel_id"] == chain["novel_id"], queried
        assert queried["world_id"] == chain["world_id"], queried
        assert queried["summary"] == approved["pending_payload"]["summary"], queried
    finally:
        cleanup_world(chain["world_id"])
