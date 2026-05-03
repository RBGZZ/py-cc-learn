<script setup lang="ts">
import { computed, ref } from 'vue'
import type { PermissionRequest } from '../stores/permission'

const props = defineProps<{
  request: PermissionRequest
}>()

const emit = defineEmits<{
  (e: 'respond', behavior: 'allow' | 'deny'): void
}>()

const showFullDiff = ref(false)

const filePath = computed(() => {
  return props.request.toolInput?.filePath ?? props.request.toolInput?.path ?? 'Unknown file'
})

const oldStr = computed(() => {
  return props.request.toolInput?.old_str ?? ''
})

const newStr = computed(() => {
  return props.request.toolInput?.new_str ?? ''
})

const assistantSummary = computed(() => {
  const msg = props.request.assistantMessage
  if (!msg) return ''
  const firstLine = msg.split('\n')[0]
  return firstLine.length > 100 ? firstLine.slice(0, 100) + '...' : firstLine
})

function toggleDiff(): void {
  showFullDiff.value = !showFullDiff.value
}

function allow(): void {
  emit('respond', 'allow')
}

function deny(): void {
  emit('respond', 'deny')
}
</script>

<template>
  <div class="permission-dialog edit-dialog">
    <div class="perm-header">
      <span class="perm-icon">&#x270F;</span>
      <span class="perm-title">File Edit Permission</span>
    </div>

    <div class="perm-body">
      <p v-if="assistantSummary" class="perm-context">
        The assistant wants to edit a file{{ assistantSummary ? `: ${assistantSummary}` : '' }}
      </p>

      <div class="edit-file-path">
        <span class="edit-label">File:</span>
        <code class="edit-path">{{ filePath }}</code>
      </div>

      <div class="edit-diff-section">
        <button class="diff-toggle" @click="toggleDiff">
          <span class="diff-toggle-arrow" :class="{ expanded: showFullDiff }">&#x25B6;</span>
          <span>View changes</span>
        </button>

        <template v-if="showFullDiff">
          <div class="diff-block">
            <div class="diff-label diff-remove-label">&#x2212; Removed:</div>
            <pre class="diff-pre diff-remove">{{ oldStr || '(nothing)' }}</pre>
          </div>
          <div class="diff-block">
            <div class="diff-label diff-add-label">&#x002B; Added:</div>
            <pre class="diff-pre diff-add">{{ newStr || '(nothing)' }}</pre>
          </div>
        </template>
      </div>
    </div>

    <div class="perm-actions">
      <button class="perm-btn perm-btn-deny" @click="deny">
        &#x2717; Deny
      </button>
      <button class="perm-btn perm-btn-allow" @click="allow">
        &#x2713; Allow
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

.edit-file-path {
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin-bottom: 8px;
}

.edit-label {
  font-size: 12px;
  color: var(--text-secondary);
  flex-shrink: 0;
}

.edit-path {
  font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
  font-size: 12px;
  color: var(--accent);
  word-break: break-all;
}

/* ---- Diff toggle ---- */
.edit-diff-section {
  border-top: 1px solid var(--border);
  padding-top: 8px;
}

.diff-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 4px 0;
  background: none;
  border: none;
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
  text-align: left;
  font-family: inherit;
}

.diff-toggle:hover {
  color: var(--text-primary);
}

.diff-toggle-arrow {
  font-size: 8px;
  transition: transform 0.2s;
  display: inline-block;
}

.diff-toggle-arrow.expanded {
  transform: rotate(90deg);
}

/* ---- Diff blocks ---- */
.diff-block {
  margin-top: 8px;
}

.diff-label {
  font-size: 11px;
  font-weight: 600;
  margin-bottom: 4px;
  padding: 0 4px;
}

.diff-remove-label {
  color: #f87171;
}

.diff-add-label {
  color: #4ade80;
}

.diff-pre {
  margin: 0;
  padding: 8px 12px;
  font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
  font-size: 11px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-all;
  border-radius: 4px;
  max-height: 200px;
  overflow-y: auto;
}

.diff-remove {
  background-color: rgba(239, 68, 68, 0.08);
  color: #f87171;
}

.diff-add {
  background-color: rgba(76, 175, 80, 0.08);
  color: #4ade80;
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
</style>
