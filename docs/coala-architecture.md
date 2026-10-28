# 四类记忆架构（2026-10-27）

依据 [CoALA §4.1–4.6](https://arxiv.org/html/2309.02427v3)：工作记忆维护当前决策状态；情景保存经历；语义保存知识；程序性记忆包括隐式模型能力与显式行为实现。检索将长期对象带入工作状态，推理更新工作状态，学习写入长期模块，决策循环选择并执行行动。以下字段、SQL 表、状态、校验、备份和停止策略全部是本项目工程选择，非论文规范。

## 入口与兼容边界

新入口为 `Memory(...).architecture`、`/api/architecture/*`，现有 `/api/chat` 已使用新架构。管理页顶部「打开四类记忆 · 任务与来源」读取真实对象、显示回执、登记并执行内置程序。个人助手显示新的来源、版本及学习失败状态。

**兼容写入保留，读取统一**：兼容层合并了远程的主题规范化、逐条证据、幂等和可靠状态更新；其新写入只接受三类长期内容，原 working 类型按标签迁移为长期内容类型，工作层仍是 state_role。任务工作记忆仍由 working_states 独立承载，管理总览继续汇总四个模块。`Memory.add_memory/search/list_memories`、默认 `/api/memories`、`/api/search`、旧演化演示及既有第三方适配器继续操作原 `memories` 表，其评分、标签、current/candidate/history 和重复强化属于旧协议。助手与 `/api/architecture/retrieve` 通过 `MemoryCatalog` 同时召回类型化对象和相关的兼容记录，因此演化页、手动添加的信息也可供新会话检索。兼容 working 不跨任务恢复，candidate 不作为当前知识，旧 procedural 仅能作为语义流程文字，不能执行；迁移记录在引用及其 record 中均标为 legacy_unverified/candidate，不冒充已验证事实。

`Memory.stats/overview` 与前端管理列表（`GET /api/memories?view=all`）汇总 working_states、episode_events、semantic_assertions、semantic_documents、procedure_versions 及兼容原记录。来源、学习回执、事件容器和程序运行日志不另计记忆；迁移隔离副本不重复计数。统计覆盖全量，列表最多加载 1000 条并标明加载范围。类型化对象没有旧写入评分，展示为“不适用”；其来源删除、程序版本状态等操作仍在类型面板管理。读取层不双写、不迁移数据；默认旧列表及搜索协议不变。

## 模型、存储和生命周期

| 模块 | 独立表与字段 | 更新与生命周期 |
|---|---|---|
| 工作 | `working_states`：user/thread/task、revision、goals、constraints、observations、active_knowledge、task_state、open_questions、candidate_actions、selected_action | active / paused / completed；按任务恢复，支持清理；低分不构成工作状态；落盘不改变其运行状态性质 |
| 情景 | `episodes` / `episode_events`：episode_id、actor、event_kind、sequence_no、occurred_at、recorded_at、observation、action_ref、outcome、parent_event_id、source_refs | 追加事件；源事件重试返回原对象，同文不同事件身份可并存；corrects 链保留纠正；未知时间为 null；unknown/partial/failed/succeeded 不混用 |
| 语义 | `semantic_assertions`：subject/predicate/value、scope、valid_from/to、epistemic_status、confidence、source_refs/evidence_ids、version、supersedes_ids；`semantic_documents`：文档版本、定位、正文和哈希 | 明确偏好可立即生效；用户自身明确纠正保留 history；普通冲突双方 disputed；推断留 candidate；多个取值关系不互相覆盖；文档版本不可原地替换 |
| 程序 | `procedures` / `procedure_versions` / `procedure_runs`：kind、契约、实现引用/哈希、验证引用、版本、状态和实际结果 | draft → validated → enabled → disabled；启用旧版本可回退；托管模型只登记 provider/model 配置，不能执行成代码，weights_managed=false |

表分别保存模块对象，ownership 和 scope 是 SQL 索引列，复杂模型字段使用 JSON；SQLite 是唯一事实源，当前词法检索没有独立向量索引。所有服务使用现有连接和锁；嵌套事务只由最外层提交；每个学习项有 SAVEPOINT，失败项回滚，成功项与其回执同事务提交。

无自动时间到期删除任务：执行层或使用者显式完成/暂停/清理。情景暂不自动按年龄归档；删除来源时清理其派生事件，保留无正文 episode 容器。对象列表用于历史检查，不等于当前事实检索。

## 输入路径、来源与隐私

`Observation` 必须携带用户、会话、任务、source_kind、source_event_id、content；可给 source_ref、observed_at、scope、retention_policy、consent。

1. `no_persist` 在提取、日志和正文检查点之前返回；聊天使用无 checkpointer 的同一 LangGraph，不创建会话标题。
2. 其他输入形成结构化 `ObservationAnalysis`：working_state_patch、episode_candidates、semantic_candidates、procedure_proposals。
3. 先更新工作观察/约束，再分别执行学习项。每项返回 operation id、模块、状态、result_refs、error。只有 succeeded 表示实际写入。
4. 模型走 `with_structured_output` 和 Pydantic 校验，格式或事件来源错误最多一次 JSON 修复。调用层单独传入原始正文验证事件片段，允许空白、标点等差异还原；真正改写不能直接写入。语义候选必须有 evidence_text，由存储层核对原文；调用元数据不作为事件证据。模型提取仍可能误解语义，不能替代事实核查。
5. 未配置 analyzer 的独立 `observe` 不猜测事实：默认仅更新工作观察。可注入假模型或传入经校验的 analysis；管理页可提交结构化 JSON，个人助手使用已配置模型自动提取。

`persist` 允许长期写入；`no_long_term` 仍保存任务状态/会话，但来源正文不保存；`no_persist` 不保存本次正文或检查点。聊天 `auto_remember=false` 等价于不写长期模块，仍保留运行状态。自然语言「不要记住/不要保存」保持旧界面语义：不写长期模块，**不是**不保存会话；完全不持久化须显式指定 API retention_policy。敏感候选缺少 consent 会阻止长期写入。模型为了答复仍接收本次输入。

概念分类由 `conversation_agent.memory_concepts.classify_memory_concept` 提供，默认 `boundaries-v2`，并保留原 `baseline` 版本。它与观察提取共享内容边界，但不替代多目标分流：人的技能例子可体现程序性记忆，用户关于自身技能的陈述仍是语义事实，不能直接注册成智能体程序。做法文本与实际能力、个人背景与具体经历分别判定；未知仍允许弃答。独立评测与真实分流检查分别见 [本轮报告](../evaluation/memory-classifier-v2/README.md)。

来源身份与正文独立：`source_records` 保存源事件身份、出处、范围和策略。`source_ref` 非空时作为独立证据根身份，否则使用 source_event_id；相同出处的多个提取不增加独立证据数。来源身份由调用者提供，系统无法证明外部来源真实独立。检索不增加 confidence。`memory_links` 包含 derived_from/supports/contradicts/supersedes/corrects/used_procedure。

删除来源时清理单来源派生对象、学习回执、程序结果中的来源副本与激活内容；多来源断言移除对应证据，清空原证据片段并降为 candidate 待复核。为覆盖旧检查点版本中可能残留的派生正文，会**保守清除该用户全部会话及工作检查点**。这不是跨库原子事务：长期库先提交，执行层再清理会话库；清理异常会向调用者返回失败，应由运维检查两个库。SQLite 旧备份由部署者管理，在线删除不擦除离线恢复副本或保证文件系统级安全擦除。

user_id 是本地命名空间，不是登录身份；查询、更新、恢复均按调用方指定用户限定。此版本不提供多租户认证或范围 ACL，不能直接公开为多用户服务。

## 程序真实能力

`install_builtins(user)` 安装代码拥有的五种实现：

- reasoning `text.normalize`：真实整理空白。
- retrieval `knowledge.retrieve`：调用类型专属知识检索。
- learning `knowledge.learn`：校验并写入有来源断言。
- grounding `text.emit`：产生文本输出。
- decision `decision.next`：从已完成步骤选择下一行动。

验证检查 kind、受支持实现和输入/输出契约，保存实现源码哈希；执行只访问固定 allowlist，不导入用户代码或 eval。失败实际记录 failed，与对应情景结果关联，不写成功经历。参数仅保存哈希，结果保存实际结构化对象；run_key 提供重试去重。普通流程提议没有实现，不能验证/启用；迁移的旧程序永久留在 legacy_unverified。托管模型登记配置不保存密钥、不声称控制供应商权重，也不声称模型别名是固定供应商版本。现阶段不支持任意新 Python、自主改代码、训练或任意外部工具调用。

## 检索与决策

知识按范围、主体、关系、有效时间和状态过滤，再做中英词法相关度排序；默认包含 disputed 并保留标签，候选/历史不当作确定当前事实。情景按任务/结果过滤，再考虑相关性、时间和序列；程序按能力 kind、enabled 和版本筛选。`retrieve(..., modules=[...])` 支持组合和 working 直读，激活对象保留 memory_id/version/source_refs/purpose，不改变原类型。

聊天是固定策略 LangGraph：observe → decide → execute → decide，最多 4 次执行，重复行动保护，完成后 turn_complete 并等待输入。候选包括检索、外部回答、学习，程序记录简要理由与执行状态；没有保存模型内部思维。首版路由是明确标注的有限规则（经历词路由 episodic、能力词路由 procedural，其余 semantic），不是通用意图分类器；不强迫所有模块都检索。回答使用最近 20 条消息、当前工作状态与检索结果；新 task_id 清除该会话模型消息历史以隔离临时约束。同一 task 可恢复跨调用状态。回答成功而学习失败返回 failed 与 warning。当前循环没有通用工具规划器，程序真实执行通过注册表 API 或 Python 服务调用。

## API 速查

| 方法 / 路径（前缀 `/api/architecture`） | 功能 |
|---|---|
| POST `/observe` | `{observation, analysis?}` 分流与实际学习回执 |
| GET `/objects/{module}?user_id=...&scope=...` | 独立对象列表、历史、来源、关系、程序版本及运行详情 |
| GET / PATCH / DELETE `/working/{thread_id}/{task_id}` | 读状态、`{user_id,patch}` 更新、清理任务 |
| POST `/assertions`, `/documents` | 类型契约写入，必须引用已登记来源 |
| POST `/retrieve` | user_id/thread_id/task_id/query/modules/scope |
| POST `/procedures`, `/procedures/install-builtins` | 提议版本 / 登记固定实现 |
| POST `/procedures/{version_id}/{validate|activate|disable}` | `{user_id}` 验证、启停或回退版本 |
| POST `/runs/{version_id}` | `{user_id,arguments,run_key,thread_id?,task_id?}` 真实执行 |
| DELETE `/sources/{source_id}?user_id=...` | 删除来源与派生内容 |

`/api/chat` 新增可选 task_id/source_event_id/retention_policy；返回 task_id、stop_reason 和 learning_operations 格式的 memory_results。旧聊天客户端仍可读取 answer/references/memory_status/warnings；引用保留展示字段并新增完整 record。新工作状态不要通过旧的 add_memory 写入。文档和断言的直接写 API 是管理入口；通常从 observe 执行可获得完整学习操作回执。

## 迁移、恢复与实际执行范围

首次打开文件库：先通过 SQLite backup API 生成 `<db>.pre-coala-v1.bak`，再在单事务创建 `architecture_migrations(version=1)` 和新表并导入旧对象。重复启动不重复导入。遇到迁移失败遗留的同名备份会拒绝覆盖，需先检查并重命名备份后再重试。`legacy_memory_map` 保留 ID 到目标表映射；无来源对象统一 legacy_unverified、scope=legacy，不伪造发生时间、执行结果或独立证据。原 working 隔离成未验证文档而不是任意任务状态；原 procedural 隔离成不可执行版本。

恢复：停止服务；保留现库以便排查；用 `.pre-coala-v1.bak` 替换数据库，清除对应旧 `-wal/-shm` 后使用旧版本代码启动。会话库独立备份/恢复；不得在服务运行中直接覆盖文件。

本次开发只对临时测试库和内存库执行迁移，未打开/迁移用户 `memory_product/data` 现有文件。下次启动新版本将触发迁移。

## 本地运行与验收

```sh
uv sync --locked
npm --prefix frontend ci
npm --prefix frontend test
npm --prefix frontend run build
uv run --locked python -m unittest discover -s tests -v
uv run python scripts/coala_example.py
uv run python -m api.app --open
```

示例完全离线：任务 → 工作状态 → 情景 → 来源知识 → 检索注册程序 → 实际执行及结果事件 → 后续任务复用知识；使用内存库。

`tests/test_architecture.py` 覆盖临时/长期偏好、明确纠正、事件身份、同来源证据、历史/范围/多值关系、激活不变类型、用户隔离、程序提议与真实执行、失败结果、混合输入、隐私、删除、旧库迁移重跑、程序回退、文档版本与推断候选。`test_architecture_api.py` 覆盖 API、循环、任务切换与检查点隐私。`test_conversation_agent.py` 保留会话恢复、隔离、格式恢复、模型失败及本地真实 SDK HTTP 测试，并改用结构化分流契约。

长版验收 1–16、19–23 在上述测试中有直接行为覆盖；17–18 覆盖显式策略与受管理来源/检查点的清理，不代表外部日志、文件系统残留或备份擦除；24 包含旧兼容存储/API 回归和新聊天协议迁移。架构验收主要为离线测试；后续补充了当前MiniMax供应商的264次概念分类调用与16条实际分流/隔离写入复测，详见本轮报告，其范围不等于完整在线验收。没有认证隔离、任意外部工具或自动归档的验收结论。

## 低价值输入（2026-10-28）

自动聊天对完整匹配的纯问候、确认、感谢、测试用语及明显重复/符号噪声跳过提取；类型化 observe 服务同时禁止其长期写入，即使分析器提出候选也会拦截。它们只留在会话和任务工作上下文，source_records 不保留正文。短句中的事实与混合问候不按长度过滤。短期上下文仍会持久化 SQLite，尚无自动到期清理；手动保存兼容接口仍遵循明确保存操作。分类与分流复测见 evaluation/current-recheck-20261028/acceptance.md。

补充：空长期候选的自动观察也使用 no_long_term，避免普通闲聊虽未形成长期对象却在来源表留下正文；学习步骤不重复持久化空候选。纯通信探测和算术提问留在上下文。固定150条及修复前后结果见 evaluation/memory-150/README.md。
