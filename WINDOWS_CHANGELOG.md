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

### 1.1) 如何从新 cURL 反推出修改点（字段对照）

以下对照用于说明：为什么看到那条新请求后，需要做当前这批代码改动。

| 抓包里观察到的字段/行为 | 代码中的对应修改 |
|---|---|
| `POST https://web.tabbitbrowser.com/api/v1/chat/completion` | `core/tabbit_client.py` 中 `send_message()` 的上游路径从 `/chat/send` 切换到 `/api/v1/chat/completion` |
| `Accept: text/event-stream` + 持续返回流分片 | `send_message()` 保持流式请求，并增强 SSE 解析逻辑，兼容仅有 `data:` 的返回格式 |
| 请求头包含 `x-nonce`、`x-signature`、`x-timestamp`、`trace-id`、`unique-uuid`、`x-req-ctx` | 新增 `_build_chat_headers()` 动态生成这些头；`x-req-ctx` 从配置项读取 |
| 请求头里的 `User-Agent` / `sec-ch-ua` 已是 146 版本风格 | `_get_headers()` 同步更新浏览器标识版本，降低与真实客户端特征偏差 |
| Cookie 中含 `token`、`user_id`、`managed`、`NEXT_LOCALE`、`SAPISID` | `_get_cookies()` 中补充 `SAPISID`，并保留已有关键 cookie |
| 请求体包含 `message_id`、`parallel_group_id`、`task_name`、`references` | `send_message()` 的 payload 补齐对应字段，避免上游校验失败或行为退化 |
| 上游会通过流事件/数据表达错误 | `routes/openai_compat.py` 对 `event=error` 增加显式抛错，避免“200 但内容空” |

此外，`x-req-ctx` 需要在不同调用路径可复用，因此新增了配置项并贯通到：

- `core/token_manager.py`（轮询 token 客户端）
- `routes/openai_compat.py`（OpenAI fallback）
- `routes/claude_api.py`（Claude fallback）
- `routes/admin_api.py`（token 测试）

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

## 8) Bug 修复批次（第 1 批）

本批次优先处理可用性、并发安全和明显边界问题。

### 8.1 已修复项

- `routes/openai_compat.py`
  - 修复流式上游错误处理：不再直接抛异常中断流，改为输出错误块并补发 `[DONE]`，避免客户端无限等待。
  - 修复 `_build_content` 单条消息分支：仅当角色是 `user` 时走直通，避免 `system` 角色语义丢失。
- `core/token_manager.py`
  - `report_success` / `report_error` 改为异步并纳入统一锁，避免并发竞态更新。
  - 引入脏标记 + 最小间隔落盘（异步 `to_thread`），降低每请求同步写盘对事件循环的阻塞。
  - `remove_client` 改为异步并显式 `aclose()`，修复连接池泄漏风险。
  - 增加可用 token 短时缓存，缓解高并发下全量扫描的锁内开销。
- `routes/admin_api.py`
  - 更新/删除 token 时改为 `await _tm.remove_client(...)`，确保旧 client 被释放。
- `routes/claude_api.py`
  - 非流式分支补充 `error` 事件处理，避免“空内容 + 200”假成功。
  - 流式解析从“每字符取事件”改为“整块喂入后取事件”，减少解释器调用开销。
- `core/tabbit_client.py`
  - 修复 JWT payload 解码 padding：改为按长度动态补齐 `=`。
- `core/claude_compat.py`
  - 修复 thinking 结束标签检测时序（在同次字符输入内完成关闭判定）。
  - 修复 thinking 开始标签前缀切片边界，避免前置文本丢/重。
  - 无工具模式 flush 阈值从 `256` 调整到 `128`（折中：事件频率与包体积）。
  - 新增 `feed_text()` 供调用方按文本块喂入。

### 8.2 本批次验证

- 语法检查：`python -m py_compile` 通过（涉及文件全部可编译）。
- 行为检查：`scripts/verify_batch1.py` 通过，覆盖以下关键点：
  - JWT padding 解码兼容；
  - parser flush 阈值生效；
  - thinking 起止标签解析不滞后；
  - OpenAI 流式错误路径输出 error 块并收尾 `[DONE]`。
- 基础接口检查：`GET /v1/models`、`POST /v1/messages/count_tokens` 返回 `200`。

### 8.3 性能记录（可复现的本地对比）

在相同输入下，对 `ToolifyParser` 进行调用方式对比（5 次平均）：

- 旧调用模式（逐字符喂入 + 每字符 consume）：`49.8 ms`
- 新调用模式（整块喂入 + 分批 consume）：`40.5 ms`
- 提升：约 `1.23x`

> 说明：受上游 Tabbit 会话可用性影响，端到端聊天延迟本批次未做稳定对比，仅保留可复现的本地解析性能对比。

---

如果后续要继续适配上游协议变动，建议优先维护：

- `core/tabbit_client.py`（请求结构、头、SSE 解析）
- `core/config.py`（可配置化字段）
- `routes/openai_compat.py`（错误透传策略）
