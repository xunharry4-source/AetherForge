# 世界层级与 Agent 迭代工作台产品需求文档

更新日期：2026-04-29  
适用范围：`/worlds` 世界层级工作台、`/lore` 世界观资料库、大纲章节迭代工作流、后端层级 API、真实 requests 测试。

## 1. 产品目标

构建一个用于小说生产的层级化创作工作台，让用户能够按真实业务关系管理：

`世界 -> (世界观, 小说) -> 大纲 -> 章节`

其中：

- 世界：创作宇宙的顶层容器。
- 世界观：世界的规则、设定、历史、势力、地理、科技、禁令等。
- 小说：发生在同一个世界中的具体故事项目。
- 大纲：某一部小说的叙事结构和章节计划。
- 章节：某一份大纲下的正文内容，继续使用 `prose` 集合存储。

产品必须保证页面展示和所有操作都来自真实数据库查询，不允许假数据、静态样例数据、mock、吞异常、隐藏错误或降级伪成功。

## 2. 核心用户价值

1. 用户可以清楚区分“世界规则”和“世界中的故事”，避免把世界观和小说混为父子关系。
2. 用户可以通过列表、树、图和工作流视图管理复杂层级，同时避免世界观和章节大数据量全量渲染导致页面卡死。
3. 用户可以用类似 Dify 的对话框和工作流节点方式与各类创作 Agent 交互。
4. 用户可以在每次 AI 迭代中选择修改范围，默认局部重写，避免“小改动导致大范围改写”。
5. 用户可以通过真实 API 测试证明新增、修改、删除、查询都真实发生在数据库中。

## 3. 信息架构

### 3.1 层级关系

- `worlds`
  - `worldviews`
  - `novels`
    - `outlines`
      - `prose`

### 3.2 关系规则

- `worldviews` 与 `novels` 为兄弟节点 (Siblings)，均直接归属 `worlds`。
- `worldview` 表示世界规则与设定，不是小说的父级。
- `novel` 表示该世界中发生的故事，是 `outline` 的父级。
- `outline` 必须归属一个 `novel`，并可关联同世界下的 `worldview` 作为设定约束。
- `prose` 必须归属一个 `outline`，并继承 `novel_id`、`worldview_id`、`world_id`。

## 14. 功能模块详解

### 14.1 世界 (World) - 顶层宇宙容器
- **所属模块**：世界管理
- **功能名称**：创作宇宙顶层容器 (World Container)
- **功能背景**：小说创作通常涉及多个平行世界或独立宇宙，需要一个顶层实体来隔离数据并作为创作资产的逻辑锚点。
- **功能描述**：提供一个全局容器，用于组织世界观、小说及所有相关创作数据，确保数据的逻辑隔离、权限管理与层级归属。
- **使用场景**：用户计划开启一个全新的创作系列（如“赛博大唐”），首先创建一个“世界”作为所有设定和故事的根基。
- **新增逻辑**：
  1. 用户提交“创建世界”表单 -> 触发 `world_agent`。
  2. `world_agent` 生成全局唯一 `world_id`。
  3. 物理写入 MongoDB `worlds` 集合，初始化空关联列表。
- **修改逻辑**：
  1. 用户提交“编辑世界”表单 -> 触发 `world_agent`。
  2. 仅允许修改名称 (name) 和 摘要 (summary)，禁止修改 `world_id`。
  3. 异步更新 `updated_at` 时间戳并广播层级树刷新信号。
- **删除逻辑**：
  1. 用户提交“删除世界”请求。
  2. 校验下属是否有关联的 `worldviews` 或 `novels`。
  3. 若非空且未传 `cascade=true`，返回 `409`。
  4. 若满足条件，执行物理级联删除所有下属资产。
- **查询逻辑**：
  1. 支持列表无条件全量查询。
  2. 也可以根据名称 (name) 等条件进行搜索与过滤。
- **是否需要调用Agent**：是 (`world_agent`)
- **Agent工作流与循环迭代机制 (State Graph)**：
  - **工作流状态 (State)**：维护 `payload` (名称/摘要)、`feedback` (修改意见)、`status` (状态)。
  - **输入节点 (Input Node)**：初始化 State，记录用户消息和表单 payload。
  - **草案节点 (Draft Node)**：根据 State 中的输入或 `feedback` 生成/修改草案，生成 `world_id`。
  - **人工节点 (Approval Node/HITL)**：展示草案给用户。用户可选择：“批准 (Approve)”、“完全重写 (Full Rewrite)”、“指定局部重写 (Targeted Partial Rewrite)” 或 “指定内容重写 (Targeted Content Rewrite)”。
    - *迭代循环*：若用户选择重写或提供修改意见，则将意见写入 `feedback`，**状态流转回 草案节点**重新生成。
  - **写库节点 (Commit Node)**：用户批准后触发，真实执行 MongoDB `worlds` 集合的写入。
- **规则说明**：
  - 世界名称必须在当前用户空间内唯一。
  - 删除世界属于高危操作，必须强制二次确认。

### 14.2 世界观 (Worldview) - 规则与设定库
- **所属模块**：世界观管理
- **功能名称**：规则与设定资料库 (Worldview Lore DB)
- **功能背景**：故事的逻辑一致性取决于严谨的设定，需要结构化的方式存储地理、历史、种族、物理规则等 Canon 内容。
- **功能描述**：管理世界的“真理”设定，支持树状分类浏览和基于语义的 RAG 检索，为后续所有 AI 创作提供强有力的上下文约束。
- **使用场景**：创作者定义了“灵气引擎”的运作原理，随后要求系统内所有涉及此类技术的小说章节必须严格遵循该设定。
- **新增逻辑**：
  1. 提交设定条目 -> 触发 `worldview_agent` 进行一致性审查。
  2. 审查通过后，生成 `worldview_id` 或 `doc_id`。
  3. 写入 MongoDB 并同步至 ChromaDB 向量库建立语义索引。
- **修改逻辑**：
  1. 修改现有条目 -> 触发 `worldview_agent` 重新审查变更影响。
  2. 更新 MongoDB 记录，同时增量更新 ChromaDB 中的向量特征。
- **删除逻辑**：
  1. 提交删除请求 -> 校验是否被当前大纲/章节引用。
  2. 物理从 MongoDB 移除，并同步从 ChromaDB 吊销对应向量。
- **查询逻辑**：
  1. 禁止无条件全量查询。
  2. 查询必须带 `world_id`、`worldview_id` 或 `query` 等业务条件，并带分页。
  3. 支持树状 (Tree) 或网状图 (Graph) 结构展示。
- **是否需要调用Agent**：是 (`worldview_agent`)
- **Agent工作流与循环迭代机制 (State Graph)**：
  - **工作流状态 (State)**：维护 `lore_data`、`review_feedback`、`user_feedback`。
  - **输入节点 (Input Node)**：初始化设定条目请求。
  - **草案节点 (Draft Node)**：生成结构化设定内容及特征实体。
  - **审查节点 (Review Node)**：基于 RAG 检索校验设定是否与已有 Canon 冲突。具体审查内容包括：内容格式是否规范、是否包含逻辑漏洞、新增设定是否与该世界下已有核心设定（历史、地理、规则等）存在直接冲突。
    - *自动迭代循环*：若审查未通过，将冲突原因写入 `review_feedback`，**状态自动流转回 草案节点**进行修正，直至审查通过。
  - **人工节点 (Approval Node/HITL)**：审查通过后提交用户确认。用户可选择：“批准 (Approve)”、“完全重写 (Full Rewrite)”、“指定局部重写 (Targeted Partial Rewrite)” 或 “指定内容重写 (Targeted Content Rewrite)”。
    - *人工迭代循环*：若用户要求修改，将意见写入 `user_feedback`，**状态流转回 草案节点**重新生成，且重新生成后必须再次经历审查节点。
  - **写库节点 (Commit Node)**：全部通过后，写入 MongoDB 并同步至 ChromaDB 建立语义索引。
- **规则说明**：
  - 所有设定条目必须强绑定特定的 `world_id`。
  - 支持 OPML 标准格式的导入导出。

### 14.3 小说 (Novel) - 故事项目管理
- **所属模块**：小说管理
- **功能名称**：独立故事项目管理 (Novel Project Management)
- **功能背景**：一个世界可以容纳多个故事，每个故事有其独立的叙事视角、角色曲线和完结状态。
- **功能描述**：作为大纲和章节的父级容器，负责协调特定故事线的创作进度，并关联当前世界下的相应设定集。
- **使用场景**：在已定义的“星际航海”世界中，开启一部名为《边缘星区往事》的特定小说创作项目。
- **新增逻辑**：
  1. 在世界节点下点击“添加小说” -> 触发 `novel_agent`。
  2. 必填 `world_id`，可选关联 `worldview_id`。
  3. 初始化小说根目录，物理写入 `novels` 集合。
- **修改逻辑**：
  1. 提交修改表单 -> 更新小说名称、简介或关联的世界观。
  2. 修改 `worldview_id` 时需校验新设定集是否属于同一个世界。
- **删除逻辑**：
  1. 提交删除请求 -> 校验是否包含大纲。
  2. 若含子项且未级联，拒绝删除。
  3. 确认后删除 `novels` 记录，并清理所有下属 `outlines` 和 `prose`。
- **查询逻辑**：
  1. 禁止全量查询。必须带 `world_id` 等业务条件。
  2. 必须进行分页展示。
- **是否需要调用Agent**：是 (`novel_agent`)
- **Agent工作流与循环迭代机制 (State Graph)**：
  - **工作流状态 (State)**：维护小说元数据、`review_feedback`、`user_feedback`。
  - **输入节点 (Input Node)**：接收标题、简介、`world_id`。
  - **草案节点 (Draft Node)**：生成/完善小说的整体构思。
  - **审查节点 (Review Node)**：校验小说大方向是否偏离关联的世界/世界观设定。具体审查内容包括：故事背景是否契合世界观约束、主角设定与核心主线是否符合逻辑、是否存在破坏世界基础规则的设定（反吃设定）。
    - *自动迭代循环*：如偏离设定，生成 `review_feedback` 并**状态回退至 草案节点**重构。
  - **人工节点 (Approval Node/HITL)**：用户确认。用户可选择：“批准 (Approve)”、“完全重写 (Full Rewrite)”、“指定局部重写 (Targeted Partial Rewrite)” 或 “指定内容重写 (Targeted Content Rewrite)”。
    - *人工迭代循环*：用户可追加修改指令 (`user_feedback`)，触发**状态回流至 草案节点**，然后重新过审。
  - **写库节点 (Commit Node)**：最终状态落盘至 `novels` 集合。
- **规则说明**：
  - 小说不可跨世界存在，必须归属于单一 `world_id`。

### 14.4 大纲 (Outline) - 叙事结构规划
- **所属模块**：叙事策划
- **功能名称**：结构化大纲迭代 (Structured Outline Iteration)
- **功能背景**：长篇创作需要稳定的结构化蓝图，AI 生成的大纲通常需要经历多轮人工反馈和局部微调。
- **功能描述**：提供大纲的层级化规划能力，支持将故事拆解为多个叙事节点，并允许用户针对特定节点进行“局部重构”。
- **新增逻辑**：
  1. `outline_agent` 根据小说简介生成初始树状结构。
  2. 支持从已有模板快速创建大纲框架。
  3. 物理写入 `outlines` 集合。
- **修改逻辑**：
  1. 修改大纲节点 -> 触发 `outline_agent` 进行 `partial_rewrite` (局部重写)。
  2. 利用 LangGraph 仅更新受影响的子路径。
  3. 更新后必须重新同步至下属章节的任务描述。
- **删除逻辑**：
  1. 删除大纲节点 -> 物理从数据库移除。
  2. 必须级联删除其下属的所有正文内容（`prose`）。
- **查询逻辑**：
  1. 必须带 `novel_id`、`world_id` 等业务条件进行查询。
  2. 支持分页和层级树状结构展示。
- **是否需要调用Agent**：是 (`outline_agent`)
- **Agent工作流与循环迭代机制 (State Graph)**：
  - **工作流状态 (State)**：维护树状结构数据、局部重写路径、审查和用户反馈。
  - **输入节点 (Input Node)**：接收大纲结构或局部重写 (`partial_rewrite`) 指令。
  - **草案节点 (Draft Node)**：生成大纲节点，或利用 LangGraph 仅更新受影响的子路径。
  - **审查节点 (Review Node)**：审查大纲逻辑连贯性、防止剧情脱轨及设定冲突。具体审查内容包括：上下文节点剧情逻辑是否连贯、故事发展是否偏离小说主旨、核心冲突与高潮安排是否合理、是否出现与前面剧情或已有世界观设定矛盾的情节。
    - *自动迭代循环*：逻辑不通或冲突时，带有约束意见的 `review_feedback` 将**状态打回 草案节点**。
  - **人工节点 (Approval Node/HITL)**：用户确认节点结构。用户可选择：“批准 (Approve)”、“完全重写 (Full Rewrite)”、“指定局部重写 (Targeted Partial Rewrite)” 或 “指定内容重写 (Targeted Content Rewrite)”。
    - *人工迭代循环*：长篇大纲通常需多轮微调。用户的局部修改指令会导致状态机在“特定节点重写”和“审查”之间**循环迭代**，直到用户满意。
  - **写库节点 (Commit Node)**：用户批准后写入 `outlines` 集合。
- **规则说明**：
  - 每次大纲修改必须记录版本快照。

### 14.5 章节 (Chapter) - 正文创作与审查
- **所属模块**：正文创作
- **功能名称**：智能章节迭代与审查 (Intelligent Chapter Iteration & Review)
- **功能背景**：正文创作是创作链路的终点，需要极高的内容质量把控和严密的逻辑审查（反吃设定）。
- **功能描述**：支持章节正文的 AI 协同生成、自动质量审查及手动润色，提供针对特定段落的“局部重写”能力以实现精细化打磨。
- **新增逻辑**：
  1. `chapter_agent` 根据大纲节点生成初稿。
  2. 继承所有父级 ID，物理写入 `prose` 集合。
- **修改逻辑**：
  1. 标记正文片段 -> 触发 AI 局部重写。
  2. 手动编辑 -> 保存时触发 `review_agent` 增量检查设定一致性。
- **删除逻辑**：
  1. 直接物理删除 `prose` 记录。
- **查询逻辑**：
  1. 绝对禁止全量显示。
  2. 必须按 `outline_id`、`novel_id` 或其他条件进行分页查询。
- **是否需要调用Agent**：是 (`chapter_agent` 及 `review_agent`)
- **Agent工作流与循环迭代机制 (State Graph)**：
  - **工作流状态 (State)**：维护正文内容、上下文记忆、大纲约束、审查报告。
  - **输入节点 (Input Node)**：注入大纲节点要求、前文上下文及重写片段标记。
  - **草案节点 (Draft Node)**：生成正文初稿，或执行精细化的局部重写 (`partial_rewrite`)。
  - **审查节点 (Review Node)**：由 `review_agent` 独立执行，严查设定一致性（反吃设定）。具体审查内容包括：人物行为动机与对话是否符合已有的人设模板、场景与道具描写是否符合世界观物理法则、剧情推进与章节收尾是否严格遵循大纲约束、文字风格与视角是否存在突兀变化。
    - *自动迭代循环*：如发生吃设定，`review_agent` 给出修改建议，将流程**驳回至 草案节点**，要求其在不改变已有设定的前提下修改正文。该循环可设置最大迭代次数（如 3 次），避免死循环。
  - **人工节点 (Approval Node/HITL)**：提供人工介入的打磨入口。用户可选择：“批准 (Approve)”、“完全重写 (Full Rewrite)”、“指定局部重写 (Targeted Partial Rewrite)” 或 “指定内容重写 (Targeted Content Rewrite)”。
    - *人工迭代循环*：用户标记不满意段落，提交修改意见，触发**相应的重写循环**，同样需要再次经过 `review_agent` 的审查。
  - **写库节点 (Commit Node)**：定稿通过后继承所有关联 ID 写入 `prose` 集合。
- **规则说明**：
  - 只有通过“人工介入”或“审查通过”状态的章节才会被标记为“正式版本”。

## 4. 页面需求

### 4.1 `/worlds` 世界层级 Agent 工作台

默认展示方式：

- 世界：列表显示。
- 世界观：列表显示，允许切换 tree 或图展示，但禁止无条件全量显示。
- 小说：列表显示。
- 大纲：列表显示。
- 章节：列表显示，但必须按大纲或其他业务条件分页查询，禁止全量显示。

工作台能力：

- 提供层级树查看完整结构，展示格式为：`世界 -> (世界观, 小说) -> 大纲 -> 章节`。
- 提供当前选中节点的直接子项表格。
- 提供 React Flow 工作流视图，展示每个 Agent 节点的执行状态。
- 每个工作流节点必须能查看输入与输出。
- 创建、修改、删除世界、世界观、小说、大纲、章节均必须通过表单。
- 删除父级时必须有 `cascade` 显式确认字段；未确认时非空父级返回冲突错误。

### 4.2 对话与人工介入

- 创建/修改/删除均通过对话框提交给独立 Agent。
- 人工介入时必须提供修改模式：
  - `full_rewrite`：完全重写。
  - `partial_rewrite`：指定局部重写，默认值。
  - `content_rewrite`：指定内容重写。
- 用户手动修改表单字段时，工作流记录必须保存 `manual_edit=true`。
- AI 根据用户反馈修改时必须遵守范围保护，不得把小范围修改扩大为全量重写。

### 4.3 `/lore` 世界观资料库

- 页面不得内置假数据。
- 所有数据必须从数据库 API 查询。
- 世界观数据禁止无条件全量查询。
- 世界观可切换 tree 或图展示，但必须带 `world_id`、`worldview_id`、`query` 等业务条件，并带分页。
- 章节禁止全量显示，必须按 `outline_id`、`worldview_id`、`novel_id` 或其他业务条件分页查询。

## 5. Agent 需求

### 5.1 独立 Agent

每类实体必须由独立 Agent 执行：

- `world_agent`
- `worldview_agent`
- `novel_agent`
- `outline_agent`
- `chapter_agent`

### 5.2 审查规则

- 世界：不需要审查，但仍需记录工作流输入、草案、人工确认和写库结果。
- 世界观：需要审查。
- 小说：需要审查。
- 大纲：需要审查。
- 章节：需要审查。

### 5.3 工作流记录

每次 Agent 运行必须写入 `hierarchy_agent_runs`，至少包含：

- `run_id`
- `agent_type`
- `action`
- `status`
- `iterations`
- `review_required`
- `pending_payload`
- `nodes`
- `commit_result`
- `created_at`

节点至少覆盖：

- 输入节点：记录用户消息和表单 payload。
- 草案节点：记录 Agent 生成或修改后的 payload。
- 审查节点：记录审查是否通过和失败原因。
- 人工节点：记录用户批准、拒绝或要求修改。
- 写库节点：记录真实数据库写入结果。

## 6. 数据模型需求

### 6.1 MongoDB 集合

`worlds`

- `world_id`
- `name`
- `summary`
- `timestamp`

`worldviews`

- `worldview_id`
- `world_id`
- `name`
- `summary`
- `timestamp`

`novels`

- `novel_id`
- `world_id`
- `name`
- `summary`
- `timestamp`

`outlines`

- `outline_id`
- `novel_id`
- `worldview_id`
- `world_id`
- `name/title`
- `summary`
- `timestamp`

`prose`

- `id/scene_id/prose_id`
- `outline_id`
- `novel_id`
- `worldview_id`
- `world_id`
- `title/name`
- `content`
- `timestamp`

### 6.2 迁移需求

- 必须提供幂等迁移脚本补齐旧数据关系。
- 重复执行不得重复创建默认世界或默认小说。
- 不得覆盖已有明确的 `world_id`、`worldview_id`、`novel_id`、`outline_id`。

迁移命令：

```bash
PYTHONPATH=.:src:src/common .venv/bin/python scripts/migrate_world_hierarchy.py
```

## 7. API 需求

### 7.1 世界 API

- `GET /api/worlds/list`
- `POST /api/worlds/create`
- `POST /api/worlds/update`
- `DELETE /api/worlds/delete`

世界列表是唯一允许无条件列表查询的业务数据接口。

### 7.2 非世界查询限制

除 `worlds` 外，所有数据库查询接口必须同时满足：

- 必须带业务条件，例如 `world_id`、`worldview_id`、`novel_id`、`outline_id`、`run_id`、`agent_type`、`status` 或 `query`。
- 必须带 `page` 与 `page_size`。
- 缺失业务条件时返回明确 `400`。
- 缺失分页时返回明确 `400`。
- `page_size` 必须有上限，当前上限为 100。

适用接口包括但不限于：

- `GET /api/worldviews/list`
- `GET /api/novels/list`
- `GET /api/outlines/list`
- `GET /api/lore/list`
- `GET /api/lore/tree`
- `GET /api/lore/mindmap`
- `GET /api/lore/entity-graph/<doc_id>`
- `GET /api/lore/export/opml`
- `GET /api/world-hierarchy/tree`
- `GET /api/workflow/outline-chapter/state`
- `GET /api/hierarchy-agent/list`

### 7.3 写入与删除

- 创建子级时必须校验父级存在。
- 修改父级字段时必须校验新父级存在。
- 删除父级时：
  - 没有子级可直接删除。
  - 有子级且未传 `cascade=true` 必须返回 `409`。
  - 有子级且传 `cascade=true` 才允许显式级联删除。
- 增删改后必须可通过查询接口验证数据库真实变化。

## 8. 禁止项

产品和测试中禁止：

- 页面写死假数据。
- API 返回假数据。
- 使用 mock、假库、fixture 伪装真实测试。
- 使用 JSONL 或本地文件作为数据库失败时的静默回退。
- 隐藏后端错误。
- 吞异常后返回成功。
- 删除断言让测试通过。
- 修改测试预期掩盖问题。
- 查询接口无条件读取大集合。
- 世界观和章节全量展示。

## 9. 验收测试要求

测试必须使用 `requests` 调用真实运行中的 API 服务。

### 9.1 正常路径

- 创建 world 后查询确认字段一致。
- 创建 worldview 后查询确认挂到 world。
- 创建 novel 后查询确认挂到 world，且不作为 worldview 子级。
- 创建 outline 后查询确认挂到 novel，并带 `worldview_id` 与 `world_id`。
- 创建 chapter/prose 后查询确认挂到 outline、novel、worldview、world。
- 查询 `/api/world-hierarchy/tree`，严格检查层级顺序 and 每层 ID。

### 9.2 修改路径

- 逐层 update 后必须再次 query。
- 检查名称、summary、content、父级字段真实变化。
- 对章节修改必须再次按 `outline_id` 或其他条件查询确认正文变化。

### 9.3 删除路径

- 非空父级未带 `cascade=true` 必须返回 `409`。
- 返回 `409` 后必须查询确认子级仍存在。
- 带 `cascade=true` 删除 novel/worldview/world 后，必须查询确认所有子级真实消失。

### 9.4 异常路径

- 父级不存在时创建子级必须返回 `400` 或 `404`。
- 缺少必填 ID/name 必须返回 `400`。
- 非法 type 或非法层级关系必须返回明确错误。
- 非世界查询缺失条件必须返回 `400`。
- 非世界查询缺失 `page/page_size` 必须返回 `400`。

### 9.5 真实验证命令

```bash
API_BASE_URL=http://127.0.0.1:5006 .venv/bin/python tests/test_world_hierarchy_requests.py
API_BASE_URL=http://127.0.0.1:5006 .venv/bin/python tests/test_hierarchy_agent_workflow_requests.py
API_BASE_URL=http://127.0.0.1:5006 .venv/bin/python tests/test_outline_chapter_workflow_requests.py
npm run build
curl -I http://127.0.0.1:5174/worlds
```

## 10. 当前验证状态

验证状态：已验证。

真实执行证据：

- `tests/test_world_hierarchy_requests.py`：通过。
- `tests/test_hierarchy_agent_workflow_requests.py`：通过。
- `tests/test_outline_chapter_workflow_requests.py`：通过。
- `npm run build`：通过。
- `curl -I http://127.0.0.1:5174/worlds`：返回 `200 OK`。

真实性标记：

- API 测试为真实 requests 调用本地 `5006` 服务。
- 前端构建为真实 `npm run build`。
- 未使用 mock、假库或 fixture 作为验收依据。

## 11. 风险与约束

- 大量历史数据迁移前可能缺少 `world_id`、`novel_id`，必须先执行迁移脚本。
- 页面如果一次性展开所有世界的完整树，仍可能造成大数据量压力；后续应支持按节点懒加载。
- 跨集合分页当前以接口级限制为主，后续如需要全局排序分页，需要引入统一聚合查询策略。
- LLM/Embedding 依赖 Ollama 时，运行环境必须保证对应模型可用；缺失模型不允许静默降级。

## 12. 回滚方案

- 数据回滚：通过测试创建数据的唯一名称或 ID 清理测试数据；生产数据删除必须使用显式 `cascade=true`。
- API 回滚：保留旧接口路径，但不得恢复无条件全量查询和假数据回退。
- 前端回滚：可以回退页面展示形态，但不得恢复静态假数据。
- 配置回滚：可恢复到上一版 `config/*.yml`，但必须保留 LLM 与 embedding 的默认项和多配置项结构。

## 13. Release Gate

- 功能正确性：已覆盖世界、世界观、小说、大纲、章节的创建、修改、查询、删除。
- 查询安全性：非世界查询必须条件化和分页化。
- 测试真实性：真实 requests API 测试通过。
- 前端可用性：`/worlds` 可访问，前端构建通过。
- 残余风险：大规模数据下仍建议继续实现节点级懒加载和更细粒度分页。

## Completion Gate

- RCA: not applicable
- Verification: passed
- Evidence: passed
- Rollback: passed
- Final Judgment: 已完成
