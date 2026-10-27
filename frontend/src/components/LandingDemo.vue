<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";
import AppIcon from "./AppIcon.vue";
const scenes = [
  { label:"选择性记忆",title:"从对话中，留下重要信息。",description:"偏好与事实通过编码门后进入记忆；临时闲聊不必都被长期保存。",steps:["用户开始对话","补充个人偏好","检查信息与隐私条件","筛选值得保留的内容","形成一条长期记忆"],messages:[{text:"你好，今天有点忙。",role:"user",at:0},{text:"我喜欢用 Python 写脚本。",role:"user",at:1},{text:"明确的工具偏好，可以作为记忆候选。",role:"assistant",at:2}] },
  { label:"记忆演化",title:"偏好改变，记忆也随之更新。",description:"新说法先进入候选区。当新的偏好得到更多一致信息的支持，更新当前状态，同时保留过去的偏好。",steps:["读取当前偏好","收到不同的说法","新说法进入候选区","补充一致证据","新状态巩固，旧状态转为历史"],messages:[{text:"我之前喜欢喝茶。",role:"assistant",at:0},{text:"我现在更喜欢喝咖啡。",role:"user",at:1},{text:"最近一直更喜欢喝咖啡。",role:"user",at:3}] },
  { label:"可追溯管理",title:"知道记住了什么，也知道为什么。",description:"查看来源、状态和写入决策。遇到“不记忆”指令时停止保存，让每次变化都能在管理页找到依据。",steps:["用户表达长期偏好","定位本轮原文依据","记忆关联来源与状态","收到不记忆指令","拦截本次写入，已有记忆保留"],messages:[{text:"以后回答请简短一些。",role:"user",at:0},{text:"记录依据来自这条用户原话。",role:"assistant",at:1},{text:"下一句话不要记住。",role:"user",at:3}] },
];
const active=ref(0), frame=ref(0), progress=ref(0), visible=ref(false), pageVisible=ref(true), section=ref(null);
const FRAME_MS=1300, SCENE_MS=FRAME_MS*5, CYCLE_MS=SCENE_MS*scenes.length;
let timer, observer, elapsed=0;
const scene=computed(()=>scenes[active.value]);
const messages=computed(()=>scene.value.messages.filter(item=>frame.value>=item.at));
const running=computed(()=>visible.value&&pageVisible.value);
const snapshot=computed(()=>{
 if(active.value===0)return frame.value>=3?{title:"偏好 · 常用工具",value:"Python",status:"当前记忆",kind:"current",note:"留下明确偏好，让后续对话更懂你"}:{title:"选择性编码",value:frame.value<2?"等待有价值的信息":"检查写入条件…",status:"处理中",kind:"pending",note:"筛选值得长期保留的信息"};
 if(active.value===1)return {title:"偏好 · 饮品",value:frame.value>=4?"更喜欢咖啡":"喜欢喝茶",status:frame.value>=4?"已巩固":"当前记忆",kind:"current",note:frame.value>=4?"历史：喜欢喝茶":frame.value>=2?"候选：更喜欢咖啡 · 等待一致证据":"已有偏好保持有效"};
 return {title:"偏好 · 回答方式",value:"简短回答",status:frame.value>=4?"新写入已拦截":frame.value>=2?"来源可追溯":"提取原文依据",kind:frame.value>=4?"blocked":"current",note:frame.value>=4?"遵循不记忆指令，已有偏好不受影响":"来源：用户原话 · 状态：当前"};
});

function visibility(){pageVisible.value=!document.hidden;}
onMounted(()=>{
 pageVisible.value=!document.hidden;
 document.addEventListener('visibilitychange',visibility);
 if(window.IntersectionObserver){observer=new IntersectionObserver(entries=>{visible.value=entries[0]?.isIntersecting||false;},{threshold:.15});observer.observe(section.value);}else visible.value=true;
 timer=setInterval(()=>{
  if(!running.value)return;
  elapsed=(elapsed+50)%CYCLE_MS;
  active.value=Math.floor(elapsed/SCENE_MS);
  frame.value=Math.floor((elapsed%SCENE_MS)/FRAME_MS);
  progress.value=(elapsed%SCENE_MS)/SCENE_MS*100;
 },50);
});
onUnmounted(()=>{clearInterval(timer);observer?.disconnect();document.removeEventListener('visibilitychange',visibility);});
</script>
<template>
 <section ref="section" id="lp-live-demo" class="ld-section" aria-labelledby="ld-heading">
  <div class="ld-intro"><div><span class="ld-kicker">SEE MEMORY IN MOTION</span><h2 id="ld-heading">记忆如何发生，<br />亲眼看一遍。</h2></div><p>从一句话开始，看信息被选择、被更新、被追溯。<br />让记忆的每一步，都有清晰的解释。</p></div>
  <div class="ld-window">
   <div class="ld-titlebar"><span class="ld-dots"><i/><i/><i/></span><span>Cognitive Memory</span></div>
   <div class="ld-tabs" role="group" aria-label="动态演示场景"><div v-for="(item,index) in scenes" :key="item.label" :class="{active:active===index}" :aria-current="active===index?'step':undefined"><span>{{ item.label }}</span><span class="ld-tab-indicator"/><span class="ld-progress" :style="{width:active===index?`${progress}%`:'0%'}"/></div></div>
   <div class="ld-content">
    <div class="ld-copy"><span class="ld-counter">0{{ active+1 }} / 03</span><div class="ld-copy-text"><Transition name="ld-dissolve"><div :key="active"><h3>{{ scene.title }}</h3><p>{{ scene.description }}</p></div></Transition></div><RouterLink to="/evolution">在工作台体验 <span>↗</span></RouterLink></div>
    <div class="ld-stage">
     <div v-for="index in 3" :key="index" class="ld-backdrop" :class="[`ld-backdrop-${index}`, {active:active===index-1}]" aria-hidden="true"/>
     <div class="ld-phone"><div class="ld-phone-header"><span class="ld-phone-avatar">m</span><span>个人助手<small>记住你的偏好</small></span><span class="ld-online"/></div><TransitionGroup name="ld-message" tag="div" class="ld-messages"><div v-for="(message,index) in messages" :key="`${active}-${index}`" class="ld-bubble" :class="message.role">{{ message.text }}</div></TransitionGroup><div class="ld-phone-input"><span>消息与记忆，自然衔接</span><AppIcon name="arrowUp"/></div></div>
     <div class="ld-result-slot"><Transition name="ld-dissolve"><div class="ld-result" :key="`${active}-${snapshot.value}-${snapshot.note}`"><div class="ld-result-heading"><span><AppIcon name="memory"/>{{ snapshot.title }}</span><span class="ld-status" :class="snapshot.kind">{{ snapshot.status }}</span></div><strong>{{ snapshot.value }}</strong><p>{{ snapshot.note }}</p></div></Transition></div>
    </div>
   </div>
   <div class="ld-statusbar"><span><span class="ld-status-dot" :class="{playing:running}"/>记忆持续演化</span><span class="ld-stage-caption">{{ scene.steps[frame] }}</span><span>{{ frame+1 }} / 5</span></div>
  </div>
 </section>
</template>
<style scoped>
.ld-section{padding:65px 0;border-top:1px solid #e7e5e9;scroll-margin-top:24px}
.ld-intro{display:flex;justify-content:space-between;gap:40px;align-items:center;margin-bottom:34px}.ld-kicker{display:block;font-size:10px;letter-spacing:1.8px;color:#9a80aa;margin-bottom:17px;font-weight:600}.ld-intro h2{font-size:39px;line-height:1.4;font-weight:550;letter-spacing:-1.5px}.ld-intro>p{color:#8d8195;font-size:13px;line-height:1.95}
.ld-window{background:#252429;color:#eeeaf2;border:1px solid #423d48;border-radius:13px;overflow:hidden;box-shadow:0 16px 50px #24102f0a}.ld-titlebar{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:14px 18px;background:#19181c;font-size:11px;border-bottom:1px solid #434047}.ld-dots{display:flex;gap:6px;min-width:105px}.ld-dots i{display:block;width:7px;height:7px;border-radius:50%;background:#f18a7b}.ld-dots i:nth-child(2){background:#e6c672}.ld-dots i:nth-child(3){background:#9fc795}.ld-demo-tag{color:#a599af;font-size:9px}
.ld-tabs{display:flex;border-bottom:1px solid #4c454f}.ld-tabs>div{position:relative;flex:1;display:flex;align-items:center;justify-content:space-between;padding:12px 18px;border:0;border-right:1px solid #48424d;background:#19181d;color:#b0a5b9;font-size:11px;overflow:hidden;gap:9px}.ld-tabs>div:last-child{border-right:0}.ld-tabs>div.active{background:#29272d;color:#fff}.ld-tab-indicator{width:11px;height:11px;border:1px solid #5c5265;border-radius:50%}.active .ld-tab-indicator{border:2px solid #e5c56e}.ld-progress{height:2px;position:absolute;bottom:0;left:0;background:#e5c56e;transition:width .5s ease}
.ld-content{display:grid;grid-template-columns:1fr 1.18fr;gap:32px;align-items:center;padding:28px}.ld-copy{padding:15px 20px 15px 3px}.ld-counter{font:10px Consolas,monospace;color:#97889e;letter-spacing:2px}.ld-copy h3{font-size:25px;line-height:1.55;letter-spacing:-.5px;font-weight:550;margin:21px 0 15px}.ld-copy>p{font-size:12px;line-height:1.95;color:#b4a9bc;margin-bottom:25px}.ld-copy>a{display:inline-flex;gap:26px;align-items:center;font-size:11px;color:#e0c8f3;border-bottom:1px solid #74627e;padding-bottom:7px}
.ld-stage{position:relative;min-height:425px;border-radius:9px;background-color:#e8c976;background-image:radial-gradient(#fff6 .7px,transparent .7px),radial-gradient(ellipse at 20% 90%,#d9aa5966,transparent 60%);background-size:5px 5px,100% 100%;padding:22px 25px 28px;display:flex;flex-direction:column;align-items:center;justify-content:space-between;gap:18px}.ld-scene-1{background-color:#cab5e5}.ld-scene-2{background-color:#b8d0bc}
.ld-phone{background:#1c1a20;border:5px solid #2b252e;border-radius:25px;width:min(280px,100%);min-height:260px;box-shadow:0 16px 25px #45304820;display:flex;flex-direction:column;padding:13px 11px 12px}.ld-phone-header{display:flex;gap:8px;align-items:center;color:#f1e7f7;font-size:10px;border-bottom:1px solid #39313e;padding-bottom:11px}.ld-phone-header small{display:block;font-size:8px;color:#9f90ad;margin-top:1px}.ld-phone-avatar{display:grid;place-items:center;background:#3d3349;width:25px;height:25px;border-radius:8px;font:20px Georgia,serif}.ld-online{width:5px;height:5px;background:#9ec9a7;border-radius:50%;margin-left:auto}.ld-messages{display:flex;flex-direction:column;gap:9px;flex:1;padding:13px 0;min-height:155px}.ld-bubble{border-radius:11px;padding:9px 11px;font-size:10px;line-height:1.7;max-width:90%;overflow-wrap:anywhere}.ld-bubble.user{background:#cfb1f1;color:#362047;align-self:flex-end;border-bottom-right-radius:3px}.ld-bubble.assistant{background:#3a3342;color:#ddd0e6;align-self:flex-start;border-bottom-left-radius:3px}.ld-phone-input{display:flex;justify-content:space-between;align-items:center;color:#81708d;font-size:8px;background:#29232f;padding:7px 9px;border-radius:8px}.ld-phone-input svg{width:11px;height:11px}.ld-result{width:100%;border:1px solid #ffffff9c;background:#fffdf6f2;box-shadow:0 5px 20px #30233512;border-radius:8px;padding:13px 15px;color:#473851;min-height:97px;animation:ld-result-in .35s ease}.ld-result-heading{display:flex;justify-content:space-between;align-items:center;gap:9px;font-size:10px}.ld-result-heading>span:first-child{display:flex;align-items:center;gap:5px;color:#8d789b}.ld-result-heading svg{width:12px;height:12px}.ld-status{font-size:8px;background:#e5eee4;color:#668265;padding:2px 5px;border-radius:4px;white-space:nowrap}.ld-status.pending{background:#eee5d4;color:#998253}.ld-status.blocked{background:#f2dfe1;color:#a76771}.ld-result strong{display:block;font-size:18px;font-weight:550;margin-top:5px;letter-spacing:-.3px}.ld-result p{font-size:9px;color:#a08aac;margin-top:4px}.ld-statusbar{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:11px 19px;border-top:1px solid #45404a;color:#ac9fb6;font-size:10px}.ld-statusbar>span:first-child{display:flex;gap:7px;align-items:center;white-space:nowrap}.ld-status-dot{width:5px;height:5px;background:#84778d;border-radius:50%}.ld-status-dot.playing{background:#d9c27a}.ld-stage-caption{text-align:center;color:#d6c7df}.ld-disclaimer{text-align:center;font-size:10px;color:#a197a8;line-height:1.8;margin-top:14px!important}
.ld-message-enter-active{transition:opacity .35s,transform .35s}.ld-message-enter-from{opacity:0;transform:translateY(9px)}.ld-message-move{transition:transform .35s}@keyframes ld-result-in{from{opacity:.4;transform:translateY(5px)}to{opacity:1;transform:translateY(0)}}
@media(max-width:800px){.ld-content{gap:22px;padding:22px}.ld-copy{padding-right:0}.ld-copy h3{font-size:22px}.ld-stage{padding:20px 15px;min-height:425px}.ld-intro{gap:24px}.ld-intro>p{font-size:12px}.ld-intro h2{font-size:32px}}
@media(max-width:600px){.ld-section{padding:40px 0}.ld-intro{display:block}.ld-intro h2{font-size:31px}.ld-intro>p{margin-top:18px}.ld-content{grid-template-columns:1fr;padding:18px;gap:20px}.ld-copy{padding:5px}.ld-copy h3{font-size:22px;margin:12px 0}.ld-copy>p{font-size:12px;margin-bottom:16px}.ld-stage{min-height:415px}.ld-titlebar{padding:12px}.ld-dots{min-width:auto;gap:4px}.ld-titlebar>span:nth-child(2){font-size:10px}.ld-demo-tag{font-size:8px}.ld-tabs>div{padding:11px;font-size:10px}.ld-stage-caption{max-width:60%;font-size:9px}.ld-statusbar{padding:11px;font-size:9px}.ld-result p{font-size:10px}.ld-bubble{font-size:11px}}
@media(prefers-reduced-motion:reduce){.ld-progress,.ld-message-enter-active,.ld-message-move{transition:none}.ld-result{animation:none}}

/* The stage stays in place while its contents flow through it. */
.ld-stage{transition:background-color 1.8s ease;min-height:445px}
.ld-phone{height:280px;min-height:280px;flex-shrink:0}
.ld-messages{position:relative;overflow:hidden;min-height:0;height:180px;flex:1}
.ld-bubble{flex-shrink:0}
.ld-message-enter-active{transition:opacity .65s ease,transform .75s cubic-bezier(.2,.7,.2,1);transition-delay:.05s}
.ld-message-leave-active{transition:opacity .45s ease,transform .55s ease;position:absolute;max-width:90%}
.ld-message-leave-active.user{right:0}.ld-message-leave-active.assistant{left:0}
.ld-message-enter-from{opacity:0;transform:translateY(7px)}
.ld-message-leave-to{opacity:0;transform:translateY(-9px)}
.ld-message-move{transition:transform .65s cubic-bezier(.2,.7,.2,1)}
.ld-progress{transition:width .08s linear}
.ld-result-slot{position:relative;width:100%;height:108px;flex-shrink:0}
.ld-result-slot .ld-result{position:absolute;inset:0;animation:none;margin:0;min-height:108px}
.ld-copy-text{position:relative;min-height:215px;margin-top:20px}
.ld-copy-text>div{position:absolute;inset:0}
.ld-copy-text h3{margin-top:0}
.ld-copy-text p{font-size:12px;line-height:1.95;color:#b4a9bc;margin:0 0 25px}
.ld-dissolve-enter-active{transition:opacity .7s ease,filter .7s ease;transition-delay:.04s}
.ld-dissolve-leave-active{transition:opacity .5s ease,filter .5s ease}
.ld-dissolve-enter-from{opacity:0;filter:blur(2px)}
.ld-dissolve-leave-to{opacity:0;filter:blur(2px)}
@media(max-width:800px){.ld-copy-text{min-height:250px}}
@media(max-width:600px){.ld-copy-text{min-height:175px;margin-top:14px}.ld-stage{min-height:445px}}
@media(prefers-reduced-motion:reduce){.ld-stage,.ld-message-enter-active,.ld-message-leave-active,.ld-message-move,.ld-dissolve-enter-active,.ld-dissolve-leave-active,.ld-progress{transition:none;transition-delay:0s}.ld-result{animation:none}}

.ld-stage{isolation:isolate;background:#b994df;background-image:none}
.ld-backdrop{position:absolute;inset:0;border-radius:inherit;opacity:0;transition:opacity 1.15s ease-in-out;pointer-events:none;z-index:-1;background-size:5px 5px,100% 100%}
.ld-backdrop.active{opacity:1}
.ld-backdrop-1{background-image:radial-gradient(#ffffff33 .6px,transparent .8px),linear-gradient(145deg,#dec7f4,#b28bdf 55%,#8156b2)}
.ld-backdrop-2{background-image:radial-gradient(#ffffff33 .6px,transparent .8px),linear-gradient(145deg,#e5c4e9,#bd8ed9 55%,#9161b8)}
.ld-backdrop-3{background-image:radial-gradient(#ffffff33 .6px,transparent .8px),linear-gradient(145deg,#d2d2f5,#a39adf 55%,#7664b5)}
.ld-phone{box-shadow:0 20px 40px #4b24642b}
.ld-result-slot .ld-result{background:#fffcfff2;border-color:#ffffffa1;box-shadow:0 8px 25px #593c7514}
@media(prefers-reduced-motion:reduce){.ld-backdrop{transition:none}.ld-dissolve-enter-from,.ld-dissolve-leave-to{filter:none}}
</style>
