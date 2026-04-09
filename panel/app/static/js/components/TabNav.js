export const TabNav = {
  name: "TabNav",
  props: {
    active: { type: String, default: "dashboard" },
  },
  emits: ["change"],
  template: `
    <div class="tabs">
      <button
        class="tab-button"
        :class="{ active: active === 'dashboard' }"
        type="button"
        @click="$emit('change', 'dashboard')"
      >
        Дешборд
      </button>
      <button
        class="tab-button"
        :class="{ active: active === 'clients' }"
        type="button"
        @click="$emit('change', 'clients')"
      >
        Управление клиентами
      </button>
      <button
        class="tab-button"
        :class="{ active: active === 'awg' }"
        type="button"
        @click="$emit('change', 'awg')"
      >
        AmneziaWG 2.0
      </button>
    </div>
  `,
};
