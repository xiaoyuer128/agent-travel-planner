<script setup lang="ts">
defineProps<{ theme: string; label: string }>();
</script>
<template>
  <svg viewBox="0 0 360 200" preserveAspectRatio="xMidYMid slice" role="img" :aria-label="label" class="scenery-art" :class="theme">
    <defs><linearGradient :id="'sky-'+theme" x2="0" y2="1"><stop stop-color="var(--sky-a)"/><stop offset="1" stop-color="var(--sky-b)"/></linearGradient></defs>
    <rect width="360" height="200" :fill="`url(#sky-${theme})`"/>
    <circle cx="282" cy="48" r="25" fill="#fff0be" opacity=".95"/>
    <path d="M0 132L65 68 114 120 186 45 270 133 320 92 360 130V200H0Z" fill="var(--mountain)" opacity=".32"/>
    <path d="M148 88L186 45 225 87 196 80 180 70 170 86Z" fill="#fff" opacity=".8"/>
    <path d="M0 155 Q85 125 160 160T360 147V200H0Z" fill="var(--water)" opacity=".5"/>
    <path d="M0 174 Q110 151 216 179T360 167" fill="none" stroke="#fff" stroke-width="2" opacity=".5"/>
    <g v-if="theme==='sakura'" fill="#303e60"><rect x="55" y="104" width="8" height="67"/><rect x="103" y="104" width="8" height="67"/><path d="M43 99H124L117 107H50Z"/><path d="M38 87Q82 100 130 87L126 96Q83 107 42 96Z"/><rect x="55" y="119" width="56" height="5"/></g>
    <g v-else-if="theme==='city'" fill="#b75f43"><rect x="39" y="111" width="31" height="66"/><rect x="78" y="87" width="26" height="90"/><rect x="111" y="122" width="35" height="55"/><path d="M31 111L54 95 78 111ZM70 87L91 70 111 87ZM104 122L130 103 153 122Z" fill="#694d53"/><path d="M44 126H64M44 137H64M83 105H98M83 119H98M116 138H140M116 150H140" stroke="#ffd5a0" stroke-width="5"/></g>
    <g v-else-if="theme==='garden'" fill="#386952"><path d="M44 155L66 102 89 155ZM82 162L104 93 130 162Z"/><rect x="65" y="143" width="3" height="35"/><rect x="103" y="143" width="4" height="35"/><path d="M142 159Q168 120 195 159" fill="none" stroke="#e5d0aa" stroke-width="10"/></g>
    <g v-else fill="#495679"><path d="M58 170L88 63 118 170H107L87 103 69 170Z"/><path d="M67 143H109M76 115H101" stroke="#495679" stroke-width="5"/><rect x="84" y="49" width="5" height="23"/></g>
    <g v-if="theme==='sakura'" fill="#f6b4c4"><circle cx="8" cy="46" r="29"/><circle cx="35" cy="24" r="24"/><circle cx="53" cy="49" r="18"/><circle cx="30" cy="62" r="23"/></g>
    <path d="M234 40q7-8 14 0m8 4q6-7 12 0" fill="none" stroke="#fff" stroke-width="2" opacity=".7"/>
  </svg>
</template>
<style scoped>
.scenery-art{display:block;width:100%;height:100%;object-fit:cover;--sky-a:#cedbe7;--sky-b:#f5dcb7;--mountain:#54718c;--water:#6387a0}.sakura{--sky-a:#bfcde8;--sky-b:#f2dce5;--mountain:#5e719a;--water:#879cc6}.city{--sky-a:#f2bd8b;--sky-b:#fae5bb;--mountain:#bb765e;--water:#8294a0}.garden{--sky-a:#bdd8c9;--sky-b:#e9edcd;--mountain:#559b83;--water:#8bb6a0}
</style>
