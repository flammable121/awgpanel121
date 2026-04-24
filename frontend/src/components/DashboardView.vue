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

const load = async () => {
  try {
    const data = await fetchSystem();
    system.value = data;
    error.value = "";
  } catch (err) {
    error.value = "Не удалось загрузить данные системы";
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
      if (sawDisconnect && uptime >= 0 && uptime < previousUptime - 5) {
        system.value = data;
        return;
      }
      if (uptime >= 0 && uptime < previousUptime - 30) {
        system.value = data;
        return;
      }
    } catch (err) {
      sawDisconnect = true;
    }
    await sleep(3000);
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
      await restartPanel();
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
      await load();
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
      await load();
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
        <button v-if="system?.allow_container_restart" class="btn ghost" type="button" @click="onRestartPanel">Перезапустить панель</button>
        <button v-if="system?.allow_container_restart" class="btn ghost" type="button" @click="onRestartAwg">Перезапустить AmneziaWG</button>
        <button v-if="system?.allow_system_reboot" class="btn danger" type="button" @click="onRestartServer">Перезагрузить сервер</button>
      </div>
      <div v-if="system && !system.allow_container_restart" class="muted">Перезапуск контейнеров отключен в настройках безопасности.</div>
      <div v-if="system && !system.allow_system_reboot" class="muted">Перезагрузка сервера отключена в настройках безопасности.</div>
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
