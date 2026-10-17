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

在仓库根目录执行：

    cd ".\memory_product"
    .\start_demo.ps1 -Open

如果 PowerShell 阻止脚本：

    cd ".\memory_product"
    python .\app.py --open

浏览器访问：

    http://127.0.0.1:8765

## 运行测试

    cd ".\memory_product"
    python -m unittest discover -s .\tests -v

## 技术文档

[认知长期记忆系统产品技术文档 v1.0](./认知长期记忆系统产品技术文档_v1.0.md)

## 协作方式

请从 main 创建个人功能分支，修改后提交并发起 Pull Request，不要直接覆盖主分支。
