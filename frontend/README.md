# 记忆工作台前端（Vue 3）

采用 Vue 3 Composition API、Vue Router 和 Vite。三个页面使用单文件组件，界面风格和记忆操作沿用原版本，会话改为服务端 SQLite 持久化；个人助手不显示额外的顶部标题区域。

## 环境

推荐 Node.js 24（版本记录在 `.node-version`），npm 10 或更新版本。也支持 Node.js 22.12+；不使用已停止维护的 Node.js 23。

依赖通过 `package.json` 和 `package-lock.json` 管理。初次安装或锁文件变化时执行 `npm ci`。

## 构建后使用 FastAPI

在仓库根目录执行：

```sh
npm --prefix frontend ci
npm --prefix frontend run build
uv sync --locked
uv run python -m api.app --open
```

访问 <http://127.0.0.1:8765>。FastAPI 提供 `frontend/dist/` 中的构建产物；源码和浏览器运行均无需外部 CDN。

`dist/` 不提交到 Git，其他协作者拉取代码后需要构建。未构建时，首页返回 503 和构建提示，API 与 `/docs` 仍可用。

## 前后端分离开发

终端一（仓库根目录）：

```sh
uv run python -m api.app
```

终端二（仓库根目录）：

```sh
npm --prefix frontend run dev
```

打开 <http://127.0.0.1:5173>。Vite 将 `/api`、`/docs`、`/openapi.json` 代理到本地 8765 端口，组件修改支持热更新。

服务端会话按用户恢复，因此 5173 和 8765 可读取同一后端的会话。浏览器缓存仍按来源隔离。旧版离线记录保留在本地，继续旧记录会新建 LLM 会话，旧消息不自动上传。

## 页面和能力

- `/#/overview`：记忆统计、类型/状态分布、最近活动、SQLite 存储与模块配置。
- `/#/assistant`：新建/切换会话、记忆检索、证据引用、手动保存消息。Enter 发送，Shift+Enter 换行。
- `/#/memories`：类型/状态/关键词筛选、分页、详情、添加/删除和保留度检查。

旧链接 `/#overview`、`/#assistant`、`/#memories` 会自动转换成 Vue Router 地址。

助手调用 `/api/chat`，通过 LangChain + LangGraph 生成连续多轮回答。会话历史按用户和 `thread_id` 保存在服务端 SQLite，页面加载和切换用户时恢复最近 100 个会话，浏览器 `localStorage` 仅用于缓存和兼容旧版记录。

输入区支持切换“自动记忆”：开启时从本轮用户原文提取候选并交给现有 Memory Engine 处理；关闭后仍保存短期会话。敏感候选必须通过手动表单明确同意保存，助手回答下显示自动记忆决策与处理警告。删除会话同时删除服务端检查点和浏览器缓存，保留长期记忆。

模型配置、环境变量及 API 见根目录 README。未配置模型时，聊天显示配置提示，其他记忆管理功能继续可用。用户空间切换仍不提供身份认证。

总览的记忆统计属于当前用户；存储字节数属于整个数据库，含 WAL。管理页最多加载最近 1000 条，超出时明确显示加载范围。

## 目录

```text
frontend/
├── index.html
├── package.json
├── package-lock.json
├── vite.config.js         # Vue 插件、开发代理与测试配置
└── src/
    ├── main.js
    ├── App.vue            # 导航与全局弹窗
    ├── router.js
    ├── styles.css
    ├── components/        # 图标、原生 dialog、记忆表单
    ├── views/             # 总览、助手和记忆管理
    ├── composables/       # 响应式状态、会话持久化和业务操作
    ├── lib/               # HTTP 客户端、展示常量和格式化
    └── __tests__/         # Vue 组件与状态回归测试
```

## 验证

```sh
npm --prefix frontend test
npm --prefix frontend run build
uv run --locked python -m unittest discover -s tests -v
```

前端测试覆盖旧会话兼容、用户切换时的过期请求、SQLite 会话恢复、thread_id 连续发送、服务端会话删除、消息响应式更新与引用、安全文本渲染、筛选、请求失败恢复和隐私拒写。后端测试需要先构建前端，以验证实际打包资源。

演示接口 `/api/demo/seed` 默认关闭。设置 `COGNITIVE_MEMORY_DEMO_TOKEN` 并重启后启用，调用必须携带匹配的 Bearer 令牌。演示数据在 `api/seed.py`，界面不自动调用；手动调用会重置指定用户的记忆和审计记录。配置示例见根目录 README。
