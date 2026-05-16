import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from real_request_test_utils import assert_review_node, cleanup_world, make_full_chain, start_agent


def test_real_review_rule_outline_review_requests():
    chain = make_full_chain("review_outline")
    try:
        run = start_agent(
            "chapter",
            "create",
            {
                "world_id": chain["world_id"],
                "worldview_id": chain["worldview_id"],
                "novel_id": chain["novel_id"],
                "outline_id": chain["outline_id"],
                "name": f"Chapter Review {chain['suffix']}",
                "content": "北港灯塔的蒸汽钟鸣响后，航图师林澈按灯塔公会登记簿核对群岛航线，发现潮汐水晶刻度异常，正对应第一章大纲中的潮汐刻度异常事件。",
            },
            "真实测试大纲审核节点",
        )
        node = assert_review_node(run, "outline_review", "chapter_outline_review_agent")
        assert node["input"]["payload"].get("outline_id") == chain["outline_id"], node
    finally:
        cleanup_world(chain["world_id"])
