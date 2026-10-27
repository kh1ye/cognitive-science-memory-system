<script setup>
import { computed, ref } from "vue";
import LandingHowItWorks from "../components/LandingHowItWorks.vue";
import LandingDemo from "../components/LandingDemo.vue";
import AppIcon from "../components/AppIcon.vue";
import IntegrationLogo from "../components/IntegrationLogo.vue";
const language = ref("python"), demoStep = ref(0), copyMessage = ref("");
const examples = {
  python: `from cognitive_memory import Memory\n\nwith Memory("example.db") as memory:\n    memory.add_memory({\n        "user_id": "alice",\n        "content": "我喜欢喝茶",\n        "tags": ["preference"],\n    })\n    result = memory.search("alice", "我喜欢什么？")\n    print(result["answer"])`,
  http: `import json\nfrom urllib.request import Request, urlopen\n\nrequest = Request(\n    "http://127.0.0.1:8765/api/search",\n    data=json.dumps({\n        "user_id": "alice", "query": "我喜欢什么？"\n    }).encode("utf-8"),\n    headers={"Content-Type": "application/json"},\n)\nwith urlopen(request) as response:\n    print(json.load(response))`,
};
const code = computed(() => examples[language.value]);
const moments = [
  { label: "记住偏好", quote: "我喜欢喝茶。", title: "一条偏好，有了自己的位置。", note: "信息通过编码门后，进入当前记忆。", current: "喜欢喝茶", candidate: "", history: "" },
  { label: "发现变化", quote: "我现在更喜欢喝咖啡。", title: "出现新说法，先留作候选。", note: "一次不同的表达，不立即覆盖已有偏好。", current: "喜欢喝茶", candidate: "更喜欢咖啡", history: "" },
  { label: "证据巩固", quote: "最近我一直更喜欢喝咖啡。", title: "证据充分后，更新当前状态。", note: "新的偏好得到确认，过去的偏好保留为历史。", current: "更喜欢咖啡", candidate: "", history: "喜欢喝茶" },
];
const moment = computed(() => moments[demoStep.value]);
function scrollTo(id) {
  const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  document.getElementById(id)?.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" });
}
async function copyCode() {
  try { await navigator.clipboard.writeText(code.value); copyMessage.value = "已复制"; }
  catch { copyMessage.value = "请选中代码手动复制"; }
}
</script>
<template>
  <div class="lp-root">
    <header class="lp-header">
      <RouterLink to="/" class="lp-brand" aria-label="认知记忆系统首页"><span class="lp-mark">m<span /></span><span>认知记忆<span class="lp-brand-sub">COGNITIVE MEMORY</span></span></RouterLink>
      <nav aria-label="产品导航"><button @click="scrollTo('lp-capabilities')">产品能力</button><button @click="scrollTo('lp-evolution')">如何工作</button><RouterLink to="/install">开发者 <AppIcon name="chevron" /></RouterLink></nav>
      <RouterLink to="/overview" class="lp-header-cta">进入工作台 <span>↗</span></RouterLink>
    </header>
    <div class="lp-announcement"><span class="lp-live-dot" /><span>本地优先 · 可追溯的 Agent 长期记忆</span><button @click="scrollTo('lp-integrations')">了解接入 <span>→</span></button></div>
    <div class="lp-main">
      <section class="lp-hero" aria-labelledby="lp-title">
        <div class="lp-eyebrow"><span /> MEMORY THAT EVOLVES WITH YOU</div>
        <h1 id="lp-title">让 AI 记住重要的事。<br /><span>也记得，事情会改变。</span></h1>
        <p>为你的 AI 助手接上长期记忆。<br class="lp-mobile-break" />从偏好、经历到工作方法，<br class="lp-desktop-break" />让每次对话接得上过去，也跟得上现在。</p>
        <div class="lp-hero-actions"><RouterLink to="/overview" class="lp-action lp-action-dark">打开记忆工作台 <span>↗</span></RouterLink><RouterLink to="/install" class="lp-action lp-action-light"><AppIcon name="layers" />开始接入 <span>→</span></RouterLink></div>
        <div class="lp-hero-note"><span>SQLite 本地存储</span><i /> <span>Python / HTTP API</span><i /><span>真实状态与证据链</span></div>
      </section>
      <section class="lp-showcase" aria-label="接入代码与记忆演化">
        <div class="lp-code-side">
          <div class="lp-code-toolbar"><div role="group" aria-label="接入代码示例"><button :class="{active:language==='python'}" :aria-pressed="language==='python'" @click="language='python';copyMessage='' "><IntegrationLogo name="python" />Python</button><button :class="{active:language==='http'}" :aria-pressed="language==='http'" @click="language='http';copyMessage='' "><AppIcon name="external" />HTTP API</button></div><button class="lp-copy" aria-label="复制接入示例" @click="copyCode"><AppIcon name="book" />复制</button></div>
          <div class="lp-code-caption"><span class="lp-code-dots"><i /><i /><i /></span><span>{{ language==='python'?'memory_quickstart.py':'search_memories.py' }}</span><span class="lp-copy-feedback" role="status">{{ copyMessage }}</span></div>
          <pre><code><span v-for="(line,index) in code.split('\n')" :key="index" class="lp-code-line"><span class="lp-line-number" aria-hidden="true">{{ index+1 }}</span><span>{{ line || ' ' }}</span></span></code></pre>
          <div class="lp-code-bottom"><span>简单接入，记忆规则由系统管理。</span><RouterLink to="/install">完整指南 →</RouterLink></div>
        </div>
        <div class="lp-memory-side">
          <div class="lp-demo-heading"><span><AppIcon name="activity" />一条记忆的变化</span><span class="lp-demo-label">偏好演化</span></div>
          <div class="lp-demo-tabs" role="group" aria-label="查看记忆变化阶段"><button v-for="(item,index) in moments" :key="item.label" :class="{active:demoStep===index}" :aria-pressed="demoStep===index" @click="demoStep=index"><span>{{ index+1 }}</span>{{ item.label }}</button></div>
          <div class="lp-demo-body" aria-live="polite"><div class="lp-quote"><span class="lp-user-avatar">A</span><span>“{{ moment.quote }}”</span></div><div class="lp-demo-connector"><span /></div><div class="lp-fact"><div><span class="lp-fact-key">饮品偏好</span><span class="lp-state lp-state-current">当前</span></div><strong>{{ moment.current }}</strong><p>alice / drink_preference</p></div><div v-if="moment.candidate" class="lp-secondary-fact"><span class="lp-state lp-state-candidate">候选</span><span>{{ moment.candidate }}</span><span class="lp-await">等待一致证据</span></div><div v-if="moment.history" class="lp-secondary-fact"><span class="lp-state lp-state-history">历史</span><span>{{ moment.history }}</span><span class="lp-await">保留演化记录</span></div><h2>{{ moment.title }}</h2><p class="lp-demo-note">{{ moment.note }}</p></div>
          <RouterLink to="/evolution" class="lp-demo-footer">在工作台体验记忆演化 <span>→</span></RouterLink>
        </div>
      </section>
      <section id="lp-integrations" class="lp-integrations" aria-labelledby="lp-integrations-title"><p id="lp-integrations-title">连接你正在使用的 Agent</p><div class="lp-integration-list"><RouterLink to="/install"><IntegrationLogo name="deepseek" />DeepSeek Harness</RouterLink><RouterLink to="/install"><IntegrationLogo name="openclaw" />OpenClaw</RouterLink><RouterLink to="/install"><IntegrationLogo name="hermes" />Hermes Agent</RouterLink><RouterLink to="/install"><IntegrationLogo name="python" />Python</RouterLink><RouterLink to="/install"><AppIcon name="external" />HTTP API</RouterLink></div></section>
      <LandingDemo />
      <section id="lp-capabilities" class="lp-capabilities" aria-labelledby="lp-capabilities-title"><div class="lp-section-heading"><span class="lp-section-kicker">MORE THAN A CHAT HISTORY</span><h2 id="lp-capabilities-title">记忆可以更新，<br />来路始终可查。</h2><p>将一次次对话，变成有状态、有依据、可管理的长期记忆。</p></div><div class="lp-features"><article><span class="lp-feature-icon"><AppIcon name="memory" /></span><h3>记住，分清是什么。</h3><p>事实与偏好、具体经历、工作流程，分为三类内容；临时信息可保留在工作层。</p><div class="lp-memory-types"><span>语义</span><span>情景</span><span>程序</span></div></article><article><span class="lp-feature-icon"><AppIcon name="activity" /></span><h3>改变，需要有依据。</h3><p>新旧信息发生冲突时先进入候选区，新的偏好得到确认后，再更新当前状态。</p><div class="lp-state-flow"><span>当前</span><b>→</b><span>候选</span><b>→</b><span>巩固</span></div></article><article><span class="lp-feature-icon"><AppIcon name="database" /></span><h3>管理，始终在你手中。</h3><p>在本地工作台查看来源、关联记录与历史状态，手动添加或删除记忆。</p><RouterLink to="/memories" class="lp-feature-link">打开记忆管理 →</RouterLink></article></div></section>
      <LandingHowItWorks />
      <section class="lp-bottom-cta"><span class="lp-section-kicker">START WITH ONE MEMORY</span><h2>让下一次对话，<span>从了解你开始。</span></h2><div><RouterLink to="/overview" class="lp-action lp-action-dark">进入工作台 <span>↗</span></RouterLink><RouterLink to="/install" class="lp-action lp-action-light">查看接入指南 <span>→</span></RouterLink></div></section>
    </div>
    <footer class="lp-footer"><RouterLink to="/" class="lp-footer-brand"><span class="lp-mark">m<span /></span>认知记忆系统</RouterLink><span>本地优先 · 认知科学启发式长期记忆</span><div><RouterLink to="/install">接入指南</RouterLink><a href="/docs" target="_blank" rel="noopener">接口文档 ↗</a><a href="https://github.com/kh1ye/cognitive-science-memory-system" target="_blank" rel="noopener">GitHub ↗</a></div></footer>
  </div>
</template>
<style scoped src="./landing.css"></style>
