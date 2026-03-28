# 技术设计文档：世界观与小说 Agent (多 Agent 架构)

[English Version](./technical_design.md) | [中文版](./technical_design_ZH.md)

## 1. 角色：工作流架构师 (Workflow Architect)

作为 **工作流架构师**，本系统的设计优先考虑 **稳定性**、**可扩展性** 和 **自愈性 (Self-healing)**。架构采用基于 LangGraph 的状态机方法，管理 AI 生成器、逻辑审计员和人类监督员之间的复杂交互。

### 核心原则

* **状态管理**：使用 `TypedDict` 确保节点间的数据一致性。
* **逻辑闭环**：实现“审计-拒绝-重写”循环，以维持高质量输出。
* **人机协作**：为关键决策定义的明确的人类干预点。
* **数据库同步**：多数据集事务性，确保 MongoDB 和 ChromaDB 保持同步。

---

## 2. 状态管理 (`AgentState`)

`AgentState` 是工作流的核心，跟踪查询、上下文、当前提案和审计历史。

```python
class AgentState(TypedDict):
    query: str
    worldview_id: str      # 关联的世界观/创作宇宙 (顶级)
    outline_id: str        # 关联的小说大纲/项目 ID (世界观的子项)
    context: str
    proposal: str
    review_log: str
    user_feedback: str
    iterations: int        # 总生成尝试计数
    audit_count: int       # 自审重试计数
    is_approved: bool      # 来自审核员或人类的信号
    category: str 
    doc_id: str
    status_message: str    # 实时执行状态
```

---

## 3. LangGraph 工作流定义

系统由 4 个主要功能节点组成：

1. **`generator` (生成器)**：利用 LLM 根据用户查询和 RAG 上下文产生或细化“提案”。
2. **`reviewer` (逻辑审计员)**：根据 **0-4 架构** 和 **最高禁令** 进行零作弊的逻辑审计。
3. **`human` (人类关卡)**：将审计结果和提案展示给用户，以获取反馈或最终批准。
4. **`saver` (同步提交器)**：执行对数据库的最终“事务性”写入。

### 执行流程 (DAG/状态机)

* **入口点**：`generator`
* **主循环**：`generator` -> `reviewer` -> (条件: `失败` -> `generator`, `通过` -> `human`)
* **最终阶段**：`human` -> (条件: `重试` -> `generator`, `批准` -> `saver`) -> `END`

---

## 4. 逻辑一致性与自愈

`reviewer` 节点设计用于 **自愈**。如果逻辑审计员识别出违反 0-4 架构（例如，未经授权的时间控制元素），它将提供详细的 `audit_log`，该日志被反馈到 `generator` 中进行强制重写。

> [!NOTE]
> 循环上限为 3 次迭代，以防止无限递归，之后会转回人类干预。

---

## 5. 层级化数据同步与隔离 (Hierarchical Isolation)

系统实现了 **世界观 (Worldview)** -> **小说大纲 (Novel Outline)** -> **小说章节 (Novel Chapter)** 的三级层级结构。该架构确保了独立创作宇宙之间的创意隔离，同时支持多个小说共享同一底层设定。

### 5.1 目录级层级结构 (Directory-Based Hierarchy)

所有持久化数据均严格分区。世界观充当多个小说项目的容器：

* **顶级目录**: `data/worldviews/{worldview_id}/`
* **世界观设定**: `data/worldviews/{worldview_id}/worldview_db.json` (命名空间 JSONL)
* **小说项目**: `data/worldviews/{worldview_id}/outlines/{outline_id}/`
* **项目专属数据**:
  * **正文存档**: `data/worldviews/{worldview_id}/outlines/{outline_id}/prose_db.json`
  * **实体草稿**: `data/worldviews/{worldview_id}/outlines/{outline_id}/entity_drafts_db.json`

### 5.2 全局注册表 (Global Registries)

中心化的注册表维护层级元数据：

* **世界观注册表**: `data/worldviews_registry.json`
* **小说注册表**: `data/outlines_db.json` (映射到 `worldview_id`)

### 5.3 向量库命名空间 (层级化 RAG)

ChromaDB 集合根据层级进行命名空间隔离，支持分层检索：

* **世界观集合**: `pga_wv_{worldview_id}` - 包含稳定的世界观设定知识。
* **章节集合**: `pga_prose_{outline_id}` - 包含特定小说的创作历史（正文）。
* **隔离效果**: Agent 仅从其所属的世界观空间检索语境，彻底杜绝不同宇宙间的语境污染。

### 5.4 语境传播 (Context Propagation)

* **Agent 状态**: `AgentState` 强制包含 `worldview_id` 与 `outline_id`。
* **API 路由**: 所有设定、Agent 和存档 API 均承载层级语境，确保确定性的文件与向量路径解析。
*   **双写一致性**: `saver` 节点负责将状态同步到对应命名空间的物理存储与向量索引。

---

### 5.3 语义检索架构 (Semantic Search)

为了解决传统关键词过滤的局限性，系统引入了基于向量数据库的异步语义检索：

*   **后端支持**: `app_api.py` 的 `/api/search` 接口通过 ChromaDB 进行相似度检索，返回带有 `id` 和 `type` 的标准化 JSON。
*   **前端集成**: 在 Lore DB 页面提供“语义搜索”开关，开启后 UI 将通过异步请求后端检索替代本地过滤，支持跨层级的实体发现。

---

## 6. 小说大纲 Agent (第二工作流)

小说大纲 Agent 遵循类似的 0-4 架构，但侧重于叙事结构。

### JSON Schema 强制执行

大纲 Agent 严格绑定到专业的小说大纲模式：

* **`meta_info`**: 元数据（类型、基调、目标受众）。
* **`core_hook`**: 核心钩子与激励事件。
* **`character_roster`**: 角色表与动机。
* **`plot_beats`**: 高层级节奏（第一幕、中点、高潮）。

* **人机交互工作流 (HITL)**：
    * **异步流式响应**: UI 通过 `httpx.stream` 实时监听 Agent 节点状态。
    * **中断与恢复**: 利用 LangGraph 的 `interrupt` 机制，Agent 在生成初稿后挂起并返回 `proposal`。
    * **指令化恢复**: UI 通过发送包含 `resume_input` 的请求，向 Graph 发送 `Command` 以恢复执行。

---

## 7. 正文管理与人工迭代 (Prose Management)

系统将章节生成视为一个包含 AI 生成、逻辑审计和人工精修的多阶段过程。

### 7.1 命名空间持久化 (Namespace Preservation)

正文章节严格存储在项目的命名空间内，以确保创意隔离：

* **存储路径**: `data/worldviews/{worldview_id}/outlines/{outline_id}/prose_db.json`
* **元数据**: 每一条记录 package `scene_id`、`scene_title`、`content` 和 `timestamp`。

### 7.2 人机协作编辑器 (HITL Editor)

章节管理 UI (`ui/pages/chapters.py`) 提供了一个专门的界面，用于：

* **项目过滤**: 查看对应项目下的所有已生成章节。
* **人工精修**: 直接编辑由 LLM 生成的正文，修复文笔问题或叙事偏差。
* **归档更新**: 编辑后的内容将写回对应项目的局部数据库，确保“事实来源 (Ground Truth)”对未来的 RAG 检索保持最新。

### 7.3 执笔 Agent 集成

`Writing Agent` 图中的 `prose_saver` 节点负责在获得人类批准或通过逻辑审计后，执行向对应命名空间的初始提交。

---

## 8. 观测与监控 (Observability & Monitoring)

系统通过增强的健康检查与后端采集提供深度观测：

1. **Sentry (错误追踪)**: 实时捕捉后端异常。
2. **LangFuse (LLM 追踪)**: 追踪 LangGraph 执行流，监控 Token 消耗。
3. **Prometheus (指标)**: 采集系统指标与自定义业务指标。
4. **Grafana (可视化)**: 提供中心化的控制面板展示系统健康状况。
5. **原子级日志 (Atomic Logs)**: 在长耗时节点内部实时推送细分步骤日志，覆盖 **正文创作、世界观审计、大纲策划、文档导入、意图路由** 全流程。

---

## 9. 项目文件映射

| 组件 | 职责 | 相关文件 | 状态 |
| :--- | :--- | :--- | :--- |
| **逻辑引擎 (世界观)** | 图执行与状态流，支持层级隔离 | `worldview_agent_langgraph.py` | ✅ 已优化 |
| **逻辑引擎 (大纲)** | 独立检索节点，定义小说主键 | `novel_outline_agent_langgraph.py` | ✅ 已优化 |
| **逻辑引擎 (正文)** | 基于层级关系的的 RAG 场次对齐 | `writing_execution_agent_langgraph.py` | ✅ 已优化 |
| **逻辑引擎 (导入)** | 文件解析与项目级切片导入 | `worldview_import_agent.py` | ✅ 已优化 |
| **逻辑引擎 (路由)** | 意图识别与层级语境转发 | `router_agent_langgraph.py` | ✅ 已优化 |
| **LLM 配置中心** | 分层模型回放与持久化 | `llm_factory.py`, `config_utils.py` | ✅ 已实现 |
| **API 路由与韧性** | 承载层级语境的流式接口 | `app_api.py` | ✅ 已优化 |
| **Web 仪表盘** | 多小说选择与动态进度渲染 | `dashboard.html` | ✅ 已实现 |
| **架构规则** | 0-4 架构与最高禁令 | `info.md`, `novel_outline_info.md` | ✅ 已定义 |
| **向量索引** | 层级化的 ChromaDB 集合 | `./chroma_db/` | ✅ 已实现 |
| **分布式存储** | 按项目隔离的 JSON 数据库 | `./data/worldviews/` | ✅ 已实现 |

---

## 10. 开发协议 (Development Protocol)

> [!IMPORTANT]
> **文档先行 (Documentation First):**
> 在添加任何新功能或 UI 页面之前，**必须**先执行以下步骤：
>
> 1. **更新技术文档**: 在 `technical_design.md` 中明确描述新功能/页面的目的。
> 2. **影响分析**: 文档化该功能对现有状态、数据库或 Agent 逻辑库的影响。
> 3. **功能分解**: 将功能分解为原子任务（UI、API、数据、验证）。
