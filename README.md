# Novel Agent (万象星际：AI 小说全链路创作引擎)

> 本项目是一个基于 **LangGraph** 和 **Gemini** 驱动的专业小说创作与世界观管理系统。它通过 RAG（检索增强生成）和人机协作（Human-in-the-loop）将复杂的创作过程拆解为可管理的 Agent 流程，确保创作内容在长篇叙事中的高度一致性与逻辑严密性。

## 🌌 核心理念：结构化创作流程

系统将小说创作拆分为三个核心 Agent 阶段：

1. **世界观设定**：通过结构化模板定义种族、文明、技术、地理等底座设定。
2. **大纲规划**：基于世界观设定生成具有戏剧张力的剧情大纲与节奏控制。
3. **正文执行**：将大纲细化为具体场次，并生成带有“逻辑快照”的正文初稿。

---

## ✨ 主要功能

### 1. 世界观 Agent (Worldview Agent)

- **多维度设定**：支持 种族、势力、地理、机制、历史 等多维度设定。
- **模板化管理**：内置可视化模板 CRUD，支持手动编辑与 AI 自动补全。
- **逻辑审查**：内置 Reviewer 节点，自动检测新设定与已有文献库之间的逻辑冲突。

### 2. 小说大纲 Agent (Novel Outline Agent)

- **剧情节拍生成**：自动生成包含 序幕、发展、高潮、终局 的标准剧情节奏。
- **冲突挖掘**：自动分析设定中的核心冲突点，转化为故事张力。

### 3. 正文执行 Agent (Writing Execution Agent)

- **场次拆解**：自动将大纲拆分为具体的写作场次（Scene Index）。
- **逻辑快照**：每场写作都会生成“人物状态”与“场景环境”逻辑快照，解决“写着写着设定崩了”的痛点。
- **视觉模拟**：支持生成场次的视觉快照描述，辅助创作者进行画面脑补。

### 4. 万象仪表盘 (Omni-Dashboard)

- **可视化工作流**：直观展示 Agent 的思考与执行过程。
- **人机协同**：支持在关键节点拦截任务，由作者输入反馈或批准提案。
- **文献档案库**：统一检索存储在 MongoDB 与 ChromaDB 中的历史设定，支持语义搜索。

---

## 📸 视觉演示

### 文献档案库 (Lore Library)

![Lore Library](./docs/images/lore_library.png)

### 设定模板管理 (Template Management)

![Template Management](./docs/images/template_mgmt.png)

### Agent 创作工作区 (Writing Workspace)

![Writing Workspace](./docs/images/workspace.png)

### 系统演示 (录屏)

![System Demo](./docs/images/demo.webp)

---

## 🛠️ 快速开始

### 1. 安装依赖

```bash
pip install flask pymongo chromadb langchain-google-genai langgraph
```

### 2. 配置环境

在 `config.json` 中配置你的 Google AI API Keys：

```json
{
    "GOOGLE_API_KEYS": ["你的_API_KEY_1", "你的_API_KEY_2"],
    "DEFAULT_MODEL": "gemini-2.0-flash"
}
```

### 3. 运行服务

```bash
python app_api.py
```

访问 `http://127.0.0.1:5005` 即可打开可视化仪表盘。

---

## ⚙️ 核心开发原则

- **最小改动原则**：所有更新通过局部注入实现，确保不影响核心逻辑。
- **功能性验证**：所有代码修改后必须经过端到端功能测试。
- **双库事务性**：所有已批准设定同步更新 MongoDB（全文）和 ChromaDB（向量）。
