<script>
export default {
  name: "ActionModal",
  props: {
    show: { type: Boolean, default: false },
    title: { type: String, default: "" },
    message: { type: String, default: "" },
    confirmText: { type: String, default: "ОК" },
    cancelText: { type: String, default: "Отмена" },
    loadingText: { type: String, default: "Выполняется..." },
    successText: { type: String, default: "Готово" },
    errorText: { type: String, default: "Ошибка" },
    state: { type: String, default: "confirm" },
  },
  emits: ["confirm", "close"],
};
</script>

<template>
  <div v-if="show" class="modal-backdrop">
    <div class="modal modal-form">
      <div class="modal-header">
        <div class="modal-title">{{ title }}</div>
      </div>
      <div class="modal-body">
        <div v-if="state === 'confirm'" class="modal-text">{{ message }}</div>
        <div v-else-if="state === 'loading'" class="modal-status">
          <div class="spinner"></div>
          <div>{{ loadingText }}</div>
        </div>
        <div v-else-if="state === 'success'" class="modal-status">
          <div class="status-icon success">✓</div>
          <div>{{ successText }}</div>
        </div>
        <div v-else-if="state === 'error'" class="modal-status">
          <div class="status-icon error">!</div>
          <div>{{ errorText }}</div>
        </div>
      </div>
      <div v-if="state === 'confirm'" class="modal-actions">
        <button class="btn primary" type="button" @click="$emit('confirm')">{{ confirmText }}</button>
        <button class="btn ghost" type="button" @click="$emit('close')">{{ cancelText }}</button>
      </div>
      <div v-else-if="state === 'success' || state === 'error'" class="modal-actions">
        <button class="btn primary" type="button" @click="$emit('close')">OK</button>
      </div>
    </div>
  </div>
</template>
