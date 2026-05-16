# 调度中心外部接入说明

调度中心用于接收外部任务请求，自动判断应交给哪个层级 Agent，并复用现有 `/api/hierarchy-agent/*` 工作流执行。它不会绕过 Agent 审查；默认启动后停在人工确认节点，只有调用方显式设置 `auto_approve=true` 且工作流已进入 `waiting_human` 时，才会自动批准写库。

## 能力查询

```bash
curl -s http://127.0.0.1:5006/api/router/agents
```

返回所有可调度 Agent、必需上下文和可处理字段：

- `world`：世界
- `worldview`：世界观
- `novel`：小说
- `outline`：大纲
- `chapter`：章节

## 提交调度

```bash
curl -s -X POST http://127.0.0.1:5006/api/router/dispatch \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: <api_key>' \
  -d '{
    "source": "external-system",
    "external_request_id": "ticket-1001",
    "external_task_ref": "ztx_taskref_abc123",
    "message": "新增一个低魔蒸汽群岛世界观",
    "payload": {
      "world_id": "world_default",
      "name": "低魔蒸汽群岛",
      "summary": "潮汐水晶供能，灯塔公会管理航线。"
    }
  }'
```

常用请求字段：

- `agent_type`：可选；显式指定 `world/worldview/novel/outline/chapter`。不传时根据 `message` 和 `payload` 推断。
- `action`：可选；`create` 或 `update`。不传时，有目标 ID 会推断为 `update`，否则默认为 `create`。
- `message` / `task` / `prompt`：任务描述。
- `payload`：业务字段和上下文。
- `dry_run`：可选；`true` 表示只返回调度计划，不启动 Agent。
- `auto_approve`：可选；`true` 表示在 Agent 进入人工确认后自动批准写库。
- `source`：可选；外部系统来源标识。
- `external_request_id`：可选；外部请求 ID，便于回查。
- `external_task_ref` / `task_ref`：可选；外部可见任务单号。对接 Zentex 时应传 `external_task_ref`，调度中心会原样保存并在响应、查询中回传。
- `invocation`：可选；兼容 Zentex invocation 上下文，可从 `invocation.external_task_ref`、`invocation.task_ref`、`invocation.zentex_task_id`、`invocation.callback_url` 读取并保存。

返回内容包含：

- `dispatch.dispatch_id`：调度记录 ID。
- `task_ref` / `external_task_ref`：如果请求传入了外部任务单号，响应会原样回传。
- `route.agent_type`：实际分配到的 Agent。
- `route.action`：实际动作。
- `run.run_id`：启动的 Agent 工作流 ID。
- `run.status`：工作流状态，例如 `waiting_human`、`review_failed`、`completed`。

## Zentex 对接示例

本项目可作为 Zentex 外部 Agent 能力源接入。推荐使用 Zentex 协议中的 `http_json` adapter 和 `api_key` auth_config，不要求 Zentex 实现本项目登录流程。

先在本项目中注册或登录用户，取得返回的 `api_key`，再通过 Zentex 凭据接口保存为 `credential_ref`。调用时注入：

```json
{
  "auth_config": {
    "type": "api_key",
    "credential_ref": "novel-agent-api-key",
    "inject": {
      "headers": {
        "X-API-Key": "$auth.api_key"
      }
    }
  }
}
```

最小注册配置示例：

```json
{
  "name": "novel-agent-router",
  "agent_name": "Novel Agent Router",
  "version": "1.0.0",
  "function_description": "Route world, worldview, novel, outline and chapter create/update tasks to the right Novel Agent workflow.",
  "endpoint": "http://127.0.0.1:5006",
  "role_tag": "writing",
  "scope": ["world.create", "worldview.create", "novel.create", "outline.create", "chapter.create", "chapter.update"],
  "adapter_type": "http_json",
  "service_hooks": ["invoke", "result_view"],
  "auth_config": {
    "type": "api_key",
    "credential_ref": "novel-agent-api-key",
    "inject": {
      "headers": {
        "X-API-Key": "$auth.api_key"
      }
    }
  },
  "adapter_config": {
    "method": "POST",
    "path": "/api/router/dispatch",
    "body_template": {
      "source": "zentex",
      "external_task_ref": "$invocation.external_task_ref",
      "zentex_task_id": "$invocation.zentex_task_id",
      "callback_url": "$invocation.callback_url",
      "message": "$payload.prompt",
      "payload": "$payload",
      "auto_approve": false
    },
    "response_mapping": {
      "status": "$response.dispatch.status",
      "task_ref": "$response.task_ref",
      "dispatch_id": "$response.dispatch.dispatch_id",
      "run_id": "$response.run.run_id",
      "agent_type": "$response.route.agent_type",
      "action": "$response.route.action"
    }
  }
}
```

Zentex `result_view` 可用 `GET /api/router/dispatch/get?task_ref=<external_task_ref>` 重新读取调度与工作流状态。

## 只做路由预判

```bash
curl -s -X POST http://127.0.0.1:5006/api/router/dispatch \
  -H 'Content-Type: application/json' \
  -d '{
    "dry_run": true,
    "message": "修改章节正文",
    "payload": {
      "outline_id": "outline_123",
      "target_id": "chapter_123",
      "name": "第一章 修订",
      "content": "修订后的章节正文。"
    }
  }'
```

## 修改请求示例

```bash
curl -s -X POST http://127.0.0.1:5006/api/router/dispatch \
  -H 'Content-Type: application/json' \
  -d '{
    "agent_type": "chapter",
    "action": "update",
    "message": "修改章节正文，保持大纲约束",
    "payload": {
      "target_id": "chapter_123",
      "outline_id": "outline_123",
      "name": "第一章 修订",
      "content": "修订后的章节正文。"
    }
  }'
```

## 自动批准示例

```bash
curl -s -X POST http://127.0.0.1:5006/api/router/dispatch \
  -H 'Content-Type: application/json' \
  -d '{
    "agent_type": "world",
    "action": "create",
    "auto_approve": true,
    "message": "创建测试世界",
    "payload": {
      "name": "测试世界",
      "summary": "供自动化联调使用。"
    }
  }'
```

## 查询调度记录

按调度 ID 查询：

```bash
curl -s 'http://127.0.0.1:5006/api/router/dispatch/get?dispatch_id=dispatch_xxx'
```

按 Zentex 外部任务号查询：

```bash
curl -s 'http://127.0.0.1:5006/api/router/dispatch/get?task_ref=ztx_taskref_abc123'
```

按条件查询列表：

```bash
curl -s 'http://127.0.0.1:5006/api/router/dispatch/list?agent_type=chapter&page=1&page_size=20'
```

支持的列表过滤条件：

- `dispatch_id`
- `run_id`
- `status`
- `source`
- `external_request_id`
- `external_task_ref`
- `agent_type`
- `action`
