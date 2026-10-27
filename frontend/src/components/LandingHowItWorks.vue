<script setup>
import { onMounted, onUnmounted, ref } from 'vue';
import AppIcon from './AppIcon.vue';
const root=ref(null), running=ref(true);
let observer, inView=true;
const effects=[];
function track(effect){
 // Canceling an infinite animation rejects these lifecycle promises normally.
 effect.finished?.catch(()=>{});
 effect.ready?.catch(()=>{});
 effects.push(effect);
}
function sync(){
 running.value=inView&&!document.hidden;
 for(const effect of effects)running.value?effect.play():effect.pause();
}
onMounted(()=>{
 const el=root.value;
 const reduced=window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
 const duration=18000;
 function animate(selector,frames,extra={}){
  el.querySelectorAll(selector).forEach(node=>{
   if(typeof node.animate!=='function')return;
   const normalized=reduced?frames.map(({transform,...frame})=>frame):frames;
   track(node.animate(normalized,{duration,iterations:Infinity,fill:'both',...extra}));
  });
 }
 // One shared, continuous film-like timeline; no scene DOM replacement.
 animate('.hw-input',[
  {offset:0,opacity:0,transform:'translateY(42px) scale(.96)'},
  {offset:.07,opacity:1,transform:'translateY(0) scale(1)',easing:'ease-out'},
  {offset:.19,opacity:1,transform:'translateY(0) scale(1)'},
  {offset:.31,opacity:0,transform:'translateY(-48px) scale(.88)'},
  {offset:1,opacity:0,transform:'translateY(-48px) scale(.88)'},
 ]);
 animate('.hw-stream',[
  {offset:0,opacity:0,transform:'translateY(-20px)'},
  {offset:.18,opacity:0,transform:'translateY(-20px)'},
  {offset:.25,opacity:1,transform:'translateY(10px)'},
  {offset:.34,opacity:0,transform:'translateY(55px)'},{offset:1,opacity:0},
 ]);
 animate('.hw-learning',[
  {offset:0,opacity:0,transform:'translateY(32px) scale(.94)'},
  {offset:.25,opacity:0,transform:'translateY(32px) scale(.94)'},
  {offset:.34,opacity:1,transform:'translateY(0) scale(1)'},
  {offset:.45,opacity:1,transform:'translateY(0) scale(1)'},
  {offset:.55,opacity:0,transform:'translateY(-38px) scale(.86)'},{offset:1,opacity:0},
 ]);
 animate('.hw-scan',[
  {offset:0,transform:'translateY(0)',opacity:0},{offset:.33,transform:'translateY(0)',opacity:1},
  {offset:.48,transform:'translateY(250px)',opacity:1},{offset:.52,opacity:0},{offset:1,opacity:0},
 ]);
 animate('.hw-memory',[
  {offset:0,opacity:0,transform:'translateY(30px) scale(.9)'},
  {offset:.48,opacity:0,transform:'translateY(30px) scale(.9)'},
  {offset:.55,opacity:1,transform:'translateY(0) scale(1)'},
  {offset:.61,opacity:1,transform:'translateY(0) scale(1)'},
  {offset:.71,opacity:0,transform:'translateY(-52px) scale(.8)'},{offset:1,opacity:0},
 ]);
 animate('.hw-question',[
  {offset:0,opacity:0,transform:'translateY(32px)'},{offset:.6,opacity:0,transform:'translateY(32px)'},
  {offset:.69,opacity:1,transform:'translateY(0)'},{offset:.92,opacity:1,transform:'translateY(0)'},
  {offset:1,opacity:0,transform:'translateY(-24px)'},
 ]);
 animate('.hw-evidence',[
  {offset:0,opacity:0,transform:'translateY(-12px)'},{offset:.7,opacity:0,transform:'translateY(-12px)'},
  {offset:.78,opacity:1,transform:'translateY(0)'},{offset:.92,opacity:1,transform:'translateY(0)'},
  {offset:1,opacity:0,transform:'translateY(-15px)'},
 ]);
 animate('.hw-answer',[
  {offset:0,opacity:0,transform:'translateY(24px)'},{offset:.78,opacity:0,transform:'translateY(24px)'},
  {offset:.86,opacity:1,transform:'translateY(0)'},{offset:.92,opacity:1,transform:'translateY(0)'},
  {offset:1,opacity:0,transform:'translateY(-12px)'},
 ]);
 animate('.hw-status-save',[
  {offset:0,opacity:0},{offset:.49,opacity:0},{offset:.56,opacity:1},{offset:.61,opacity:1},{offset:.67,opacity:0},{offset:1,opacity:0},
 ]);
 animate('.hw-status-recall',[
  {offset:0,opacity:0},{offset:.74,opacity:0},{offset:.82,opacity:1},{offset:.93,opacity:1},{offset:1,opacity:0},
 ]);
 animate('.hw-timeline > span',[{transform:'scaleX(0)'},{transform:'scaleX(1)'}]);
 el.querySelectorAll('.hw-steps li').forEach((node,index)=>{
  if(typeof node.animate!=='function')return;
  track(node.animate([
   {offset:0,color:'#a776d0'},{offset:.28,color:'#a776d0'},
   {offset:.34,color:'#c2b8c7'},{offset:.95,color:'#c2b8c7'},{offset:1,color:'#a776d0'},
  ],{duration,iterations:Infinity,delay:-duration*(3-index)/3}));
 });
 if(effects.length){
  el.dataset.animated='true';
  const start=document.timeline?.currentTime;
  if(typeof start==='number')effects.forEach(effect=>{effect.startTime=start;});
 }
 if(window.IntersectionObserver){observer=new IntersectionObserver(entries=>{inView=Boolean(entries[0]?.isIntersecting);sync();},{threshold:.05});observer.observe(el);}
 document.addEventListener('visibilitychange',sync);
 sync();
});
onUnmounted(()=>{effects.forEach(effect=>effect.cancel());observer?.disconnect();document.removeEventListener('visibilitychange',sync);});
</script>
<template>
 <section id="lp-evolution" ref="root" class="hw-section" :style="{'--hw-play':running?'running':'paused'}" aria-labelledby="hw-heading">
  <div class="hw-heading"><span>HOW IT WORKS</span><h2 id="hw-heading">从一句话开始，<br /><strong>记住，再自然地想起。</strong></h2></div>
  <div class="hw-panel">
   <ol class="hw-steps"><li><span class="hw-node"/><div><span class="hw-number">01</span><h3>添加</h3><p>输入一段对话或明确的事实，<br />从你的原话开始。</p></div></li><li><span class="hw-node"/><div><span class="hw-number">02</span><h3>学习</h3><p>提取有依据的信息，检查隐私条件，<br />交给记忆规则判断如何保存。</p></div></li><li><span class="hw-node"/><div><span class="hw-number">03</span><h3>取回</h3><p>当下一次问题到来，<br />找回相关记忆作为回答依据。</p></div></li></ol>
   <div class="hw-stage" role="img" aria-label="记忆流程：添加 Python 偏好，提取并保存，在后续问题中找回相关记忆。">
    <div class="hw-grain"/>
    <div class="hw-orbit hw-orbit-one"/><div class="hw-orbit hw-orbit-two"/>
    <div class="hw-caption">COGNITIVE MEMORY / REMEMBER & RECALL</div>
    <div class="hw-input hw-animated"><div class="hw-bubble-icon">A</div><div><small>用户原话</small><p>我喜欢用 Python 写自动化脚本。</p></div><AppIcon name="arrowUp"/></div>
    <div class="hw-stream hw-animated"><span/><span/><span/><span/></div>
    <div class="hw-learning hw-animated"><div class="hw-card-top"><span><AppIcon name="memory"/>选择性编码</span><b>原文证据</b></div><div class="hw-field"><span>主题</span><strong>编程语言偏好</strong></div><div class="hw-field"><span>取值</span><strong>Python</strong></div><div class="hw-field hw-gate"><span>写入条件</span><strong>通过后写入当前记忆</strong></div><div class="hw-scan"/></div>
    <div class="hw-memory hw-animated"><span class="hw-mini-mark">m</span><span><small>已记住偏好</small><strong>偏好使用 Python</strong></span><span class="hw-check">✓</span></div>
    <div class="hw-question hw-animated"><span>下一次对话</span><p>写自动化脚本，我适合用什么？</p></div>
    <div class="hw-evidence hw-animated"><AppIcon name="database"/><span>从记忆找回：<strong>偏好使用 Python</strong></span></div>
    <div class="hw-answer hw-animated"><span class="hw-mini-mark">m</span><p>可以从 Python 开始，<br /><strong>这也是你之前提到的偏好。</strong></p></div>
    <div class="hw-status-save hw-animated">✓ 记忆已更新</div><div class="hw-status-recall hw-animated">✓ 已找到相关记忆</div>
    <div class="hw-timeline"><span/></div>
   </div>
  </div>
  <div class="hw-footnote"><RouterLink to="/evolution">体验记忆流程 →</RouterLink></div>
 </section>
</template>
<style scoped>
.hw-section{padding:64px 0;border-block:1px solid #e7e5e9;scroll-margin-top:24px;--hw-duration:24s}.hw-heading{margin-bottom:37px}.hw-heading>span{font-size:10px;letter-spacing:1.8px;font-weight:600;color:#9a80aa;display:block;margin-bottom:18px}.hw-heading h2{font-size:39px;line-height:1.45;letter-spacing:-1.5px;font-weight:500;color:#a79aac}.hw-heading strong{font-weight:550;color:#28212e}.hw-panel{display:grid;grid-template-columns:.76fr 1.4fr;gap:45px;padding:38px;border:1px solid #e0d8e7;border-radius:13px;background:#fcfbfd;align-items:center}.hw-steps{list-style:none;margin:0;padding:0;display:flex;flex-direction:column}.hw-steps li{display:flex;gap:17px;position:relative;min-height:135px;color:#b5aaba;animation:hw-step var(--hw-duration) linear infinite;animation-play-state:var(--hw-play)}.hw-steps li:nth-child(2){animation-delay:-16s}.hw-steps li:nth-child(3){animation-delay:-8s}.hw-steps li:last-child{min-height:105px}.hw-node{width:12px;height:12px;border-radius:50%;background:currentColor;flex-shrink:0;position:relative;margin-top:9px;box-shadow:0 0 0 5px #fcfbfd;z-index:1}.hw-steps li:not(:last-child):after{content:"";position:absolute;top:22px;bottom:0;left:5px;width:1px;background:#e4dce9}.hw-number{font:9px Consolas,monospace;letter-spacing:1px;opacity:.75}.hw-steps h3{font-size:23px;font-weight:550;letter-spacing:-.5px;margin:0 0 11px}.hw-steps p{font-size:11px;line-height:1.95;margin:0}.hw-stage{position:relative;min-height:410px;overflow:hidden;border-radius:10px;isolation:isolate;background:linear-gradient(145deg,#d7bcf1,#b18ade 55%,#7851af);color:#fff}.hw-grain{position:absolute;inset:0;background-image:radial-gradient(#fff5 .6px,transparent .7px);background-size:4px 4px;opacity:.35;z-index:-1}.hw-orbit{position:absolute;width:450px;height:450px;left:-160px;top:120px;border:1px solid #f3dfff27;border-radius:50%;box-shadow:0 0 0 28px #f8eaff0a,0 0 0 60px #f8eaff09,0 0 0 100px #f8eaff08;z-index:-1}.hw-orbit-two{left:auto;right:-230px;top:-270px;transform:scale(1.3)}.hw-caption{position:absolute;top:22px;left:25px;font-size:8px;letter-spacing:1.6px;color:#f4e7ffb0}.hw-animated,.hw-timeline>span{animation-duration:var(--hw-duration);animation-timing-function:linear;animation-iteration-count:infinite;animation-play-state:var(--hw-play)}.hw-input{position:absolute;left:8%;right:8%;top:100px;background:#fff;border-radius:14px;box-shadow:0 10px 35px #3b12541c;display:flex;align-items:center;gap:12px;padding:20px 18px;color:#63516e;animation-name:hw-input}.hw-bubble-icon{width:29px;height:29px;border-radius:50%;display:grid;place-items:center;background:#f1e9f9;color:#ab8abd;font-size:11px;flex-shrink:0}.hw-input small{display:block;font-size:9px;color:#b399c2;margin-bottom:6px}.hw-input p{font-size:12px;line-height:1.8;margin:0}.hw-input>svg{margin-left:auto;width:15px;height:15px;color:#b296c6}.hw-stream{position:absolute;left:50%;top:195px;display:flex;flex-direction:column;gap:7px;animation-name:hw-stream}.hw-stream>span{width:3px;height:3px;background:#f9e9ff;border-radius:50%}.hw-learning{position:absolute;top:95px;left:12%;right:12%;padding:18px;background:#fffefcf5;border:1px solid #fff;border-radius:12px;color:#85708d;box-shadow:0 15px 30px #62358413;overflow:hidden;animation-name:hw-learning}.hw-card-top{display:flex;justify-content:space-between;align-items:center;gap:10px;font-size:10px;margin-bottom:15px}.hw-card-top>span{display:flex;align-items:center;gap:6px;color:#9972af}.hw-card-top svg{width:14px;height:14px}.hw-card-top>b{font-size:8px;font-weight:400;border:1px solid #eee2f3;padding:2px 5px;border-radius:4px}.hw-field{display:flex;justify-content:space-between;gap:10px;padding:9px 0;font-size:11px;border-top:1px solid #f0e9f4}.hw-field>span{font-size:10px;color:#b5a2bf}.hw-field strong{font-weight:500}.hw-gate strong{font-size:9px;color:#a182b5}.hw-scan{position:absolute;left:0;right:0;height:45px;top:-45px;background:linear-gradient(transparent,#e5ccfa55,transparent);animation:hw-scan var(--hw-duration) linear infinite;animation-play-state:var(--hw-play)}.hw-memory{position:absolute;top:90px;left:15%;right:15%;padding:15px 18px;background:#f9f4ffd9;border:1px solid #ffffffa8;border-radius:12px;display:flex;align-items:center;gap:12px;color:#7c558f;animation-name:hw-memory}.hw-mini-mark{background:#b88bde;color:#fff;border-radius:9px;width:30px;height:30px;font:24px Georgia,serif;display:grid;place-items:center;flex-shrink:0}.hw-memory small{display:block;font-size:9px;color:#ad8bbd;margin-bottom:4px}.hw-memory strong{display:block;font-size:12px;font-weight:500}.hw-check{margin-left:auto;font-size:17px;color:#a37bbc}.hw-question{position:absolute;top:142px;left:10%;right:10%;animation-name:hw-question}.hw-question>span{font-size:9px;color:#f3dcffbb;display:block;margin-bottom:9px}.hw-question p{background:#fff;padding:17px 21px;border-radius:14px;color:#634d70;font-size:13px;line-height:1.8;margin:0;box-shadow:0 9px 30px #3b125410}.hw-evidence{position:absolute;top:244px;left:12%;right:10%;display:flex;gap:10px;align-items:center;font-size:11px;color:#f7eaff;animation-name:hw-evidence}.hw-evidence svg{width:16px;height:16px;flex-shrink:0}.hw-evidence strong{font-weight:500}.hw-answer{position:absolute;top:293px;left:12%;right:10%;display:flex;gap:12px;align-items:center;animation-name:hw-answer}.hw-answer>.hw-mini-mark{background:#d5b1ee}.hw-answer p{font-size:11px;line-height:1.85;color:#f9f0ff;margin:0}.hw-answer strong{font-weight:500}.hw-status-save,.hw-status-recall{position:absolute;top:53px;left:0;right:0;text-align:center;font-size:11px;color:#fff;animation-name:hw-save}.hw-status-recall{animation-name:hw-recall}.hw-timeline{position:absolute;bottom:19px;left:25px;right:25px;height:2px;background:#ffffff26;border-radius:2px;overflow:hidden}.hw-timeline>span{height:100%;width:100%;background:#f8e8ff;display:block;transform-origin:left;animation-name:hw-progress}.hw-footnote{display:flex;justify-content:space-between;gap:15px;margin-top:16px;font-size:10px;color:#a294ac}.hw-footnote a{color:#9775ad}
@keyframes hw-step{0%,29%{color:#a776d0}34%,96%{color:#c2b8c7}100%{color:#a776d0}}
@keyframes hw-input{0%{opacity:0;transform:translateY(35px) scale(.97)}5%,20%{opacity:1;transform:translateY(0) scale(1)}28%{opacity:0;transform:translateY(-40px) scale(.9)}100%{opacity:0;transform:translateY(-40px) scale(.9)}}
@keyframes hw-stream{0%,17%{opacity:0;transform:translateY(-10px)}22%,29%{opacity:1;transform:translateY(18px)}34%,100%{opacity:0;transform:translateY(35px)}}
@keyframes hw-learning{0%,24%{opacity:0;transform:translateY(28px) scale(.95)}31%,47%{opacity:1;transform:translateY(0) scale(1)}55%{opacity:0;transform:translateY(-35px) scale(.92)}100%{opacity:0;transform:translateY(-35px) scale(.92)}}
@keyframes hw-scan{0%,30%{transform:translateY(0)}47%,100%{transform:translateY(250px)}}
@keyframes hw-memory{0%,47%{opacity:0;transform:translateY(22px) scale(.92)}54%,60%{opacity:1;transform:translateY(0) scale(1)}70%,100%{opacity:0;transform:translateY(-50px) scale(.8)}}
@keyframes hw-question{0%,59%{opacity:0;transform:translateY(30px)}67%,92%{opacity:1;transform:translateY(0)}99%,100%{opacity:0;transform:translateY(-22px)}}
@keyframes hw-evidence{0%,68%{opacity:0;transform:translateY(-12px)}75%,92%{opacity:1;transform:translateY(0)}99%,100%{opacity:0;transform:translateY(-16px)}}
@keyframes hw-answer{0%,76%{opacity:0;transform:translateY(20px)}84%,92%{opacity:1;transform:translateY(0)}99%,100%{opacity:0;transform:translateY(-12px)}}
@keyframes hw-save{0%,48%{opacity:0;transform:translateY(7px)}54%,61%{opacity:1;transform:translateY(0)}67%,100%{opacity:0;transform:translateY(-7px)}}
@keyframes hw-recall{0%,72%{opacity:0;transform:translateY(7px)}80%,93%{opacity:1;transform:translateY(0)}99%,100%{opacity:0;transform:translateY(-7px)}}
@keyframes hw-progress{0%{transform:scaleX(0)}100%{transform:scaleX(1)}}
@media(max-width:800px){.hw-panel{padding:24px;gap:25px;grid-template-columns:.7fr 1.3fr}.hw-heading h2{font-size:32px}.hw-steps h3{font-size:20px}.hw-steps p{font-size:10px}.hw-stage{min-height:410px}.hw-input{left:6%;right:6%;padding:16px 13px;gap:8px}.hw-input p{font-size:11px}.hw-memory{left:8%;right:8%}}
@media(max-width:600px){.hw-section{padding:40px 0}.hw-heading h2{font-size:31px}.hw-panel{grid-template-columns:1fr;padding:18px;gap:25px}.hw-steps{flex-direction:row;gap:13px}.hw-steps li{flex:1;min-height:0!important;gap:8px}.hw-node{width:8px;height:8px;box-shadow:none}.hw-steps li:after{display:none}.hw-number{font-size:8px}.hw-steps h3{font-size:19px;margin-bottom:6px}.hw-steps p{font-size:9px}.hw-steps p br{display:none}.hw-stage{min-height:420px}.hw-question{left:7%;right:7%}.hw-question p{font-size:12px;padding-inline:15px}.hw-evidence{left:8%;right:8%;font-size:10px}.hw-answer{left:8%;right:8%}.hw-footnote{flex-wrap:wrap;font-size:9px}.hw-field{font-size:10px}}
@media(prefers-reduced-motion:reduce){.hw-input,.hw-learning,.hw-memory,.hw-question,.hw-evidence,.hw-answer,.hw-stream,.hw-status-save,.hw-status-recall,.hw-scan{animation:none}.hw-input,.hw-learning,.hw-memory,.hw-stream,.hw-status-save,.hw-scan{opacity:0}.hw-question,.hw-evidence,.hw-answer,.hw-status-recall{opacity:1}.hw-steps li{animation:none}.hw-steps li:last-child{color:#a776d0}.hw-timeline>span{animation:none}}

/* Native animation drives the same persistent objects as a single continuous film. */
.hw-section[data-animated="true"] .hw-animated,
.hw-section[data-animated="true"] .hw-scan,
.hw-section[data-animated="true"] .hw-timeline>span,
.hw-section[data-animated="true"] .hw-steps li{animation:none}
.hw-stage{min-height:435px;background:linear-gradient(145deg,#d7bcf1,#b18ade 55%,#7851af)}
.hw-stage .hw-caption{font-size:9px}
.hw-input{padding-block:23px;box-shadow:0 15px 45px #4d247929;will-change:opacity,transform}
.hw-input p{font-size:13px}
.hw-learning,.hw-memory,.hw-question,.hw-evidence,.hw-answer{will-change:opacity,transform}
.hw-question p{font-size:14px;padding-block:20px}
.hw-answer p{font-size:12px}
.hw-evidence{font-size:12px}
.hw-steps li{transition:color .8s ease}
.hw-node{box-shadow:0 0 0 6px #fcfbfd;transition:background .8s ease}
@media(max-width:600px){.hw-stage{min-height:435px}.hw-input p,.hw-question p{font-size:12px}.hw-evidence,.hw-answer p{font-size:11px}.hw-node{box-shadow:none}}
</style>
