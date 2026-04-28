# Windows 侧改动说明（本次）

本文档记录了当前 `d:\MyProjects\wo\tabb2` 中，为了让本地 API 网关可稳定运行并与 Tabbit 新接口对齐，所做的主要修改。

## 1) 核心协议对齐（最关键）

文件：`core/tabbit_client.py`

- 上游发送端点由旧的 `/chat/send` 调整为：
  - `POST /api/v1/chat/completion`
- 请求体字段补齐为浏览器抓包一致结构，包含：
  - `chat_session_id`
  - `message_id`
  - `content`
  - `selected_model`
  - `parallel_group_id`
  - `task_name`
  - `agent_mode`
  - `metadatas`
  - `references`
  - `entity`
- 请求头补齐并动态生成关键参数：
  - `x-nonce`
  - `x-signature`
  - `x-timestamp`
  - `trace-id`
  - `unique-uuid`
  - `x-req-ctx`
- 请求头中的浏览器标识同步到新版本（Chrome/Tabbit 146 风格）。
- Cookie 侧增加 `SAPISID`（与 `user_id` 对齐）。
- SSE 解析增强：兼容仅有 `data:`、没有 `event:` 的分片流格式，减少“有返回但被解析器吞掉”的情况。

## 2) 配置项扩展

文件：`core/config.py`

- `tabbit` 配置新增：
  - `req_ctx`（默认值：`MC4yOS40OSgxMDAyOTQ5KQ==`）
- 用于统一传递到请求头 `x-req-ctx`。

## 3) 配置在各路由与管理器中贯通

文件：
- `core/token_manager.py`
- `routes/openai_compat.py`
- `routes/claude_api.py`
- `routes/admin_api.py`

改动：
- `TabbitClient` 构造统一增加 `req_ctx` 参数注入，确保：
  - Token 轮询路径
  - OpenAI 兼容 fallback 路径
  - Claude 兼容 fallback 路径
  - Admin 的 token 测试路径
  都能使用同一套新协议上下文。

## 4) 错误可见性增强

文件：`routes/openai_compat.py`

- 对上游流式返回中的 `event=error` 显式处理，不再静默吞掉，改为直接抛出网关错误并返回给调用方。
- 非流式路径同样增加该处理，避免出现“HTTP 200 但内容空白、且无明确错误原因”的现象。

## 5) 管理页模型列表改为后端驱动

文件：
- `routes/admin_api.py`
- `static/index.html`

改动：
- `/api/admin/settings` 响应增加 `available_models`。
- 前端模型下拉框不再写死，改为使用 `available_models` 动态渲染。
- 新增模型映射后，管理页无需再次手动改前端常量。

## 6) Windows / WSL 启动与测试辅助

新增或调整：
- `scripts/run_windows.ps1`
- `scripts/run_wsl.sh`
- `start.ps1`
- `start.sh`
- `RUN_GUIDE.md`
- `test_api_windows.ps1`

用途：
- 一键启动（含 venv 与依赖安装流程）
- 可指定端口（Windows 默认已调整为 `9900`）
- API 冒烟测试脚本（模型、聊天、token 计数）

## 7) 结果

在 Windows 本机环境验证：

- `GET /v1/models` 正常
- `POST /v1/chat/completions` 返回 `200`
- `choices[0].message.content` 为非空
- `POST /v1/messages/count_tokens` 正常

---

如果后续要继续适配上游协议变动，建议优先维护：

- `core/tabbit_client.py`（请求结构、头、SSE 解析）
- `core/config.py`（可配置化字段）
- `routes/openai_compat.py`（错误透传策略）
