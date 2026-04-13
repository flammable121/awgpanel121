<script setup>
import { ref, onMounted } from "vue";
import {
  fetchAwgParams,
  updateAwgParams,
  fetchIChain,
  fetchAwgSettings,
  updateAwgSettings,
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

const settingsForm = ref({
  public_endpoint: "",
  default_client_allowed_ips: "0.0.0.0/0, ::/0",
  default_client_dns: "",
});
const settingsSaving = ref(false);
const settingsMessage = ref("");

const load = async () => {
  loading.value = true;
  message.value = "";
  try {
    const [paramsData, settingsData] = await Promise.all([
      fetchAwgParams(),
      fetchAwgSettings(),
    ]);
    params.value = { ...params.value, ...(paramsData.params || {}) };
    settingsForm.value = {
      public_endpoint: settingsData.public_endpoint || "",
      default_client_allowed_ips: settingsData.default_client_allowed_ips || "0.0.0.0/0, ::/0",
      default_client_dns: settingsData.default_client_dns || "",
    };
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
