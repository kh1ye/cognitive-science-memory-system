# 个人助手个性化建模选型

调研日期：2026-11-15。范围：官方仓库、文档与本项目代码审阅；未运行第三方服务、未进行性能对比、未修改依赖或业务数据。以下适配度和实施方案是本项目的工程判断，不是开源项目的性能排名。

## 结论

建议在现有四模块记忆之上增加可追溯的用户画像投影。优先借鉴 Memobase 的画像组织和上下文装配，选择性验证 LangMem / Trustcall 的结构化增量更新。现阶段无需替换 SQLite 事实源，也无需为了画像先引入图数据库。

## 候选方案

| 方案 | 官方可核实能力 | 本项目适配判断 |
| --- | --- | --- |
| [Memobase](https://github.com/memodb-io/memobase) | Apache-2.0；topic/sub_topic/content 画像；事件；缓冲与 flush；有预算的 context API | 画像设计最值得参考。官方部署含 PostgreSQL/pgvector、Redis、API；整体接入会增加独立状态和同步工作 |
| [LangMem](https://github.com/langchain-ai/langmem) | MIT；Pydantic/JSON Schema 定义画像；根据 existing 更新单一画像；可独立使用提取原语 | 技术栈最接近现有 LangGraph。优先只使用生成候选的能力，持久化仍走我们的来源、状态和事务逻辑 |
| [Trustcall](https://github.com/hinthornw/trustcall) | MIT；对已有结构生成 JSON Patch；校验失败时通过 patch 修复 | 是结构化更新工具，不是完整用户建模产品。值得测试能否减少全量重写导致的信息丢失；patch 必须验证来源及并发版本 |
| [Mem0](https://github.com/mem0ai/mem0) | 开源记忆引擎；提取、存储、检索；另有 Platform User Profiles API | 与现有记忆层重叠较多。官方画像文档使用 MemoryClient 和 Platform 路径，不能把 SDK 中的接口等同于可本地部署的画像实现 |
| [Graphiti](https://github.com/getzep/graphiti) | 动态时序知识图谱；双时间；实体关系；混合检索 | 将来做人物、组织、项目关系和时点查询时有价值。当前新增图后端及索引不太符合轻量画像目标 |
| [memU](https://github.com/NevaMind-AI/memU) | 当前主分支定位为跨会话、跨 Agent 的个人 Wiki，支持记忆与检索 | 可参考可读、可编辑的记忆呈现；并非本轮首选的结构化画像管理器。评估时需固定版本，避免套用旧版介绍 |

## 官方材料

- LangMem 画像示例：https://langchain-ai.github.io/langmem/guides/manage_user_profile/ 。包含 schemas、existing、enable_inserts=False 以及用户 namespace。
- LangMem 依赖声明：https://github.com/langchain-ai/langmem/blob/main/pyproject.toml 。当前项目已经使用 LangGraph 1.x 和 LangChain provider 1.x；接入前仍须锁版本并验证 SDK 与 MiniMax 的工具调用兼容，不能仅凭依赖范围宣称兼容。
- Trustcall 更新示例：https://github.com/hinthornw/trustcall#updating-schemas 。增量更新不能代替事实核验。
- Memobase 部署：https://github.com/memodb-io/memobase/blob/main/src/server/docker-compose.yml 。
- Memobase 的 flush / context 说明：https://github.com/memodb-io/memobase#4-get-your-memory 。默认会清除已处理 blob；若直接接入，必须单独设计与我们来源证据保存、删除的映射。
- Mem0 画像：https://docs.mem0.ai/platform/features/user-profiles 。本轮核实到的是 Platform 用法，未验证本地画像生成实现。
- Graphiti 的依赖与图后端：https://github.com/getzep/graphiti#installation 。时序图能力不等于自带完整画像产品。

## 现有系统的接入点

- `src/conversation_agent/graph.py`：已经先观察/提取，再检索、回答、学习；`_reply` 注入 preference_context、retrieved 和 working，但没有独立的全局用户画像。
- `src/cognitive_memory/architecture_models.py`、`architecture.py`：已有语义断言、来源、置信度和状态，可成为画像事实基础。
- `src/cognitive_memory/catalog.py`：统一读取四模块对象。画像构建应复用有效事实规则，不能直接将管理列表的所有行当作当前画像。
- `frontend/src/views/AssistantView.vue`：人工偏好和会话模式目前在浏览器维护，应逐步接到服务端的用户级偏好与会话级覆盖。
- `docs/storage-policy-adapter.md`：当前策略约束。画像不得引入绕过原写入评分、候选巩固或来源删除的新路径。

## 建议的数据和执行设计

1. 用户画像按维度组织：基本称呼与语言、交流偏好、工具与技能、兴趣、长期目标。项目/任务约束单独保留范围和有效期，不自动上升为终身偏好。
2. 每个条目保存 value、source_refs、assertion_ids、confidence、status、updated_at；用户明确填写与模型推测区分。未知保持空值，推测保持候选。
3. 画像是已有有效记忆的投影，可重建；候选、历史和争议条目不冒充已确认画像。只纳入描述该用户的记录，不把助手讲授的知识、第三方人物事实或任务产物当作用户特征。
4. 首版可以确定性归类现有结构化偏好，无需每轮额外调用模型。难以归类的事实再由可替换的 LangMem/Trustcall 适配器提出映射建议，通过现有证据与状态校验后采用。
5. 检索与画像分别加载：小型稳定画像按预算进入上下文，问题相关经历走原检索。优先级建议为当前明确请求 > 会话模式 > 用户明确设定 > 已确认画像 > 候选推测；冲突显式呈现。
6. 已成功提交的相关学习项触发重建/失效；新请求先检查画像修订号，避免新事实入库而旧画像持续生效。删除来源或事实必须使派生画像失效；不能仅更新 UI。
7. 修改画像沿用可追溯的用户纠正与现有策略，不直接覆盖 JSON。允许从个性化中排除条目；来源仍存在时，需保存排除策略，防止下一次重建又加入。
8. `no_persist` 不加载个人画像，保持当前匿名式无持久化调用语义；关闭自动记忆不新增画像事实，但可使用已有画像。敏感信息继续受现有 consent 和来源策略约束。

## 第一版建议范围

- 一个用户画像读取 API，返回维度、条目、来源与修订号。
- 将当前浏览器个人偏好迁移到服务端的显式偏好入口；会话模式保持局部覆盖。
- 在回答前装配有预算的画像上下文，并保留原有检索和记忆策略。
- 个人助手增加“助手了解的我”：查看、纠正、排除、跳转来源。
- 先用规则实现画像投影；在临时库中对照测试现有提取与 Trustcall/LangMem，验证有改善后才增加依赖。

## 验收

跨会话稳定使用语言/风格；临时要求不污染长期画像；不同用户隔离；明确纠正不再使用旧值；相冲突的事实不会静默选择；来源删除后无法从画像恢复；第三方/助手知识不混入个人特征；不保存模式不加载个人画像；重试及并发不丢字段。比较无画像/规则画像/第三方辅助画像的偏好遵循、无依据画像、错误沿用率，同时记录 token、延迟和模型调用次数。

没有统一跑分可以据此证明哪套方案在我们的中文个人助手中最好。最终选型应由上述临时库与真实模型小规模评测决定。
