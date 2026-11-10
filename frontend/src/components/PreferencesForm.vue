<script setup lang="ts">
import { reactive } from "vue";
import type { PlanRequest, TravelStyle } from "../types/plan";

defineProps<{ loading: boolean }>();
const emit = defineEmits<{ (e: "submit", req: PlanRequest): void }>();

const STYLES: { value: TravelStyle; label: string }[] = [
  { value: "comfort", label: "舒适" },
  { value: "budget", label: "经济" },
  { value: "luxury", label: "豪华" },
  { value: "adventure", label: "探险" },
  { value: "cultural", label: "文化" },
  { value: "relaxation", label: "休闲" },
];

const INTERESTS = ["美食", "历史", "艺术", "自然", "购物", "摄影", "运动"];
const DESTINATIONS = ["杭州", "三亚", "上海", "南京", "北京", "西安"];

function dateStr(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}
function defaultStart(): string {
  const d = new Date();
  d.setDate(d.getDate() + 7);
  return dateStr(d);
}
function defaultEnd(): string {
  const d = new Date();
  d.setDate(d.getDate() + 11);
  return dateStr(d);
}

const form = reactive({
  budget: 10000,
  departure_city: "北京",
  start_date: defaultStart(),
  end_date: defaultEnd(),
  travel_style: "comfort" as TravelStyle,
  num_travelers: 1,
  interests: ["美食", "历史"] as string[],
  notes: "",
  destination: "",
});

function submit() {
  emit("submit", {
    budget: form.budget,
    departure_city: form.departure_city,
    start_date: form.start_date,
    end_date: form.end_date,
    travel_style: form.travel_style,
    num_travelers: form.num_travelers,
    interests: form.interests,
    notes: form.notes,
    destination: form.destination || null,
  });
}
</script>

<template>
  <div class="card">
    <h3>📝 旅行偏好</h3>
    <el-form label-position="top" @submit.prevent="submit">
      <el-form-item label="总预算（¥）">
        <el-input-number v-model="form.budget" :min="1000" :max="500000" :step="1000" style="width: 100%" />
      </el-form-item>

      <el-form-item label="出发城市">
        <el-input v-model="form.departure_city" placeholder="例：北京" />
      </el-form-item>

      <el-form-item label="想去的目的地（可选，支持任意城市）">
        <el-select
          v-model="form.destination"
          clearable
          filterable
          allow-create
          default-first-option
          placeholder="留空由 AI 自动推荐，或输入任意城市"
          style="width: 100%"
        >
          <el-option v-for="d in DESTINATIONS" :key="d" :label="d" :value="d" />
        </el-select>
      </el-form-item>

      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item label="出发日期">
            <el-date-picker v-model="form.start_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="返回日期">
            <el-date-picker v-model="form.end_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
          </el-form-item>
        </el-col>
      </el-row>

      <el-form-item label="旅行风格">
        <el-select v-model="form.travel_style" style="width: 100%">
          <el-option v-for="s in STYLES" :key="s.value" :label="s.label" :value="s.value" />
        </el-select>
      </el-form-item>

      <el-form-item label="出行人数">
        <el-input-number v-model="form.num_travelers" :min="1" :max="10" style="width: 100%" />
      </el-form-item>

      <el-form-item label="兴趣标签">
        <el-select v-model="form.interests" multiple style="width: 100%">
          <el-option v-for="i in INTERESTS" :key="i" :label="i" :value="i" />
        </el-select>
      </el-form-item>

      <el-form-item label="额外备注">
        <el-input v-model="form.notes" type="textarea" :rows="2" placeholder="例：不吃辣、需要无障碍设施…" />
      </el-form-item>

      <el-button type="primary" native-type="submit" :loading="loading" style="width: 100%">
        🚀 开始规划
      </el-button>
    </el-form>
  </div>
</template>