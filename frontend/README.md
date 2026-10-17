# 记忆工作台前端

`frontend/static/` 是无需构建、无需 CDN 的原生 HTML/CSS/JavaScript 界面，由 FastAPI 提供静态资源。

## 启动

在仓库根目录执行：

```sh
uv sync --locked
uv run python -m api.app --open
```

打开 <http://127.0.0.1:8765>。

## 页面

- 系统总览 `/#overview`：记忆数量、类型和状态分布、最近审计活动、SQLite 存储、核心模块配置。
- 个人助手 `/#assistant`：创建和切换会话、查询个人记忆、查看引用，支持手动将消息保存为记忆。Enter 发送，Shift+Enter 换行。
- 记忆管理 `/#memories`：类型/状态/关键词筛选、分页、详情、手动添加、删除和保留度检查。

助手目前采用离线词法检索和证据整理，尚未接入 LLM。会话按用户保存在当前浏览器的 localStorage，聊天内容不会自动写入 SQLite；用户可明确选择“保存为记忆”。用户空间切换不提供身份认证。

总览的类型、状态和数量属于当前用户；存储字节数属于整个数据库（包括 WAL 日志）。管理页最多加载最近 1000 条，超出时页脚明确提示加载范围。

## 文件

```text
frontend/static/index.html # 三个页面和表单
frontend/static/styles.css # 样式与响应式布局
frontend/static/app.js     # 导航、数据绑定、会话与记忆操作
api/seed.py                # 保留旧演示接口的测试数据
```

`/api/demo/seed` 为兼容保留，会重置指定用户的记忆；界面不自动调用此接口，不会初始化或覆盖已有记忆。
