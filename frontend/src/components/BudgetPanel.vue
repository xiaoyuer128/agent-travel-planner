<script setup lang="ts">
import { computed } from "vue";
import type { TravelPlanState } from "../types/plan";
import { money } from "../utils/format";

const props = defineProps<{ state: TravelPlanState }>();
const b = computed(() => props.state.budget_breakdown);

const percent = computed(() => {
  if (!b.value) return 0;
  const p = (b.value.total_cost / b.value.budget) * 100;
  return Math.min(100, Math.round(p));
});

const status = computed<"success" | "warning" | "exception">(() => {
  if (!b.value) return "success";
  if (percent.value >= 100) return "exception";
  if (percent.value >= 80) return "warning";
  return "success";
});
</script>

<template>
  <div v-if="b" class="card">
    <div class="metric-row">
      <div class="metric">
        <div class="label">✈️ 航班</div>
        <div class="value">{{ money(b.flight_cost) }}</div>
      </div>
      <div class="metric">
        <div class="label">🏨 酒店</div>
        <div class="value">{{ money(b.hotel_cost) }}</div>
      </div>
      <div class="metric">
        <div class="label">🎯 活动</div>
        <div class="value">{{ money(b.activity_cost) }}</div>
      </div>
    </div>

    <div style="margin: 18px 0 8px">
      <div class="row-between">
        <span class="muted">总预算使用</span>
        <span>
          <strong>{{ money(b.total_cost) }}</strong> / {{ money(b.budget) }}
          <span v-if="b.remaining >= 0" class="tag tag-green">剩余 {{ money(b.remaining) }}</span>
          <span v-else class="tag tag-warn">超支 {{ money(b.over_budget_amount) }}</span>
        </span>
      </div>
      <el-progress :percentage="percent" :status="status" :stroke-width="14" />
    </div>

    <div v-if="b.is_within_budget" class="budget-ok">✅ {{ props.state.adjustment_round }} 轮调整后已控制在预算内</div>
    <div v-else class="budget-over">⚠️ 已达到 {{ props.state.max_adjustments }} 轮最大调整次数</div>

    <div v-if="b.suggestions.length" style="margin-top: 12px">
      <div class="muted" style="margin-bottom: 6px">💡 预算优化建议</div>
      <div v-for="(s, i) in b.suggestions" :key="i" class="suggestion">• {{ s }}</div>
    </div>
  </div>

  <el-alert
    v-else
    title="暂无预算数据"
    type="info"
    :closable="false"
    description="预算面板由预算 Agent 在规划末尾生成。"
  />
</template>

<style scoped>
.budget-ok {
  background: #e8f7ef;
  color: #1a7f4b;
  border-radius: 10px;
  padding: 10px 14px;
  margin-top: 14px;
  font-weight: 600;
}
.budget-over {
  background: #fff4e6;
  color: #c46a08;
  border-radius: 10px;
  padding: 10px 14px;
  margin-top: 14px;
  font-weight: 600;
}
.suggestion {
  padding: 4px 0;
  color: #5a6b82;
  font-size: 0.92rem;
}
</style>