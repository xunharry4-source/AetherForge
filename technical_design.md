# Technical Design Document: Worldview & Novel Agent

[English Version](./technical_design.md) | [中文版](./technical_design_ZH.md)

## 1. Role: Workflow Architect

As a **Workflow Architect**, the design of this system prioritizes **Stability**, **Scalability**, and **Self-correction (Self-healing)**. The architecture utilizes a state-machine approach implemented via LangGraph to manage complex interactions between AI generators, logical auditors, and human overseers.

### Core Principles

* **State Management**: Using `TypedDict` for data consistency across nodes.
* **Logic Closure**: Implementing "审核-退回-重写" (Audit-Reject-Rewrite) loops to maintain high output quality.
* **Human-in-the-loop**: Explicitly defined human intervention points for critical decisions.
* **Database Synchronization**: Multi-dataset transactionality ensuring MongoDB and ChromaDB remain in sync.

---

## 2. State Management (`AgentState`)

The `AgentState` is the backbone of the workflow, tracking the query, context, current proposal, and audit history.

```python
class AgentState(TypedDict):
    query: str
    worldview_id: str      # Associated creative universe (Top level)
    outline_id: str        # Associated project/novel ID (Child of worldview)
    context: str
    proposal: str
    review_log: str
    user_feedback: str
    iterations: int        # Counter for total generation attempts
    audit_count: int       # Counter for self-audit retries
    is_approved: bool      # Signal from reviewer or human
    category: str 
    doc_id: str
    status_message: str    # Real-time execution status
```

---

## 3. LangGraph Workflow Definition

The system consists of 4 primary functional nodes:

1. **`generator` (The Creator)**: Uses LLM to produce or refine a "Proposal" based on the user's query and RAG context.
2. **`reviewer` (The Logical Auditor)**: Performs a zero-cheating, logic-based audit against the **0-4 Architecture** and **Highest Prohibitions**.
3. **`human` (Human Gate)**: Presents the audit results and proposal to the user for feedback or final approval.
4. **`saver` (Sync Committer)**: Executes the final "transactional" write to the databases.

### Execution Flow (DAG/State Machine)

* **Entry Point**: `generator`
* **Primary Loop**: `generator` -> `reviewer` -> (Conditional: `fail` -> `generator`, `pass` -> `human`)
* **Final Phase**: `human` -> (Conditional: `retry` -> `generator`, `approve` -> `saver`) -> `END`

---

## 4. Logical Consistency & Self-correction

The `reviewer` node is designed for **Self-correction**. If the logical auditor identifies a violation of the 0-4 architecture (e.g., an unauthorized time-control element), it provides a detailed `audit_log` which is fed back into the `generator` for a forced rewrite.

> [!NOTE]
> The loop is capped at 3 iterations to prevent infinite recursion, after which it reverts to human intervention.

---

## 5. Hierarchical Data Synchronization & Isolation

The system implements a three-tier hierarchy: **Worldview** -> **Novel Outline** -> **Novel Chapter**. This architecture ensures creative isolation between independent universes while enabling shared world-building foundations.

### 5.1 Directory-Based Hierarchy

All persistent data is strictly partitioned. A worldview acts as a container for multiple novel projects:

* **Top Level**: `data/worldviews/{worldview_id}/`
* **Worldview Lore**: `data/worldviews/{worldview_id}/worldview_db.json` (Namespaced JSONL)
* **Novel Projects**: `data/worldviews/{worldview_id}/outlines/{outline_id}/`
* **Project Specifics**:
  * **Prose Archive**: `data/worldviews/{worldview_id}/outlines/{outline_id}/prose_db.json`
  * **Entity Drafts**: `data/worldviews/{worldview_id}/outlines/{outline_id}/entity_drafts_db.json`

### 5.2 Global Registries

Central registries maintain the metadata for the hierarchy:

* **Worldview Registry**: `data/worldviews_registry.json`
* **Novel Registry**: `data/outlines_db.json` (Mapped to `worldview_id`)

### 5.3 Vector Store Namespacing (Hierarchical RAG)

ChromaDB collections are namespaced to support layered retrieval:

* **Worldview Collection**: `pga_wv_{worldview_id}` - Contains stable world-building knowledge.
* **Prose Collection**: `pga_prose_{outline_id}` - Contains the narrative history of a specific novel.
* **Isolation**: Agents retrieve context from the specific worldview they belong to, ensuring no cross-contamination between different universes.

### 5.4 Context Propagation

* **Agent State**: `AgentState` includes both `worldview_id` and `outline_id`.
* **API Endpoints**: All lore, agent, and archive APIs propagate the hierarchical context to ensure deterministic file and vector resolution.
* **Dual-Write Consistency**: The `saver` nodes translate the `AgentState` into both local file persistence and vector index updates within the correct namespace.

---

### 5.3 Semantic Search Architecture

To overcome the limitations of keyword-based filtering, the system introduces vector-based semantic search:

* **Backend Core**: The `/api/search` endpoint in `app_api.py` leverages ChromaDB for similarity retrieval, returning standardized JSON with `id` and `type` fields.
* **Frontend Toggle**: A "Semantic Search" toggle in the Lore DB UI enables asynchronous backend queries, allowing deep intent-based retrieval across hierarchical layers.

---

## 6. Novel Outline Agent (The Second Workflow)

The Novel Outline Agent follows a similar 0-4 architecture but focuses on narrative structure.

### JSON Schema Enforcement

The outline agent is strictly bound to a professional novel outline schema:

* **`meta_info`**: Metadata (Genre, Tone, Target Audience).
* **`core_hook`**: Logline and inciting incidents.
* **`character_roster`**: Roles and motivations.
* **`plot_beats`**: High-level pacing (Act 1, Midpoint, Climax).
* **Human-in-the-loop (HITL) Workflow**:
  * **Async Streaming**: The UI uses `httpx.stream` to listen to real-time Node updates from the Agent Graph.
  * **Interrupt & Resume**: Utilizing LangGraph's `interrupt`, the Agent pauses after drafting. The UI then resumes the flow by sending a `Command(resume=...)` based on user feedback.

### Multi-Agent Orchestration

The `app_api.py` acts as a router, selecting between `worldview_app` and `outline_app` based on the `agent_type` flag sent by the dashboard.

---

## 7. Chapters & Prose Management

The system treats chapter generation as a multi-stage process involving AI generation, logical auditing, and human refinement.

### 7.1 Namespace Preservation

Prose chapters are strictly stored within the project's namespace to ensure creative isolation:

* **Storage Path**: `data/worldviews/{worldview_id}/outlines/{outline_id}/prose_db.json`
* **Metadata**: Each entry includes `scene_id`, `scene_title`, `content`, and a `timestamp`.

### 7.2 Human-in-the-loop (HITL) Editor

The Chapter Management UI (`ui/pages/chapters.py`) provides a dedicated interface for:

* **Project Filtering**: Viewing all generated chapters for a specific novel.
* **Manual Refinement**: Direct editing of the LLM-generated prose to fix stylistic issues or narrative drift.
* **Versioning through Persistence**: Edits are saved back to the namespaced JSONL, ensuring the project's "Ground Truth" remains updated for future RAG retrievals.

### 7.3 Integration with Writing Agent

The `prose_saver` node in the `Writing Agent` graph executes the initial commit to the namespaced database after human approval or after passing the logical audit.

---

## 8. Observability & Monitoring (观测与监控)

To ensure the stability and traceability of the Multi-Agent system, a comprehensive observability stack is integrated:

1. **Sentry (Error Tracking)**: Captures backend exceptions and performance data in real-time.
2. **LangFuse (LLM Tracing)**: Traces every step of the LangGraph execution, providing a detailed view of prompt history, completion tokens, and transition latency.
3. **Prometheus (Metrics)**: Exposes a `/metrics` endpoint to collect time-series data, including HTTP latencies and custom business metrics.
4. **Grafana (Visualization)**: Provides a centralized dashboard for visualizing system health and LLM usage patterns.
5. **Atomic Logs**: Real-time, granular sub-step logging within long-running Agent nodes (covering **Writing, Worldview, Outline, Import, and Router** workflows) to ensure maximum transparency.

### Custom Metrics

* **`llm_token_usage_total`**: A counter that tracks token consumption across different agents (worldview, outline, router) and models.

---

## 9. Project Files Mapping

| Component | Responsibility | Relevant Files | Status |
| :--- | :--- | :--- | :--- |
| **Logic Engine (Worldview)** | Graph execution & state flow, supports hierarchy | `worldview_agent_langgraph.py` | ✅ Optimized |
| **Logic Engine (Outline)** | Novel outline generation graph, defines project key | `novel_outline_agent_langgraph.py` | ✅ Optimized |
| **Worldview Import Agent** | Doc parsing & namespaced categorization | `worldview_import_agent.py` | ✅ Optimized |
| **Dispatcher/Router Agent** | Intent classification & project context routing | `router_agent_langgraph.py` | ✅ Optimized |
| **Writing Agent** | Prose generation with hierarchical RAG | `writing_execution_agent_langgraph.py` | ✅ Optimized |
| **LLM Configuration** | Fallback and per-agent model management | `llm_factory.py`, `config_utils.py` | ✅ Implemented |
| **API Router & Metrics** | Namespaced request handling & persistence | `app_api.py` | ✅ Optimized |
| **Web Dashboard** | Multi-novel selection & project-scoped UI | `dashboard.html` | ✅ Implemented |
| **Architectural Rules**| 0-4 Architecture Definitions | `info.md`, `novel_outline_info.md` | ✅ Defined |
| **Vector Index** | Hierarchical ChromaDB collections | `./chroma_db/` | ✅ Implemented |
| **Distributed Storage** | Isolated Worldview & Outline databases | `./data/worldviews/` | ✅ Implemented |

---

## 10. Development Protocol (开发协议)

> [!IMPORTANT]
> **Documentation First (文档先行):**
> Before adding any new feature or UI page, the following steps **MUST** be performed:
> 1. **Update Technical Documentation**: Explicitly describe the purpose of the new feature/page in `technical_design.md`.
> 2. **Impact Analysis**: Document the downstream effects on existing state, databases, or Agent logic.
> 3. **Functional Decomposition**: Break down the feature into atomic tasks (UI, API, Data, Verification).
