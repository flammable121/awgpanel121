<script setup>
import { ref } from "vue";
import DashboardView from "./components/DashboardView.vue";
import ClientsView from "./components/ClientsView.vue";
import AwgInfoView from "./components/AwgInfoView.vue";
import ApiInfoView from "./components/ApiInfoView.vue";

const basePath = (window.__PANEL_BASE__ || "").replace(/\/+$/, "");
const logoutUrl = basePath ? `${basePath}/logout` : "/logout";

const tab = ref("dashboard");
const navOpen = ref(false);

document.body.dataset.theme = "dark";
document.body.classList.add("theme-dark");
localStorage.removeItem("theme");

const setTab = (value) => {
  tab.value = value;
  const url = new URL(window.location.href);
  url.searchParams.set("tab", value);
  history.replaceState(null, "", url);
};

const initialTab = new URLSearchParams(window.location.search).get("tab");
if (["dashboard", "clients", "awg", "api"].includes(initialTab)) {
  tab.value = initialTab;
}

const closeNav = () => {
  navOpen.value = false;
};
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="sidebar-head">
        <button class="mobile-toggle" type="button" @click="navOpen = !navOpen">☰</button>
        <div class="side-title">Меню</div>
      </div>
      <div class="sidebar-panel" :class="{ open: navOpen }">
        <nav class="sidebar-nav">
          <button
            class="side-link"
            :class="{ active: tab === 'dashboard' }"
            type="button"
            @click="setTab('dashboard'); closeNav()"
          >
            Дешборд
          </button>
          <button
            class="side-link"
            :class="{ active: tab === 'clients' }"
            type="button"
            @click="setTab('clients'); closeNav()"
          >
            Клиенты
          </button>
          <button
            class="side-link"
            :class="{ active: tab === 'awg' }"
            type="button"
            @click="setTab('awg'); closeNav()"
          >
            AmneziaWG 2.0
          </button>
          <button
            class="side-link"
            :class="{ active: tab === 'api' }"
            type="button"
            @click="setTab('api'); closeNav()"
          >
            API
          </button>
        </nav>
        <div class="sidebar-footer">
          <form method="post" :action="logoutUrl">
            <button class="side-link ghost" type="submit">Выход</button>
          </form>
        </div>
      </div>
    </aside>
    <div v-if="navOpen" class="sidebar-backdrop" @click="closeNav"></div>
    <main class="main">
      <div class="content">
        <DashboardView v-if="tab === 'dashboard'" />
        <ClientsView v-else-if="tab === 'clients'" />
        <AwgInfoView v-else-if="tab === 'awg'" />
        <ApiInfoView v-else />
      </div>
    </main>
  </div>
</template>
