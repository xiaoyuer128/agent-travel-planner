<script setup lang="ts">
import { computed } from "vue";
import type { TravelPlanState } from "../types/plan";

const props = defineProps<{ state: TravelPlanState }>();

const dest = computed(() => props.state.destination_rec?.selected ?? null);

const COST: Record<string, string> = { low: "低消费", medium: "中消费", high: "高消费" };
const SEASON: Record<string, string> = { spring: "春", summer: "夏", autumn: "秋", winter: "冬" };

function seasonZh(s: string): string {
  return (
    s
      .split(",")
      .map((x) => SEASON[x.trim()] ?? x.trim())
      .join("/") || "全年"
  );
}

const safetyPct = computed(() =>
  dest.value ? Math.round(Math.max(0, Math.min(10, dest.value.safety_score)) * 10) : 0,
);
</script>

<template>
  <div v-if="dest" class="card">
    <div class="dest-title">
      {{ dest.city }}<span class="dest-country">{{ dest.country }}</span>
    </div>
    <div class="muted" style="margin: 6px 0 10px">{{ dest.description }}</div>

    <div style="margin: 8px 0">
      <span class="tag">{{ COST[dest.cost_level] ?? dest.cost_level }}</span>
      <span class="tag">最佳季节 {{ seasonZh(dest.best_season) }}</span>
      <span class="tag" :class="dest.visa_required ? 'tag-warn' : 'tag-green'">
        {{ dest.visa_required ? "需签证" : "免签/落地签" }}
      </span>
    </div>

    <div style="margin: 10px 0">
      <div style="font-size: 0.82rem; color: var(--muted)">安全评分 · {{ dest.safety_score.toFixed(1) }} / 10</div>
      <el-progress :percentage="safetyPct" :show-text="false" :stroke-width="10" />
    </div>

    <div style="margin-top: 8px">
      <span v-for="h in dest.highlights" :key="h" class="tag">{{ h }}</span>
    </div>
  </div>
</template>

<style scoped>
.dest-title {
  font-size: 1.75rem;
  font-weight: 800;
  color: #1e3a5f;
}
.dest-country {
  font-size: 1.05rem;
  color: #6b7c93;
  margin-left: 6px;
  font-weight: 400;
}
</style>