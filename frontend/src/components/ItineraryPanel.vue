<script setup lang="ts">
import { computed } from "vue";
import type { TravelPlanState } from "../types/plan";
import { money } from "../utils/format";

const props = defineProps<{ state: TravelPlanState }>();
const plans = computed(() => props.state.activity_result?.day_plans ?? []);
const total = computed(() => props.state.activity_result?.total_activity_cost ?? 0);

const SLOT_CLASS: Record<string, string> = {
  上午: "tag-green",
  下午: "tag",
  晚上: "tag-warn",
};
</script>

<template>
  <div class="card">
    <div class="metric-row">
      <div class="metric">
        <div class="label">活动总费用</div>
        <div class="value">{{ money(total) }}</div>
      </div>
    </div>

    <div v-for="day in plans" :key="day.date" class="day">
      <div class="day-head">
        <span>📅 {{ day.date }}</span>
        <span class="day-cost">{{ money(day.day_cost) }}</span>
      </div>
      <div v-for="(a, i) in day.activities" :key="i" class="activity">
        <span class="slot" :class="SLOT_CLASS[a.time_slot] ?? 'tag'">{{ a.time_slot }}</span>
        <div class="act-main">
          <div class="act-name">{{ a.name }}</div>
          <div class="muted">{{ a.location }} · {{ a.duration_hours }}h · ⭐{{ a.rating }}</div>
        </div>
        <span class="act-price">{{ money(a.price) }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.day {
  margin-bottom: 18px;
}
.day-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: linear-gradient(120deg, #16324f, #1f4e8c);
  color: #fff;
  padding: 9px 16px;
  border-radius: 10px 10px 0 0;
  font-weight: 700;
}
.day-cost {
  color: #ffd98a;
}
.activity {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  border: 1px solid #eef1f7;
  border-top: none;
  background: #fff;
}
.activity:last-child {
  border-radius: 0 0 10px 10px;
}
.slot {
  flex: 0 0 auto;
  min-width: 44px;
  text-align: center;
}
.act-main {
  flex: 1;
}
.act-name {
  font-weight: 700;
  color: #1e3a5f;
}
.act-price {
  font-weight: 800;
  color: #2b5cae;
  flex: 0 0 auto;
}
</style>