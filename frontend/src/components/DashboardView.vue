<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from "vue";
import { fetchSystem, restartPanel, restartAwg, restartServer, resetTraffic } from "../api.js";
import { formatBytes, formatDuration } from "../format.js";
import GaugeCard from "./GaugeCard.vue";
import TrafficCard from "./TrafficCard.vue";
import ActionModal from "./ActionModal.vue";

const system = ref(null);
const error = ref("");
const modal = ref({
  show: false,
  title: "",
  message: "",
  confirmText: "",
  loadingText: "",
  successText: "",
  errorText: "",
  action: null,
});
const modalState = ref("confirm");
let timer = null;

const applySystem = (data) => {
  system.value = data;
  error.value = "";
};

const load = async ({ force = false, quiet = false } = {}) => {
  if (modalState.value === "loading" && !force) return;
  try {
    const data = await fetchSystem();
    applySystem(data);
  } catch (err) {
    if (!quiet) {
      error.value = "Не удалось загрузить данные системы";
    }
  }
};

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const waitForReboot = async (previousUptime) => {
  const startedAt = Date.now();
  const timeoutMs = 5 * 60 * 1000;
  let sawDisconnect = false;
  while (Date.now() - startedAt < timeoutMs) {
    try {
      const data = await fetchSystem();
      const uptime = Number(data.uptime_seconds || 0);
      if (!previousUptime && sawDisconnect) {
        applySystem(data);
        return;
      }
      if (sawDisconnect && uptime >= 0 && uptime < previousUptime - 5) {
        applySystem(data);
        return;
      }
      if (uptime >= 0 && uptime < previousUptime - 30) {
        applySystem(data);
        return;
      }
    } catch (err) {
      sawDisconnect = true;
    }
    await sleep(3000);
  }
  throw new Error("timeout");
};

const waitForPanelRestart = async (previousStartedAt) => {
  const startedAt = Date.now();
  const timeoutMs = 2 * 60 * 1000;
  let sawDisconnect = false;
  await sleep(1200);
  while (Date.now() - startedAt < timeoutMs) {
    try {
      const data = await fetchSystem();
      const startedAtValue = Number(data.panel_started_at || 0);
      if (previousStartedAt && startedAtValue && startedAtValue !== previousStartedAt) {
        applySystem(data);
        return;
      }
      if (!previousStartedAt && sawDisconnect) {
        applySystem(data);
        return;
      }
    } catch (err) {
      sawDisconnect = true;
    }
    await sleep(1500);
  }
  throw new Error("timeout");
};

onMounted(() => {
  load();
  timer = setInterval(load, 1000);
});

onBeforeUnmount(() => {
  if (timer) clearInterval(timer);
});

const cpuSubtitle = computed(() => {
  if (!system.value) return "";
  return `ЦП: ${system.value.cpu_cores} Cores`;
});

const memSubtitle = computed(() => {
  if (!system.value) return "";
  return `ОЗУ: ${formatBytes(system.value.mem_used)} / ${formatBytes(system.value.mem_total)}`;
});

const diskSubtitle = computed(() => {
  if (!system.value) return "";
  return `Диск: ${formatBytes(system.value.disk_used)} / ${formatBytes(system.value.disk_total)}`;
});

const uptimeLabel = computed(() => {
  if (!system.value) return "—";
  return formatDuration(system.value.uptime_seconds);
});

const trafficItems = computed(() => {
  if (!system.value) return [];
  const overallTotal = system.value.overall_total_display || "—";
  const overallTx = system.value.overall_tx_display || "—";
  const overallRx = system.value.overall_rx_display || "—";
  const currentTotal = system.value.current_total_display || "—";
  const currentTx = system.value.current_tx_display || "—";
  const currentRx = system.value.current_rx_display || "—";
  return [
    {
      label: "Общий трафик",
      value: overallTotal,
      sub: `↑ ${overallTx} · ↓ ${overallRx}`,
    },
    {
      label: "С момента перезапуска AWG",
      value: currentTotal,
      sub: `↑ ${currentTx} · ↓ ${currentRx}`,
    },
    {
      label: "Отправлено всего",
      value: overallTx,
    },
  ];
});

const openAction = (config) => {
  modal.value = {
    ...modal.value,
    ...config,
    show: true,
  };
  modalState.value = "confirm";
};

const closeModal = () => {
  modal.value.show = false;
  modalState.value = "confirm";
};

const runAction = async () => {
  if (!modal.value.action) return;
  modalState.value = "loading";
  try {
    await modal.value.action();
    modalState.value = "success";
  } catch (err) {
    modalState.value = "error";
  }
};

const onRestartPanel = () => {
  openAction({
    title: "Перезапустить панель?",
    message: "Панель управления будет перезапущена.",
    confirmText: "Перезапустить",
    loadingText: "Перезапуск панели...",
    successText: "Панель управления успешно перезапущена",
    errorText: "Не удалось перезапустить панель",
    action: async () => {
      const previousStartedAt = Number(system.value?.panel_started_at || 0);
      try {
        await restartPanel();
      } catch (err) {
        if (!previousStartedAt) throw err;
      }
      await waitForPanelRestart(previousStartedAt);
    },
  });
};

const onRestartAwg = () => {
  openAction({
    title: "Перезапустить AmneziaWG?",
    message: "Туннель будет кратковременно недоступен.",
    confirmText: "Перезапустить",
    loadingText: "Перезапуск AmneziaWG...",
    successText: "AmneziaWG успешно перезапущен",
    errorText: "Не удалось перезапустить AmneziaWG",
    action: async () => {
      await restartAwg();
      await load({ force: true });
    },
  });
};

const onRestartServer = () => {
  openAction({
    title: "Перезагрузить сервер?",
    message: "Сервер будет перезагружен. Подключение может прерваться.",
    confirmText: "Перезагрузить",
    loadingText: "Перезагрузка сервера...",
    successText: "Сервер успешно перезагружен",
    errorText: "Не удалось перезагрузить сервер",
    action: async () => {
      const previousUptime = Number(system.value?.uptime_seconds || 0);
      await restartServer();
      await waitForReboot(previousUptime);
    },
  });
};

const onResetTraffic = () => {
  openAction({
    title: "Сбросить трафик?",
    message: "Общий счетчик трафика будет обнулен.",
    confirmText: "Сбросить",
    loadingText: "Сброс трафика...",
    successText: "Трафик успешно сброшен",
    errorText: "Не удалось сбросить трафик",
    action: async () => {
      await resetTraffic();
      await load({ force: true });
    },
  });
};
</script>

<template>
  <section class="dashboard">
    <div v-if="error" class="banner error">{{ error }}</div>
    <div class="dashboard-grid">
      <GaugeCard :percent="system?.cpu_percent || 0" title="ЦП" :subtitle="cpuSubtitle" />
      <GaugeCard :percent="system?.mem_percent || 0" title="ОЗУ" :subtitle="memSubtitle" />
      <GaugeCard :percent="system?.disk_percent || 0" title="Диск" :subtitle="diskSubtitle" />
    </div>

    <div class="info-grid">
      <div class="info-card">
        <div class="info-label">Версия ОС</div>
        <div class="info-value">{{ system?.os_version || "—" }}</div>
      </div>
      <div class="info-card">
        <div class="info-label">AmneziaWG</div>
        <div class="info-value">{{ system?.awg_version || "—" }}</div>
      </div>
      <div class="info-card">
        <div class="info-label">Uptime</div>
        <div class="info-value">{{ uptimeLabel }}</div>
      </div>
    </div>

    <TrafficCard :items="trafficItems" @reset="onResetTraffic" />

    <div class="control-card">
      <div class="control-title">Управление сервером</div>
      <div class="control-actions">
        <button class="btn ghost" type="button" @click="onRestartPanel">Перезапустить панель</button>
        <button class="btn ghost" type="button" @click="onRestartAwg">Перезапустить AmneziaWG</button>
        <button class="btn danger" type="button" @click="onRestartServer">Перезагрузить сервер</button>
      </div>
    </div>

    <ActionModal
      :show="modal.show"
      :title="modal.title"
      :message="modal.message"
      :confirm-text="modal.confirmText"
      :loading-text="modal.loadingText"
      :success-text="modal.successText"
      :error-text="modal.errorText"
      :state="modalState"
      @confirm="runAction"
      @close="closeModal"
    />
  </section>
</template>
