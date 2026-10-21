<script setup lang="ts">
import { computed } from "vue";
import type { Hotel, TravelPlanState } from "../types/plan";
import { money } from "../utils/format";

const props = defineProps<{ state: TravelPlanState }>();
const h = computed(() => props.state.hotel_result);

function ratingFmt(row: Hotel): string {
  return row.user_rating.toFixed(1);
}
function distFmt(row: Hotel): string {
  return `${row.distance_to_center_km} km`;
}
function priceFmt(row: Hotel): string {
  return money(row.price_per_night);
}
</script>

<template>
  <div v-if="h" class="card">
    <div v-if="h.recommended" class="hotel-card">
      <div>
        <div class="hotel-name">{{ h.recommended.name }}</div>
        <div class="muted">{{ h.recommended.address }}</div>
      </div>
      <div class="hotel-right">
        <div class="hotel-price">{{ money(h.recommended.price_per_night) }}<span class="muted">/晚</span></div>
        <div class="hotel-stars">⭐ {{ h.recommended.star_rating }} 星 · {{ h.recommended.user_rating.toFixed(1) }} 分</div>
      </div>
    </div>

    <div style="margin: 8px 0" v-if="h.recommended">
      <span v-for="a in h.recommended.amenities" :key="a" class="tag">{{ a }}</span>
    </div>

    <h3 style="margin-top: 16px">可选酒店</h3>
    <el-table :data="h.hotels" size="small" stripe>
      <el-table-column prop="name" label="酒店" />
      <el-table-column prop="star_rating" label="星级" width="70" />
      <el-table-column label="评分" :formatter="ratingFmt" width="80" />
      <el-table-column label="距离市中心" :formatter="distFmt" width="110" />
      <el-table-column label="每晚价格" :formatter="priceFmt" sortable />
    </el-table>

    <div class="metric-row">
      <div class="metric">
        <div class="label">入住晚数</div>
        <div class="value">{{ h.total_nights }} 晚</div>
      </div>
      <div class="metric">
        <div class="label">酒店总费用</div>
        <div class="value">{{ money(h.total_hotel_cost) }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.hotel-card {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  background: linear-gradient(135deg, #f0f8ff, #fdf6ec);
  border: 1px solid #d6e4f5;
  border-radius: 14px;
  padding: 16px 20px;
}
.hotel-name {
  font-size: 1.2rem;
  font-weight: 800;
  color: #1e3a5f;
}
.hotel-right {
  text-align: right;
}
.hotel-price {
  font-size: 1.3rem;
  font-weight: 800;
  color: #2b5cae;
}
.hotel-stars {
  font-size: 0.85rem;
  color: #c46a08;
  margin-top: 4px;
}
</style>