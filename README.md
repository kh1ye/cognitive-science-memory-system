# Cognitive Science Memory System

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
- 可视化 Web 演示页面
- 29 项后端测试 + 7 项前端回归测试

## 快速启动

项目使用 [uv](https://docs.astral.sh/uv/getting-started/installation/) 管理 Python、虚拟环境和依赖。安装 uv 和 Node.js 24 后，在仓库根目录执行（macOS、Linux、Windows 通用）：

```sh
uv sync --locked
npm --prefix frontend ci
npm --prefix frontend run build
uv run python -m api.app --open
```

默认使用 Python 3.12，uv 会在需要时自动下载解释器，并在 `.venv` 中创建隔离环境。核心记忆逻辑仍使用 Python 标准库；HTTP 层使用 FastAPI + Uvicorn，uv 会安装锁定依赖。

浏览器访问：<http://127.0.0.1:8765>

接口文档：<http://127.0.0.1:8765/docs>；OpenAPI：<http://127.0.0.1:8765/openapi.json>。

也可以直接运行 ASGI 服务（在仓库根目录执行）：

```sh
uv run uvicorn api.app:app --host 127.0.0.1 --port 8765
```

开发时可添加 `--reload`。使用 `--db` 自定义数据库或自动打开浏览器时，继续使用 `uv run python -m api.app --db 路径 --open`。

完成前端构建后，Windows 也可以使用 PowerShell 启动脚本：

```powershell
.\scripts\start_demo.ps1 -Open
```

## 前端工作台（Vue 3）

前端使用 Vue 3 单文件组件、Composition API 和 Vue Router，生产构建输出到 `frontend/dist/`，由 FastAPI 提供。开发时运行 `npm --prefix frontend run dev`，访问 5173 端口，API 自动代理到 8765。

左侧导航包含三个页面：系统总览、个人助手、记忆管理。总览使用真实记忆统计和 SQLite 存储数据；个人助手支持浏览器本地会话、记忆检索和引用；管理中心提供筛选、详情、添加和删除。

当前助手尚未接入大模型，回答来自已有记忆的检索与证据整理。聊天内容不会自动写入记忆，可手动保存。详见 [前端说明](frontend/README.md)。

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
api/                   # FastAPI 应用、请求模型与请求中间件
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
