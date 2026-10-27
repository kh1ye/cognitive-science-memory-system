# 记忆分类与观察提取修订

本轮修正代码和提示，并保留原始数据、标签与失败结果。

- 概念分类：[新旧提示交错对照报告](results/20261027-231927/report.md)。同一模型、同一批100条，基线95/100，新版99/100；新编32条，基线28/32，新版32/32。此前单次94/100仍保留，新旧对照使用两臂本轮新调用，没有挑较低的历史分数作基线。
- 实际分流：[观察提取与隔离写入报告](observation-results/20261027-232356/report.md)。16条开发检查，初始9/16，最终15/16；最后一轮17项写入全部成功，没有程序启用。仍有教育背景被重复提取为情景，以及事实状态被误判为history的风险。
- [回归测试日志](regression-tests.log)：101项，100项通过、1项外部运行环境缺失而跳过。

代码对应：

- src/conversation_agent/memory_concepts.py：可复用概念分类函数、版本化提示、共享内容边界。分类函数不接收答案；文本JSON可从同一响应恢复，不依答案重问或强改标签。
- src/conversation_agent/prompts.py：多目标观察提取提示，区分技能陈述与智能体程序，不将单次活动默认转成长期个人事实。
- src/conversation_agent/llm.py：事件证据在写入前验证，只有标点/空白等差异才还原原文；真正改写触发一次格式与来源修复，仍不合格则失败。
- src/conversation_agent/graph.py：把真实观察正文单独传给来源校验，不把可信调用元数据当成事件证据。
- evaluation/project-memory-100/run_concept_eval.py：调用项目分类函数，支持baseline/boundaries-v2，并记录提示版本。默认boundaries-v2，历史基线仍可重跑。

复现命令：

```sh
.venv/bin/python evaluation/memory-classifier-v2/run_comparison.py
.venv/bin/python evaluation/memory-classifier-v2/run_observation_check.py --versions current
.venv/bin/python -m unittest discover -s tests -v
```

比较中的新32条是在修改提示后、调用前冻结的作者自建样本，尚未经独立专家标注，也是在看到旧错误后编写；不应称为外部独立基准。原100条中的N058保持原标签，未因存在歧义而移除分母。概念分类仍不等于数据库写入路由，真实多目标检查单独报告。

实际分流的初始旧提示保存在observation-results/20261027-232034/prompt-baseline.txt。当前检查器使用更新后的代码，选择baseline只替换旧提示，不回滚事件证据校验；不能把未来的baseline调用声称为旧代码完整复现。
