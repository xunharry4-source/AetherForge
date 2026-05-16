import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from real_request_test_utils import approve_agent, cleanup_world, create_chapter, get_chapter, make_full_chain, start_agent


def test_real_agent_chapter_flow_requests():
    chain = make_full_chain("agent_chapter")
    try:
        create_chapter(
            world_id=chain["world_id"],
            worldview_id=chain["worldview_id"],
            novel_id=chain["novel_id"],
            outline_id=chain["outline_id"],
            chapter_id=f"chapter_prev_{chain['suffix']}",
            name="前置章节",
            content="林澈在北港灯塔发现潮汐刻度异常，并决定封锁离港信号。",
        )
        run = start_agent(
            "chapter",
            "create",
            {
                "world_id": chain["world_id"],
                "worldview_id": chain["worldview_id"],
                "novel_id": chain["novel_id"],
                "outline_id": chain["outline_id"],
                "name": f"Agent Chapter {chain['suffix']}",
                "content": "北港灯塔的蒸汽钟再次鸣响后，林澈按灯塔公会登记簿复核潮汐水晶刻度，发现异常从外海群岛航线延伸到内港。他记录异常编号，维持禁航信号，并准备沿登记簿追查潮汐刻度异常的来源。",
            },
            "真实测试章节 Agent 流程",
        )
        assert run["review_required"] is True, run
        for node_id in ("world_review", "worldview_review", "novel_review", "outline_review", "chapter_review"):
            assert any(node["node_id"] == node_id for node in run["nodes"]), run
        approved = approve_agent(run["run_id"])
        chapter_id = approved["commit_result"]["id"]
        queried = get_chapter(chapter_id, outline_id=chain["outline_id"], worldview_id=chain["worldview_id"])
        assert queried is not None, approved
        assert queried["outline_id"] == chain["outline_id"], queried
        assert queried["novel_id"] == chain["novel_id"], queried
        assert queried["content"] == approved["pending_payload"]["content"], queried
    finally:
        cleanup_world(chain["world_id"])
