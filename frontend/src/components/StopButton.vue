<script setup lang="ts">
withDefaults(defineProps<{
  isProcessing?: boolean
}>(), {
  isProcessing: false,
})

const emit = defineEmits<{
  (e: 'stop'): void
}>()

function handleClick(): void {
  emit('stop')
}
</script>

<template>
  <button
    v-show="isProcessing"
    class="stop-button"
    :class="{ 'stop-pulse': isProcessing }"
    title="Stop generation"
    @click="handleClick"
  >
    <span class="stop-icon">
      <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor">
        <rect x="1" y="1" width="12" height="12" rx="1.5" />
      </svg>
    </span>
    <span class="stop-label">Stop</span>
  </button>
</template>

<style scoped>
.stop-button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  background-color: #ef4444;
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background-color 0.15s, transform 0.15s;
  font-family: inherit;
}

.stop-button:hover {
  background-color: #dc2626;
  transform: scale(1.04);
}

.stop-button:active {
  transform: scale(0.97);
}

.stop-pulse {
  animation: stop-pulse-anim 1.5s ease-in-out infinite;
}

.stop-icon {
  display: flex;
  align-items: center;
}

.stop-label {
  white-space: nowrap;
}

@keyframes stop-pulse-anim {
  0%, 100% {
    box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.6);
  }
  50% {
    box-shadow: 0 0 0 8px rgba(239, 68, 68, 0);
  }
}
</style>
