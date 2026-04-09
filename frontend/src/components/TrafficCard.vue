<script>
export default {
  name: "TrafficCard",
  props: {
    items: { type: Array, default: () => [] },
    resetDisabled: { type: Boolean, default: false },
  },
  emits: ["reset"],
};
</script>

<template>
  <div class="traffic-card">
    <div class="traffic-head">
      <div class="traffic-title">Трафик</div>
      <button class="btn ghost tiny" type="button" :disabled="resetDisabled" @click="$emit('reset')">Сбросить</button>
    </div>
    <div class="traffic-grid traffic-grid-3">
      <div v-for="(item, index) in items" :key="index" class="traffic-item">
        <div class="traffic-label">{{ item.label }}</div>
        <div class="traffic-value">{{ item.value }}</div>
        <div v-if="item.sub" class="traffic-sub">{{ item.sub }}</div>
      </div>
    </div>
  </div>
</template>
