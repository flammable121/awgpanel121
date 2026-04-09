import { ref, computed, onMounted } from "https://unpkg.com/vue@3/dist/vue.esm-browser.js";
import { fetchApiInfo, resetApiToken } from "../api.js";
import { ActionModal } from "./ActionModal.js";

export const ApiInfoView = {
  name: "ApiInfoView",
  components: { ActionModal },
  setup() {
    const token = ref("");
    const showToken = ref(false);
    const message = ref("");
    const baseUrl = ref("");
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

    const maskedToken = computed(() => {
      if (!token.value) return "";
      if (showToken.value) return token.value;
      return token.value.replace(/.(?=.{4})/g, "•");
    });

    const load = async () => {
      try {
        const data = await fetchApiInfo();
        token.value = data.api_token || "";
        baseUrl.value = data.base_url || window.location.origin;
      } catch (err) {
        message.value = "Не удалось загрузить API информацию";
      }
    };

    const copyToken = async () => {
      if (!token.value) return;
      try {
        await navigator.clipboard.writeText(token.value);
        message.value = "API ключ скопирован";
      } catch (err) {
        message.value = "Не удалось скопировать API ключ";
      }
    };

    const openReset = () => {
      modal.value = {
        ...modal.value,
        show: true,
        title: "Перегенерировать API ключ?",
        message: "Старый ключ перестанет работать. Обновите интеграции после сброса.",
        confirmText: "Сбросить",
        loadingText: "Генерация ключа...",
        successText: "API ключ успешно обновлен",
        errorText: "Не удалось перегенерировать ключ",
        action: resetApiToken,
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
        const data = await modal.value.action();
        if (data && data.api_token) {
          token.value = data.api_token;
        }
        modalState.value = "success";
      } catch (err) {
        modalState.value = "error";
      }
    };

    onMounted(load);

    return {
      token,
      showToken,
      maskedToken,
      message,
      baseUrl,
      copyToken,
      openReset,
      modal,
      modalState,
      closeModal,
      runAction,
    };
  },
  template: `
    <section class="card api-card">
      <h2>API</h2>
      <p class="muted">
        API защищён токеном. Передавайте его в заголовке Authorization: Bearer или X-API-Key.
      </p>

      <div class="form">
        <label>
          <span>API ключ</span>
          <div class="api-row">
            <input type="text" :value="maskedToken" readonly />
            <button class="btn ghost" type="button" @click="showToken = !showToken">
              {{ showToken ? 'Скрыть' : 'Показать' }}
            </button>
            <button class="btn ghost" type="button" @click="copyToken">Скопировать</button>
            <button class="btn danger" type="button" @click="openReset">Сбросить/перегенерировать API-ключ</button>
          </div>
        </label>
        <div v-if="message" class="muted">{{ message }}</div>
      </div>

      <div class="awg-divider"></div>

      <div class="api-doc">
        <div class="api-doc-title">Базовый URL</div>
        <div class="api-doc-text">{{ baseUrl }}</div>

        <div class="api-doc-title">Авторизация</div>
        <pre class="api-pre">Authorization: Bearer &lt;API_TOKEN&gt;
или
X-API-Key: &lt;API_TOKEN&gt;</pre>

        <div class="api-doc-title">Эндпоинты</div>
        <pre class="api-pre">GET    /api/v1/peers
GET    /api/v1/peers/&lt;id&gt;
POST   /api/v1/peers
PATCH  /api/v1/peers/&lt;id&gt;
POST   /api/v1/peers/&lt;id&gt;/toggle
DELETE /api/v1/peers/&lt;id&gt;
GET    /api/v1/peers/&lt;id&gt;/config
GET    /api/v1/peers/&lt;id&gt;/qr</pre>

        <div class="api-doc-title">Пример: список конфигов</div>
        <pre class="api-pre">curl -H "Authorization: Bearer &lt;API_TOKEN&gt;" \\
  {{ baseUrl }}/api/v1/peers</pre>
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
  `,
};
