<script setup lang="ts">
import { computed } from 'vue'
import type { PermissionRequest } from '../stores/permission'

const props = defineProps<{
  request: PermissionRequest
}>()

const emit = defineEmits<{
  (e: 'respond', behavior: 'allow' | 'deny' | 'always_allow'): void
}>()

const command = computed(() => {
  return props.request.toolInput?.command ?? 'Unknown command'
})

const assistantSummary = computed(() => {
  const msg = props.request.assistantMessage
  if (!msg) return ''
  // Show first line or truncate to ~80 chars
  const firstLine = msg.split('\n')[0]
  return firstLine.length > 100 ? firstLine.slice(0, 100) + '...' : firstLine
})

function allow(): void {
  emit('respond', 'allow')
}

function deny(): void {
  emit('respond', 'deny')
}

function alwaysAllow(): void {
  emit('respond', 'always_allow')
}
</script>

<template>
  <div class="permission-dialog bash-dialog">
    <div class="perm-header">
      <span class="perm-icon">&#x1F4BB;</span>
      <span class="perm-title">Bash Permission</span>
    </div>

    <div class="perm-body">
      <p v-if="assistantSummary" class="perm-context">
        The assistant wants to run a command{{ assistantSummary ? `: ${assistantSummary}` : '' }}
      </p>

      <div class="perm-command-box">
        <code class="perm-command">{{ command }}</code>
      </div>
    </div>

    <div class="perm-actions">
      <button class="perm-btn perm-btn-deny" @click="deny">
        &#x2717; Deny
      </button>
      <button class="perm-btn perm-btn-allow" @click="allow">
        &#x2713; Allow
      </button>
      <button class="perm-btn perm-btn-always" @click="alwaysAllow">
        &#x2605; Always Allow
      </button>
    </div>
  </div>
</template>

<style scoped>
.permission-dialog {
  margin: 8px 0;
  border-radius: 8px;
  border: 1px solid var(--warning);
  background-color: var(--bg-secondary);
  overflow: hidden;
  font-size: 13px;
}

/* ---- Header ---- */
.perm-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background-color: rgba(255, 152, 0, 0.1);
  border-bottom: 1px solid var(--border);
}

.perm-icon {
  font-size: 14px;
}

.perm-title {
  font-weight: 600;
  color: var(--warning);
}

/* ---- Body ---- */
.perm-body {
  padding: 12px;
}

.perm-context {
  margin: 0 0 8px;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.perm-command-box {
  padding: 8px 12px;
  background-color: rgba(0, 0, 0, 0.2);
  border-radius: 6px;
  border: 1px solid var(--border);
}

.perm-command {
  font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
  font-size: 12px;
  color: var(--warning);
  white-space: pre-wrap;
  word-break: break-all;
}

/* ---- Actions ---- */
.perm-actions {
  display: flex;
  gap: 8px;
  padding: 8px 12px 12px;
  justify-content: flex-end;
}

.perm-btn {
  padding: 6px 14px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  border: 1px solid transparent;
  transition: background-color 0.15s, transform 0.1s;
  font-family: inherit;
}

.perm-btn:active {
  transform: scale(0.97);
}

.perm-btn-allow {
  background-color: var(--success);
  color: #fff;
}

.perm-btn-allow:hover {
  background-color: #43a047;
}

.perm-btn-deny {
  background-color: transparent;
  color: var(--text-secondary);
  border-color: var(--border);
}

.perm-btn-deny:hover {
  background-color: rgba(239, 68, 68, 0.15);
  color: #f87171;
  border-color: #ef4444;
}

.perm-btn-always {
  background-color: var(--warning);
  color: #fff;
}

.perm-btn-always:hover {
  background-color: #f57c00;
}
</style>
