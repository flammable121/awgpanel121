<script>
import ToggleSwitch from "./ToggleSwitch.vue";

export default {
  name: "ClientTable",
  components: { ToggleSwitch },
  props: {
    peers: { type: Array, default: () => [] },
    filter: { type: String, default: "" },
    sortKey: { type: String, default: "name" },
    sortDir: { type: Number, default: 1 },
  },
  emits: ["filter", "sort", "toggle", "config", "delete", "edit"],
  data() {
    return {
      openMenuId: null,
    };
  },
  mounted() {
    document.addEventListener("click", this.onDocClick);
  },
  beforeUnmount() {
    document.removeEventListener("click", this.onDocClick);
  },
  methods: {
    toggleMenu(id) {
      this.openMenuId = this.openMenuId === id ? null : id;
    },
    closeMenu() {
      this.openMenuId = null;
    },
    onDocClick() {
      this.openMenuId = null;
    },
    onConfig(peer) {
      this.$emit("config", peer);
      this.closeMenu();
    },
    onDelete(peer) {
      this.$emit("delete", peer);
      this.closeMenu();
    },
    onEdit(peer) {
      this.$emit("edit", peer);
      this.closeMenu();
    },
  },
};
</script>

<template>
  <section class="card">
    <div class="table-head">
      <h2>Клиенты</h2>
      <div class="table-tools">
        <input
          type="search"
          :value="filter"
          placeholder="Поиск..."
          @input="$emit('filter', $event.target.value)"
        />
      </div>
    </div>
    <table class="table">
      <thead>
        <tr>
          <th class="col-menu">Меню</th>
          <th class="col-client">
            <button class="th-sort" type="button" @click="$emit('sort', 'name')">Клиент</button>
          </th>
          <th class="col-traffic hide-mobile">
            <button class="th-sort" type="button" @click="$emit('sort', 'traffic')">Трафик</button>
          </th>
          <th class="col-toggle center hide-mobile">Вкл</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="peer in peers" :key="peer.id">
          <td class="col-menu">
            <div class="menu-wrapper" @click.stop>
              <button class="menu-button" type="button" @click.stop="toggleMenu(peer.id)">⋯</button>
              <div v-if="openMenuId === peer.id" class="menu-popover" @click.stop>
                <div class="menu-list">
                  <button class="menu-item" type="button" @click.stop="onConfig(peer)">
                    <span class="menu-icon" aria-hidden="true">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
                        <rect x="3" y="3" width="6" height="6" rx="1" />
                        <rect x="15" y="3" width="6" height="6" rx="1" />
                        <rect x="3" y="15" width="6" height="6" rx="1" />
                        <rect x="13" y="13" width="8" height="8" rx="1" />
                        <path d="M7 9v6M9 7h6M15 9v6M9 15h4" />
                      </svg>
                    </span>
                    QR-код
                  </button>
                  <button class="menu-item" type="button" @click.stop="onEdit(peer)">
                    <span class="menu-icon" aria-hidden="true">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
                        <path d="M12 20h9" />
                        <path d="M16.5 3.5a2.1 2.1 0 1 1 3 3L7 19l-4 1 1-4 12.5-12.5z" />
                      </svg>
                    </span>
                    Редактировать
                  </button>
                  <button class="menu-item danger" type="button" @click.stop="onDelete(peer)">
                    <span class="menu-icon" aria-hidden="true">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
                        <path d="M3 6h18" />
                        <path d="M8 6v-2h8v2" />
                        <path d="M6 6l1 14h10l1-14" />
                        <path d="M10 11v6M14 11v6" />
                      </svg>
                    </span>
                    Удалить
                  </button>
                </div>
                <div class="menu-divider"></div>
                <div class="menu-meta">
                  <div><span>Статус:</span> {{ peer.status_label }}</div>
                  <div><span>Срок:</span> {{ peer.expires_display }}</div>
                  <div><span>IP:</span> {{ peer.allowed_ips }}</div>
                  <div v-if="peer.client_allowed_ips"><span>Маршруты:</span> {{ peer.client_allowed_ips }}</div>
                  <div v-if="peer.client_dns"><span>DNS:</span> {{ peer.client_dns }}</div>
                  <div v-if="peer.note"><span>Заметка:</span> {{ peer.note }}</div>
                </div>
                <div class="menu-divider only-mobile"></div>
                <div class="menu-meta only-mobile">
                  <div><span>Трафик:</span> {{ peer.traffic_display }}</div>
                  <div class="speed" :class="{ muted: !peer.online }">
                    {{ peer.online ? ("↓ " + peer.speed_rx + " · ↑ " + peer.speed_tx) : "—" }}
                  </div>
                </div>
                <div class="menu-toggle only-mobile">
                  <ToggleSwitch
                    :checked="peer.enabled"
                    :disabled="peer.busy"
                    label="Включить"
                    @toggle="$emit('toggle', peer)"
                  />
                </div>
              </div>
            </div>
          </td>
          <td class="col-client">
            <div class="client-cell">
              <div class="client-name">{{ peer.name }}</div>
              <span class="pill" :class="[peer.status, { online: peer.online }]">
                {{ peer.status_label }}
              </span>
            </div>
          </td>
          <td class="col-traffic traffic-cell hide-mobile">
            <div class="traffic-main">{{ peer.traffic_display }}</div>
            <div class="speed" :class="{ muted: !peer.online }">
              {{ peer.online ? ("↓ " + peer.speed_rx + " · ↑ " + peer.speed_tx) : "—" }}
            </div>
          </td>
          <td class="col-toggle center hide-mobile">
            <ToggleSwitch
              :checked="peer.enabled"
              :disabled="peer.busy"
              label=""
              @toggle="$emit('toggle', peer)"
            />
          </td>
        </tr>
        <tr v-if="!peers.length">
          <td colspan="4" class="empty">Клиентов нет</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>
