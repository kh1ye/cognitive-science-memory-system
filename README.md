# Cognitive Memory System

面向 AI Agent 的认知科学启发式长期记忆系统原型。

## 核心方法

- Melo：闭环记忆生命周期与选择性编码
- AB-Mem：注意力画像与优先级检索
- AxoMem：预测误差和证据门控巩固

## 已实现功能

- Working、Episodic、Semantic、Procedural 四类记忆
- Current、Candidate、History 状态演化
- 单次冲突进入候选区，重复一致证据触发巩固
- 注意力调制检索与历史状态查询
- 隐私写入门、遗忘、物理删除和审计记录
- SQLite 本地持久化
- 可视化 Web 工作台
- LangChain + LangGraph 多轮对话、SQLite 会话恢复与自动长期记忆
- 48 项后端测试 + 11 项前端回归测试

## 快速启动

项目使用 [uv](https://docs.astral.sh/uv/getting-started/installation/) 管理 Python、虚拟环境和依赖。安装 uv 和 Node.js 24 后，在仓库根目录执行（macOS、Linux、Windows 通用）：

```sh
uv sync --locked
npm --prefix frontend ci
npm --prefix frontend run build
uv run python -m api.app --open
```

默认使用 Python 3.12，uv 会在需要时自动下载解释器，并在 `.venv` 中创建隔离环境。核心记忆逻辑仍使用 Python 标准库；Agent 使用 LangChain + LangGraph；HTTP 层使用 FastAPI + Uvicorn，uv 会安装锁定依赖。

浏览器访问：<http://127.0.0.1:8765>

接口文档：<http://127.0.0.1:8765/docs>；OpenAPI：<http://127.0.0.1:8765/openapi.json>。

也可以直接运行 ASGI 服务（在仓库根目录执行）：

```sh
uv run uvicorn api.app:app --host 127.0.0.1 --port 8765
```

开发时可添加 `--reload`。使用 `--db` 自定义数据库或自动打开浏览器时，继续使用 `uv run python -m api.app --db 路径 --open`。

完成前端构建后，Windows 也可以使用 PowerShell 启动脚本：

```powershell
.\scripts\start.ps1 -Open
```

## 前端工作台（Vue 3）

前端使用 Vue 3 单文件组件、Composition API 和 Vue Router，生产构建输出到 `frontend/dist/`，由 FastAPI 提供。开发时运行 `npm --prefix frontend run dev`，访问 5173 端口，API 自动代理到 8765。

左侧导航包含三个页面：系统总览、个人助手、记忆管理。总览使用真实记忆统计和 SQLite 存储数据；个人助手支持 LLM 多轮对话、SQLite 会话恢复、记忆检索和引用；管理中心提供筛选、详情、添加和删除。

个人助手通过 LangChain 调用模型，并用 LangGraph 的 SQLite Checkpointer 恢复同一 `thread_id` 的上下文。自动记忆开关默认开启，每轮从用户明确陈述中提取结构化候选，再交给原有 Memory Engine 决定写入、强化、候选和巩固。仍支持手动保存。详见 [前端说明](frontend/README.md)。

## 本地记忆演化页面

左侧「记忆演化」只需输入一次自然语言并点击「查看记忆全过程」，就会自动提取信息、执行真实写入，并从上到下完整展开原话、提取结果、选择性编码、新旧比较、巩固决策和最终 SQLite JSON。无需填写记忆键、类型或评分参数，也不需要点击下一步或展开详情。

已配置模型时复用现有结构化提取与原文证据校验；没有模型时使用明确标注的有限本地规则，仅识别「我喜欢喝茶。」「我现在更喜欢喝咖啡。」「我喜欢用 Python。」等简单完整偏好句式。本地规则的重要性 0.7、置信度 0.8 为固定默认参数。未识别、无原文依据、隐私拦截或证据不足时如实展示，不生成额外用户证据，不强制走完巩固流程。

`POST /api/evolution/analyze` 接受 `user_id`、`content` 并自动执行完整流程；底层 `POST /api/evolution` 仍支持结构化输入的单次执行追踪。通过请求范围的存储与编码代理采集真实结果，不改变原评分、状态转换及其他页面。完全重复正文直接强化；工作层仍为 SQLite 持久记录。页面展示提交当时的快照，刷新后不保留展示，但实际记忆保留。更新后需重新构建前端并重启后端。

## 配置对话模型

先执行 `uv sync --locked`。在启动后端的终端中配置模型，环境变量或项目根目录 `.env` 变更后重启后端。

macOS / Linux：

```sh
export LLM_MODEL="gpt-4o-mini"
export LLM_API_KEY="你的密钥"
export LLM_BASE_URL="https://api.openai.com/v1"
uv run --locked python -m api.app --open
```

Windows PowerShell：

```powershell
$env:LLM_MODEL = "gpt-4o-mini"
$env:LLM_API_KEY = "你的密钥"
$env:LLM_BASE_URL = "https://api.openai.com/v1"
.\scripts\start.ps1 -Open
```

`LLM_PROVIDER=openai`（默认）使用 OpenAI 兼容的 Chat Completions 服务；`LLM_PROVIDER=anthropic` 使用 Anthropic 兼容服务。自动提取需要模型支持工具调用形式的结构化输出。`LLM_API_KEY` / `LLM_BASE_URL` 未设置时，也读取 `OPENAI_API_KEY` / `OPENAI_BASE_URL`。模型默认 `gpt-4o-mini`。示例见 `.env.example`，程序会自动读取项目根目录的 `.env`，同名 shell 环境变量优先。

未配置密钥时，记忆管理、检索、会话管理仍可使用，聊天返回 503 和配置提示。临时连接或限流错误由 SDK 最多重试一次，持续失败返回 502；自动提取格式失败时会尝试一次 JSON 修复，仍失败则保留已生成的回答并返回警告，用户可手动保存。

### 会话与长期记忆

- **短期会话**：同一用户和 `thread_id` 的对话由 SQLite Checkpointer 保存；重启后恢复。模型每轮读取最多最近 20 条消息，完整记录仍保留在数据库中。
- **长期记忆**：通过现有 `cognitive_memory.Memory.search/add_memory` 读写，同一用户的不同会话共享。Agent 不控制状态转换。
- **数据文件**：默认会话库与记忆库分开，例如 `memory_demo_sessions.db` 与 `memory_demo.db`。可用 `CONVERSATION_DB_PATH` 指定会话库路径；更改会话库路径会切换到另一组会话。
- **提取边界**：只写入可回溯到本轮用户原文的片段，兼容空格、大小写及句末标点差异；没有原话依据时明确显示未写入原因；“不要记住”等指令阻止自动长期记忆提取。敏感候选没有自动保存同意，会由原有隐私门拒写，需手动明确同意。短期会话记录依然持久化；模型会收到所需历史及检索记忆。
- **会话管理**：页面从服务端恢复最近 100 个会话，浏览器仅作缓存。旧版离线聊天保留在本地；继续旧会话时会新建 LLM 会话，旧记录不自动上传。
- **部署范围**：沿用本地单进程部署，聊天与会话操作串行处理。`user_id` 仍是空间标识，不提供身份认证。删除会话清除该会话的检查点和浏览器缓存，保留已写入的长期记忆。

### 聊天 API

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/api/chat` | 输入 `user_id`、`thread_id`、`message`、`auto_remember`；返回回答、引用、记忆写入决策和警告 |
| GET | `/api/chat/status` | 查看模型是否配置及模型名称，不返回密钥 |
| POST | `/api/sessions` | 新建会话，可指定 `thread_id`；不指定则生成 UUID |
| GET | `/api/sessions?user_id=alice` | 恢复最近 100 个会话及记录 |
| GET | `/api/sessions/{thread_id}?user_id=alice` | 获取单个会话 |
| DELETE | `/api/sessions/{thread_id}?user_id=alice` | 删除会话与检查点 |

`/api/chat` 不提供 `thread_id` 时会生成新 ID，连续对话需保留返回的 `thread_id`。例如：

```sh
curl -X POST http://127.0.0.1:8765/api/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id":"alice","thread_id":"my-chat","message":"我主要使用 Python","auto_remember":true}'
curl -X POST http://127.0.0.1:8765/api/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id":"alice","thread_id":"my-chat","message":"我刚才说使用什么？","auto_remember":false}'
```

实现参考官方 [LangGraph 持久化](https://docs.langchain.com/oss/python/langgraph/persistence)、[SQLite Checkpointer](https://reference.langchain.com/python/langgraph.checkpoint.sqlite/SqliteSaver) 与 [ChatOpenAI](https://docs.langchain.com/oss/python/integrations/chat/openai) 文档。

## 演示数据接口

正式服务统一使用名称 `Cognitive Memory System`。默认不注册 `/api/demo/seed`，调用返回 404，接口文档也不展示该路径。正式部署请保持 `COGNITIVE_MEMORY_DEMO_TOKEN` 未设置。

需要演示数据时，先生成随机令牌并通过环境变量 `COGNITIVE_MEMORY_DEMO_TOKEN` 配置到服务进程，再启动服务。启用后每次调用必须携带 `Authorization: Bearer <令牌>`；缺失或错误令牌返回 401。Swagger `/docs` 支持通过 Authorize 输入令牌。

PowerShell 示例（先完成依赖安装和前端构建）：

```powershell
$env:COGNITIVE_MEMORY_DEMO_TOKEN = uv run python -c "import secrets; print(secrets.token_urlsafe(32))"
.\scripts\start.ps1 -Open
```

在另一个终端使用同一令牌调用：

```sh
curl -X POST http://127.0.0.1:8765/api/demo/seed \
  -H "Authorization: Bearer <令牌>" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"demo-sandbox"}'
```

此操作会重置指定用户的记忆和审计记录，仅用于可重置的演示空间。未提供 `user_id` 时仍兼容旧行为，使用 `demo-user`。演示结束后移除环境变量并重启服务，即可关闭接口。

## 运行测试

在仓库根目录执行（后端测试前需先构建前端）：

```sh
npm --prefix frontend test
npm --prefix frontend run build
uv run --locked python -m unittest discover -s tests -v
```

## 依赖管理

```sh
uv add 包名             # 添加运行依赖并更新锁文件
uv add --dev 包名       # 添加开发依赖
uv remove 包名          # 移除依赖
uv lock                 # 修改配置后更新锁文件
uv sync --locked        # 按锁文件同步环境
```

将 `pyproject.toml`、`uv.lock` 和 `.python-version` 一起提交；`.venv` 已被 Git 忽略。

## 项目结构

```text
src/cognitive_memory/   # 可安装的 Python 记忆库
├── memory.py          # 统一入口与写入事务
├── models.py          # 记录与写入结果类型
├── enums.py           # 记忆类型与状态
├── config.py          # 参数配置
├── encoding.py        # 隐私门、分类、选择性编码和注意力画像
├── consolidation.py   # 冲突判断、证据累计和巩固
├── retention.py       # 遗忘和归档
├── retrieval/         # 词法召回与注意力排序
└── storage/           # 存储接口、SQLite 和审计落库
src/conversation_agent/ # 独立 Agent：graph、state、llm、prompts、memory
api/                   # FastAPI 应用、依赖、请求模型与中间件
├── routers/memories.py # 记忆增删查、审计和保留度检查
├── routers/retrieval.py # 检索
├── routers/system.py   # 健康、配置、统计和总览
├── routers/chat.py     # LLM 聊天、会话恢复和删除
└── routers/demo.py     # 默认关闭、令牌保护的演示数据接口
frontend/              # Vue 3 + Vue Router + Vite 三页面工作台
scripts/               # 启动脚本
tests/                 # 自动化测试
```

业务规则通过存储接口读写记录；SQL 仅位于 SQLite 适配层。HTTP 请求通过 Pydantic 模型校验，校验失败保持原有 400 和 `error/message` 格式；数据库操作由同步路由在线程池执行，应用生命周期负责创建和关闭连接。一次写入中的状态变化和审计记录在同一事务内提交，失败时一起回滚。

### Python 调用

```python
from cognitive_memory import Memory

with Memory("memory_product/data/memory_demo.db") as memory:
    memory.add_memory({
        "user_id": "alice",
        "content": "我喜欢 Python",
        "tags": ["preference"],
    })
    result = memory.search("alice", "我喜欢什么？")
    print(result["answer"])
```

核心库可以安装后从任意工作目录导入。HTTP 和前端从仓库根目录启动。数据库格式保持兼容，前端服务默认仍使用 `memory_product/data/memory_demo.db`，已有数据无需搬迁；该目录只保留运行数据。

## 技术文档

[认知长期记忆系统产品技术文档 v1.0](./认知长期记忆系统产品技术文档_v1.0.md)

## 协作方式

小团队日常修改可直接提交到 `main`。推送前同步远程代码，提交前运行相关测试；较大改动或需要同伴审阅时按需使用分支和 Pull Request。
