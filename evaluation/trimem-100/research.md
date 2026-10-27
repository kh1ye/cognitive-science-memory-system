# 记忆分类数据集核查

检索日期：2026-10-27。查找目标：输入记忆类型识别、多标签分流、记忆写入决策。学术 MCP 未挂载，改查 arXiv、ACL Anthology、作者 GitHub 原文与数据。

## 最相关：MemoType / TriMEM

- 论文：[Memory Type Varies: Empowering LLM Agents for Long-Term Memory with Diverse Strategies](https://arxiv.org/html/2610.11573v1)，2026。
- 作者仓库：[wenyiwy99/MemoType](https://github.com/wenyiwy99/MemoType)。注意不要与 tmlr-group/TriMem 的另一项工作混淆。
- 原始数据：[TriMEM/TriMEM.csv](https://github.com/wenyiwy99/MemoType/blob/main/TriMEM/TriMEM.csv)。实际读取并解析为 6,000 条记录；列为 Content、Episodic Memory、Personal Semantic Memory、General Semantic Memory。
- 三个标签是独立二值标签，可同时为 1；全 0 为 None。数据直接面向对话记忆内容分类，并训练 Memory Type Router；Query Type Router 是另外的任务。
- 论文附录 B.3：采样并改写来自既有数据的对话，使用模型辅助标注并迭代验证；报告对 1,200 条样本作人工核查。它不是全部由人类从零写作、全部独立人工标注的真实用户语料。
- 本次抽样 100 条，固定种子 20261027，按原标签组合近似比例取样，保留原文与原标签；尚未调用任何评测模型，不是作者指定的 held-out test split。

## 相关但输入任务不同：PerLTQA

- 论文：[PerLTQA](https://aclanthology.org/2024.sighan-1.18/)，SIGHAN 2024。
- 作者仓库：[Elvin-Yiming-Du/PerLTQA](https://github.com/Elvin-Yiming-Du/PerLTQA)。Dataset/README.md 公开说明人物记忆与问答数据结构，原始人物、经历等由 ChatGPT 生成；有中文数据。
- 定义语义记忆（人物画像、社会关系）与情景记忆（事件、对话）。论文 A.5 的分类实验是用问题预测相关记忆类型，不应直接当作单次新输入写入分类的同一任务。
- 作者仓库许可证写明 CC BY-NC 4.0；引用以作者当前 README 为准，不混淆论文许可与数据许可。

## 与本项目的映射边界

TriMEM 直接覆盖语义/情景分类，但把语义分为个人与通用两个标签；本项目暂未细分这两个输出，不能宣称直接有三类路由评分。可以另报保持原始三标签的分类实验，或明确报告将 PM OR GM 合并后的二标签适配评分。

TriMEM 没有 CoALA 工作状态与可执行程序的输入标签。None 也不等于工作记忆；它只表示三种长期内容类别均未命中。程序候选/验证/启用是生命周期问题，不能以文本里是否含步骤取代。工作记忆、程序执行、保存策略等仍需独立行为测试，不混算为 TriMEM 分类准确率。

对最终约 100 条实测，应先固定数据与评价协议，再调用模型；同时报告原标签分布、每标签 precision/recall/F1、多标签 exact match，以及调用失败和模型结构化输出失败。不要看过结果再挑样本。
