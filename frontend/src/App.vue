<script setup lang="ts">
import { ref } from "vue";
import type { PlanRequest, TravelPlanState } from "./types/plan";
import { planFull } from "./api/client";
import HeroBanner from "./components/HeroBanner.vue";
import PreferencesForm from "./components/PreferencesForm.vue";
import DestinationCard from "./components/DestinationCard.vue";
import FlightPanel from "./components/FlightPanel.vue";
import HotelPanel from "./components/HotelPanel.vue";
import ItineraryPanel from "./components/ItineraryPanel.vue";
import BudgetPanel from "./components/BudgetPanel.vue";
import RagPanel from "./components/RagPanel.vue";

const state = ref<TravelPlanState | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);
const activeTab = ref("flight");

async function handleSubmit(req: PlanRequest) {
  loading.value = true;
  error.value = null;
  try {
    state.value = await planFull(req);
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <HeroBanner />

  <el-row :gutter="20">
    <el-col :xs="24" :md="9">
      <PreferencesForm :loading="loading" @submit="handleSubmit" />
    </el-col>

    <el-col :xs="24" :md="15">
      <el-alert
        v-if="error"
        :title="error"
        type="error"
        :closable="false"
        style="margin-bottom: 16px"
      />

      <template v-if="state">
        <DestinationCard :state="state" />
        <el-tabs v-model="activeTab">
          <el-tab-pane label="🛫 航班" name="flight">
            <FlightPanel :state="state" />
          </el-tab-pane>
          <el-tab-pane label="🏨 酒店" name="hotel">
            <HotelPanel :state="state" />
          </el-tab-pane>
          <el-tab-pane label="📅 每日行程" name="itinerary">
            <ItineraryPanel :state="state" />
          </el-tab-pane>
          <el-tab-pane label="💰 预算" name="budget">
            <BudgetPanel :state="state" />
          </el-tab-pane>
          <el-tab-pane label="📚 RAG 知识库" name="rag">
            <RagPanel :state="state" />
          </el-tab-pane>
        </el-tabs>
      </template>

      <el-empty v-else-if="!loading" description="填写左侧偏好，点击「开始规划」" />
      <el-skeleton v-if="loading" :rows="6" animated style="margin-top: 16px" />
    </el-col>
  </el-row>

  <div class="footer">
    多 Agent 智能旅游行程规划系统 · 6-Agent Pipeline + 并行搜索 + 预算循环 + RAG
  </div>
</template>