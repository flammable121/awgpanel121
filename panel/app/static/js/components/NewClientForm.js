export const NewClientForm = {
  name: "NewClientForm",
  props: {
    loading: { type: Boolean, default: false },
  },
  emits: ["submit"],
  data() {
    return {
      name: "",
      neverExpires: true,
      expiresDate: "",
      expiresTime: "",
      maxDevices: 1,
    };
  },
  methods: {
    onSubmit() {
      this.$emit("submit", {
        name: this.name,
        never_expires: this.neverExpires ? "1" : "",
        expires_date: this.neverExpires ? "" : this.expiresDate,
        expires_time: this.neverExpires ? "" : this.expiresTime,
        max_devices: this.maxDevices,
      });
      this.name = "";
      this.neverExpires = true;
      this.expiresDate = "";
      this.expiresTime = "";
    },
  },
  template: `
    <section class="card">
      <h2>Новый клиент</h2>
      <div class="form">
        <label>
          <span>Имя</span>
          <input type="text" v-model="name" placeholder="например, iPhone" />
        </label>
        <div class="form-row">
          <label>
            <span>Дата</span>
            <input type="date" v-model="expiresDate" :disabled="neverExpires" />
          </label>
          <label>
            <span>Время</span>
            <input type="time" v-model="expiresTime" :disabled="neverExpires" />
          </label>
        </div>
        <label class="check">
          <input type="checkbox" v-model="neverExpires" />
          <span>Бессрочно</span>
        </label>
        <label>
          <span>Устройства (0 = ∞)</span>
          <input type="number" min="0" max="50" v-model.number="maxDevices" />
        </label>
        <button class="btn primary" type="button" :disabled="loading" @click="onSubmit">
          {{ loading ? 'Создание...' : 'Создать' }}
        </button>
      </div>
    </section>
  `,
};
