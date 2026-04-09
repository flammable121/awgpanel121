export const ConfigModal = {
  name: "ConfigModal",
  props: {
    show: { type: Boolean, default: false },
    qrUrl: { type: String, default: "" },
    configUrl: { type: String, default: "" },
    title: { type: String, default: "Конфигурация" },
    available: { type: Boolean, default: true },
  },
  emits: ["close", "copy"],
  template: `
    <div v-if="show" class="modal-backdrop" @click.self="$emit('close')">
      <div class="modal">
        <div class="modal-header">
          <h3>{{ title }}</h3>
        </div>
        <div class="modal-body">
          <template v-if="available">
            <img :src="qrUrl" alt="QR" />
            <div class="modal-hint">Сканируйте QR или скачайте файл.</div>
          </template>
          <template v-else>
            <div class="modal-hint">
              Конфигурация недоступна — приватный ключ отсутствует. Создайте новый конфиг в панели.
            </div>
          </template>
        </div>
        <div class="modal-actions">
          <a
            v-if="available"
            class="btn primary"
            :href="configUrl"
            :download="(title || 'config') + '.conf'"
          >
            Скачать файл
          </a>
          <button
            class="btn ghost"
            type="button"
            :disabled="!available"
            @click="$emit('copy')"
          >
            Копировать URL
          </button>
          <button class="btn ghost" type="button" @click="$emit('close')">Отмена</button>
        </div>
      </div>
    </div>
  `,
};
