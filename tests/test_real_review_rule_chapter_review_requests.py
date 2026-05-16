import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from real_request_test_utils import assert_review_node, cleanup_world, create_chapter, make_full_chain, start_agent


def test_real_review_rule_chapter_review_requests():
    chain = make_full_chain("review_chapter")
    previous_chapter_id = f"chapter_prev_{chain['suffix']}"
    try:
        create_chapter(
            world_id=chain["world_id"],
            worldview_id=chain["worldview_id"],
            novel_id=chain["novel_id"],
            outline_id=chain["outline_id"],
            chapter_id=previous_chapter_id,
            name="前置章节",
            content="林澈在北港灯塔发现潮汐刻度异常，并决定封锁离港信号。",
        )
        run = start_agent(
            "chapter",
            "create",
            {"world_id": chain["world_id"], "worldview_id": chain["worldview_id"], "novel_id": chain["novel_id"], "outline_id": chain["outline_id"], "name": f"Chapter Review {chain['suffix']}", "content": "林澈继续检查登记簿，确认封锁离港信号的决定。"},
            "真实测试章节审查节点",
        )
        node = assert_review_node(run, "chapter_review", "chapter_consistency_review_agent")
        assert node["input"]["payload"].get("outline_id") == chain["outline_id"], node
    finally:
        cleanup_world(chain["world_id"])
