export const DeleteModal = {
  name: "DeleteModal",
  props: {
    show: { type: Boolean, default: false },
    name: { type: String, default: "" },
    busy: { type: Boolean, default: false },
  },
  emits: ["confirm", "cancel"],
  template: `
    <div v-if="show" class="modal-backdrop" @click.self="$emit('cancel')">
      <div class="modal">
        <div class="modal-header">
          <h3>Удалить конфигурацию?</h3>
        </div>
        <div class="modal-body">
          <div class="modal-text">
            Клиент: <strong>{{ name || 'Без имени' }}</strong>
          </div>
          <div class="modal-hint">Действие необратимо. Конфигурация будет удалена навсегда.</div>
        </div>
        <div class="modal-actions">
          <button class="btn danger" type="button" :disabled="busy" @click="$emit('confirm')">
            {{ busy ? 'Удаление...' : 'Удалить' }}
          </button>
          <button class="btn ghost" type="button" @click="$emit('cancel')">Отмена</button>
        </div>
      </div>
    </div>
  `,
};
