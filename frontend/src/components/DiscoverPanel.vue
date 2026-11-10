<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import SceneryArt from './SceneryArt.vue';
const props = defineProps<{ destination?: string; disabled: boolean }>();
const emit = defineEmits<{ choose: [city: string] }>();
const browsing = ref('');
const cities = ['杭州','南京','北京','西安','成都','重庆','上海','三亚'];
const city = computed(() => browsing.value || props.destination || '杭州');
watch(() => props.destination, () => { browsing.value = ''; });
type Spot = {name:string; subtitle:string; tag:string; theme:string; image?:string; source:string; seasonal:boolean};
const cards = ref<Spot[]>([]);
const loading = ref(false);
const note = ref('');
const mode = ref('');
const broken = ref<string[]>([]);
watch(city, async (value, _, onCleanup) => {
  const controller = new AbortController(); onCleanup(() => controller.abort());
  cards.value = []; broken.value = []; loading.value = true; note.value = '';
  try {
    const r = await fetch('/api/discover/spots?city='+encodeURIComponent(value), {signal:controller.signal});
    if (!r.ok) throw new Error('推荐服务暂不可用');
    const data = await r.json();
    cards.value = data.spots; note.value = data.message; mode.value = data.mode;
  } catch(e) {
    if (!controller.signal.aborted) { note.value = '暂时无法获取推荐，请稍后切换城市重试。'; mode.value='unavailable'; }
  } finally { if (!controller.signal.aborted) loading.value = false; }
}, {immediate:true});
</script>
<template>
  <aside class="discover-panel">
    <div class="discover-heading"><div><span class="eyebrow">03 / DISCOVER CHINA</span><h2>发现中国好风景</h2></div><span class="sparkle">✦</span></div>
    <div class="city-tabs" aria-label="浏览国内目的地"><button v-for="item in cities" :key="item" :class="{active:city===item}" @click="browsing=item">{{ item }}</button></div>
    <div class="discover-scroll">
      <div class="discover-city"><strong>{{ city }}</strong><span>{{ loading ? '正在寻找风景…' : mode==='live' ? '高德地点资料' : mode==='mixed' ? '高德 + 本地示例' : '国内旅行灵感' }}</span></div>
      <div v-if="!loading && !cards.length" class="discover-unavailable">{{ note }}</div>
      <article v-for="(spot,i) in cards" :key="spot.name" class="spot-card">
        <div class="spot-art">
          <img v-if="spot.image && !broken.includes(spot.name)" :src="spot.image" :alt="spot.name+' · 高德地点照片（非实时实景）'" loading="lazy" referrerpolicy="no-referrer" @error="broken.push(spot.name)" />
          <template v-else><SceneryArt :theme="spot.theme" :label="spot.name+'示意插画'"/><small class="art-label">示意插画</small></template>
          <span class="spot-index">0{{ i+1 }}</span><span class="spot-tag">{{ spot.tag }}</span>
        </div>
        <div class="spot-content"><h3>{{ spot.name }}</h3><p>{{ spot.subtitle }}</p><small>{{ spot.source }} · {{ spot.seasonal ? '适合当季探索（月份规则）' : '全年灵感参考' }}</small></div>
      </article>
      <div class="discover-tip"><span>✧</span><p>山河远阔，<br>从身边的风景出发。</p></div>
      <p class="discover-footnote">{{ note }} 照片非当前实景；开放时间与预约以景区公告为准。</p>
    </div>
    <div class="discover-action"><button :disabled="disabled || !cities.includes(city)" @click="emit('choose',city)">以{{ city }}为目的地 <span>↗</span></button><small>更新目的地；其他条件继续在对话中确认</small></div>
  </aside>
</template>
<style scoped>
.discover-panel{background:#fff;border:1px solid #e0e9e8;border-radius:18px;display:flex;flex-direction:column;min-height:0;overflow:hidden}.discover-heading{display:flex;justify-content:space-between;align-items:center;padding:20px 18px 14px}.discover-heading h2{font-size:17px;margin:6px 0 0}.sparkle{font-size:28px;color:#9bb8a4}.city-tabs{display:flex;gap:6px;padding:0 16px 13px;overflow:auto;flex-shrink:0;scrollbar-width:thin}.city-tabs button{white-space:nowrap;border:0;background:#f4f6f5;color:#84938e;border-radius:20px;padding:6px 10px;font-size:11px;cursor:pointer}.city-tabs button.active{background:#294d46;color:#fff}.discover-scroll{flex:1;min-height:0;overflow:auto;padding:0 16px;scrollbar-width:thin}.discover-city{display:flex;align-items:baseline;justify-content:space-between;gap:8px;margin:4px 0 12px}.discover-city strong{font-size:20px}.discover-city span{font-size:9px;color:#99a9a4}.spot-card{border:1px solid #e8eeeb;border-radius:12px;overflow:hidden;margin-bottom:14px;transition:transform .2s,box-shadow .2s}.spot-card:hover{transform:translateY(-2px);box-shadow:0 8px 20px #254a4010}.spot-art{height:125px;position:relative;overflow:hidden}.spot-index{position:absolute;top:10px;left:12px;color:white;font:italic 24px Georgia,serif;opacity:.9}.spot-tag{position:absolute;right:9px;bottom:9px;background:#ffffffdc;color:#49635b;font-size:9px;border-radius:5px;padding:4px 7px;backdrop-filter:blur(6px)}.spot-content{padding:12px}.spot-content h3{font-size:13px;margin:0 0 6px}.spot-content p{font-size:11px;line-height:1.7;color:#85958e;margin:0}.discover-tip{display:flex;align-items:center;justify-content:center;gap:15px;background:#f5f2e9;border-radius:12px;padding:15px;margin:4px 0 14px}.discover-tip span{font-size:35px;color:#c2ae7f}.discover-tip p{font-size:13px;font-family:serif;line-height:1.7;color:#8c856e;margin:0}.discover-footnote{font-size:9px;line-height:1.7;color:#a4afa9}.discover-action{padding:13px 16px;border-top:1px solid #ecf0ed;background:#fff}.discover-action button{width:100%;border:0;border-radius:9px;background:#315a4c;color:white;padding:11px 12px;font-size:12px;cursor:pointer;display:flex;justify-content:space-between}.discover-action button:disabled{opacity:.5;cursor:default}.discover-action small{font-size:9px;color:#a1ada7;display:block;text-align:center;margin-top:7px}.discover-unavailable{font-size:12px;color:#90a298;line-height:1.8;padding:30px 0}
.spot-art img{width:100%;height:100%;object-fit:cover}.art-label{position:absolute;left:8px;bottom:8px;background:#ffffffd9;padding:3px 6px;font-size:9px;color:#4c665a;border-radius:4px}.spot-content small{display:block;font-size:9px;line-height:1.8;color:#7a9184;margin-top:6px}
</style>
