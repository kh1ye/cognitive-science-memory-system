<script setup>
import codexLogo from "../assets/codex.svg";
import openclawLogo from "../assets/openclaw.svg";
import hermesLogo from "../assets/hermes.png";
import deepseekLogo from "../assets/deepseek.svg";
import pythonLogo from "../assets/python.svg";
defineProps({ name: { type: String, default: "terminal" } });
</script>
<template>
  <span class="integration-logo" aria-hidden="true">
    <img v-if="name === 'codex'" :src="codexLogo" alt="" />
    <img v-else-if="name === 'openclaw'" :src="openclawLogo" alt="" />
    <img v-else-if="name === 'hermes'" :src="hermesLogo" alt="" />
    <img v-else-if="name === 'deepseek'" :src="deepseekLogo" alt="" />
    <img v-else-if="name === 'python'" :src="pythonLogo" alt="" />
    <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
      <template v-if="name === 'terminal'"><path d="m5 6 6 6-6 6M13 18h6" /></template>
      <template v-else-if="name === 'agent'"><rect x="4" y="7" width="16" height="13" rx="4"/><path d="M12 3v4M2 12v4m20-4v4M9 16h6"/><circle cx="9" cy="12" r=".7"/><circle cx="15" cy="12" r=".7"/></template>
      <template v-else-if="name === 'sdk'"><path d="m8 7-5 5 5 5m8-10 5 5-5 5m-3-12-2 18"/></template>
      <template v-else><path d="M8 3v5m8-5v5M6 8h12v3a6 6 0 0 1-6 6v4m0-4a6 6 0 0 1-6-6"/></template>
    </svg>
  </span>
</template>
