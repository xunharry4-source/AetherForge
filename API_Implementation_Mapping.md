# 小说创作助手 (PGA Admin) 开发接口映射手册 (技术视角)

本文档面向开发与运维团队，定义了 UI 各功能模块与后端 API/Agent 的技术映射关系及健康状态。

## 1. 系统基础服务接口

| 功能模块 | 对应 API 路径 | 方法 | 说明 | 状态 |
| :--- | :--- | :--- | :--- | :--- |
| 健康自检 | `/api/system/health` | GET | 检查 Flask/Mongo/Chroma 连接 | ✅ 正常 |
| LLM 元数据 | `/api/system/llm-info` | GET | 返回当前活动的模型与 Supplier 信息 | ✅ 正常 |
| 实时审计日志 | `/api/system/logs` | WS/GET| 流式输出 `logger_utils` 捕获的日志 | ✅ 正常 |

## 2. 档案与知识库操作 (CRUD & Sync)

| 功能模块 | 对应 API 路径 | 方法 | 数据流向 | 状态 |
| :--- | :--- | :--- | :--- | :--- |
| 树状分类获取 | `/api/lore/tree` | GET | Worldview JSONL -> UI Tree | ✅ 正常 |
| 通用条目更新 | `/api/archive/update` | POST | UI -> JSONL + ChromaDB Sync | ✅ 正常 |
| 通用条目删除 | `/api/archive/delete` | DELETE| JSONL Delete + Vector Purge | ✅ 正常 |
| 关系图谱生成 | `/api/lore/entity-graph`| GET | Lore Analysis -> Vis Graph Data | ✅ 正常 |
| 思维导图生成 | `/api/lore/mindmap` | GET | Category Hierarchy -> Markmap | ✅ 正常 |
| 全文检索 | `/api/search` | POST | ChromaDB Semantic Search | ✅ 正常 |
| 全文检索 (UI) | 本地关键词过滤 (Keyword Filter) | 否 | N/A (Client-side) | ⚠️ 搜索返回空 |

> [!IMPORTANT]
> **技术诊断**: UI 层的 `filter_tree` 函数仅对已加载的 `all_docs` 进行字符串匹配。如果需要基于 ChromaDB 的深度检索，应调用 `/api/search` 接口。

## 3. Agent 交互与工作流

| 功能模块 | 对应 API 路径 | 方法 | 核心逻辑实现 | 状态 |
| :--- | :--- | :--- | :--- | :--- |
| 交互式创作/对话 | `/api/agent/query` | POST | `router_agent_langgraph` 判定分发 | ✅ 正常 |
| 大纲提案生成 | `/api/agent/query` | POST | `novel_outline_agent_langgraph` | ✅ 正常 |
| 人工反馈插入 | `/api/agent/feedback`| POST | 线程信号挂起与恢复 | ✅ 正常 |

## 4. 设定草案管理与审批

| 功能模块 | 对应 API 路径 | 方法 | 说明 | 状态 |
| :--- | :--- | :--- | :--- | :--- |
| 草案列表 | `/api/entity-drafts` | GET | 获取 `entity_drafts_db.json` | ✅ 正常 |
| 单条审批 | `/api/entity-drafts/approve`| POST | `lore_utils.approve_draft_entity` | ✅ 正常 |
| 批量操作 | `/api/entity-drafts/batch-*` | POST | 支持 approve/reject 批量更新 | ✅ 正常 |
| 草案修正 | `/api/entity-drafts/refine` | POST | 调用 `worldview_agent` 再次生成 | ✅ 正常 |

## 5. 配置中心

| 功能模块 | 对应核心入口 | 实现文件 | 说明 | 状态 |
| :--- | :--- | :--- | :--- | :--- |
| 模型/Key 切换 | `/config_utils` | `config.json` | 支持动态重载 API Keys | ✅ 正常 |
| 设定模版管理 | `/api/worldview/templates`| `worldview_templates.json` | 定义各实体的 JSON Schema 约束 | ✅ 正常 |

---
**版本**: v2.2.0-Production
**技术基座**: NiceGUI (Frontend) + Flask (Backend) + JSONL (DB) + ChromaDB (Vector)
