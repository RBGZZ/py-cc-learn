<script setup lang="ts">
import { computed } from 'vue'
import { useChatStore } from '../stores/chat'

const store = useChatStore()

const modelDisplay = computed(() => store.currentModel || 'Not connected')
const permissionDisplay = computed(() => {
  const map: Record<string, string> = {
    default: 'Default',
    acceptEdits: 'Accept Edits',
    bypassPermissions: 'Bypass',
    dontAsk: "Don't Ask",
    plan: 'Plan Mode',
  }
  return map[store.permissionMode] || store.permissionMode
})
const costDisplay = computed(() => `$${store.totalCostUsd.toFixed(4)}`)
const tokenDisplay = computed(
  () => `${(store.contextTokens / 1000).toFixed(1)}k / ${(store.contextLimit / 1000).toFixed(0)}k tokens`
)
const statusClass = computed(() => (store.isProcessing ? 'status-processing' : 'status-idle'))
</script>

<template>
  <div class="status-bar" :class="statusClass">
    <div class="status-item">
      <span class="status-label">Model</span>
      <span class="status-value">{{ modelDisplay }}</span>
    </div>
    <div class="status-item">
      <span class="status-label">Permissions</span>
      <span class="status-value">{{ permissionDisplay }}</span>
    </div>
    <div class="status-item">
      <span class="status-label">Cost</span>
      <span class="status-value">{{ costDisplay }}</span>
    </div>
    <div class="status-item">
      <span class="status-label">Context</span>
      <span class="status-value">{{ tokenDisplay }}</span>
    </div>
    <div class="status-item status-indicator">
      <span class="status-dot" :class="statusClass"></span>
      <span class="status-value">{{ store.isProcessing ? 'Processing' : 'Idle' }}</span>
    </div>
  </div>
</template>

<style scoped>
.status-bar {
  display: flex;
  gap: 16px;
  padding: 6px 16px;
  background-color: var(--bg-secondary);
  border-bottom: 1px solid var(--border);
  font-size: 11px;
  flex-shrink: 0;
  flex-wrap: wrap;
}

.status-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.status-label {
  color: var(--text-secondary);
  font-weight: 500;
}

.status-value {
  color: var(--text-primary);
  font-weight: 600;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}

.status-idle .status-dot {
  background-color: var(--success);
}

.status-processing .status-dot {
  background-color: var(--accent);
  animation: pulse-dot 1s ease-in-out infinite;
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}
</style>
