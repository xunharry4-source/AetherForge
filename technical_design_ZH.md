# 技术设计文档：世界观与小说 Agent (多 Agent 架构)

## 1. 角色：工作流架构师 (Workflow Architect)

作为 **工作流架构师**，本系统的设计优先考虑 **稳定性**、**可扩展性** 和 **自愈性 (Self-healing)**。架构采用基于 LangGraph 的状态机方法，管理 AI 生成器、逻辑审计员和人类监督员之间的复杂交互。

### 核心原则
* **状态管理**：使用 `TypedDict` 确保节点间的数据一致性。
* **逻辑闭环**：实现“审计-拒绝-重写”循环，以维持高质量输出。
- **人机协作**：为关键决策定义的明确的人类干预点。
* **数据库同步**：多数据集事务性，确保 MongoDB 和 ChromaDB 保持同步。

---

## 2. 状态管理 (`AgentState`)

`AgentState` 是工作流的核心，跟踪查询、上下文、当前提案和审计历史。

```python
class AgentState(TypedDict):
    query: str
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

## 5. 数据库同步与多项目隔离 (Multi-Project Isolation)

系统支持多项目共存，通过配置层实现逻辑与物理双重隔离：
1. **逻辑隔离**：在 `config.json` 中配置 `MONGO_DB_NAME` 和 `CHROMA_COLLECTION_NAME`。
2. **物理隔离**：项目根目录提供专用的 `docker-compose.yml`，使用项目专属容器名（如 `novel_agent_mongodb`）。

数据持久化流程：
1. **MongoDB**：由 `saver` 节点将全文和元数据写入指定的独立数据库。
2. **ChromaDB**：将文本切片向量化并存入指定的专属 Collection，避免跨项目索引污染。

---

### 5.3 语义检索架构 (Semantic Search)
为了解决传统关键词过滤的局限性，系统引入了基于向量数据库的异步语义检索：
- **后端支持**: `app_api.py` 的 `/api/search` 接口通过 ChromaDB 进行相似度检索，返回带有 `id` 和 `type` 的标准化 JSON。
- **前端集成**: 在 Lore DB 页面提供“语义搜索”开关，开启后 UI 将通过异步请求后端检索替代本地过滤，支持跨层级的实体发现。

---

## 6. 小说大纲 Agent (第二工作流)

小说大纲 Agent 遵循类似的 0-4 架构，但侧重于叙事结构。
- **JSON Schema 强制执行**：大纲 Agent 严格绑定到专业的小说大纲模式，包含 `meta_info`、`core_hook`、`character_roster` 和 `plot_beats`。
- **人机交互工作流 (HITL)**：
    - **异步流式响应**: UI 通过 `httpx.stream` 实时监听 Agent 节点状态。
    - **中断与恢复**: 利用 LangGraph 的 `interrupt` 机制，Agent 在生成初稿后挂起并返回 `proposal`。
    - **指令化恢复**: UI 通过发送包含 `resume_input` (如 "批准" 或修改意见) 的请求，向 Graph 发送 `Command` 以恢复执行。

---

## 7. 全链路展示与观测 (Observability)
 
 系统通过增强的健康检查与后端采集提供深度观测：
- **实时进度反馈**: 
    - **节点化粒度**: 每一个 LangGraph 节点（如 `retriever`, `planner`, `defense` 等）都会更新 `status_message` 状态。
    - **RAG 独立化**: 将耗时较长的“知识库检索”步骤独立为 `retriever` 节点，确保用户能明确区分“搜索中”与“构思中”。
    - **流式传输**: 后端通过 NDJSON 格式实时推送节点更新和心跳信号，前端 UI 动态渲染当前状态。
- **韧性与自愈**:
    - **429 自动修复**: 在 API 层面实现 API KEY 自动轮换机制（支持多达 5 次重试）。
    - **连接保持**: 引入 5 秒心跳机制，防止长耗时 RAG 任务导致 HTTP 连接超时。
- **监控集成**:
    - **Sentry**: 实时捕捉后端异常。
    - **LangFuse**: 追踪 LangGraph 执行流，监控 Token 消耗。
    - **Prometheus + Grafana**: 采集系统指标与自定义业务指标。
- **实时健康检查**: `/api/system/health` 实时探测数据库连通性并提供中文化反馈。

---

## 8. 测试与验证原则 (Testing & Verification)

> [!IMPORTANT]
> **测试的目的是找出系统的错误与问题，并且是尽可能发现系统的漏洞与可能的存在的缺陷，不是为了逃避错误与问题。**

---

## 8. 项目文件映射

| 组件 | 职责 | 相关文件 | 状态 |
| :--- | :--- | :--- | :--- |
| **逻辑引擎 (世界观)** | 图执行与状态流，含进度日志 | `worldview_agent_langgraph.py` | ✅ 已优化 |
| **逻辑引擎 (大纲)** | 独立检索节点，含进度日志 | `novel_outline_agent_langgraph.py` | ✅ 已优化 |
| **逻辑引擎 (正文)** | RAG 节点拆分，语境对齐 | `writing_execution_agent_langgraph.py` | ✅ 已优化 |
| **逻辑引擎 (导入)** | 文件解析与分篇，含进度日志 | `worldview_import_agent.py` | ✅ 已优化 |
| **API 路由与韧性** | 异步流、429 轮换、心跳 | `app_api.py` | 🏗️ 优化中 |
| **Web 仪表盘** | 动态进度渲染与 JSON 预览 | `dashboard.html` | 🏗️ 待对接 |
| **架构规则** | 0-4 架构与最高禁令 | `info.md`, `novel_outline_info.md` | ✅ 已定义 |
| **向量索引** | 跨项目隔离的 ChromaDB | `./chroma_db/` | ✅ 已实现 |

---

## 10. 开发协议 (Development Protocol)

> [!IMPORTANT]
> **文档先行 (Documentation First):**
> 在添加任何新功能或 UI 页面之前，**必须**先执行以下步骤：
> 1. **更新技术文档**: 在 `technical_design.md` 中明确描述新功能/页面的目的。
> 2. **影响分析**: 文档化该功能对现有状态、数据库或 Agent 逻辑的下游影响。
> 3. **功能分解**: 将功能分解为原子任务（UI、API、数据、验证）。
