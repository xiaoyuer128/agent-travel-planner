<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue';
import type { Preferences, Session, SessionItem } from './types/chat';
import { listSessions, newSession, loadSession, sendTurn, restorePlan } from './api/chat';
import DiscoverPanel from './components/DiscoverPanel.vue';
import SceneryArt from './components/SceneryArt.vue';

const sessions = ref<SessionItem[]>([]);
const session = ref<Session | null>(null);
const input = ref('');
const busy = ref(false);
const error = ref('');
const provider = ref('');
const preview = ref<number | null>(null);
const messagesEl = ref<HTMLElement>();
const editor = ref(false);
const form = ref<Preferences>({});
const plan = computed(() => preview.value ? session.value?.versions.find(p => p.version === preview.value) : session.value?.plan);
const current = computed(() => session.value?.plan);
const yuan = (cents: number) => `¥${(cents / 100).toLocaleString('zh-CN', {maximumFractionDigits: 2})}`;
const hints = ['两个人，预算8000，重庆出发，去杭州，2026-12-01出发，玩5天', '酒店换便宜一些，其他不变', '增加美食活动', '预算改成6000'];
async function remember(s: Session) {
  session.value = s; preview.value = null;
  localStorage.setItem('travel-chat-session', s.id);
  sessions.value = await listSessions();
  await nextTick(); messagesEl.value?.scrollTo({top: messagesEl.value.scrollHeight, behavior: 'smooth'});
}
async function guarded(action: () => Promise<void>) {
  if (busy.value) return;
  busy.value = true; error.value = '';
  try { await action(); } catch (e) { error.value = e instanceof Error ? e.message : String(e); }
  finally { busy.value = false; }
}
async function create() { await guarded(async () => remember(await newSession())); }
async function select(id: string) { await guarded(async () => remember(await loadSession(id))); }
async function send(text = input.value, patch?: Preferences, action = 'auto') {
  if (!text.trim() || !session.value) return;
  await guarded(async () => {
    const updated = await sendTurn(session.value!, text, patch, action);
    await remember(updated); input.value = ''; editor.value = false;
  });
}
function edit() { form.value = {...session.value?.preferences}; editor.value = true; }
async function saveForm() {
  const patch = Object.fromEntries(Object.entries(form.value).filter(([,v]) => v !== '' && v != null)) as Preferences;
  await send('已通过需求面板更新旅行条件', patch);
}
async function restore() {
  if (!session.value || !preview.value) return;
  await guarded(async () => remember(await restorePlan(session.value!, preview.value!)));
}
onMounted(async () => {
  await guarded(async () => {
    const configResponse = await fetch('/api/chat/config');
    if (!configResponse.ok) throw new Error('无法获取模型配置，请确认后端已启动');
    provider.value = (await configResponse.json()).provider;
    sessions.value = await listSessions();
    const remembered = localStorage.getItem('travel-chat-session');
    const exists = sessions.value.some(s => s.id === remembered);
    await remember(exists ? await loadSession(remembered!) : await newSession());
  });
});
</script>

<template>
  <header class="chat-hero">
    <div class="hero-brand"><div class="brand-mark">↗</div><div><div class="eyebrow">ROAM / TRAVEL WORKSPACE</div><h1>和旅行聊一聊<span>出发，从一个想法开始。</span></h1></div></div>
    <div class="hero-right"><span class="hero-note">把向往，变成行程。</span><div class="mode-pill">● {{ provider === 'deepseek' ? 'DeepSeek · 国内旅行' : provider === 'mock' ? 'Mock 演示' : '正在连接' }}</div></div>
  </header>
  <div class="mock-notice">航班、酒店与费用为示例，不支持预订；攻略来自本地示例，右侧景点资料另行标注来源。</div>
  <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon class="error-banner" />
  <div class="workspace">
    <aside class="session-sidebar">
      <div class="sidebar-heading">我的旅行 <el-button size="small" :disabled="busy" @click="create">＋ 新建</el-button></div>
      <button v-for="item in sessions" :key="item.id" class="session-item" :class="{selected:item.id===session?.id}" :disabled="busy" @click="select(item.id)">
        <strong>{{ item.title }}</strong><small>{{ new Date(item.updated).toLocaleDateString() }} · {{ item.revision }} 次更新</small>
      </button>
      <div class="sidebar-note">会话和每版方案保存在本地服务数据库，刷新后继续。此演示未启用多用户登录。</div>
    </aside>
    <section class="conversation">
      <div class="panel-heading"><div><span class="eyebrow">01 / CONVERSATION</span><h2>旅行对话</h2></div><el-button size="small" :disabled="busy || !session" @click="edit">编辑需求</el-button></div>
      <div class="preference-strip" v-if="session">
        <span>{{ session.preferences.departure_city || '待定出发地' }} → {{ session.preferences.destination || '待定目的地' }}</span>
        <span>{{ session.preferences.num_travelers || '?' }} 人 · {{ session.preferences.days || '?' }} 天</span>
        <span>{{ session.preferences.budget ? '预算 ¥'+session.preferences.budget : '预算待定' }}</span>
      </div>
      <div class="messages" ref="messagesEl" aria-live="polite">
        <div v-if="!session?.messages.length" class="welcome"><div class="welcome-visual"><SceneryArt theme="garden" label="旅行灵感示意插画"/><span>YOUR NEXT CHAPTER</span></div><h3>下一站，你想去哪里？</h3><p>一段山城漫步，还是一次江南漫游？告诉我预算和想法，我们一起安排。</p><div class="starter-cities"><button v-for="city in ['杭州','成都','重庆']" :key="city" :disabled="busy" @click="send('我想去'+city, {destination:city})">{{ city }} ↗</button></div><p class="muted">还没想好？可以分几次说，也可以从右侧寻找灵感。</p></div>
        <div v-for="(message,i) in session?.messages" :key="i" class="message" :class="message.role"><div class="message-label">{{ message.role === 'user' ? '你' : (session?.provider === 'deepseek' ? '旅行助手 · DeepSeek' : '旅行助手 · 示例') }}</div><div class="bubble">{{ message.content }}</div></div>
        <div v-if="busy" class="thinking">{{ provider === 'deepseek' ? 'DeepSeek 正在理解需求并规划路线…' : '正在更新旅行工作台…' }}</div>
      </div>
      <div class="composer">
        <div class="quick-actions"><button v-for="(hint,i) in hints" :key="hint" :disabled="busy" @click="i===0 ? input=hint : send(hint)">{{ i===0 ? '填入示例需求' : hint }}</button></div>
        <el-input v-model="input" type="textarea" :rows="3" maxlength="2000" show-word-limit placeholder="例如：重庆出发，两个人，预算8000，去杭州玩5天…" :disabled="busy" @keydown.ctrl.enter.prevent="send()" />
        <div class="send-row"><span>Ctrl + Enter 发送 · 先补充条件，再生成方案</span><el-button type="primary" :loading="busy" :disabled="!session || !input.trim()" @click="send()">发送消息 →</el-button></div>
      </div>
    </section>
    <section class="plan-panel">
      <div class="panel-heading"><div><span class="eyebrow">02 / YOUR PLAN</span><h2>结构化方案</h2></div><el-select v-if="session?.versions.length" v-model="preview" placeholder="当前版本" clearable style="width:135px" :disabled="busy"><el-option v-for="v in session.versions" :key="v.version" :value="v.version" :label="'方案 v'+v.version" /></el-select></div>
      <div v-if="!plan" class="plan-empty"><div class="empty-ticket"><span>YOUR ITINERARY</span><div>出发地 <b>✈</b> 目的地</div><i>··································</i><small>一张属于你的旅行计划，等待开启</small></div><h3>让期待，有迹可循。</h3><p>补齐需求后，在这里查看每日路线、预算和攻略引用。每次修改，都有新版本可回看。</p><div class="empty-steps"><span>01 说出想法</span><span>02 一起规划</span><span>03 随心调整</span></div></div>
      <template v-else>
        <div class="plan-summary"><div><span class="eyebrow">{{ plan.preferences.start_date }} · {{ plan.preferences.days }} DAYS · v{{ plan.version }}</span><h2>{{ plan.preferences.departure_city }} → {{ plan.preferences.destination }}</h2><p>{{ plan.preferences.num_travelers }} 人 · {{ plan.cost.rooms }} 间房 · {{ plan.cost.nights }} 晚</p></div><div class="total-price">{{ yuan(plan.cost.total_cents) }}<small>已建模总费用</small></div></div>
        <div v-if="preview && current && preview!==current.version" class="version-diff">正在查看历史 v{{ preview }}；与当前版价差 {{ yuan(plan.cost.total_cents-current.cost.total_cents) }}<el-button size="small" :disabled="busy" @click="restore">恢复为新版本</el-button></div>
        <div class="plan-body">
          <div class="budget-banner" :class="{over:!plan.cost.within_budget}">{{ plan.cost.within_budget ? '✓ 预算内' : '！超预算' }} · 预算 {{ yuan(plan.cost.budget_cents) }} · {{ plan.cost.within_budget ? '剩余' : '超出' }} {{ yuan(Math.abs(plan.cost.remaining_cents)) }}</div>
          <div class="cost-grid"><div>航班<strong>{{ yuan(plan.cost.flight_cents) }}</strong></div><div>住宿<strong>{{ yuan(plan.cost.hotel_cents) }}</strong></div><div>活动<strong>{{ yuan(plan.cost.activity_cents) }}</strong></div></div>
          <div class="hotel-card"><span class="eyebrow">STAY / MOCK</span><h3>{{ plan.hotel.name }}</h3><p>{{ yuan(plan.hotel.price_cents) }} / 房 / 晚 · {{ plan.hotel.stars }} 星示例</p><el-button size="small" :disabled="busy || !!preview" @click="send('酒店换便宜一些，其他不变')">换便宜一些</el-button><el-button size="small" :disabled="busy || !!preview" @click="send('酒店升级，其他不变')">升级酒店</el-button></div>
          <h3 class="subheading">每日安排 <span>引用随方案版本保留</span></h3>
          <article v-for="day in plan.days" :key="day.day" class="day-card"><div class="day-number">{{ String(day.day).padStart(2,'0') }}</div><div><small>{{ day.date }}</small><h4>{{ day.title }}</h4><p>{{ day.description }}</p><a v-for="id in day.source_ids" :key="id" :href="'#source-'+id">[来源：{{ id }}]</a><small v-if="!day.source_ids.length">无攻略来源 · 通用建议</small></div></article>
          <h3 class="subheading">攻略来源 <span>{{ plan.sources.length }} 条 · 本地 Mock</span></h3>
          <div v-if="!plan.sources.length" class="source-empty">知识库暂无该城市资料，不会伪造引用。</div>
          <article v-for="source in plan.sources" :key="source.id" :id="'source-'+source.id" class="source-card"><strong>{{ source.title }}</strong><p>{{ source.text }}</p><small>{{ source.source }} · {{ source.uri }} · score {{ source.score }}</small></article>
          <details class="diagnostics"><summary>执行与修改记录</summary><p>LangGraph：{{ session?.trace.join(' → ') }}</p><p>本版更新：{{ plan.changed_sections.join('、') || '无结构变更' }}</p><p v-for="warning in plan.warnings" :key="warning">{{ warning }}</p></details>
        </div>
      </template>
    </section>
    <DiscoverPanel :destination="plan?.preferences.destination || session?.preferences.destination" :disabled="busy || !session" @choose="city => send('将目的地设为'+city, {destination:city})" />
  </div>
  <el-dialog v-model="editor" title="精确编辑旅行需求" width="min(520px, 94vw)">
    <el-form label-position="top" @submit.prevent="saveForm">
      <el-form-item label="出发城市"><el-input v-model="form.departure_city" maxlength="30" /></el-form-item>
      <el-form-item label="目的地"><el-input v-model="form.destination" maxlength="30" /></el-form-item>
      <el-form-item label="总预算（元）"><el-input-number v-model="form.budget" :min="1" :max="1000000" /></el-form-item>
      <el-form-item label="人数"><el-input-number v-model="form.num_travelers" :min="1" :max="10" /></el-form-item>
      <el-form-item label="出发日期"><el-date-picker v-model="form.start_date" value-format="YYYY-MM-DD" /></el-form-item>
      <el-form-item label="旅行天数"><el-input-number v-model="form.days" :min="1" :max="30" /></el-form-item>
      <el-button type="primary" native-type="submit" :loading="busy">更新需求并规划</el-button>
    </el-form>
  </el-dialog>
</template>

<style>
#app { max-width:1600px; padding:28px 28px 36px; }
.chat-hero { display:flex; justify-content:space-between; align-items:center; margin:0 0 18px; gap:20px; }
.chat-hero h1 { margin:6px 0; font-size:32px; letter-spacing:-1px; }.chat-hero p{margin:0;color:#74839a;font-size:14px}
.eyebrow{font-size:10px;letter-spacing:1.5px;color:#7f91aa;font-weight:700}.mode-pill{border:1px solid #c9e5da;background:#ecf8f2;color:#2c7962;border-radius:22px;padding:9px 16px;font-size:12px;white-space:nowrap}
.mock-notice{font-size:12px;color:#8b774e;background:#fff9ec;padding:10px 14px;border-radius:9px;margin-bottom:18px}.error-banner{margin-bottom:14px}
.workspace{display:grid;grid-template-columns:180px minmax(320px, .95fr) minmax(380px, 1.2fr);gap:18px;align-items:start}.session-sidebar{padding-top:12px}.sidebar-heading{display:flex;align-items:center;justify-content:space-between;font-size:13px;font-weight:700;margin-bottom:15px}
.session-item{display:block;text-align:left;border:1px solid transparent;background:transparent;padding:12px;width:100%;border-radius:10px;color:#425570;cursor:pointer;margin-bottom:6px}.session-item.selected{background:#e6edf8;border-color:#d4e0f2}.session-item strong,.session-item small{display:block}.session-item small{font-size:10px;color:#8998af;margin-top:6px}.sidebar-note{font-size:11px;color:#99a6b7;line-height:1.8;padding:16px 8px}
.conversation,.plan-panel{background:white;border:1px solid #e4eaf2;border-radius:16px;overflow:hidden;box-shadow:0 4px 16px #24395805}.conversation{height:calc(100vh - 185px);min-height:640px;max-height:1000px;display:flex;flex-direction:column}.panel-heading{padding:20px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #edf0f5;gap:10px}.panel-heading h2{font-size:17px;margin:5px 0 0}.preference-strip{display:flex;flex-wrap:wrap;gap:5px;padding:12px 16px;border-bottom:1px solid #f0f3f7}.preference-strip span{font-size:10px;background:#f0f4fa;padding:5px 7px;border-radius:5px;color:#6d7f99}
.messages{flex:1;overflow:auto;padding:20px;scroll-behavior:smooth}.welcome{padding:35px 8px;color:#788aa4;font-size:13px;line-height:1.9}.welcome-icon{font-size:38px;color:#758fd4}.welcome h3{color:#263e64;font-size:20px;margin:10px 0}.welcome .muted{font-size:11px}.message{margin:0 0 20px;max-width:94%}.message.user{margin-left:auto}.message-label{font-size:10px;color:#8b9bb0;margin-bottom:6px}.user .message-label{text-align:right}.bubble{padding:13px 15px;border-radius:12px;background:#f0f4fa;font-size:13px;line-height:1.85;white-space:pre-wrap;overflow-wrap:anywhere}.user .bubble{background:#284e83;color:white}.thinking{font-size:12px;color:#7d92ae}
.composer{border-top:1px solid #edf0f5;padding:14px}.quick-actions{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px}.quick-actions button{border:1px solid #e2e9f2;color:#6880a0;background:white;border-radius:14px;padding:5px 8px;font-size:10px;cursor:pointer}.send-row{display:flex;align-items:center;justify-content:space-between;margin-top:12px;gap:8px}.send-row span{font-size:10px;color:#9ca9ba}.plan-empty{padding:90px 30px;text-align:center;font-size:13px;color:#9aa8ba;line-height:1.8}.plan-empty>div{font-size:50px;color:#c4d2e7}.plan-empty h3{font-size:17px;color:#6f85a3}
.plan-summary{padding:24px;background:#eef3fb;display:flex;justify-content:space-between;gap:10px}.plan-summary h2{font-size:23px;margin:9px 0}.plan-summary p{font-size:12px;color:#7c8fa9;margin:0}.total-price{font-size:25px;font-weight:700;white-space:nowrap;align-self:center}.total-price small{font-size:10px;display:block;color:#92a1b6;font-weight:400;text-align:right;margin-top:6px}.plan-body{padding:20px}.budget-banner{background:#edf8f2;color:#427c64;font-size:12px;padding:10px 12px;border-radius:8px}.budget-banner.over{background:#fff2e8;color:#b46732}.cost-grid{display:grid;grid-template-columns:repeat(3,1fr);margin:16px 0;gap:10px}.cost-grid>div{font-size:11px;color:#9aa8b9;background:#f8fafc;border-radius:8px;padding:12px}.cost-grid strong{display:block;color:#3f5779;font-size:17px;margin-top:6px}.hotel-card{border:1px solid #e6edf6;padding:16px;border-radius:12px}.hotel-card h3{font-size:16px;margin:8px 0}.hotel-card p{font-size:12px;color:#8190a5}.subheading{font-size:15px;margin:25px 0 15px;display:flex;justify-content:space-between;align-items:center}.subheading span{font-size:10px;color:#a2aec0;font-weight:400}.day-card{display:flex;gap:14px;padding:16px 0;border-bottom:1px solid #edf0f5}.day-number{font-size:21px;font-weight:700;color:#b2c3dc;padding-top:15px}.day-card small{font-size:10px;color:#98a7bb}.day-card h4{font-size:14px;margin:5px 0}.day-card p{font-size:12px;line-height:1.8;color:#788ba6;margin:7px 0}.day-card a{font-size:10px;color:#537fba;text-decoration:none;margin-right:8px}.source-card{background:#f6f8fc;padding:13px;border-radius:9px;margin-bottom:10px;scroll-margin-top:20px}.source-card strong{font-size:12px}.source-card p{font-size:11px;line-height:1.8;color:#7a8ca7}.source-card small{font-size:9px;color:#9eacc0;overflow-wrap:anywhere}.source-empty{font-size:12px;color:#99a8bd}.diagnostics{font-size:11px;color:#92a0b4;margin-top:20px;line-height:1.8}.version-diff{padding:12px 20px;font-size:11px;background:#fff8e9;color:#a58146;display:flex;justify-content:space-between;gap:8px}
@media(max-width:1150px){.workspace{grid-template-columns:150px minmax(280px,1fr) minmax(320px,1fr)}#app{padding:20px 16px}.total-price{font-size:20px}.panel-heading{padding:16px}.send-row>span{display:none}}
@media(max-width:900px){.workspace{grid-template-columns:1fr}.session-sidebar{display:flex;gap:8px;overflow:auto;align-items:center;padding:0}.sidebar-heading{flex-shrink:0;margin:0}.session-item{min-width:145px;width:auto;margin:0}.sidebar-note{display:none}.conversation{height:660px;min-height:0}.chat-hero h1{font-size:25px}.chat-hero{align-items:flex-start}.mode-pill{font-size:10px;padding:8px}.chat-hero p{font-size:12px}.plan-panel{min-width:0}}
</style>
