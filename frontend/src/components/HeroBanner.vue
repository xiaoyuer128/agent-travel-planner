<template>
  <div class="hero">
    <h1>✈️ 智能旅行规划</h1>
    <p class="sub">6 个 AI Agent 协作，输入预算与偏好，一键生成完整行程</p>
    <div>
      <span class="hero-badge">⚡ 6-Agent 协作</span>
      <span class="hero-badge">🔀 并行搜索</span>
      <span class="hero-badge">💰 智能预算控制</span>
      <span class="hero-badge">📚 RAG 知识库</span>
    </div>
  </div>
</template>

<style scoped>
.hero {
  background: linear-gradient(120deg, #16324f 0%, #1f4e8c 45%, #4a5fd0 100%);
  border-radius: 20px;
  padding: 32px 42px;
  color: #fff;
  margin-bottom: 20px;
  box-shadow: 0 12px 32px rgba(31, 78, 140, 0.28);
}
.hero h1 {
  color: #fff;
  font-size: 2.15rem;
  margin: 0 0 8px;
  letter-spacing: 0.5px;
}
.hero .sub {
  font-size: 1.02rem;
  opacity: 0.92;
  margin: 0 0 18px;
}
.hero-badge {
  display: inline-block;
  background: rgba(255, 255, 255, 0.16);
  border: 1px solid rgba(255, 255, 255, 0.3);
  padding: 6px 15px;
  border-radius: 999px;
  margin-right: 8px;
  font-size: 0.85rem;
}
</style>