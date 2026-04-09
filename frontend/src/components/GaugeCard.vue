<script>
import { computed } from "vue";

export default {
  name: "GaugeCard",
  props: {
    percent: { type: Number, default: 0 },
    title: { type: String, default: "" },
    subtitle: { type: String, default: "" },
  },
  setup(props) {
    const radius = 46;
    const circumference = 2 * Math.PI * radius;
    const safePercent = computed(() => Math.max(0, Math.min(100, Number(props.percent) || 0)));
    const offset = computed(() => circumference * (1 - safePercent.value / 100));
    const label = computed(() => `${safePercent.value.toFixed(0)}%`);
    return { radius, circumference, offset, label };
  },
};
</script>

<template>
  <div class="gauge-card">
    <div class="gauge-wrap">
      <svg class="gauge" viewBox="0 0 120 120">
        <circle class="gauge-bg" cx="60" cy="60" :r="radius" fill="none" stroke-width="10" />
        <circle
          class="gauge-fg"
          cx="60"
          cy="60"
          :r="radius"
          fill="none"
          stroke-width="10"
          stroke-linecap="round"
          :stroke-dasharray="circumference"
          :stroke-dashoffset="offset"
        />
      </svg>
      <div class="gauge-percent">{{ label }}</div>
    </div>
    <div class="gauge-meta">
      <div class="gauge-title">{{ title }}</div>
      <div class="gauge-subtitle">{{ subtitle }}</div>
    </div>
  </div>
</template>
