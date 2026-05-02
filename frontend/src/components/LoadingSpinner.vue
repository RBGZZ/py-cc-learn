<script setup lang="ts">
withDefaults(defineProps<{
  size?: 'sm' | 'md' | 'lg'
  text?: string
}>(), {
  size: 'md',
})
</script>

<template>
  <div class="loading-spinner" :class="`spinner-${size}`">
    <span class="spinner-circle"></span>
    <span v-if="text" class="spinner-text">{{ text }}</span>
  </div>
</template>

<style scoped>
.loading-spinner {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}

.spinner-circle {
  display: inline-block;
  border-radius: 50%;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  animation: spinner-rotate 0.7s linear infinite;
}

.spinner-sm .spinner-circle {
  width: 14px;
  height: 14px;
  border-width: 2px;
}

.spinner-md .spinner-circle {
  width: 24px;
  height: 24px;
  border-width: 3px;
}

.spinner-lg .spinner-circle {
  width: 40px;
  height: 40px;
  border-width: 4px;
}

.spinner-text {
  font-size: 12px;
  color: var(--text-secondary);
  text-align: center;
}

@keyframes spinner-rotate {
  to {
    transform: rotate(360deg);
  }
}
</style>
