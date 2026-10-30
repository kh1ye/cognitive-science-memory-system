# 记忆例子与评测资料

[Vatsalabench 500条数据与实验记录](Vatsalabench/README.md)：含六维指标原文、逐轮原始结果、评分和失败日志。最新扩大测试记录见[六维报告](Vatsalabench/results/expansion-20261030-144500/report.md)。

代码修订后的[新旧分类与实际分流对照](memory-classifier-v2/README.md)：原100条本轮基线95/100、新版99/100；新编32条28/32→32/32；实际分流开发检查最终15/16。

针对6条分类分歧的[102次对照诊断](memory-boundary-diagnostic/results/20261027-231131/interpretation.md)：区分重复波动、语序影响、提示边界与参考标注歧义；不改动原100条成绩。

基础集：[四种记忆的100个生活化例子](project-memory-100/review.md)。

四类各25条，版本 examples-v3。已使用 MiniMax-M3[1m] 完成独立概念识别评测，100/100 与参考标签一致：[基础集实测报告](project-memory-100/results/20261027-224900/report.md)。此结果不代表对应技能已经在项目中实现。

修订稿：[100条自然口语例子](project-memory-challenge-100/review.md)。版本 natural-v2，每类25条；首次测试94/100与参考标签一致。[实测报告](project-memory-challenge-100/results/20261027-230557/report.md)。根据“例子太刻意”的反馈改写表达，不再强行凑同主题四类。[修订说明](project-memory-challenge-100/README.md)。

旧版 challenge-v1 的97/100只保留为历史标签一致记录，撤回作为有效进阶分类能力结论的用法。旧样本已归档，原始预测与统计保留；该分数不适用于当前修订稿。

- [生活化例子 JSON](project-memory-100/cases.json)
- [概念口径说明](project-memory-100/paper-basis.md)
- [较复杂的 v2 工程验收稿](project-memory-100/archive/review-v2/review.md)：留档，不作为当前阅读入口。
- [更早的 v1 稿](project-memory-100/archive/review-v1/review.md)
- project-memory-smoke-20 和 memory-routing-100：早期自建草稿。
- trimem-100：公开数据抽样及辅助中文翻译，保留作研究参照。
