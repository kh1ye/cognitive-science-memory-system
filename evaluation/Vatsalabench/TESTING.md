# 本项目的 Vatsalabench 接入测试

在项目根目录运行。原始交付包保持不变，运行结果写入 `evaluation/Vatsalabench/results/`，每次新建独立数据库。

## 数据检查

```powershell
uv run --locked python scripts/vatsalabench_preflight.py
```

检查500条样本的公开文件哈希、题目及分支引用等；不调用模型，不代表记忆质量得分。

## 单样本原生记忆流程

通过本地环境变量配置 `LLM_API_KEY`、`LLM_BASE_URL=https://api.deepseek.com`、`LLM_MODEL=deepseek-v4-flash`，不要把密钥写进评测报告或提交到Git。

```powershell
uv run --locked python scripts/vatsalabench_full.py --sample b86304ba
```

执行原生 `analyze_observation` 自动抽取和 `architecture.observe` 分类、写入、更新，再通过原生 `ConversationAgent.chat` 回答12道题。DeepSeek提取阶段关闭思考模式，以兼容强制工具调用；回答阶段沿用模型默认思考配置。保留原始角色、文本、历史顺序和观察时间，以每会话最多16000字符的固定块导入。历史助手回答不重新生成。

BASE基础库建好后，各分支从SQLite完整备份开始。保持分支连续追加50个会话，分别在10/30/50处提问；更新和三种冲突分支互相隔离。每次提问另建完整数据库副本，允许原生检索和聊天状态更新，但不将问题、答案及检索副作用带回后续检查点。知识检索时间使用题目query_time。

`results.json` 保存提取分析、写入操作、回答、检索引用和检查点哈希。标准答案仅在全部回答生成后加载供核对，不进入被测模型。调用或提取失败会标记incomplete，不能算作正确答案或完整成绩。

中断后可用同一个样本继续（不要用于替换模型或更改适配配置后的对比实验）：

```powershell
uv run --locked python scripts/vatsalabench_full.py --sample b86304ba --resume evaluation/Vatsalabench/results/native-运行时间
```

这是探索性历史回放适配，不是逐轮HTTP聊天测试。观察来源使用document，角色在文本中保留；这与在线user_report路径存在差异。尚未实现官方资源消耗指标、独立评分器或11项综合报告。交付包的审核标记尚未通过，正式基准发布前需完成对应审核。单样本结果不能推断500条整体成绩。

`scripts/vatsalabench_pilot.py` 是较早的原文文档导入诊断，仅跑5道BASE题，不使用自动提取，不应与本脚本的结果混淆。

## 批量测试和六维评分

```powershell
uv run --locked python -m scripts.vatsalabench_batch --count 5
uv run --locked python -m scripts.vatsalabench_score evaluation/Vatsalabench/results/expansion-实际时间戳
```

批次默认按固定种子选取未用于此前调试的reviewed_umrr样本，逐条串行运行质量与独立效率实例。选择清单和预定查询数先写入batch.json，失败样本保留，不自动替换。每批次、每样本分别存储在子目录中。

裁判输出需按[六维指标](docs/VatsalaBench_六维指标.docx)复核，尤其是“两次拒答不能算FSRC一致”和AFP内容单元划分。人工修订需保留model_judgment/model_quality及manual_audit，不修改被测原始回答。聚合器不会覆盖已有评分文件。效率缺失时整批记NA，可另报已完成实例的条件统计及覆盖率。

已提交历史记录的原始路径保持运行时原样，迁移后可按results/relocation.json定位。当前脚本会直接写入数据集下的results目录。
