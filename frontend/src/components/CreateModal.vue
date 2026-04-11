<script>
import ToggleSwitch from "./ToggleSwitch.vue";

export default {
  name: "CreateModal",
  components: { ToggleSwitch },
  props: {
    show: { type: Boolean, default: false },
    loading: { type: Boolean, default: false },
  },
  emits: ["close", "submit"],
  data() {
    return {
      name: "",
      neverExpires: true,
      expiresDate: "",
      expiresTime: "",
    };
  },
  methods: {
    submit() {
      this.$emit("submit", {
        name: this.name,
        never_expires: this.neverExpires ? "1" : "",
        expires_date: this.neverExpires ? "" : this.expiresDate,
        expires_time: this.neverExpires ? "" : this.expiresTime,
        tz_offset: String(new Date().getTimezoneOffset()),
      });
      this.name = "";
      this.neverExpires = true;
      this.expiresDate = "";
      this.expiresTime = "";
    },
  },
};
</script>

<template>
  <div v-if="show" class="modal-backdrop" @click.self="$emit('close')">
    <div class="modal modal-form">
      <div class="modal-header">
        <h3>Создать конфигурацию</h3>
      </div>
      <div class="form">
        <label>
          <span>Имя</span>
          <input type="text" v-model="name" placeholder="например, iPhone" />
        </label>
        <div class="form-row form-row-inline">
          <label>
            <span>Дата</span>
            <input type="date" v-model="expiresDate" :disabled="neverExpires" />
          </label>
          <label>
            <span>Время</span>
            <input type="time" v-model="expiresTime" :disabled="neverExpires" />
          </label>
          <div class="toggle-inline">
            <span>Бессрочно</span>
            <ToggleSwitch :checked="neverExpires" label="" @toggle="neverExpires = $event" />
          </div>
        </div>
      </div>
      <div class="modal-actions">
        <button class="btn primary" type="button" :disabled="loading" @click="submit">
          {{ loading ? 'Создание...' : 'Создать' }}
        </button>
        <button class="btn ghost" type="button" @click="$emit('close')">Отмена</button>
      </div>
    </div>
  </div>
</template>
