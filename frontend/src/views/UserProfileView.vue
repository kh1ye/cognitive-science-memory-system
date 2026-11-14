<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import AppIcon from "../components/AppIcon.vue";
import { api } from "../lib/api";
import { formatDate } from "../lib/format";
import { useWorkspace } from "../composables/useWorkspace";

const emit = defineEmits(["close"]);
const { state, openMemory, refresh } = useWorkspace();
const profile = ref(null), loading = ref(true), saving = ref(false), error = ref("");
const editingId = ref(null), editValue = ref("");
let version = 0;
const items = computed(() => profile.value?.items || []);
const knownCount = computed(() => items.value.length);
const displayName = computed(() => profile.value?.preferences?.name || state.user);
const latest = computed(() => items.value.map(item => item.updated_at).filter(Boolean).sort().at(-1));
function statement(item) { return item.description || item.value; }

async function load() {
  if (saving.value) return;
  const user = state.user, request = ++version;
  loading.value = true;
  error.value = "";
  try {
    const result = await api(`/api/profile?user_id=${encodeURIComponent(user)}`);
    if (user === state.user && request === version) profile.value = result;
  } catch (e) { if (user === state.user && request === version) error.value = e.message; }
  finally { if (user === state.user && request === version) loading.value = false; }
}
async function changeItem(item, remove = false) {
  if (saving.value || state.sending) return;
  const user = state.user, request = ++version;
  saving.value = true;
  error.value = "";
  try {
    const result = await api(`/api/profile/${encodeURIComponent(item.id)}?user_id=${encodeURIComponent(user)}`, {
      method: remove ? "DELETE" : "PATCH",
      ...(remove ? {} : { body: JSON.stringify({ user_id: user, value: editValue.value }) }),
    });
    if (user !== state.user || request !== version) return;
    profile.value = result;
    editingId.value = null;
    await refresh();
  } catch (e) { if (user === state.user && request === version) error.value = e.message; }
  finally {
    saving.value = false;
    if (user !== state.user) load();
  }
}
watch(() => state.user, () => {
  ++version;
  profile.value = null;
  editingId.value = null;
  load();
}, { immediate: true });
onMounted(() => window.addEventListener("focus", load));
onBeforeUnmount(() => { ++version; window.removeEventListener("focus", load); });
</script>

<template>
  <section class="user-profile-page" :aria-label="$t('用户画像')">
    <div class="portrait-content">
    <header class="portrait-heading">
      <div><p class="portrait-eyebrow">{{ $t('你的专属画像') }}</p><h1>{{ $t('个人助手对你的了解') }}</h1><p class="portrait-description">{{ $t('这里是助手目前记住的你。你可以随时补充或纠正。') }}</p></div>
      <button class="button portrait-back" @click="emit('close')"><AppIcon name="chat" />{{ $t('返回对话') }}</button>
    </header>
    <div v-if="error" class="portrait-error" role="alert"><span>{{ error }}</span><button class="text-button" :disabled="saving" @click="load">{{ $t('重试') }}</button></div>
    <p v-if="loading" class="portrait-loading" role="status">{{ $t('正在整理助手对你的了解…') }}</p>
    <template v-else-if="profile">
      <section class="portrait-summary" :aria-label="$t('画像概览')">
        <div class="portrait-person"><span class="portrait-avatar">{{ displayName.slice(0, 1).toUpperCase() }}</span><div><strong>{{ displayName }}</strong><span>{{ $t('随着交流，持续了解') }}</span></div></div>
        <div class="portrait-stat"><strong>{{ knownCount }}<small>{{ $t('条') }}</small></strong><span>{{ $t('已记住的个人信息') }}</span></div>

        <div class="portrait-updated"><span class="portrait-live-dot" /><div><strong>{{ $t('与当前记忆同步') }}</strong><span>{{ latest ? formatDate(latest) : $t('等待你的第一次分享') }}</span></div></div>
      </section>
      <div class="portrait-layout">
        <div class="portrait-sections">
          <p class="portrait-list-intro">{{ $t('目前，我了解到这样的你') }}</p>
          <p v-if="knownCount < 3" class="portrait-sparse">{{ $t('目前可确认的信息还不多，我会在后续交流中继续了解你。') }}</p>
          <section v-for="(item, index) in items" :key="item.id" class="portrait-section portrait-fact">
            <header class="portrait-section-heading"><span class="portrait-number">{{ index + 1 }}.</span><div><h2>{{ statement(item) }}</h2></div></header>
            <div class="portrait-fact-body">
              <form v-if="editingId === item.id" class="portrait-edit" @submit.prevent="changeItem(item)"><textarea v-model="editValue" :aria-label="$t('修改画像内容')" maxlength="2000" rows="3" required /><div><button class="button primary" :disabled="saving || state.sending || !editValue.trim()">{{ $t('保存') }}</button><button type="button" class="button" :disabled="saving" @click="editingId = null">{{ $t('取消') }}</button></div></form>
              <details v-else-if="item.evidence_text" class="portrait-evidence"><summary>{{ $t('记忆依据') }}</summary><p>{{ item.evidence_text }}</p></details>
              <div class="portrait-fact-footer"><span>{{ item.updated_at ? formatDate(item.updated_at) : $t('已确认') }}</span><div class="portrait-fact-actions"><button class="text-button" @click="openMemory(item.id)">{{ $t('查看来源') }}</button><button class="text-button" :disabled="saving || state.sending" @click="editingId = item.id; editValue = item.value">{{ $t('修改') }}</button><button class="text-button portrait-delete" :disabled="saving || state.sending" @click="changeItem(item, true)">{{ $t('删除') }}</button></div></div>
            </div>
          </section>
          <footer class="portrait-bottom"><AppIcon name="chat" /><div><strong>{{ $t('让助手再多了解你一点') }}</strong><p>{{ $t('继续聊聊你的近况，或回到偏好设置补充信息。已确认的记忆会自然体现在这里。') }}</p></div><button class="text-button" @click="emit('close')">{{ $t('去聊聊') }} →</button></footer>
        </div>
      </div>
    </template>
    </div>
  </section>
</template>

<style scoped>
.user-profile-page { width:100%; min-width:0; padding:38px 32px 48px; color:var(--ink); overflow:auto; overflow-wrap:anywhere; }
.portrait-content { width:100%; max-width:800px; margin:0 auto; }
.portrait-heading { display:flex; justify-content:space-between; align-items:center; gap:24px; margin-bottom:26px; }
.portrait-heading>div { min-width:0; }
.portrait-eyebrow { color:var(--blue); font-size:11px; margin:0 0 10px; }
.portrait-heading h1 { font-size:25px; font-weight:600; letter-spacing:-.6px; margin:0 0 10px; }
.portrait-description { color:var(--muted); line-height:1.8; font-size:12px; margin:0; }
.portrait-back { display:flex; gap:7px; flex-shrink:0; font-size:12px; }
.portrait-summary { display:grid; grid-template-columns:1.3fr .8fr 1fr; align-items:center; gap:22px; padding:20px 22px; background:var(--surface, #fff); border:1px solid var(--line); border-radius:12px; margin-bottom:24px; }
.portrait-person { display:flex; align-items:center; gap:12px; min-width:0; }
.portrait-avatar { display:grid; place-items:center; width:38px; height:38px; flex-shrink:0; border-radius:11px; background:var(--accent-soft, #e9edfa); color:var(--blue); font-size:17px; }
.portrait-person>div { min-width:0; display:grid; gap:4px; }
.portrait-person strong { font-size:13px; overflow-wrap:anywhere; font-weight:550; }
.portrait-person div>span,.portrait-stat>span,.portrait-updated div>span { color:var(--muted); font-size:10px; }
.portrait-stat { border-left:1px solid var(--line); padding-left:22px; display:grid; gap:3px; }
.portrait-stat>strong { font-size:22px; font-weight:500; line-height:1.3; }
.portrait-stat small { color:var(--muted); font-size:11px; padding-left:6px; }
.portrait-updated { display:flex; gap:8px; align-items:flex-start; }
.portrait-updated>div { display:grid; gap:5px; }
.portrait-updated strong { font-size:11px; font-weight:400; color:var(--muted); }
.portrait-live-dot { width:5px; height:5px; border-radius:50%; background:var(--green); margin-top:5px; flex-shrink:0; }
.portrait-sections { min-width:0; padding:6px 24px 0; border:1px solid var(--line); border-radius:12px; background:var(--surface, #fff); }
.portrait-list-intro { margin:0; padding:17px 0 14px; color:var(--muted); font-size:11px; border-bottom:1px solid var(--line); }
.portrait-section { min-width:0; padding:20px 0 18px; border-bottom:1px solid var(--line); }
.portrait-section-heading { display:flex; align-items:baseline; gap:13px; margin-bottom:9px; }
.portrait-number { font-size:17px; line-height:1.5; color:var(--blue); width:23px; flex-shrink:0; font-variant-numeric:tabular-nums; }
.portrait-section-heading h2 { font-size:15px; font-weight:500; margin:0; line-height:1.8; white-space:pre-wrap; }
.portrait-fact-body { padding-left:36px; }
.portrait-evidence { margin:0 0 12px; color:var(--muted); font-size:11px; }
.portrait-evidence summary { cursor:pointer; width:fit-content; line-height:1.8; }
.portrait-evidence summary:hover { color:var(--ink); }
.portrait-evidence p { padding:10px 13px; margin:8px 0 0; background:var(--paper); border-left:2px solid var(--line); border-radius:0 6px 6px 0; font-size:12px; white-space:pre-wrap; line-height:1.8; }
.portrait-fact-footer { display:flex; gap:12px; justify-content:space-between; align-items:center; }
.portrait-fact-footer>span { font-size:10px; color:var(--muted); }
.portrait-fact-actions { display:flex; gap:14px; }
.portrait-fact-actions button { font-size:11px; }
.portrait-delete { color:var(--muted); }
.portrait-delete:hover { color:#da8b92; }
.portrait-edit { margin:12px 0; }
.portrait-edit textarea { width:100%; resize:vertical; padding:12px; border:1px solid var(--line); border-radius:8px; background:var(--paper); color:var(--ink); font:inherit; }
.portrait-edit>div { display:flex; gap:8px; margin-top:10px; }
.portrait-edit .button { font-size:12px; }
.portrait-sparse { color:var(--muted); font-size:12px; line-height:1.9; }
.portrait-bottom { display:flex; align-items:center; gap:12px; padding:20px 0; color:var(--muted); }
.portrait-bottom>i { color:var(--blue); }
.portrait-bottom strong { color:var(--ink); font-size:12px; font-weight:500; }
.portrait-bottom p { font-size:10px; line-height:1.8; margin:4px 0 0; }
.portrait-bottom>button { margin-left:auto; flex-shrink:0; color:var(--blue); font-size:11px; }
.portrait-error { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:14px; margin:0 0 20px; border:1px solid #914151; border-radius:10px; color:#da8b92; }
.portrait-loading { padding:32px 0; color:var(--muted); }
@media(max-width:700px) { .user-profile-page { padding:24px 20px; } .portrait-summary { grid-template-columns:1fr 1fr; gap:16px; padding:18px; } .portrait-updated { grid-column:1/-1; padding-top:12px; border-top:1px solid var(--line); } .portrait-updated>div { display:flex; flex-wrap:wrap; gap:10px; } }
@media(max-width:480px) { .user-profile-page { padding:22px 14px; } .portrait-heading { align-items:flex-start; gap:16px; flex-direction:column; } .portrait-heading h1 { font-size:23px; } .portrait-sections { padding:4px 16px 0; } .portrait-fact-footer { align-items:flex-start; flex-direction:column; gap:9px; } .portrait-bottom>i { display:none; } .portrait-bottom p { max-width:220px; } }
</style>
