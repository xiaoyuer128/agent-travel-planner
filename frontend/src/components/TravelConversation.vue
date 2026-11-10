<script setup lang="ts">
import {ref,computed,watch,nextTick} from 'vue';
import type {Session} from '../types/chat';
const props=defineProps<{session:Session|null;busy:boolean;widget?:boolean;draft?:string;steps?:string[];stopping?:boolean;canRetry?:boolean}>();
const emit=defineEmits<{send:[text:string];generate:[];edit:[];close:[];drag:[event:PointerEvent];reset:[];cancel:[];retry:[]}>();
const text=ref('');const scroll=ref<HTMLElement>();
const ready=computed(()=>props.session&&['departure_city','destination','budget','num_travelers','start_date','days'].every(k=>(props.session!.preferences as Record<string,unknown>)[k]));
watch(()=>props.session?.messages.length,async()=>{await nextTick();scroll.value?.scrollTo({top:scroll.value.scrollHeight,behavior:'smooth'})});
watch(()=>props.draft,async()=>{await nextTick();scroll.value?.scrollTo({top:scroll.value.scrollHeight})});
function send(){if(!text.value.trim()||props.busy)return;emit('send',text.value);text.value=''}
</script>
<template>
 <section class="travel-conversation" :class="{widget}">
  <div class="conversation-head" :class="{'drag-handle':widget}" @pointerdown="widget&&emit('drag',$event)"><div><span class="small-label">{{widget?'可拖动到喜欢的位置':'YOUR TRAVEL COMPANION'}}</span><h2>一起，把旅行安排好 <span class="online-dot"></span></h2></div><template v-if="widget"><button class="icon-button" aria-label="重置助手位置" @click="emit('reset')">⌖</button><button class="icon-button" aria-label="收起旅行助手" @click="emit('close')">×</button></template><button v-else class="text-button" @click="emit('edit')">编辑需求</button></div>
  <div class="chat-scroll" ref="scroll" aria-live="polite">
   <div v-if="!session?.messages.length" class="chat-intro"><div class="assistant-avatar">✦</div><h3>嗨，下一站想去哪里？</h3><p>告诉我出发地、时间和预算，或者先聊聊你喜欢的风景。</p><button class="suggestion" @click="emit('send','想去杭州看风景，帮我安排一次轻松的旅行')">想去杭州，轻松玩几天 ↗</button></div>
   <div v-for="(m,i) in session?.messages" :key="i" class="chat-message" :class="m.role"><small>{{m.role==='user'?'你':'旅行助手'}}</small><div>{{m.content}}</div><details v-if="m.sources?.length" class="chat-sources"><summary>知识参考 · {{m.sources.length}} 条</summary><article v-for="source in m.sources"><b>{{source.title}}</b><p>{{source.text}}</p><a v-if="source.uri.startsWith('http')" :href="source.uri" target="_blank" rel="noopener">{{source.source}} ↗</a><small v-else>{{source.source}}</small></article></details><details v-if="m.tools?.length" class="chat-sources"><summary>已查询 {{m.tools.length}} 个工具</summary><article v-for="tool in m.tools"><b>{{({search_places:'景点搜索',get_weather:'天气查询',get_route:'路线查询',search_knowledge:'知识检索'} as Record<string,string>)[tool.name]||'工具查询'}}</b><small>{{tool.status==='ok'?'取得查询结果':'未取得可靠结果'}} · {{tool.elapsed_ms}}ms</small></article></details></div>
   <div v-if="busy" class="thinking"><span class="online-dot"></span> {{stopping?'正在停止生成…':steps?.[steps.length-1]||'正在为你整理旅行想法…'}}<details v-if="steps?.length"><summary>查看处理进度</summary><p v-for="step in steps">{{step}}</p></details></div>
   <div v-if="busy&&draft" class="chat-message assistant streaming-draft"><small>正在生成 · 校验完成后保存</small><div>{{draft}}<span class="stream-caret">▍</span></div></div>
   <button v-if="!busy&&canRetry" class="text-button" @click="emit('retry')">重试上一条请求</button>
  </div>
  <div v-if="session" class="collected"><button @click="emit('edit')">{{session.preferences.destination||'目的地待定'}} · {{session.preferences.days?session.preferences.days+'天':'天数待定'}} · {{session.preferences.budget?'¥'+session.preferences.budget:'预算待定'}} <span>编辑 ›</span></button></div>
  <div v-if="widget||!session?.plan" class="confirm-trip"><p>{{ready?'需求已就绪，确认后可生成完整行程。':'可以只聊景点与旅行问题，不用先填表。'}}</p><button v-if="ready" class="primary" :disabled="busy" @click="emit('generate')">{{busy?'正在生成…':'生成行程 →'}}</button><button v-else class="text-button" :disabled="busy" @click="emit('edit')">我想规划完整行程 →</button></div>
  <form class="chat-composer" @submit.prevent="send"><textarea v-model="text" aria-label="旅行需求" maxlength="2000" :disabled="busy" rows="3" placeholder="例如：上海出发，两个人，下周去杭州玩3天，预算3000…" @keydown.ctrl.enter.prevent="send"></textarea><div><small>Ctrl + Enter 发送</small><button v-if="busy" class="outline" :disabled="stopping" type="button" @click="emit('cancel')">{{stopping?'正在停止':'停止生成'}}</button><button v-else class="primary" :disabled="!text.trim()" type="submit">发送 ↗</button></div></form>
 </section>
</template>
