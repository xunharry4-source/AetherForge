import uuid
import time
from typing import Dict, Any, List, Optional
from logger_utils import get_logger
import writing_execution_agent_langgraph as writing_agent

logger = get_logger("novel_agent.batch_writer")
writing_app = writing_agent.app

class BatchWriter:
    def __init__(self, thread_id: Optional[str] = None):
        self.thread_id = thread_id or str(uuid.uuid4())
        self.config = {"configurable": {"thread_id": self.thread_id}}
        self.progress = {
            "chapter_id": None,
            "total_scenes": 0,
            "current_scene_index": 0,
            "status": "idle",
            "scenes_completed": []
        }

    def start_batch(self, outline_id: str, outline_content: str, current_act: str):
        """
        开始批量写作会话
        """
        logger.info(f"Starting batch write session for outline {outline_id}, Act: {current_act}")
        self.progress.update({
            "chapter_id": outline_id,
            "status": "planning",
            "current_scene_index": 0
        })

        initial_state = {
            "outline_id": outline_id,
            "outline_content": outline_content,
            "current_act": current_act,
            "is_batch_mode": True,  # 开启批量模式
            "retry_count": 0        # 初始化重试计数
        }

        # 运行初始 planning
        events = writing_app.stream(initial_state, self.config, stream_mode="values")
        last_state = None
        for event in events:
            last_state = event
            
        if not last_state or "scene_list" not in last_state:
            logger.error("Failed to plan scenes for batch write.")
            self.progress["status"] = "failed"
            return {"error": "Failed to plan scenes"}

        self.progress["total_scenes"] = len(last_state["scene_list"])
        self.progress["status"] = "writing"
        
        return self.progress

    def get_progress(self):
        """获取当前进度"""
        return self.progress

    def run_next_step(self):
        """
        驱动 Graph 运行到下一个状态（通常是完成一个场次或处理一次审计故障）
        """
        state = writing_app.get_state(self.config)
        if state.next:
            # 如果有 interrupt (通常是 audit 失败或 batch 模式被覆盖)
            # 在 Batch 模式下，如果审计通过，Graph 应该自动流转到 prose_saver
            # 如果没自动流转，说明遇到了 interrupt 或者 END
            logger.info(f"Stepping graph from {state.next}")
            # 这里调用 Command(resume=True) 或者继续 stream
            # 但在我们的设计中，is_batch_mode 会在 route 阶段跳过 human_review
            pass

        # 重新开始流，直到遇到下一个节点或结束
        events = writing_app.stream(None, self.config, stream_mode="values")
        last_state = None
        for event in events:
            last_state = event
            
        if not last_state:
            self.progress["status"] = "completed"
            return self.progress

        self.progress["current_scene_index"] = last_state.get("active_scene_index", 0)
        
        # 检查是否结束
        if self.progress["current_scene_index"] >= self.progress["total_scenes"]:
            self.progress["status"] = "completed"
        
        return self.progress
