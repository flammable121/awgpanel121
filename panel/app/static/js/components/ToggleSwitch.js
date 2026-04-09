export const ToggleSwitch = {
  name: "ToggleSwitch",
  props: {
    checked: { type: Boolean, default: false },
    disabled: { type: Boolean, default: false },
    label: { type: String, default: "Включить" },
  },
  emits: ["toggle"],
  template: `
    <label class="toggle">
      <span v-if="label" class="toggle-text">{{ label }}</span>
      <input type="checkbox" :checked="checked" :disabled="disabled" @change="$emit('toggle', $event.target.checked)" />
      <span class="toggle-track"></span>
    </label>
  `,
};
