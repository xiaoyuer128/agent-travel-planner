<script setup lang="ts">
import { computed } from "vue";
import type { TravelPlanState } from "../types/plan";

const props = defineProps<{ state: TravelPlanState }>();
const contexts = computed(() => props.state.rag_context ?? []);
</script>

<template>
  <div class="card">
    <div v-if="contexts.length">
      <div class="muted" style="margin-bottom: 10px">
        共检索到 <strong>{{ contexts.length }}</strong> 篇目的地攻略片段（BGE-M3 + Milvus，默认 Mock 模式）
      </div>
      <div v-for="(ctx, i) in contexts" :key="i" class="rag-item">
        <div class="rag-num">#{{ i + 1 }}</div>
        <p>{{ ctx }}</p>
      </div>
    </div>
    <el-empty v-else description="未检索到 RAG 上下文" />
  </div>
</template>

<style scoped>
.muted strong {
  color: #2b5cae;
}
.rag-item {
  display: flex;
  gap: 12px;
  background: #f7f9fd;
  border: 1px solid #eef1f7;
  border-radius: 12px;
  padding: 12px 15px;
  margin-bottom: 10px;
}
.rag-num {
  flex: 0 0 auto;
  color: #2b5cae;
  font-weight: 800;
}
.rag-item p {
  margin: 0;
  line-height: 1.7;
  color: #3a4c63;
}
</style>