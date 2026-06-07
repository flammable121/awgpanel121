<script setup>
import { ref, computed, onMounted } from "vue";
import {
  fetchAwgParams,
  updateAwgParams,
  fetchIChain,
  fetchAwgSettings,
  updateAwgSettings,
  fetchAwgRouting,
  updateAwgRouting,
  updateAwgRoutingGeoip,
  updateAwgRoutingGeosite,
  applyAwgRouting,
  clearAwgRouting,
} from "../api.js";

const params = ref({
  Jc: "",
  Jmin: "",
  Jmax: "",
  S1: "",
  S2: "",
  S3: "",
  S4: "",
  H1: "",
  H2: "",
  H3: "",
  H4: "",
});
const iChain = ref(null);
const loading = ref(false);
const saving = ref(false);
const message = ref("");
const showAwg = ref(true);
const showRanges = ref(false);
const showDefaults = ref(false);
const showRouting = ref(false);

const settingsForm = ref({
  public_endpoint: "",
  default_client_allowed_ips: "0.0.0.0/0, ::/0",
  default_client_dns: "",
});
const settingsSaving = ref(false);
const settingsMessage = ref("");
const routingForm = ref({
  enabled: false,
  geoip_url: "",
  geoip_tags_text: "",
  dns_block_enabled: false,
  dns_redirect_enabled: true,
  dns_upstreams_text: "",
  geosite_url: "",
  geosite_tags_text: "",
  manual_domains_text: "",
});
const routingGeoip = ref({
  exists: false,
  tags: [],
  mtime: null,
  size: 0,
});
const routingGeosite = ref({
  exists: false,
  tags: [],
  mtime: null,
  size: 0,
});
const routingSaving = ref(false);
const routingUpdating = ref(false);
const routingGeositeUpdating = ref(false);
const routingApplying = ref(false);
const routingMessage = ref("");
const geoipTagsInput = ref(null);
const geositeTagsInput = ref(null);
const manualDomainInput = ref(null);
const textAutocomplete = ref({
  field: "",
  open: false,
  query: "",
  start: 0,
  end: 0,
});
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

const formatDate = (value) => {
  if (!value) return "—";
  return new Date(Number(value) * 1000).toLocaleString();
};

const normalizeTagsText = (value) =>
  String(value || "")
    .replace(/\n/g, ",")
    .split(",")
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean)
    .join(", ");

const splitDomainText = (value) =>
  String(value || "")
    .replace(/\n/g, ",")
    .split(",")
    .map((item) => item.trim().toLowerCase().replace(/^\*\./, "").replace(/\.$/, ""))
    .filter(Boolean);

const splitTextItems = (value) =>
  String(value || "")
    .replace(/\n/g, ",")
    .split(",")
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean);

const autocompleteSources = {
  geoip_tags_text: {
    minLength: 1,
    source: () => routingGeoip.value.tags,
    existing: () => splitTextItems(routingForm.value.geoip_tags_text),
    valid: () => true,
  },
  geosite_tags_text: {
    minLength: 1,
    source: () => routingGeosite.value.tags,
    existing: () => splitTextItems(routingForm.value.geosite_tags_text),
    valid: () => true,
  },
  manual_domains_text: {
    minLength: 2,
    source: () => commonBlockedDomains,
    existing: () => splitDomainText(routingForm.value.manual_domains_text),
    valid: (item) => item.includes("."),
  },
};

const inputRefs = {
  geoip_tags_text: geoipTagsInput,
  geosite_tags_text: geositeTagsInput,
  manual_domains_text: manualDomainInput,
};

const autocompleteSuggestions = computed(() => {
  const field = textAutocomplete.value.field;
  const config = autocompleteSources[field];
  const query = textAutocomplete.value.query;
  if (!config || !query || query.length < config.minLength) return [];
  const existing = new Set(config.existing());
  const pool = new Set(config.source());
  return Array.from(pool)
    .map((item) => String(item || "").trim().toLowerCase())
    .filter((item) => item && config.valid(item) && item.includes(query) && !existing.has(item))
    .sort((a, b) => {
      const aStarts = a.startsWith(query) ? 0 : 1;
      const bStarts = b.startsWith(query) ? 0 : 1;
      if (aStarts !== bStarts) return aStarts - bStarts;
      return a.localeCompare(b);
    })
    .slice(0, 8);
});

const updateTextAutocomplete = (event, field) => {
  const input = event.target;
  const value = input.value;
  const pos = input.selectionStart ?? value.length;
  const left = value.slice(0, pos);
  const tokenStart = Math.max(left.lastIndexOf("\n"), left.lastIndexOf(",")) + 1;
  const right = value.slice(pos);
  const nextBreaks = [right.indexOf("\n"), right.indexOf(",")].filter((item) => item >= 0);
  const tokenEnd = nextBreaks.length ? pos + Math.min(...nextBreaks) : value.length;
  const query = value.slice(tokenStart, pos).trim().toLowerCase().replace(/^\*\./, "");
  const minLength = autocompleteSources[field]?.minLength || 2;
  textAutocomplete.value = {
    field,
    open: query.length >= minLength,
    query,
    start: tokenStart,
    end: tokenEnd,
  };
};

const closeTextAutocompleteSoon = () => {
  setTimeout(() => {
    textAutocomplete.value.open = false;
  }, 120);
};

const handleTextAutocompleteKeydown = (event) => {
  if (event.key === "Escape") {
    textAutocomplete.value.open = false;
    return;
  }
  if ((event.key === "Enter" || event.key === "Tab") && textAutocomplete.value.open && autocompleteSuggestions.value.length) {
    event.preventDefault();
    applyTextSuggestion(autocompleteSuggestions.value[0]);
  }
};

const applyTextSuggestion = (suggestion) => {
  const field = textAutocomplete.value.field;
  if (!field || !(field in routingForm.value)) return;
  const value = routingForm.value[field] || "";
  const before = value.slice(0, textAutocomplete.value.start);
  const after = value.slice(textAutocomplete.value.end);
  const separator = after.startsWith("\n") || after.startsWith(",") || !after ? "" : "\n";
  routingForm.value[field] = `${before}${suggestion}${separator}${after}`;
  textAutocomplete.value.open = false;
  requestAnimationFrame(() => {
    inputRefs[field]?.value?.focus();
  });
};

const applyRoutingPayload = (data) => {
  const config = data?.config || {};
  routingForm.value = {
    enabled: !!config.enabled,
    geoip_url: config.geoip_url || "",
    geoip_tags_text: (config.geoip_tags || []).join(", "),
    dns_block_enabled: !!config.dns_block_enabled,
    dns_redirect_enabled: config.dns_redirect_enabled !== false,
    dns_upstreams_text: (config.dns_upstreams || []).join(", "),
    geosite_url: config.geosite_url || "",
    geosite_tags_text: (config.geosite_tags || []).join(", "),
    manual_domains_text: (config.manual_domains || []).join("\n"),
  };
  routingGeoip.value = {
    exists: !!data?.geoip?.exists,
    tags: data?.geoip?.tags || [],
    mtime: data?.geoip?.mtime || null,
    size: data?.geoip?.size || 0,
  };
  routingGeosite.value = {
    exists: !!data?.geosite?.exists,
    tags: data?.geosite?.tags || [],
    mtime: data?.geosite?.mtime || null,
    size: data?.geosite?.size || 0,
  };
  if (config.last_error) {
    routingMessage.value = config.last_error;
  }
};

const load = async () => {
  loading.value = true;
  message.value = "";
  try {
    const [paramsData, settingsData, routingData] = await Promise.all([
      fetchAwgParams(),
      fetchAwgSettings(),
      fetchAwgRouting(),
    ]);
    params.value = { ...params.value, ...(paramsData.params || {}) };
    settingsForm.value = {
      public_endpoint: settingsData.public_endpoint || "",
      default_client_allowed_ips: settingsData.default_client_allowed_ips || "0.0.0.0/0, ::/0",
      default_client_dns: settingsData.default_client_dns || "",
    };
    applyRoutingPayload(routingData);
  } catch (err) {
    message.value = "Не удалось загрузить настройки AmneziaWG";
  } finally {
    loading.value = false;
  }
};

const save = async () => {
  saving.value = true;
  message.value = "";
  try {
    const data = await updateAwgParams(params.value);
    params.value = { ...params.value, ...(data.params || {}) };
    message.value = "Параметры сохранены";
  } catch (err) {
    message.value = "Не удалось сохранить параметры";
  } finally {
    saving.value = false;
  }
};

const saveDefaults = async () => {
  settingsSaving.value = true;
  settingsMessage.value = "";
  try {
    const data = await updateAwgSettings(settingsForm.value);
    settingsForm.value = {
      public_endpoint: data.public_endpoint || "",
      default_client_allowed_ips: data.default_client_allowed_ips || "0.0.0.0/0, ::/0",
      default_client_dns: data.default_client_dns || "",
    };
    settingsMessage.value = "Настройки клиентских конфигов сохранены";
  } catch (err) {
    settingsMessage.value = err && err.message ? err.message : "Не удалось сохранить настройки";
  } finally {
    settingsSaving.value = false;
  }
};

const genChain = async () => {
  try {
    iChain.value = await fetchIChain();
  } catch (err) {
    message.value = "Не удалось сгенерировать I1–I5";
  }
};

const saveRouting = async () => {
  routingSaving.value = true;
  routingMessage.value = "";
  try {
    const data = await updateAwgRouting({
      enabled: routingForm.value.enabled,
      geoip_url: routingForm.value.geoip_url,
      geoip_tags: normalizeTagsText(routingForm.value.geoip_tags_text).split(", ").filter(Boolean),
      dns_block_enabled: routingForm.value.dns_block_enabled,
      dns_redirect_enabled: routingForm.value.dns_redirect_enabled,
      dns_upstreams: normalizeTagsText(routingForm.value.dns_upstreams_text).split(", ").filter(Boolean),
      geosite_url: routingForm.value.geosite_url,
      geosite_tags: normalizeTagsText(routingForm.value.geosite_tags_text).split(", ").filter(Boolean),
      manual_domains: String(routingForm.value.manual_domains_text || "")
        .replace(/\n/g, ",")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
    });
    applyRoutingPayload(data);
    routingMessage.value = "Настройки маршрутизации сохранены";
    return true;
  } catch (err) {
    routingMessage.value = err && err.message ? err.message : "Не удалось сохранить маршрутизацию";
    throw err;
  } finally {
    routingSaving.value = false;
  }
};

const updateGeosite = async () => {
  routingGeositeUpdating.value = true;
  routingMessage.value = "";
  try {
    const data = await updateAwgRoutingGeosite({ geosite_url: routingForm.value.geosite_url });
    applyRoutingPayload(data);
    routingMessage.value = "GEOSITE база обновлена";
  } catch (err) {
    routingMessage.value = err && err.message ? err.message : "Не удалось обновить GEOSITE";
  } finally {
    routingGeositeUpdating.value = false;
  }
};

const updateGeoip = async () => {
  routingUpdating.value = true;
  routingMessage.value = "";
  try {
    const data = await updateAwgRoutingGeoip({ geoip_url: routingForm.value.geoip_url });
    applyRoutingPayload(data);
    routingMessage.value = "GEOIP база обновлена";
  } catch (err) {
    routingMessage.value = err && err.message ? err.message : "Не удалось обновить GEOIP";
  } finally {
    routingUpdating.value = false;
  }
};

const applyRouting = async () => {
  routingApplying.value = true;
  routingMessage.value = "";
  try {
    await saveRouting();
    const data = routingForm.value.enabled ? await applyAwgRouting() : await clearAwgRouting();
    applyRoutingPayload(data);
    const rules = data.rules || {};
    routingMessage.value = routingForm.value.enabled
      ? `Блокировка применена: IPv4 ${rules.ipv4 || 0}, IPv6 ${rules.ipv6 || 0}, доменов ${rules.domains || 0}`
      : routingForm.value.dns_block_enabled
        ? `DNS-блокировка применена: доменов ${rules.domains || 0}`
        : "Блокировка отключена";
  } catch (err) {
    routingMessage.value = err && err.message ? err.message : "Не удалось применить маршрутизацию";
  } finally {
    routingApplying.value = false;
  }
};

onMounted(() => {
  load();
});
</script>

<template>
  <section class="card">
    <h2>AmneziaWG 2.0</h2>

    <div class="collapse">
      <button class="collapse-header" :class="{ open: showAwg }" @click="showAwg = !showAwg">
        <span>Настройки AmneziaWG</span>
        <span class="collapse-chevron">v</span>
      </button>
      <div class="collapse-body" :class="{ open: showAwg }">
        <div class="collapse-inner">
          <p class="muted">
            Параметры обфускации AmneziaWG. Обычно менять не требуется — используйте только при
            проблемах с подключением или блокировками.
          </p>

          <div class="awg-grid">
            <div class="awg-group">
              <div class="awg-title">J (Jc/Jmin/Jmax)</div>
              <div class="awg-row">
                <label><span>Jc</span><input type="text" v-model="params.Jc" /></label>
                <label><span>Jmin</span><input type="text" v-model="params.Jmin" /></label>
                <label><span>Jmax</span><input type="text" v-model="params.Jmax" /></label>
              </div>
            </div>
            <div class="awg-group">
              <div class="awg-title">S (S1–S4)</div>
              <div class="awg-row">
                <label><span>S1</span><input type="text" v-model="params.S1" /></label>
                <label><span>S2</span><input type="text" v-model="params.S2" /></label>
                <label><span>S3</span><input type="text" v-model="params.S3" /></label>
                <label><span>S4</span><input type="text" v-model="params.S4" /></label>
              </div>
            </div>
            <div class="awg-group">
              <div class="awg-title">H (H1–H4)</div>
              <div class="awg-row">
                <label><span>H1</span><input type="text" v-model="params.H1" /></label>
                <label><span>H2</span><input type="text" v-model="params.H2" /></label>
                <label><span>H3</span><input type="text" v-model="params.H3" /></label>
                <label><span>H4</span><input type="text" v-model="params.H4" /></label>
              </div>
            </div>
          </div>

          <div class="awg-actions">
            <button class="btn primary" type="button" :disabled="saving" @click="save">
              {{ saving ? "Сохранение..." : "Сохранить" }}
            </button>
            <div v-if="message" class="muted">{{ message }}</div>
          </div>

          <div class="sub-collapse">
            <button class="collapse-header small" :class="{ open: showDefaults }" @click="showDefaults = !showDefaults">
              <span>Настройки клиентских конфигов</span>
              <span class="collapse-chevron">v</span>
            </button>
            <div class="collapse-body" :class="{ open: showDefaults }">
              <div class="collapse-inner">
                <div class="form">
                  <label>
                    <span>Public endpoint (host:port)</span>
                    <input type="text" v-model="settingsForm.public_endpoint" placeholder="example.com:51820" />
                  </label>
                  <label>
                    <span>AllowedIPs по умолчанию</span>
                    <input type="text" v-model="settingsForm.default_client_allowed_ips" placeholder="0.0.0.0/0, ::/0" />
                  </label>
                  <label>
                    <span>DNS по умолчанию</span>
                    <input type="text" v-model="settingsForm.default_client_dns" placeholder="1.1.1.1, 8.8.8.8" />
                  </label>
                </div>
                <div class="awg-actions">
                  <button class="btn primary" type="button" :disabled="settingsSaving" @click="saveDefaults">
                    {{ settingsSaving ? "Сохранение..." : "Сохранить настройки" }}
                  </button>
                  <div v-if="settingsMessage" class="muted">{{ settingsMessage }}</div>
                </div>
              </div>
            </div>
          </div>

          <div class="sub-collapse">
            <button class="collapse-header small" :class="{ open: showRouting }" @click="showRouting = !showRouting">
              <span>Маршрутизация</span>
              <span class="collapse-chevron">v</span>
            </button>
            <div class="collapse-body" :class="{ open: showRouting }">
              <div class="collapse-inner">
                <div class="form">
                  <label class="check-row">
                    <input type="checkbox" v-model="routingForm.enabled" />
                    <span>Включить GEOIP Block</span>
                  </label>
                  <label class="check-row">
                    <input type="checkbox" v-model="routingForm.dns_block_enabled" />
                    <span>Включить DNS/GEOSITE Block</span>
                  </label>
                  <label class="check-row">
                    <input type="checkbox" v-model="routingForm.dns_redirect_enabled" />
                    <span>Перехватывать DNS клиентов AWG</span>
                  </label>
                  <label>
                    <span>Upstream DNS для DNS Block</span>
                    <input
                      type="text"
                      v-model="routingForm.dns_upstreams_text"
                      placeholder="1.1.1.1, 8.8.8.8"
                    />
                  </label>
                  <label>
                    <span>GEOIP URL</span>
                    <input
                      type="text"
                      v-model="routingForm.geoip_url"
                      placeholder="https://github.com/v2fly/geoip/releases/latest/download/geoip.dat"
                    />
                  </label>
                  <label>
                    <span>Блокируемые GEOIP теги</span>
                    <div class="autocomplete-wrap">
                      <textarea
                        ref="geoipTagsInput"
                        v-model="routingForm.geoip_tags_text"
                        rows="3"
                        placeholder="ru, cn, private"
                        @input="updateTextAutocomplete($event, 'geoip_tags_text')"
                        @click="updateTextAutocomplete($event, 'geoip_tags_text')"
                        @keyup="updateTextAutocomplete($event, 'geoip_tags_text')"
                        @keydown="handleTextAutocompleteKeydown"
                        @blur="closeTextAutocompleteSoon"
                      ></textarea>
                      <div v-if="textAutocomplete.open && textAutocomplete.field === 'geoip_tags_text' && autocompleteSuggestions.length" class="autocomplete-list">
                        <button
                          v-for="tag in autocompleteSuggestions"
                          :key="tag"
                          class="autocomplete-item"
                          type="button"
                          @mousedown.prevent="applyTextSuggestion(tag)"
                        >
                          {{ tag }}
                        </button>
                      </div>
                    </div>
                  </label>
                  <label>
                    <span>GEOSITE URL</span>
                    <input
                      type="text"
                      v-model="routingForm.geosite_url"
                      placeholder="https://github.com/v2fly/domain-list-community/releases/latest/download/dlc.dat"
                    />
                  </label>
                  <label>
                    <span>Блокируемые GEOSITE теги</span>
                    <div class="autocomplete-wrap">
                      <textarea
                        ref="geositeTagsInput"
                        v-model="routingForm.geosite_tags_text"
                        rows="3"
                        placeholder="ru, category-ads-all"
                        @input="updateTextAutocomplete($event, 'geosite_tags_text')"
                        @click="updateTextAutocomplete($event, 'geosite_tags_text')"
                        @keyup="updateTextAutocomplete($event, 'geosite_tags_text')"
                        @keydown="handleTextAutocompleteKeydown"
                        @blur="closeTextAutocompleteSoon"
                      ></textarea>
                      <div v-if="textAutocomplete.open && textAutocomplete.field === 'geosite_tags_text' && autocompleteSuggestions.length" class="autocomplete-list">
                        <button
                          v-for="tag in autocompleteSuggestions"
                          :key="tag"
                          class="autocomplete-item"
                          type="button"
                          @mousedown.prevent="applyTextSuggestion(tag)"
                        >
                          {{ tag }}
                        </button>
                      </div>
                    </div>
                  </label>
                  <label>
                    <span>Домены вручную</span>
                    <div class="autocomplete-wrap">
                      <textarea
                        ref="manualDomainInput"
                        v-model="routingForm.manual_domains_text"
                        rows="5"
                        placeholder="wildberries.ru&#10;wb.ru&#10;sberbank.ru&#10;gosuslugi.ru"
                        @input="updateTextAutocomplete($event, 'manual_domains_text')"
                        @click="updateTextAutocomplete($event, 'manual_domains_text')"
                        @keyup="updateTextAutocomplete($event, 'manual_domains_text')"
                        @keydown="handleTextAutocompleteKeydown"
                        @blur="closeTextAutocompleteSoon"
                      ></textarea>
                      <div v-if="textAutocomplete.open && textAutocomplete.field === 'manual_domains_text' && autocompleteSuggestions.length" class="autocomplete-list">
                        <button
                          v-for="domain in autocompleteSuggestions"
                          :key="domain"
                          class="autocomplete-item"
                          type="button"
                          @mousedown.prevent="applyTextSuggestion(domain)"
                        >
                          {{ domain }}
                        </button>
                      </div>
                    </div>
                  </label>
                </div>
                <div class="route-meta">
                  <div><span>GEOIP:</span> {{ routingGeoip.exists ? "загружен" : "не загружен" }}</div>
                  <div><span>Обновлен:</span> {{ formatDate(routingGeoip.mtime) }}</div>
                  <div><span>Тегов:</span> {{ routingGeoip.tags.length }}</div>
                  <div><span>GEOSITE:</span> {{ routingGeosite.exists ? "загружен" : "не загружен" }}</div>
                  <div><span>Обновлен:</span> {{ formatDate(routingGeosite.mtime) }}</div>
                  <div><span>Тегов:</span> {{ routingGeosite.tags.length }}</div>
                </div>
                <div v-if="routingGeoip.tags.length" class="tag-list">
                  <button
                    v-for="tag in routingGeoip.tags.slice(0, 80)"
                    :key="tag"
                    class="tag-button"
                    type="button"
                    @click="routingForm.geoip_tags_text = normalizeTagsText(`${routingForm.geoip_tags_text}, ${tag}`)"
                  >
                    {{ tag }}
                  </button>
                </div>
                <div v-if="routingGeosite.tags.length" class="tag-list">
                  <button
                    v-for="tag in routingGeosite.tags.slice(0, 120)"
                    :key="tag"
                    class="tag-button"
                    type="button"
                    @click="routingForm.geosite_tags_text = normalizeTagsText(`${routingForm.geosite_tags_text}, ${tag}`)"
                  >
                    {{ tag }}
                  </button>
                </div>
                <div class="awg-actions">
                  <button class="btn ghost" type="button" :disabled="routingUpdating" @click="updateGeoip">
                    {{ routingUpdating ? "Обновление..." : "Обновить GEOIP" }}
                  </button>
                  <button class="btn ghost" type="button" :disabled="routingGeositeUpdating" @click="updateGeosite">
                    {{ routingGeositeUpdating ? "Обновление..." : "Обновить GEOSITE" }}
                  </button>
                  <button class="btn ghost" type="button" :disabled="routingSaving" @click="saveRouting">
                    {{ routingSaving ? "Сохранение..." : "Сохранить" }}
                  </button>
                  <button class="btn primary" type="button" :disabled="routingApplying" @click="applyRouting">
                    {{ routingApplying ? "Применение..." : "Применить" }}
                  </button>
                  <div v-if="routingMessage" class="muted">{{ routingMessage }}</div>
                </div>
              </div>
            </div>
          </div>

          <div class="sub-collapse">
            <button class="collapse-header small" :class="{ open: showRanges }" @click="showRanges = !showRanges">
              <span>Диапазоны параметров</span>
              <span class="collapse-chevron">v</span>
            </button>
            <div class="collapse-body" :class="{ open: showRanges }">
              <div class="collapse-inner">
                <div class="range-grid">
                  <div class="range-item">
                    <div class="range-name">Jc</div>
                    <div class="range-value">1–255</div>
                    <div class="range-note">целое число</div>
                  </div>
                  <div class="range-item">
                    <div class="range-name">Jmin / Jmax</div>
                    <div class="range-value">1–255</div>
                    <div class="range-note">Jmin ≤ Jmax</div>
                  </div>
                  <div class="range-item">
                    <div class="range-name">S1–S4</div>
                    <div class="range-value">1–255</div>
                    <div class="range-note">целые числа</div>
                  </div>
                  <div class="range-item">
                    <div class="range-name">H1–H4</div>
                    <div class="range-value">0–4294967295</div>
                    <div class="range-note">диапазон min-max</div>
                  </div>
                </div>
                <p class="muted">
                  Рекомендуется менять параметры осторожно и сохранять базовые значения.
                </p>
              </div>
            </div>
          </div>

          <div class="awg-divider"></div>

          <div class="awg-group">
            <div class="awg-title">I (I1–I5)</div>
            <p class="muted">I1–I5 генерируются автоматически для каждого клиента. Ниже пример цепочки.</p>
            <div class="awg-row awg-row-compact">
              <button class="btn ghost" type="button" @click="genChain">Сгенерировать пример</button>
            </div>
            <div v-if="iChain" class="awg-chain">
              <div><span>I1</span><code>{{ iChain.i1 }}</code></div>
              <div><span>I2</span><code>{{ iChain.i2 }}</code></div>
              <div><span>I3</span><code>{{ iChain.i3 }}</code></div>
              <div><span>I4</span><code>{{ iChain.i4 }}</code></div>
              <div><span>I5</span><code>{{ iChain.i5 }}</code></div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
