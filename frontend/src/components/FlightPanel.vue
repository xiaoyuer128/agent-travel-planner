<script setup lang="ts">
import { computed } from "vue";
import type { Flight, TravelPlanState } from "../types/plan";
import { money, tTime } from "../utils/format";

const props = defineProps<{ state: TravelPlanState }>();
const f = computed(() => props.state.flight_result);

function depFmt(row: Flight): string {
  return tTime(row.departure_time);
}
function arrFmt(row: Flight): string {
  return tTime(row.arrival_time);
}
function priceFmt(row: Flight): string {
  return money(row.price);
}
</script>

<template>
  <div v-if="f" class="card">
    <el-row :gutter="12" v-if="f.recommended_outbound || f.recommended_return">
      <el-col :span="12" v-if="f.recommended_outbound">
        <div class="flight-card highlight">
          <div class="flight-head">⭐ 推荐去程</div>
          <div class="airline">{{ f.recommended_outbound.airline }} · {{ f.recommended_outbound.flight_no }}</div>
          <div class="times">{{ tTime(f.recommended_outbound.departure_time) }} → {{ tTime(f.recommended_outbound.arrival_time) }}</div>
          <div class="muted">{{ f.recommended_outbound.departure_city }} → {{ f.recommended_outbound.arrival_city }}</div>
          <div class="price">{{ money(f.recommended_outbound.price) }}</div>
        </div>
      </el-col>
      <el-col :span="12" v-if="f.recommended_return">
        <div class="flight-card highlight">
          <div class="flight-head">⭐ 推荐回程</div>
          <div class="airline">{{ f.recommended_return.airline }} · {{ f.recommended_return.flight_no }}</div>
          <div class="times">{{ tTime(f.recommended_return.departure_time) }} → {{ tTime(f.recommended_return.arrival_time) }}</div>
          <div class="muted">{{ f.recommended_return.departure_city }} → {{ f.recommended_return.arrival_city }}</div>
          <div class="price">{{ money(f.recommended_return.price) }}</div>
        </div>
      </el-col>
    </el-row>

    <h3 style="margin-top: 16px">去程航班</h3>
    <el-table :data="f.outbound_flights" size="small" stripe>
      <el-table-column prop="airline" label="航司" />
      <el-table-column prop="flight_no" label="航班号" />
      <el-table-column label="起飞" :formatter="depFmt" />
      <el-table-column label="到达" :formatter="arrFmt" />
      <el-table-column prop="stops" label="经停" width="70" />
      <el-table-column label="价格" :formatter="priceFmt" sortable />
    </el-table>

    <h3 style="margin-top: 16px">返程航班</h3>
    <el-table :data="f.return_flights" size="small" stripe>
      <el-table-column prop="airline" label="航司" />
      <el-table-column prop="flight_no" label="航班号" />
      <el-table-column label="起飞" :formatter="depFmt" />
      <el-table-column label="到达" :formatter="arrFmt" />
      <el-table-column prop="stops" label="经停" width="70" />
      <el-table-column label="价格" :formatter="priceFmt" sortable />
    </el-table>

    <div class="metric-row">
      <div class="metric">
        <div class="label">航班总费用</div>
        <div class="value">{{ money(f.total_flight_cost) }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.flight-card {
  background: #f7f9fd;
  border: 1px solid #eef1f7;
  border-radius: 14px;
  padding: 14px 16px;
  margin-bottom: 12px;
}
.flight-card.highlight {
  background: linear-gradient(135deg, #eef4ff, #f7f0ff);
  border-color: #c9d8f5;
}
.flight-head {
  font-size: 0.78rem;
  color: #7c8aa0;
}
.airline {
  font-weight: 700;
  margin-top: 4px;
}
.times {
  font-size: 1.25rem;
  font-weight: 800;
  color: #1e3a5f;
  margin: 4px 0;
}
.price {
  font-size: 1.1rem;
  font-weight: 800;
  color: #2b5cae;
  margin-top: 6px;
}
</style>