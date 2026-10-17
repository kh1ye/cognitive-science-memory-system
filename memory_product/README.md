# Cognitive Memory Lab - 本地演示产品

这是一个无需云端 API、Docker 或第三方 Python 包的认知长期记忆系统 MVP。它把以下机制串成一个真实可运行的闭环：

- 选择性编码：低价值信息只进入工作记忆，敏感信息默认拒绝持久化。
- 四类记忆：Working、Episodic、Semantic、Procedural。
- 状态角色：Current、Candidate、History、Archived。
- 证据门控巩固：单次冲突不覆盖稳定记忆，重复一致证据才提交更新。
- 注意力调制检索：基础相关度乘以持久注意力偏置、动态上下文匹配和角色因子。
- 保留度、物理删除与审计：支持遗忘检查、用户删除和全链路事件记录。

## 启动

安装 [uv](https://docs.astral.sh/uv/getting-started/installation/)，在仓库根目录执行：

```sh
uv sync --locked
uv run memory_product/app.py --open
```

Windows PowerShell 也可执行：

```powershell
.\memory_product\start_demo.ps1 -Open
```

成功信号：终端显示 `Web UI: http://127.0.0.1:8765`，浏览器打开同一地址。

数据库默认写入仓库内的 `memory_product/data/memory_demo.db`。

## 三分钟演示

1. 点击“运行一键演示”。
2. 查看事件序列：前两条进入 Current，第一次 Rust 偏好进入 Candidate，第二次确认后触发 Consolidated。
3. 在状态表中确认 Python 为 History、Rust 为 Current。
4. 检索“我现在主要使用什么编程语言？”，确认答案引用 Rust 当前记忆。
5. 检索“我以前主要使用什么编程语言？”，观察历史意图提高 History 权重。
6. 查看审计时间线中的 Candidate、Consolidate 和 Retrieve 事件。

## 测试

在仓库根目录执行：

```sh
uv run --locked python -m unittest discover -s memory_product/tests -v
```

测试覆盖核心状态机、隐私门、重复强化、遗忘、删除、页面、健康接口与端到端 seed-search-stats 流程。

## 目录

```text
memory_product/
├── app.py                    # HTTP API 与静态页面服务
├── memory_core.py            # 记忆领域逻辑、SQLite 与检索
├── start_demo.ps1            # Windows 一键启动
├── static/index.html         # 响应式演示界面
├── tests/test_memory_core.py # 核心逻辑测试
└── tests/test_http_api.py    # HTTP 集成测试
```

## 重要边界

- 当前相似度是中英文词元与汉字 n-gram 的确定性离线基线，不是向量模型。
- 主题冲突的稳定演示依赖 `memory_key` / `memory_value`；自由文本自动实体关系抽取尚未实现。
- 规则参数可解释但未针对生产数据学习或校准。
- 这是本地单用户命名空间演示，没有登录、权限隔离、加密、备份或分布式部署。
- 系统不会调用 LLM 生成答案；“基于当前记忆”是证据拼接式演示回答。

完整架构、接口、算法、状态与路线图见上一级目录的 `认知长期记忆系统产品技术文档_v1.0.md`。
