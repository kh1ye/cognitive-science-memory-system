<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { useWorkspace } from '../composables/useWorkspace';
import { api } from '../lib/api';

const { state, refresh: load } = useWorkspace();
const filter = ref(''), query = ref('');
const records = computed(()=>state.memories), loading = computed(()=>state.loading), error = computed(()=>state.error);
const selectedId = ref(''), zoom = ref(1), yaw = ref(-.18), pitch = ref(.12), rotating = ref(false);
const stage = ref(null), dragging = ref(false), detailDialog = ref(null);
let timer, pointer=null;
const kinds = [
  { id:'episodic', label:'情景记忆', subtitle:'那些发生过的事', color:'#69ded4' },
  { id:'semantic', label:'语义记忆', subtitle:'逐渐积累的认知', color:'#88baff' },
  { id:'procedural', label:'程序记忆', subtitle:'方法与行动能力', color:'#c5a3ee' },
];
const owner=computed(()=>state.user);
function content(record) { return record.content || '未记录正文'; }
const all = computed(()=>records.value.filter(r=>kinds.some(k=>k.id===r.memory_type)).map(r=>({...r,display:content(r)})));
const visible = computed(()=>all.value.filter(r=>(!filter.value||r.memory_type===filter.value)&&(!query.value.trim()||r.display.toLowerCase().includes(query.value.trim().toLowerCase()))));
const selected=computed(()=>all.value.find(r=>r.id===selectedId.value));
let scrollLock = null;
function releaseDialog() {
  if (detailDialog.value?.open) detailDialog.value.close();
  if (!scrollLock) return;
  const saved=scrollLock; scrollLock=null;
  document.documentElement.style.overflow=saved.rootOverflow;
  document.documentElement.style.scrollbarGutter=saved.gutter;
  document.body.style.overflow=saved.bodyOverflow;
  if (saved.focus?.isConnected) saved.focus.focus({preventScroll:true});
  if (window.scrollX!==saved.x || window.scrollY!==saved.y) window.scrollTo({left:saved.x,top:saved.y,behavior:'instant'});
}
watch(()=>Boolean(selected.value), open=>{
  if (!open) { releaseDialog(); return; }
  scrollLock={x:window.scrollX,y:window.scrollY,focus:document.activeElement,
    rootOverflow:document.documentElement.style.overflow,
    bodyOverflow:document.body.style.overflow,gutter:document.documentElement.style.scrollbarGutter};
  document.documentElement.style.scrollbarGutter='stable';
  document.documentElement.style.overflow='hidden';
  document.body.style.overflow='hidden';
  detailDialog.value.showModal();
}, {flush:'post'});
function closeDetail(){selectedId.value='';}
function dismissBackdrop(event){
  if(event.target!==detailDialog.value)return;
  const box=detailDialog.value.getBoundingClientRect();
  if(event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom)closeDetail();
}
const rawRecord=ref(null), detailLoading=ref(false), detailError=ref('');
let detailVersion=0;
watch([selected,owner],async ([record,user])=>{
  const version=++detailVersion;rawRecord.value=null;detailError.value='';detailLoading.value=Boolean(record);
  if(!record)return;
  try {
    const path=record.storage_kind==='typed'
      ? `/api/architecture/objects/${encodeURIComponent(record.module)}/${encodeURIComponent(record.id)}`
      : `/api/memories/${encodeURIComponent(record.id)}`;
    const result=await api(`${path}?user_id=${encodeURIComponent(user)}`);
    if(version===detailVersion)rawRecord.value=result;
  } catch(e){if(version===detailVersion)detailError.value=e.message;}
  finally {if(version===detailVersion)detailLoading.value=false;}
});
function fieldValue(value){return typeof value==='object'?JSON.stringify(value,null,2):value===''?'""':String(value);}
const selectedKind=computed(()=>kinds.find(k=>k.id===selected.value?.memory_type));
const hubs=[[-.43,-.3,.3],[.42,-.15,.2],[-.08,.43,.3]];
function hash(text) { let n=2166136261; for (const ch of text) n=Math.imul(n^ch.charCodeAt(0),16777619); return (n>>>0)/4294967296; }
function project(x,y,z) {
  const xx=x*Math.cos(yaw.value)+z*Math.sin(yaw.value), zz=-x*Math.sin(yaw.value)+z*Math.cos(yaw.value);
  const yy=y*Math.cos(pitch.value)-zz*Math.sin(pitch.value), depth=y*Math.sin(pitch.value)+zz*Math.cos(pitch.value);
  const scale=1/(1-depth*.22);
  return {x:500+xx*340*zoom.value*scale,y:400+yy*340*zoom.value*scale,depth,scale};
}
const stars = Array.from({length:850},(_,i)=>{
  const z=1-2*(i+.5)/850, a=i*2.3999632297, r=Math.sqrt(1-z*z);
  return {x:r*Math.cos(a),y:z,z:r*Math.sin(a),radius:.45+hash('s'+i)*1.05,opacity:.15+hash('o'+i)*.65};
});
const projectedStars=computed(()=>stars.map(s=>({...project(s.x,s.y,s.z),radius:s.radius,opacity:s.opacity})));
const groups=computed(()=>kinds.map((k,i)=>({...k,...project(...hubs[i]),count:all.value.filter(r=>r.memory_type===k.id).length})));
const nodes=computed(()=>visible.value.map(r=>{
  const group=kinds.findIndex(k=>k.id===r.memory_type), siblings=all.value.filter(a=>a.memory_type===r.memory_type), i=siblings.findIndex(a=>a.id===r.id);
  const a=i*2.39996+group*.7, radius=.16+.32*Math.sqrt((i+.5)/Math.max(1,siblings.length));
  const h=hubs[group]; const p=project(h[0]+Math.cos(a)*radius,h[1]+Math.sin(a)*radius,(hash(r.id)-.5)*1.1);
  return {...r,...p,color:kinds[group].color,hub:groups.value[group]};
}).sort((a,b)=>a.depth-b.depth));
watch(owner,()=>{selectedId.value='';filter.value='';query.value='';});
watch(visible, rows=>{if(selectedId.value&&!rows.some(r=>r.id===selectedId.value))selectedId.value='';});
function reset(){zoom.value=1;yaw.value=-.18;pitch.value=.12;filter.value='';query.value='';}
function down(e){if(e.target.closest('[data-node],button,select,input'))return;pointer={id:e.pointerId,x:e.clientX,y:e.clientY};dragging.value=true;stage.value.setPointerCapture(e.pointerId);}
function move(e){if(!pointer)return;yaw.value+=(e.clientX-pointer.x)*.004;pitch.value=Math.max(-1.2,Math.min(1.2,pitch.value+(e.clientY-pointer.y)*.004));pointer.x=e.clientX;pointer.y=e.clientY;}
function up(){pointer=null;dragging.value=false;}
onMounted(()=>{timer=setInterval(()=>{if(rotating.value&&!dragging.value&&!selectedId.value)yaw.value+=.002;},40);});
onUnmounted(()=>{++detailVersion;clearInterval(timer);releaseDialog();});
</script>

<template>
  <section class="galaxy-page">
    <header class="galaxy-heading">
      <div><div class="galaxy-eyebrow">MEMORY ATLAS <span> / </span> 记忆星图</div><h1>让记忆，有迹可循<span>。</span></h1><p>每一个光点，都是一段可以重新打开的记忆。</p></div>
      <div class="galaxy-source"><span>当前空间 · {{ state.user }}<small>与记忆管理同步</small></span><button @click="load" :disabled="loading" aria-label="刷新记忆星图">↻</button></div>
    </header>
    <div class="galaxy-filters"><button :class="{active:!filter}" @click="filter=''">全部记忆 <span>{{ all.length }}</span></button><button v-for="k in kinds" :key="k.id" :class="{active:filter===k.id}" :style="{'--type':k.color}" @click="filter=filter===k.id?'':k.id"><i :style="{background:k.color}"/>{{ k.label }}<span>{{ all.filter(r=>r.memory_type===k.id).length }}</span></button><input v-model="query" aria-label="搜索星图记忆" placeholder="搜索一段记忆…" /></div>
    <div class="galaxy-layout">
      <div ref="stage" class="galaxy-stage" :class="{dragging}" @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="up" @wheel.prevent="zoom=Math.max(.55,Math.min(1.8,zoom-$event.deltaY*.001))">
        <div class="galaxy-stage-title"><span class="galaxy-live"/>我的记忆星图<small>{{ visible.length }} 个记忆节点</small></div>
        <svg viewBox="0 0 1000 800" class="galaxy-svg" aria-label="记忆节点星图">
          <defs><radialGradient id="atlas-haze"><stop stop-color="#88d3d2" stop-opacity=".15"/><stop offset="1" stop-color="#88d3d2" stop-opacity="0"/></radialGradient><filter id="atlas-glow" x="-200%" y="-200%" width="500%" height="500%"><feGaussianBlur stdDeviation="3"/></filter></defs>
          <ellipse cx="500" cy="440" rx="315" ry="340" fill="url(#atlas-haze)" transform="rotate(-25 500 440)"/>
          <circle cx="500" cy="400" :r="335*zoom" fill="none" stroke="#a5d4d4" stroke-opacity=".055"/>
          <g aria-hidden="true"><circle v-for="(s,i) in projectedStars" :key="i" :cx="s.x" :cy="s.y" :r="s.radius*s.scale" :fill="i%13===0?'#83dcd7':'#d9e8ee'" :opacity="s.opacity*(s.depth+2)/3"/></g>
          <g aria-hidden="true"><path v-for="n in nodes" :key="n.id" :d="`M${n.hub.x},${n.hub.y} Q${(n.x+n.hub.x)/2+35},${(n.y+n.hub.y)/2-25} ${n.x},${n.y}`" fill="none" :stroke="n.color" :stroke-opacity="selectedId===n.id?.65:.12" :stroke-width="selectedId===n.id?1.4:.7"/></g>
          <g v-for="g in groups" :key="g.id" v-show="!filter||filter===g.id" aria-hidden="true"><circle :cx="g.x" :cy="g.y" r="15" :fill="g.color" filter="url(#atlas-glow)" opacity=".5"/><circle :cx="g.x" :cy="g.y" r="4.2" :fill="g.color"/><text :x="g.x+14" :y="g.y-7" fill="#e8eff1" font-size="12">{{ g.label }}</text></g>
          <g v-for="n in nodes" :key="n.id" data-node role="button" tabindex="0" :aria-label="`查看记忆：${n.display}`" :aria-pressed="selectedId===n.id" class="galaxy-node" @click.stop="selectedId=n.id" @keydown.enter.prevent="selectedId=n.id" @keydown.space.prevent="selectedId=n.id">
            <title>{{ n.display }}</title><circle :cx="n.x" :cy="n.y" r="14" fill="transparent"/><circle :cx="n.x" :cy="n.y" :r="selectedId===n.id?13:8" :fill="n.color" filter="url(#atlas-glow)" :opacity="selectedId===n.id?.8:.4"/><circle :cx="n.x" :cy="n.y" :r="selectedId===n.id?4.5:2.6" :fill="n.color"/><circle v-if="selectedId===n.id" :cx="n.x" :cy="n.y" r="12" fill="none" :stroke="n.color" stroke-opacity=".65"/>
          </g>
        </svg>
        <div v-if="loading||error||!visible.length" class="galaxy-message" role="status"><strong>{{ loading?'正在连接记忆…':error?'暂时无法读取星图':query||filter?'没有找到这段记忆':'这片星空，等待第一段记忆' }}</strong><p>{{ error || (loading?'':'在记忆管理或个人助手中保存的长期记忆会同步到这里。') }}</p><button v-if="error" @click="load">重新加载</button></div>
        <div class="galaxy-stage-bottom"><span>拖动旋转 · 滚轮缩放 · 点击光点</span><div><button @click="rotating=!rotating" :aria-pressed="rotating">{{ rotating?'暂停旋转':'自动旋转' }}</button><button @click="zoom=Math.max(.55,zoom-.15)" aria-label="缩小星图">−</button><button @click="reset" aria-label="重置星图">{{ Math.round(zoom*100) }}%</button><button @click="zoom=Math.min(1.8,zoom+.15)" aria-label="放大星图">＋</button></div></div>
      </div>

    </div>
    <dialog ref="detailDialog" class="galaxy-detail-dialog" aria-label="记忆节点详情" aria-labelledby="galaxy-detail-title" @cancel.prevent="closeDetail" @close="closeDetail" @click="dismissBackdrop">
      <header class="galaxy-modal-header"><div><div class="galaxy-detail-kicker"><span :style="{background:selectedKind?.color}"/>{{ selectedKind?.label || '记忆' }}</div><h2 id="galaxy-detail-title">记忆详情</h2></div><button type="button" autofocus aria-label="关闭记忆详情" @click="closeDetail">×</button></header>
      <div v-if="selected" class="galaxy-detail-content">
        <p class="galaxy-memory-body">{{ selected.display }}</p>
        <h3 class="galaxy-fields-title">记忆字段</h3>
        <p v-if="detailLoading" class="galaxy-detail-note" role="status">正在读取记忆字段…</p>
        <p v-else-if="detailError" class="galaxy-detail-note" role="alert">{{ detailError }}</p>
        <dl v-else-if="rawRecord" class="galaxy-record-fields"><template v-for="(value,key) in rawRecord" :key="key"><dt>{{ key }}</dt><dd><pre>{{ fieldValue(value) }}</pre></dd></template></dl>
      </div>
    </dialog>
    <footer class="galaxy-footer"><span>当前空间 · {{ state.user }} · 展示已加载的 {{ all.length }} 条长期记忆</span><span>与记忆管理共用数据；工作记忆在对话中查看。</span></footer>
  </section>
</template>

<style scoped>
.galaxy-page{padding:34px 38px 22px;color:#dce5eb;max-width:1800px;margin:auto}.galaxy-heading{display:flex;justify-content:space-between;align-items:center;gap:24px;margin-bottom:30px}.galaxy-eyebrow{font-size:10px;letter-spacing:3px;color:#829295}.galaxy-eyebrow span{margin:0 10px;color:#48555e}.galaxy-heading h1{font-size:29px;font-weight:500;letter-spacing:1px;margin:12px 0}.galaxy-heading h1 span{color:#8bd8d1}.galaxy-heading p{font-size:12px;color:#8a959f;margin:0}.galaxy-source{display:flex;gap:10px;align-items:end}.galaxy-source label{font-size:10px;color:#879499;display:grid;gap:7px}.galaxy-source select{background:#11171c;border:1px solid #2a343b;color:#cad7df;padding:9px 12px;border-radius:7px;font:inherit;font-size:12px;min-width:180px}.galaxy-source>span{font-size:12px;color:#cad7df}.galaxy-source>span small{display:block;font-size:10px;color:#879499;margin-top:7px}.galaxy-source>button{height:34px;width:34px}.galaxy-page button{cursor:pointer;border:1px solid #28353c;background:#10181d;color:#c1d0d8;border-radius:7px}.galaxy-page button:hover{color:white;border-color:#6a969e}.galaxy-page button:focus-visible,.galaxy-node:focus-visible{outline:2px solid #b0f1e9;outline-offset:4px}.galaxy-filters{display:flex;gap:8px;align-items:center;margin-bottom:18px;flex-wrap:wrap}.galaxy-filters button{font-size:11px;padding:9px 12px;display:flex;align-items:center;gap:7px;background:transparent}.galaxy-filters button.active{background:#1b2b30;border-color:#568987;color:#e6f7f3}.galaxy-filters span{font-size:10px;color:#82969c;margin-left:6px}.galaxy-filters i,.galaxy-type-guide i{width:5px;height:5px;border-radius:50%;flex-shrink:0}.galaxy-filters input{margin-left:auto;width:180px;background:#10161b;border:1px solid #29333b;border-radius:7px;padding:9px 12px;font-size:11px;color:#e2e8ef}.galaxy-layout{display:grid;grid-template-columns:minmax(0,1fr);border:1px solid #263238;border-radius:12px;overflow:hidden;background:#050a0e}.galaxy-stage{position:relative;min-height:610px;overflow:hidden;cursor:grab;touch-action:none;background:radial-gradient(ellipse at 50% 65%,#0d1b20 0%,#070e13 38%,#04080c 76%)}.galaxy-stage.dragging{cursor:grabbing}.galaxy-svg{stroke:none;stroke-width:0;display:block;width:100%;height:100%;position:absolute;inset:0;min-height:610px}.galaxy-node{cursor:pointer;outline:none}.galaxy-node:hover circle:last-child{stroke:white;stroke-width:2}.galaxy-stage-title{position:absolute;left:23px;top:23px;font-size:11px;color:#bcccd3;display:flex;gap:8px;align-items:center;z-index:1;pointer-events:none}.galaxy-stage-title small{margin-left:9px;color:#677d88;font-size:10px}.galaxy-live{width:5px;height:5px;background:#81cfc4;border-radius:50%;box-shadow:0 0 10px #81cfc4}.galaxy-stage-bottom{position:absolute;bottom:20px;left:23px;right:20px;display:flex;justify-content:space-between;align-items:center;gap:10px}.galaxy-stage-bottom>span{font-size:10px;color:#697e89;pointer-events:none}.galaxy-stage-bottom>div{display:flex;gap:5px}.galaxy-stage-bottom button{font-size:10px;padding:6px 9px;background:#0b1218b8}.galaxy-detail-dialog{position:fixed;inset:0;margin:auto;padding:0;width:min(620px,calc(100vw - 32px));max-width:none;height:min(80dvh,760px);max-height:calc(100dvh - 32px);overflow:hidden;border:1px solid #344851;border-radius:16px;background:#101920;color:#dce5eb;box-shadow:0 28px 100px #000a;overscroll-behavior:contain}.galaxy-detail-dialog[open]{display:flex;flex-direction:column}.galaxy-detail-dialog::backdrop{background:#02070bb8;backdrop-filter:blur(4px)}.galaxy-modal-header{flex:none;display:flex;justify-content:space-between;align-items:center;padding:22px 26px;border-bottom:1px solid #293942}.galaxy-modal-header h2{font-size:18px;font-weight:500;margin:9px 0 0}.galaxy-modal-header button{width:36px;height:36px;flex-shrink:0;font-size:24px;line-height:1;background:#17242d}.galaxy-detail-kicker{font-size:10px;letter-spacing:1px;color:#8fa5ad;display:flex;align-items:center;gap:8px}.galaxy-detail-kicker>span{width:6px;height:6px;border-radius:50%}.galaxy-detail-content{padding:24px 26px;flex:1;min-height:0;overflow:auto;overscroll-behavior:contain;scrollbar-gutter:stable;touch-action:pan-y}.galaxy-memory-body{font-size:16px;line-height:1.9;color:#e3edf2;white-space:pre-wrap;overflow-wrap:anywhere;margin:0 0 24px}.galaxy-fields-title{font-size:11px;font-weight:500;color:#899fab;letter-spacing:1px;margin:0;padding-top:20px;border-top:1px solid #293942}.galaxy-record-fields{margin:0}.galaxy-record-fields dt{font-family:monospace;font-size:11px;margin:16px 0 6px;color:#8da8b9}.galaxy-record-fields dd{margin:0;border-bottom:1px solid #22313a;padding-bottom:12px}.galaxy-record-fields pre{white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word;font:11px/1.8 monospace;color:#d3e0e8;margin:0}.galaxy-detail-note{font-size:12px;line-height:1.9;color:#8ba0ac;margin-top:18px}
.galaxy-message{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;pointer-events:none;background:#050b1066}.galaxy-message strong{font-size:16px;font-weight:400}.galaxy-message p{font-size:12px;color:#92a6af;padding:0 20px;text-align:center}.galaxy-message button{pointer-events:auto;padding:8px 16px}.galaxy-footer{font-size:9px;color:#697d87;display:flex;justify-content:space-between;gap:15px;margin-top:14px;line-height:1.8}
@media(min-width:1500px){.galaxy-stage{min-height:720px}}@media(max-width:1050px){.galaxy-page{padding:24px}.galaxy-filters input{width:150px}.galaxy-stage-bottom>span{display:none}}@media(max-width:760px){.galaxy-heading{align-items:start;flex-direction:column;gap:18px}.galaxy-heading h1{font-size:25px}.galaxy-stage{min-height:490px}.galaxy-svg{min-height:490px;width:165%;left:-32.5%;max-width:none}.galaxy-filters input{margin-left:0;flex:1;min-width:140px}.galaxy-footer{flex-direction:column;gap:2px}.galaxy-modal-header{padding:18px 20px}.galaxy-detail-content{padding:20px}.galaxy-detail-dialog{height:84dvh}}
</style>
