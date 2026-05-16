import json
import os
import sys
import inspect
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents import chapter_agent, novel_agent, outline_agent, worldview_agent, world_agent


class FakeLLM:
    def __init__(self, agent_name, calls):
        self.agent_name = agent_name
        self.calls = calls

    def invoke(self, prompt, config=None):
        self.calls.append({"agent_name": self.agent_name, "prompt": prompt, "config": config})
        payloads = {
            "world_agent": {
                "world_id": "world_test",
                "name": "测试世界",
                "summary": "world_agent LLM 已扩充：底层规则、资源机制、组织结构、核心冲突、地理边界、风险约束都已形成可执行设定。",
            },
            "worldview_agent": {
                "world_id": "world_test",
                "worldview_id": "wv_test",
                "name": "测试世界观",
                "summary": "worldview_agent LLM 已扩充：设定边界、核心规则、冲突风险、引用约束都已形成可检索 Canon。",
            },
            "novel_agent": {
                "world_id": "world_test",
                "novel_id": "novel_test",
                "name": "测试小说",
                "summary": "novel_agent LLM 已扩充：故事定位、主角视角、核心冲突、世界规则契合方式、后续大纲约束都已明确。",
            },
            "outline_agent": {
                "world_id": "world_test",
                "worldview_id": "wv_test",
                "novel_id": "novel_test",
                "outline_id": "outline_test",
                "name": "测试大纲",
                "summary": "outline_agent LLM 已扩充：卷章结构、关键转折、冲突升级、高潮收束、设定一致性约束都已明确。",
            },
            "chapter_agent": {
                "world_id": "world_test",
                "worldview_id": "wv_test",
                "novel_id": "novel_test",
                "outline_id": "outline_test",
                "chapter_id": "chapter_test",
                "id": "chapter_test",
                "name": "测试章节",
                "content": "chapter_agent LLM 已生成：正文场景、人物行动、冲突推进、设定执行和段落节奏都已写成可入库正文。",
            },
        }
        body = {
            "payload": payloads[self.agent_name],
            "modification_notes": f"{self.agent_name} modification notes",
            "change_summary": f"{self.agent_name} change summary",
        }
        return SimpleNamespace(content=json.dumps(body, ensure_ascii=False))


def test_all_hierarchy_modules_content_modification_calls_dedicated_llm():
    calls = []

    def fake_get_llm(json_mode=False, agent_name="unknown"):
        assert json_mode is True
        return FakeLLM(agent_name, calls)

    cases = [
        (world_agent, "world_agent", "summary", {"world_id": "world_test", "name": "测试世界", "summary": "短"}),
        (worldview_agent, "worldview_agent", "summary", {"world_id": "world_test", "worldview_id": "wv_test", "name": "测试世界观", "summary": "短"}),
        (novel_agent, "novel_agent", "summary", {"world_id": "world_test", "novel_id": "novel_test", "name": "测试小说", "summary": "短"}),
        (outline_agent, "outline_agent", "summary", {"world_id": "world_test", "worldview_id": "wv_test", "novel_id": "novel_test", "outline_id": "outline_test", "name": "测试大纲", "summary": "短"}),
        (chapter_agent, "chapter_agent", "content", {"world_id": "world_test", "worldview_id": "wv_test", "novel_id": "novel_test", "outline_id": "outline_test", "chapter_id": "chapter_test", "id": "chapter_test", "name": "测试章节", "content": "短"}),
    ]

    for module, expected_agent_name, primary_field, payload in cases:
        with (
            patch.object(module, "get_llm", fake_get_llm),
            patch.object(module, "get_langfuse_callback", lambda: None),
            patch.object(module, "get_unified_context", lambda *args, **kwargs: "测试检索上下文"),
        ):
            calls.clear()
            result = module.generate_content_modification(
                "create",
                payload,
                "用户不同意，请修改内容",
            )
            assert calls, expected_agent_name
            assert calls[0]["agent_name"] == expected_agent_name
            assert result["llm_invoked"] is True
            assert result["agent_name"] == expected_agent_name
            assert result["llm_agent_name"] == expected_agent_name
            assert result["llm_call"]["llm_agent_name"] == expected_agent_name
            assert result["llm_call"]["raw_response_chars"] > 0
            assert expected_agent_name in result["payload"][primary_field]
            assert result["raw_response"]
            assert result["parsed_response"]["payload"]


def test_all_hierarchy_modules_initial_expansion_calls_dedicated_llm():
    calls = []

    def fake_get_llm(json_mode=False, agent_name="unknown"):
        assert json_mode is True
        return FakeLLM(agent_name, calls)

    cases = [
        (world_agent, "world_agent", {"world_id": "world_test", "name": "测试世界", "summary": "短"}),
        (worldview_agent, "worldview_agent", {"world_id": "world_test", "worldview_id": "wv_test", "name": "测试世界观", "summary": "短"}),
        (novel_agent, "novel_agent", {"world_id": "world_test", "novel_id": "novel_test", "name": "测试小说", "summary": "短"}),
        (outline_agent, "outline_agent", {"world_id": "world_test", "worldview_id": "wv_test", "novel_id": "novel_test", "outline_id": "outline_test", "name": "测试大纲", "summary": "短"}),
        (chapter_agent, "chapter_agent", {"world_id": "world_test", "worldview_id": "wv_test", "novel_id": "novel_test", "outline_id": "outline_test", "chapter_id": "chapter_test", "id": "chapter_test", "name": "测试章节", "content": "短"}),
    ]

    for module, expected_agent_name, payload in cases:
        with (
            patch.object(module, "get_llm", fake_get_llm),
            patch.object(module, "get_langfuse_callback", lambda: None),
        ):
            calls.clear()
            result = module.generate_initial_expansion(
                "create",
                payload,
                "请先做初始扩充",
            )
            assert calls, expected_agent_name
            assert calls[0]["agent_name"] == expected_agent_name
            assert result["llm_invoked"] is True
            assert result["agent_name"] == expected_agent_name
            assert result["llm_agent_name"] == expected_agent_name
            assert result["llm_call"]["llm_agent_name"] == expected_agent_name
            assert result["llm_call"]["raw_response_chars"] > 0
            assert isinstance(result["expanded_input"], dict)
            assert isinstance(result["payload"], dict)
            assert result["raw_response"]


def test_five_agents_are_independent_state_graph_instances():
    cases = [
        (world_agent, "world_agent", []),
        (worldview_agent, "worldview_agent", ["world_rule_review", "worldview_consistency_review"]),
        (novel_agent, "novel_agent", ["review"]),
        (outline_agent, "outline_agent", ["world_review", "worldview_review", "novel_review"]),
        (chapter_agent, "chapter_agent", ["world_review", "worldview_review", "novel_review", "outline_review", "chapter_review"]),
    ]

    apps = []
    for module, expected_agent_name, review_nodes in cases:
        assert module.AGENT_NAME == expected_agent_name
        assert module.WORKFLOW_DESCRIPTION
        assert module.WORKFLOW_STEPS
        assert module.NODE_ANNOTATIONS
        assert hasattr(module, "app")
        assert hasattr(module, "workflow")
        apps.append(module.app)
        graph = module.app.get_graph()
        node_names = set(graph.nodes.keys())
        assert {"input", "initial_expansion", "human", "modify_content", "commit"}.issubset(node_names)
        assert "draft" not in node_names
        assert module.WORKFLOW_STEPS["initial_expansion"]["step_index"] == 2
        assert module.NODE_ANNOTATIONS["initial_expansion"]["input_annotation"]
        assert module.NODE_ANNOTATIONS["initial_expansion"]["output_annotation"]
        assert module.NODE_ANNOTATIONS["initial_expansion"]["next_step_annotation"]
        for review_node in review_nodes:
            assert review_node in node_names
        if module in {worldview_agent, outline_agent, chapter_agent}:
            assert "review" not in node_names
        elif not review_nodes:
            assert "review" not in node_names
        for node_id, step in module.WORKFLOW_STEPS.items():
            assert step["step_index"]
            assert step["step_title"].startswith("步骤")
            assert step["function"]
            assert step["description"]
            rendered = module._node(node_id, "completed", {}, {})
            assert rendered["step_index"] == step["step_index"]
            assert rendered["step_title"] == step["step_title"]
            assert rendered["function"] == step["function"]
            assert rendered["description"] == step["description"]
            assert rendered["node_annotation"].startswith(rendered["step_title"])
            assert rendered["input_annotation"]
            assert rendered["output_annotation"]
            assert rendered["next_step_annotation"]

    assert len({id(app) for app in apps}) == 5


def test_agent_methods_have_chinese_annotations():
    cases = [world_agent, worldview_agent, novel_agent, outline_agent, chapter_agent]
    required_methods = [
        "_extract_llm_content",
        "_llm_metadata",
        "_invoke_llm",
        "_node",
        "build_initial_expansion_prompt",
        "generate_initial_expansion",
        "input_node",
        "initial_expansion_node",
        "human_node",
        "route_after_human",
        "commit_node",
    ]
    modify_methods = ["build_modification_prompt", "generate_content_modification", "modify_content_node"]
    review_methods = ["review_node", "route_after_review"]
    worldview_review_methods = [
        "world_rule_review_node",
        "route_after_world_rule_review",
        "worldview_consistency_review_node",
        "route_after_worldview_consistency_review",
    ]
    outline_review_methods = [
        "world_review_node",
        "route_after_world_review",
        "worldview_review_node",
        "route_after_worldview_review",
        "novel_review_node",
        "route_after_novel_review",
    ]
    chapter_review_methods = [
        "world_review_node",
        "route_after_world_review",
        "worldview_review_node",
        "route_after_worldview_review",
        "novel_review_node",
        "route_after_novel_review",
        "outline_review_node",
        "route_after_outline_review",
        "chapter_review_node",
        "route_after_chapter_review",
    ]

    for module in cases:
        names = list(required_methods)
        names.extend(modify_methods)
        if module is worldview_agent:
            names.extend(worldview_review_methods)
        elif module is outline_agent:
            names.extend(outline_review_methods)
        elif module is chapter_agent:
            names.extend(chapter_review_methods)
        elif module is not world_agent:
            names.extend(review_methods)
        for name in names:
            method = getattr(module, name)
            doc = inspect.getdoc(method)
            assert doc, f"{module.AGENT_NAME}.{name} 缺少中文方法注解"
            assert any("\u4e00" <= char <= "\u9fff" for char in doc), f"{module.AGENT_NAME}.{name} 注解不是中文"


def test_review_nodes_are_split_into_dedicated_files():
    root = Path(__file__).resolve().parents[1]
    review_dir = root / "src" / "agents" / "review_nodes"
    expected_review_files = {
        "world_review.py",
        "worldview_review.py",
        "novel_review.py",
        "outline_review.py",
        "chapter_review.py",
    }
    actual_review_files = {path.name for path in review_dir.glob("*.py")}
    assert expected_review_files <= actual_review_files

    for filename in expected_review_files:
        source = (review_dir / filename).read_text(encoding="utf-8")
        assert "execute_llm_review" in source or "build_chapter_review_nodes" in source, f"{filename} 必须承载独立审核调用或章节审核组装"
        assert any("\u4e00" <= char <= "\u9fff" for char in source), f"{filename} 必须包含中文审核说明"

    for relative_path in [
        "src/agents/worldview_agent.py",
        "src/agents/novel_agent.py",
        "src/agents/outline_agent.py",
        "src/agents/chapter_agent.py",
    ]:
        source = (root / relative_path).read_text(encoding="utf-8")
        assert "from src.agents.review_agent import execute_llm_review" not in source
        assert "execute_llm_review(" not in source


if __name__ == "__main__":
    test_all_hierarchy_modules_content_modification_calls_dedicated_llm()
    test_all_hierarchy_modules_initial_expansion_calls_dedicated_llm()
    test_five_agents_are_independent_state_graph_instances()
    test_agent_methods_have_chinese_annotations()
    test_review_nodes_are_split_into_dedicated_files()
