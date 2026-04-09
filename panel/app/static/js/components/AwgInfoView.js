import { ref, onMounted } from "https://unpkg.com/vue@3/dist/vue.esm-browser.js";
import { fetchAwgParams, updateAwgParams, fetchIChain } from "../api.js";

export const AwgInfoView = {
  name: "AwgInfoView",
  setup() {
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

    const load = async () => {
      loading.value = true;
      message.value = "";
      try {
        const data = await fetchAwgParams();
        params.value = { ...params.value, ...(data.params || {}) };
      } catch (err) {
        message.value = "Не удалось загрузить параметры";
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

    return {
      params,
      iChain,
      loading,
      saving,
      message,
      save,
      genChain,
      showAwg,
    };
  },
  template: `
    <section class="card">
      <h2>AmneziaWG 2.0</h2>

      <div class="collapse">
        <button class="collapse-header" :class="{ open: showAwg }" @click="showAwg = !showAwg">
          <span>Настройки AmneziaWG</span>
          <span class="collapse-chevron">⌄</span>
        </button>
        <div class="collapse-body" :class="{ open: showAwg }">
          <div class="collapse-inner">
            <p class="muted">
              Параметры обфускации AmneziaWG. Обычно менять не требуется — используйте только при проблемах
              с подключением или блокировками.
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
                {{ saving ? 'Сохранение...' : 'Сохранить' }}
              </button>
              <div v-if="message" class="muted">{{ message }}</div>
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
  `,
};
