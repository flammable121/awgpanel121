<script setup>
import { computed, onMounted, ref } from "vue";
import ToggleSwitch from "./ToggleSwitch.vue";
import {
  fetchAwgRouting,
  updateAwgRouting,
  updateAwgRoutingGeoip,
  updateAwgRoutingGeosite,
  applyAwgRouting,
  clearAwgRouting,
} from "../api.js";

const commonBlockedDomains = [
  "wildberries.ru",
  "wb.ru",
  "sberbank.ru",
  "sber.ru",
  "tbank.ru",
  "tinkoff.ru",
  "alfabank.ru",
  "vtb.ru",
  "gazprombank.ru",
  "raiffeisen.ru",
  "ozon.ru",
  "ozonbank.ru",
  "avito.ru",
  "gosuslugi.ru",
  "nalog.gov.ru",
  "mos.ru",
  "domclick.ru",
  "yoomoney.ru",
  "qiwi.com",
  "rzd.ru",
];

const bypassSuggestions = [
  "gemini.google.com",
  "generativelanguage.googleapis.com",
  "googleapis.com",
  "googleusercontent.com",
  "spotify.com",
  "open.spotify.com",
  "spclient.wg.spotify.com",
  "scdn.co",
  "spotifycdn.com",
  "audio-ak-spotify-com.akamaized.net",
];

const form = ref({
  enabled: false,
  dns_block_enabled: false,
  dns_redirect_enabled: true,
  dns_upstreams: [],
  geoip_url: "",
  geoip_tags: [],
  geosite_url: "",
  geosite_tags: [],
  manual_domains: [],
  bypass_domains: [],
  bypass_geosite_tags: [],
});
const geoip = ref({ exists: false, tags: [], mtime: null });
const geosite = ref({ exists: false, tags: [], mtime: null });
const loading = ref(false);
const saving = ref(false);
const updatingGeoip = ref(false);
const updatingGeosite = ref(false);
const applying = ref(false);
const message = ref("");
const activeInput = ref({ field: "", query: "", index: 0 });

const normalize = (value) => String(value || "").trim().toLowerCase().replace(/^\*\./, "").replace(/\.$/, "");
const uniqueList = (items, domains = false) =>
  Array.from(new Set((items || []).map(normalize).filter((item) => item && (!domains || item.includes(".")))));

const formatDate = (value) => {
  if (!value) return "—";
  return new Date(Number(value) * 1000).toLocaleString();
};

const fields = {
  geoip_tags: {
    suggestions: () => geoip.value.tags,
    domains: false,
    min: 1,
  },
  geosite_tags: {
    suggestions: () => geosite.value.tags,
    domains: false,
    min: 1,
  },
  manual_domains: {
    suggestions: () => commonBlockedDomains,
    domains: true,
    min: 2,
  },
  bypass_domains: {
    suggestions: () => bypassSuggestions,
    domains: true,
    min: 2,
  },
  bypass_geosite_tags: {
    suggestions: () => geosite.value.tags,
    domains: false,
    min: 1,
  },
  dns_upstreams: {
    suggestions: () => ["111.88.96.50", "111.88.96.51", "1.1.1.1", "8.8.8.8", "9.9.9.9"],
    domains: false,
    min: 1,
  },
};

const suggestions = computed(() => {
  const field = activeInput.value.field;
  const query = activeInput.value.query;
  const config = fields[field];
  if (!config || query.length < config.min) return [];
  const existing = new Set(form.value[field]);
  return Array.from(new Set(config.suggestions().map(normalize)))
    .filter((item) => item && item.includes(query) && !existing.has(item))
    .sort((a, b) => {
      const aStarts = a.startsWith(query) ? 0 : 1;
      const bStarts = b.startsWith(query) ? 0 : 1;
      if (aStarts !== bStarts) return aStarts - bStarts;
      return a.localeCompare(b);
    })
    .slice(0, 10);
});

const bypassDomainPool = computed(() =>
  Array.from(new Set([...bypassSuggestions, ...commonBlockedDomains, ...geosite.value.tags, ...form.value.manual_domains]))
);

fields.bypass_domains.suggestions = () => bypassDomainPool.value;

const applyPayload = (data) => {
  const config = data?.config || {};
  form.value = {
    enabled: !!config.enabled,
    dns_block_enabled: !!config.dns_block_enabled,
    dns_redirect_enabled: config.dns_redirect_enabled !== false,
    dns_upstreams: uniqueList(config.dns_upstreams || []),
    geoip_url: config.geoip_url || "",
    geoip_tags: uniqueList(config.geoip_tags || []),
    geosite_url: config.geosite_url || "",
    geosite_tags: uniqueList(config.geosite_tags || []),
    manual_domains: uniqueList(config.manual_domains || [], true),
    bypass_domains: uniqueList(config.bypass_domains || [], true),
    bypass_geosite_tags: uniqueList(config.bypass_geosite_tags || []),
  };
  geoip.value = {
    exists: !!data?.geoip?.exists,
    tags: data?.geoip?.tags || [],
    mtime: data?.geoip?.mtime || null,
  };
  geosite.value = {
    exists: !!data?.geosite?.exists,
    tags: data?.geosite?.tags || [],
    mtime: data?.geosite?.mtime || null,
  };
  if (config.last_error) message.value = config.last_error;
};

const load = async () => {
  loading.value = true;
  message.value = "";
  try {
    applyPayload(await fetchAwgRouting());
  } catch (err) {
    message.value = err?.message || "Не удалось загрузить маршрутизацию";
  } finally {
    loading.value = false;
  }
};

const save = async () => {
  saving.value = true;
  message.value = "";
  try {
    const data = await updateAwgRouting({ ...form.value });
    applyPayload(data);
    message.value = "Настройки маршрутизации сохранены";
  } catch (err) {
    message.value = err?.message || "Не удалось сохранить маршрутизацию";
    throw err;
  } finally {
    saving.value = false;
  }
};

const updateGeoip = async () => {
  updatingGeoip.value = true;
  message.value = "";
  try {
    applyPayload(await updateAwgRoutingGeoip({ geoip_url: form.value.geoip_url }));
    message.value = "GEOIP база обновлена";
  } catch (err) {
    message.value = err?.message || "Не удалось обновить GEOIP";
  } finally {
    updatingGeoip.value = false;
  }
};

const updateGeosite = async () => {
  updatingGeosite.value = true;
  message.value = "";
  try {
    applyPayload(await updateAwgRoutingGeosite({ geosite_url: form.value.geosite_url }));
    message.value = "GEOSITE база обновлена";
  } catch (err) {
    message.value = err?.message || "Не удалось обновить GEOSITE";
  } finally {
    updatingGeosite.value = false;
  }
};

const applyRouting = async () => {
  applying.value = true;
  message.value = "";
  try {
    await save();
    const data = form.value.enabled || form.value.dns_block_enabled ? await applyAwgRouting() : await clearAwgRouting();
    applyPayload(data);
    const rules = data.rules || {};
    message.value = `Применено: IPv4 ${rules.ipv4 || 0}, IPv6 ${rules.ipv6 || 0}, доменов ${rules.domains || 0}`;
  } catch (err) {
    message.value = err?.message || "Не удалось применить маршрутизацию";
  } finally {
    applying.value = false;
  }
};

const addItem = (field, value) => {
  const config = fields[field];
  const item = normalize(value);
  if (field === "bypass_domains" && item && !item.includes(".")) {
    form.value.bypass_geosite_tags = uniqueList([...form.value.bypass_geosite_tags, item]);
    activeInput.value = { field: "", query: "", index: 0 };
    return;
  }
  if (!item || (config?.domains && !item.includes("."))) return;
  form.value[field] = uniqueList([...form.value[field], item], !!config?.domains);
  activeInput.value = { field: "", query: "", index: 0 };
};

const removeItem = (field, item) => {
  form.value[field] = form.value[field].filter((value) => value !== item);
};

const onChipInput = (field, event) => {
  activeInput.value = { field, query: normalize(event.target.value), index: 0 };
};

const commitInput = (field, event) => {
  addItem(field, event.target.value);
  event.target.value = "";
};

const pickSuggestion = (field, item, event) => {
  addItem(field, item);
  const input = event.currentTarget.closest(".chip-input")?.querySelector("input");
  if (input) input.value = "";
};

const onKeydown = (field, event) => {
  if (event.key === "ArrowDown" && suggestions.value.length) {
    event.preventDefault();
    activeInput.value.index = Math.min(activeInput.value.index + 1, suggestions.value.length - 1);
  } else if (event.key === "ArrowUp" && suggestions.value.length) {
    event.preventDefault();
    activeInput.value.index = Math.max(activeInput.value.index - 1, 0);
  } else if (event.key === "Enter" || event.key === "Tab" || event.key === ",") {
    event.preventDefault();
    const suggestion = suggestions.value[activeInput.value.index];
    addItem(field, suggestion || event.target.value);
    event.target.value = "";
  } else if (event.key === "Escape") {
    activeInput.value = { field: "", query: "", index: 0 };
  }
};

onMounted(load);
</script>

<template>
  <section class="card routing-card">
    <div class="table-head">
      <h2>Маршрутизация</h2>
    </div>

    <div class="route-switches">
      <div class="route-switch-row">
        <span>Включить GEOIP Block</span>
        <ToggleSwitch :checked="form.enabled" label="" @toggle="form.enabled = $event" />
      </div>
      <div class="route-switch-row">
        <span>Включить DNS/GEOSITE Block</span>
        <ToggleSwitch :checked="form.dns_block_enabled" label="" @toggle="form.dns_block_enabled = $event" />
      </div>
      <div class="route-switch-row">
        <span>Перехватывать DNS клиентов AWG</span>
        <ToggleSwitch :checked="form.dns_redirect_enabled" label="" @toggle="form.dns_redirect_enabled = $event" />
      </div>
    </div>

    <div class="route-url-grid">
      <label>
        <span>GEOIP URL</span>
        <input type="text" v-model="form.geoip_url" />
      </label>
      <label>
        <span>GEOSITE URL</span>
        <input type="text" v-model="form.geosite_url" />
      </label>
    </div>

    <div class="form">
      <label>
        <span>Upstream DNS для DNS Block</span>
        <div class="chip-input">
          <span v-for="item in form.dns_upstreams" :key="item" class="chip">
            {{ item }} <button type="button" @click="removeItem('dns_upstreams', item)">×</button>
          </span>
          <input type="text" :placeholder="form.dns_upstreams.length ? '' : '111.88.96.50'" @input="onChipInput('dns_upstreams', $event)" @keydown="onKeydown('dns_upstreams', $event)" @blur="commitInput('dns_upstreams', $event)" />
          <div v-if="activeInput.field === 'dns_upstreams' && suggestions.length" class="autocomplete-list chip-suggestions">
            <button v-for="(item, index) in suggestions" :key="item" class="autocomplete-item" :class="{ active: index === activeInput.index }" type="button" @mousedown.prevent="pickSuggestion('dns_upstreams', item, $event)">{{ item }}</button>
          </div>
        </div>
      </label>

      <label>
        <span>Блокируемые GEOIP теги</span>
        <div class="chip-input">
          <span v-for="item in form.geoip_tags" :key="item" class="chip">
            {{ item }} <button type="button" @click="removeItem('geoip_tags', item)">×</button>
          </span>
          <input type="text" :placeholder="form.geoip_tags.length ? '' : 'ru'" @input="onChipInput('geoip_tags', $event)" @keydown="onKeydown('geoip_tags', $event)" @blur="commitInput('geoip_tags', $event)" />
          <div v-if="activeInput.field === 'geoip_tags' && suggestions.length" class="autocomplete-list chip-suggestions">
            <button v-for="(item, index) in suggestions" :key="item" class="autocomplete-item" :class="{ active: index === activeInput.index }" type="button" @mousedown.prevent="pickSuggestion('geoip_tags', item, $event)">{{ item }}</button>
          </div>
        </div>
      </label>

      <label>
        <span>Блокируемые GEOSITE теги</span>
        <div class="chip-input">
          <span v-for="item in form.geosite_tags" :key="item" class="chip">
            {{ item }} <button type="button" @click="removeItem('geosite_tags', item)">×</button>
          </span>
          <input type="text" :placeholder="form.geosite_tags.length ? '' : 'category-ads-all'" @input="onChipInput('geosite_tags', $event)" @keydown="onKeydown('geosite_tags', $event)" @blur="commitInput('geosite_tags', $event)" />
          <div v-if="activeInput.field === 'geosite_tags' && suggestions.length" class="autocomplete-list chip-suggestions">
            <button v-for="(item, index) in suggestions" :key="item" class="autocomplete-item" :class="{ active: index === activeInput.index }" type="button" @mousedown.prevent="pickSuggestion('geosite_tags', item, $event)">{{ item }}</button>
          </div>
        </div>
      </label>

      <label>
        <span>Домены вручную</span>
        <div class="chip-input">
          <span v-for="item in form.manual_domains" :key="item" class="chip">
            {{ item }} <button type="button" @click="removeItem('manual_domains', item)">×</button>
          </span>
          <input type="text" :placeholder="form.manual_domains.length ? '' : 'wildberries.ru'" @input="onChipInput('manual_domains', $event)" @keydown="onKeydown('manual_domains', $event)" @blur="commitInput('manual_domains', $event)" />
          <div v-if="activeInput.field === 'manual_domains' && suggestions.length" class="autocomplete-list chip-suggestions">
            <button v-for="(item, index) in suggestions" :key="item" class="autocomplete-item" :class="{ active: index === activeInput.index }" type="button" @mousedown.prevent="pickSuggestion('manual_domains', item, $event)">{{ item }}</button>
          </div>
        </div>
      </label>

      <label>
        <span>Исключения DNS Block</span>
        <div class="chip-input">
          <span v-for="item in form.bypass_domains" :key="item" class="chip">
            {{ item }} <button type="button" @click="removeItem('bypass_domains', item)">×</button>
          </span>
          <input type="text" :placeholder="form.bypass_domains.length ? '' : 'gemini.google.com'" @input="onChipInput('bypass_domains', $event)" @keydown="onKeydown('bypass_domains', $event)" @blur="commitInput('bypass_domains', $event)" />
          <div v-if="activeInput.field === 'bypass_domains' && suggestions.length" class="autocomplete-list chip-suggestions">
            <button v-for="(item, index) in suggestions" :key="item" class="autocomplete-item" :class="{ active: index === activeInput.index }" type="button" @mousedown.prevent="pickSuggestion('bypass_domains', item, $event)">{{ item }}</button>
          </div>
        </div>
      </label>

      <label>
        <span>Исключения GEOSITE теги</span>
        <div class="chip-input">
          <span v-for="item in form.bypass_geosite_tags" :key="item" class="chip">
            {{ item }} <button type="button" @click="removeItem('bypass_geosite_tags', item)">×</button>
          </span>
          <input type="text" :placeholder="form.bypass_geosite_tags.length ? '' : 'google-gemini'" @input="onChipInput('bypass_geosite_tags', $event)" @keydown="onKeydown('bypass_geosite_tags', $event)" @blur="commitInput('bypass_geosite_tags', $event)" />
          <div v-if="activeInput.field === 'bypass_geosite_tags' && suggestions.length" class="autocomplete-list chip-suggestions">
            <button v-for="(item, index) in suggestions" :key="item" class="autocomplete-item" :class="{ active: index === activeInput.index }" type="button" @mousedown.prevent="pickSuggestion('bypass_geosite_tags', item, $event)">{{ item }}</button>
          </div>
        </div>
      </label>
    </div>

    <div class="route-resource-grid">
      <div class="route-resource">
        <div class="route-resource-title">GEOIP</div>
        <div><span>Статус:</span> {{ geoip.exists ? "загружен" : "не загружен" }}</div>
        <div><span>Обновлен:</span> {{ formatDate(geoip.mtime) }}</div>
        <div><span>Тегов:</span> {{ geoip.tags.length }}</div>
      </div>
      <div class="route-resource">
        <div class="route-resource-title">GEOSITE</div>
        <div><span>Статус:</span> {{ geosite.exists ? "загружен" : "не загружен" }}</div>
        <div><span>Обновлен:</span> {{ formatDate(geosite.mtime) }}</div>
        <div><span>Тегов:</span> {{ geosite.tags.length }}</div>
      </div>
    </div>

    <div class="awg-actions">
      <button class="btn ghost" type="button" :disabled="updatingGeoip" @click="updateGeoip">{{ updatingGeoip ? "Обновление..." : "Обновить GEOIP" }}</button>
      <button class="btn ghost" type="button" :disabled="updatingGeosite" @click="updateGeosite">{{ updatingGeosite ? "Обновление..." : "Обновить GEOSITE" }}</button>
      <button class="btn ghost" type="button" :disabled="saving" @click="save">{{ saving ? "Сохранение..." : "Сохранить" }}</button>
      <button class="btn primary" type="button" :disabled="applying || loading" @click="applyRouting">{{ applying ? "Применение..." : "Применить" }}</button>
      <div v-if="message" class="muted">{{ message }}</div>
    </div>
  </section>
</template>
