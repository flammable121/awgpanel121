<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from "vue";
import { fetchPeers, togglePeer, deletePeer, fetchStats, createPeer, withBase } from "../api.js";
import { formatBytes, formatDateTime } from "../format.js";
import ClientTable from "./ClientTable.vue";
import ConfigModal from "./ConfigModal.vue";
import CreateModal from "./CreateModal.vue";
import DeleteModal from "./DeleteModal.vue";

const peers = ref([]);
const filter = ref("");
const sortKey = ref("name");
const sortDir = ref(1);
const modalPeer = ref(null);
const createOpen = ref(false);
const creating = ref(false);
const deletePeerTarget = ref(null);
const deleteBusy = ref(false);
let statsTimer = null;
const lastStats = new Map();

const loadPeers = async () => {
  try {
    const data = await fetchPeers();
    const rows = data.rows || data.peers || [];
    peers.value = rows.map((peer) => {
      const total = peer?.traffic?.total ?? peer.traffic_total ?? 0;
      const expiresSort = peer.expires_at ? Date.parse(peer.expires_at) : 0;
      const expiresDisplay = peer.expires_at ? formatDateTime(peer.expires_at) : "∞";
      return {
        ...peer,
        busy: false,
        online: false,
        speed_rx: "0 B/s",
        speed_tx: "0 B/s",
        traffic_total: total,
        traffic_display: formatBytes(total),
        expires_sort: expiresSort,
        expires_display: expiresDisplay,
      };
    });
  } catch (err) {
    alert("Не удалось загрузить клиентов");
  }
};

const filteredPeers = computed(() => {
  const needle = filter.value.trim().toLowerCase();
  return peers.value.filter((peer) => {
    const hay = `${peer.name} ${peer.allowed_ips} ${peer.client_allowed_ips || ""} ${peer.client_dns || ""} ${peer.note || ""} ${peer.status_label}`.toLowerCase();
    return !needle || hay.includes(needle);
  });
});

const sortedPeers = computed(() => {
  const data = [...filteredPeers.value];
  const key = sortKey.value;
  const dir = sortDir.value;
  const order = { active: 0, disabled: 1, expired: 2 };
  data.sort((a, b) => {
    let aVal = a[key];
    let bVal = b[key];
    if (key === "expires") {
      aVal = Number(a.expires_sort || 0);
      bVal = Number(b.expires_sort || 0);
    }
    if (key === "status") {
      aVal = order[a.status] ?? 9;
      bVal = order[b.status] ?? 9;
    }
    if (key === "traffic") {
      aVal = Number(a.traffic_total || 0);
      bVal = Number(b.traffic_total || 0);
    }
    if (typeof aVal === "string") {
      aVal = aVal.toLowerCase();
      bVal = bVal.toLowerCase();
    }
    if (aVal < bVal) return -1 * dir;
    if (aVal > bVal) return 1 * dir;
    return 0;
  });
  return data;
});

const onSort = (key) => {
  if (sortKey.value === key) {
    sortDir.value *= -1;
  } else {
    sortKey.value = key;
    sortDir.value = 1;
  }
};

const onToggle = async (peer) => {
  const prevEnabled = peer.enabled;
  const prevStatus = peer.status;
  const prevLabel = peer.status_label;
  peer.busy = true;
  peer.enabled = !peer.enabled;
  peer.status = peer.enabled ? "active" : "disabled";
  peer.status_label = peer.enabled ? "Активен" : "Отключен";
  if (!peer.enabled) {
    peer.online = false;
  }
  try {
    const data = await togglePeer(peer.id);
    peer.enabled = data.enabled;
    peer.status = data.status;
    peer.status_label = data.status_label || (peer.enabled ? "Активен" : "Отключен");
  } catch (err) {
    peer.enabled = prevEnabled;
    peer.status = prevStatus;
    peer.status_label = prevLabel;
    alert("Не удалось изменить статус");
  } finally {
    peer.busy = false;
  }
};

const onDelete = (peer) => {
  deletePeerTarget.value = peer;
};

const confirmDelete = async () => {
  if (!deletePeerTarget.value) return;
  deleteBusy.value = true;
  const target = deletePeerTarget.value;
  target.busy = true;
  try {
    await deletePeer(target.id);
    peers.value = peers.value.filter((item) => item.id !== target.id);
    deletePeerTarget.value = null;
  } catch (err) {
    alert("Не удалось удалить клиента");
  } finally {
    target.busy = false;
    deleteBusy.value = false;
  }
};

const cancelDelete = () => {
  deletePeerTarget.value = null;
};

const onCreate = async (payload) => {
  creating.value = true;
  try {
    await createPeer(payload);
    await loadPeers();
    createOpen.value = false;
  } catch (err) {
    alert("Не удалось создать клиента");
  } finally {
    creating.value = false;
  }
};

const onConfig = (peer) => {
  modalPeer.value = peer;
};

const onEdit = (peer) => {
  if (!peer) return;
  window.location.href = withBase(`/peers/${peer.id}`);
};

const closeModal = () => {
  modalPeer.value = null;
};

const copyUrl = async () => {
  if (!modalPeer.value) return;
  const url = `${window.location.origin}${withBase(`/peers/${modalPeer.value.id}/config`)}`;
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(url);
      alert("URL скопирован");
      return;
    }
    const textarea = document.createElement("textarea");
    textarea.value = url;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "absolute";
    textarea.style.left = "-9999px";
    document.body.appendChild(textarea);
    textarea.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(textarea);
    if (ok) {
      alert("URL скопирован");
    } else {
      prompt("Скопируйте URL вручную:", url);
    }
  } catch (err) {
    prompt("Скопируйте URL вручную:", url);
  }
};

const updateTraffic = async () => {
  try {
    const stats = await fetchStats();
    const map = new Map();
    (stats.peers || []).forEach((item) => {
      map.set(item.public_key, item);
    });
    const now = stats.server_time || Math.floor(Date.now() / 1000);
    peers.value.forEach((peer) => {
      const stat = map.get(peer.public_key);
      if (!stat) {
        peer.online = false;
        peer.speed_rx = "0 B/s";
        peer.speed_tx = "0 B/s";
        return;
      }
      if (stat.total_display) {
        peer.traffic_display = stat.total_display;
        peer.traffic_total = stat.total;
      }
      const prev = lastStats.get(peer.public_key);
      if (prev) {
        const dt = Math.max(1, now - prev.ts);
        const rxRate = Math.max(0, stat.rx - prev.rx) / dt;
        const txRate = Math.max(0, stat.tx - prev.tx) / dt;
        peer.speed_rx = `${formatBytes(rxRate)}/s`;
        peer.speed_tx = `${formatBytes(txRate)}/s`;
      } else {
        peer.speed_rx = "0 B/s";
        peer.speed_tx = "0 B/s";
      }
      const last = Number(stat.latest_handshake || 0);
      peer.online = peer.enabled && last > 0 && now - last <= 120;
      lastStats.set(peer.public_key, { rx: stat.rx, tx: stat.tx, ts: now });
    });
  } catch (err) {
    // ignore
  }
};

onMounted(async () => {
  await loadPeers();
  updateTraffic();
  statsTimer = setInterval(updateTraffic, 1000);
});

onBeforeUnmount(() => {
  if (statsTimer) clearInterval(statsTimer);
});

const openCreate = () => {
  createOpen.value = true;
};

const closeCreate = () => {
  createOpen.value = false;
};
</script>

<template>
  <div class="toolbar">
    <button class="btn primary" type="button" @click="openCreate">Создать конфигурацию</button>
  </div>

  <ClientTable
    :peers="sortedPeers"
    :filter="filter"
    :sort-key="sortKey"
    :sort-dir="sortDir"
    @filter="filter = $event"
    @sort="onSort"
    @toggle="onToggle"
    @config="onConfig"
    @delete="onDelete"
    @edit="onEdit"
  />

  <ConfigModal
    :show="!!modalPeer"
    :qr-url="modalPeer ? withBase('/peers/' + modalPeer.id + '/qr?t=' + Date.now()) : ''"
    :config-url="modalPeer ? withBase('/peers/' + modalPeer.id + '/config') : ''"
    :title="modalPeer ? modalPeer.name : 'Конфигурация'"
    :available="modalPeer ? !!modalPeer.has_private_key : true"
    @close="closeModal"
    @copy="copyUrl"
  />

  <CreateModal
    :show="createOpen"
    :loading="creating"
    @close="closeCreate"
    @submit="onCreate"
  />

  <DeleteModal
    :show="!!deletePeerTarget"
    :name="deletePeerTarget ? deletePeerTarget.name : ''"
    :busy="deleteBusy"
    @confirm="confirmDelete"
    @cancel="cancelDelete"
  />
</template>
