<script setup>
import { computed, ref } from "vue";
import IntegrationLogo from "../components/IntegrationLogo.vue";
import AppIcon from "../components/AppIcon.vue";
import { useWorkspace } from "../composables/useWorkspace";
const { state, notify } = useWorkspace();
const harness = ref("openclaw");
const plugin = ref("deepseek");
const plugins = [
 { id: "deepseek", title: "DeepSeek Harness", status: "本地插件已实现 · 官方工具运行时验证通过", description: "原生 Cordis 记忆工具插件，支持显式保存与检索。已验证 DSH 0.2.1-rc.2 工具运行时；完整 Web / 桌面客户端启用尚未验证。", url: "https://github.com/deepseek-ai/deepseek-harness" },
 { id: "codex", title: "Codex", status: "待适配", description: "Codex 专用插件与 MCP 适配尚未实现，当前没有可执行的安装命令。" },
];
const selectedPlugin = computed(() => plugins.find(item => item.id === plugin.value));
const pluginSteps = computed(() => plugin.value === "deepseek" ? [
  { title: "1. 启动记忆服务", hint: "在本项目根目录执行。插件不需要模型密钥；Harness 的模型由其自身配置。", code: "uv run --locked python -m api.app" },
  { title: "2. 安装本地插件包", hint: "适用于已安装的 DSH 0.2.1-rc.2。以下为 PowerShell 命令，在本项目根目录运行；其他系统请传入插件目录的绝对路径。自定义 Profile 请替换 web。", code: "dsh plugin --profile web add (Resolve-Path ./integrations/deepseek-harness).Path" },
  { title: "3. 设置记忆空间", hint: "将片段追加或合并到活动 Profile 的 cordis.patch.yml（通常为 ~/.dsh/profiles/web/cordis.patch.yml，DSH_HOME 可更改根目录）。保留其他配置，然后重启 Harness。该插件面向单用户本地 Profile。", code: `- id: cognitive-memory\n  config:\n    baseUrl: http://127.0.0.1:8765\n    userId: ${JSON.stringify(state.user)}` },
  { title: "4. 验证保存与检索", hint: "在 Harness 中发送以下请求，并确认当前 Agent 预设允许这两个工具。管理页可查看来源 deepseek_harness_plugin。候选或隐私拦截会如实返回。", code: "请调用 cognitive_memory_save 记住：我喜欢使用 Python。然后调用 cognitive_memory_search 查询我的编程偏好。" },
] : []);

const harnesses = [
 { id:"openclaw", title:"OpenClaw", status:"本地工具插件 · 待客户端验证", url:"https://docs.openclaw.ai/plugins", description:"已提供本地记忆工具插件，支持显式保存和检索，不替换内置记忆。适用于同机、单用户 Agent；尚未在真实客户端完成验证。" },
 { id:"hermes", title:"Hermes Agent", status:"本地 Memory Provider · 待客户端验证", url:"https://hermes-agent.nousresearch.com/docs/developer-guide/memory-provider-plugin/", description:"已提供原生目录式 Memory Provider，支持显式保存和检索。按活动 Profile 读取配置；不自动保存整段对话。尚未在真实客户端完成验证。" },
];
const selectedHarness = computed(() => harnesses.find(item => item.id === harness.value));
const mode = ref("python"), method = ref("write"), copied = ref("");
const choices = [
  { id: "agent", title: "Agent 接入", text: "OpenClaw 与 Hermes 记忆接入", icon: "chat" },
  { id: "python", title: "SDK / API 接入", text: "在自己的应用中读写记忆", icon: "database" },
  { id: "plugin", title: "插件 / MCP", text: "查看客户端集成支持情况", icon: "layers" },
];
const language = ref("python");
const baseUrl = window.location.origin;
const user = computed(() => JSON.stringify(state.user));
const install = 'uv pip install -e .';
const steps = computed(() => {
  if (mode.value === "agent" && harness.value === "openclaw") return [
    { title: "1. 启动本地记忆服务", hint: "在本项目根目录执行。OpenClaw 与服务需运行于同一环境。", code: "uv run --locked python -m api.app" },
    { title: "2. 安装本地插件", hint: "在本项目根目录执行；需要已安装 OpenClaw。按客户端提示审核本地插件源码。", code: "openclaw plugins install --link ./integrations/openclaw" },
    { title: "3. 合并插件配置", hint: "将以下片段合并到已有 OpenClaw 配置。保留其他插件与 allow 列表；如有 allow 列表需追加 cognitive-memory。该用户空间由此单用户 Agent 独占。", code: JSON.stringify({plugins:{entries:{"cognitive-memory":{enabled:true,config:{baseUrl:"http://127.0.0.1:8765",userId:state.user}}}}},null,2) },
    { title: "4. 检查工具注册", hint: "如有工具白名单，请允许 cognitive_memory_search 和 cognitive_memory_save。然后让 Agent 显式保存一条普通偏好并检索，核对管理页中的来源 openclaw_plugin。", code: "openclaw plugins enable cognitive-memory\nopenclaw plugins inspect cognitive-memory --runtime --json" },
  ];
  if (mode.value === "agent" && harness.value === "hermes") return [
    { title: "1. 启动本地记忆服务", hint: "在本项目根目录执行；Hermes 与服务需运行于同一环境。", code: "uv run --locked python -m api.app" },
    { title: "2. 安装到活动 Profile", hint: "将路径替换为真实存在的活动 HERMES_HOME 目录。安装器保留已有配置；不会自动切换 Provider。", code: `uv run python integrations/install_hermes.py --home "/absolute/path/to/active/hermes-profile" --user-id ${JSON.stringify(state.user)}` },
    { title: "3. 选择记忆 Provider", hint: "选择 cognitive-memory，确认地址和用户空间后重启 Hermes。只允许一个外部 Provider 生效。让 Agent 调用 cognitive_memory_save / cognitive_memory_search 验证，管理页来源为 hermes_plugin。", code: "hermes memory setup" },
  ];
  if (mode.value === "plugin") return [];
  if (language.value === "http") return [
    { title: "1. 启动本地服务", hint: "在已安装项目依赖的仓库根目录执行；当前工作台已连接时无需重复启动。", code: "uv run --locked python -m api.app" },
    { title: method.value === "write" ? "2. 写入一条记忆" : "2. 检索已有记忆", hint: method.value === "write" ? "复制到 Python 运行；会向当前服务的用户空间写入一条示例记忆。" : "复制到 Python 运行；检索会记录访问与审计信息。", code: `import json\nfrom urllib.request import Request, urlopen\n\npayload = ${method.value === "write" ? `{\n    "user_id": ${user.value},\n    "content": "我主要使用 Python",\n    "memory_type": "semantic",\n    "tags": ["preference"],\n}` : `{\n    "user_id": ${user.value},\n    "query": "我主要使用什么编程语言？",\n    "top_k": 5,\n}`}\nrequest = Request(\n    "${baseUrl}/api/${method.value === "write" ? "memories" : "search"}",\n    data=json.dumps(payload).encode("utf-8"),\n    headers={"Content-Type": "application/json"},\n    method="POST",\n)\nwith urlopen(request, timeout=30) as response:\n    print(json.load(response))` },
  ];
  return [
    { title: "1. 安装本地 Python 包", hint: "在本项目根目录、目标 Python 虚拟环境中执行。当前使用仓库本地安装方式。", code: install },
    { title: method.value === "write" ? "2. 写入一条记忆" : "2. 检索已有记忆", hint: "可在 Python 应用中直接调用，无需启动 HTTP 服务。示例使用独立数据库 integration_example.db，不与工作台数据库共享。", code: `from cognitive_memory import Memory\n\nwith Memory("integration_example.db") as memory:\n    result = ${method.value === "write" ? `memory.add_memory({\n        "user_id": ${user.value},\n        "content": "我主要使用 Python",\n        "memory_type": "semantic",\n        "tags": ["preference"],\n    })` : `memory.search(\n        ${user.value},\n        "我主要使用什么编程语言？",\n    )`}\n    print(result)` },
  ];
});
async function copy(code, id) {
  try { await navigator.clipboard.writeText(code); copied.value = id; }
  catch { notify("复制失败，请选中代码手动复制。"); }
}
</script>
<template>
  <div class="page install-page">
    <div class="install-banner"><AppIcon name="book" /><div><strong>把记忆能力接入你的应用</strong><p>选择接入方式，复制示例，从第一条记忆开始。</p></div><a class="button small" href="/docs" target="_blank" rel="noopener">接口文档 <AppIcon name="external" /></a></div>
    <div class="install-content">
      <div class="page-heading"><div><h1>安装与接入</h1><p>Cognitive Science Memory System · 本地优先的记忆服务</p></div></div>
      <div class="install-choices" aria-label="接入方式">
        <button v-for="item in choices" :key="item.id" class="panel install-choice" :class="{ active: mode === item.id }" :aria-pressed="mode === item.id" @click="mode = item.id; copied = ''"><span class="integration-logo-tile"><IntegrationLogo :name="item.id === 'agent' ? 'agent' : item.id === 'python' ? 'sdk' : 'plugin'" /></span><span><strong>{{ item.title }}</strong><small>{{ item.text }}</small></span></button>
      </div>
      <template v-if="mode !== 'plugin'">
        <template v-if="mode === 'agent'">
          <div class="install-switch" aria-label="Agent 客户端"><button v-for="item in harnesses" :key="item.id" class="button" :class="{ primary: harness === item.id }" :aria-pressed="harness === item.id" @click="harness = item.id"><IntegrationLogo :name="item.id" />{{ item.title }}</button></div>
          <section class="panel install-guide"><span class="badge">{{ selectedHarness.status }}</span><h2>{{ selectedHarness.title }}</h2><p class="install-footnote">{{ selectedHarness.description }}</p><a class="button small" :href="selectedHarness.url" target="_blank" rel="noopener">官方接入文档 <AppIcon name="external" /></a></section>
          <p class="install-footnote">插件连接本地记忆 API，支持检索和显式保存，不自动捕获聊天。隐私门和候选巩固规则仍由记忆服务执行。</p>
        </template>
        <div v-if="mode === 'python'" class="install-switch" aria-label="调用方式"><button class="button" :class="{ primary: language === 'python' }" @click="language = 'python'"><IntegrationLogo name="python" />Python 本地库</button><button class="button" :class="{ primary: language === 'http' }" @click="language = 'http'"><IntegrationLogo name="terminal" />HTTP API</button></div>
        <section class="panel install-guide">
          <div class="install-guide-heading"><div v-if="mode === 'python'" class="install-switch"><button class="button small" :class="{ primary: method === 'write' }" @click="method = 'write'">写入记忆</button><button class="button small" :class="{ primary: method === 'search' }" @click="method = 'search'">检索记忆</button></div><strong v-else><IntegrationLogo :name="harness" /> {{ selectedHarness.title }} · 本地记忆插件</strong><span class="subtle">示例用户：{{ state.user }}</span></div>
          <article v-for="(step,index) in steps" :key="mode + language + method + index" class="install-step"><div class="install-step-copy"><h2>{{ step.title }}</h2><p>{{ step.hint }}</p></div><div class="install-code"><div class="install-code-title"><IntegrationLogo :name="step.code.startsWith('LLM_') ? 'deepseek' : mode === 'agent' && harness !== 'deepseek' ? harness : step.code.startsWith('uv') ? 'terminal' : 'python'" /><span>{{ step.code.startsWith('LLM_') ? '.env · DeepSeek' : mode === 'agent' && harness !== 'deepseek' ? selectedHarness.title : step.code.startsWith('uv') ? '终端' : 'Python' }}</span></div><button class="button small" :aria-label="`复制${step.title}`" @click="copy(step.code, step.code)">{{ copied === step.code ? '已复制' : '复制' }}</button><pre><code>{{ step.code }}</code></pre></div></article>
        </section>
        <p class="install-footnote">代码仅供复制，不会在页面自动执行。HTTP 地址跟随当前工作台：{{ baseUrl }}。用户 ID 用于区分数据空间，不提供身份认证。</p>
      </template>
      <template v-else>
        <div class="install-switch" aria-label="插件客户端">
          <button v-for="item in plugins" :key="item.id" class="button" :class="{ primary: plugin === item.id }" :aria-pressed="plugin === item.id" @click="plugin = item.id"><IntegrationLogo :name="item.id" />{{ item.title }}</button>
        </div>
        <section class="panel install-guide">
          <span class="badge">{{ selectedPlugin.status }}</span>
          <h2><IntegrationLogo :name="selectedPlugin.id" /> {{ selectedPlugin.title }} · 记忆插件 / MCP</h2>
          <p class="install-footnote">{{ selectedPlugin.description }}</p>
          <a v-if="selectedPlugin.url" class="button small" :href="selectedPlugin.url" target="_blank" rel="noopener">官方文档 <AppIcon name="external" /></a>
          <article v-for="step in pluginSteps" :key="step.title" class="install-step">
            <div class="install-step-copy"><h2>{{ step.title }}</h2><p>{{ step.hint }}</p></div>
            <div class="install-code"><div class="install-code-title"><IntegrationLogo name="deepseek" /><span>DeepSeek Harness</span></div><button class="button small" :aria-label="`复制${step.title}`" @click="copy(step.code, step.code)">{{ copied === step.code ? '已复制' : '复制' }}</button><pre><code>{{ step.code }}</code></pre></div>
          </article>
          <p v-if="pluginSteps.length" class="install-footnote">仅显式保存，不自动捕获聊天。请求只发送到同机本地记忆服务，敏感数据不推定授权。页面代码不会自动执行。</p>
          <p class="install-footnote">已实现的 OpenClaw 和 Hermes 本地记忆适配，可在 Agent 接入侧查看安装步骤。</p>
          <button class="button" @click="mode = 'agent'">查看已实现的接入方式</button>
        </section>
      </template>
    </div>
  </div>
</template>
