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
- 13 项自动化测试

## 快速启动

项目使用 [uv](https://docs.astral.sh/uv/getting-started/installation/) 管理 Python、虚拟环境和依赖。安装 uv 后，在仓库根目录执行（macOS、Linux、Windows 通用）：

```sh
uv sync --locked
uv run memory_product/app.py --open
```

默认使用 Python 3.12，uv 会在需要时自动下载解释器，并在 `.venv` 中创建隔离环境。当前仅使用 Python 标准库，无第三方依赖。

浏览器访问：<http://127.0.0.1:8765>

Windows 也可以使用 PowerShell 启动脚本：

```powershell
.\memory_product\start_demo.ps1 -Open
```

## 运行测试

在仓库根目录执行：

```sh
uv run --locked python -m unittest discover -s memory_product/tests -v
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

## 技术文档

[认知长期记忆系统产品技术文档 v1.0](./认知长期记忆系统产品技术文档_v1.0.md)

## 协作方式

请从 main 创建个人功能分支，修改后提交并发起 Pull Request，不要直接覆盖主分支。
