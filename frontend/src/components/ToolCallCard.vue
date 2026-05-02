<script setup lang="ts">
import { ref, computed } from 'vue'
import LoadingSpinner from './LoadingSpinner.vue'

export interface ToolCallData {
  name: string
  input: any
  result?: any
  status: 'running' | 'completed' | 'error'
  error?: string
}

const props = defineProps<{
  toolCall: ToolCallData
}>()

const inputExpanded = ref(false)
const resultExpanded = ref(false)

function toggleInput(): void {
  inputExpanded.value = !inputExpanded.value
}

function toggleResult(): void {
  resultExpanded.value = !resultExpanded.value
}

function formatJson(data: any): string {
  try {
    if (typeof data === 'string') {
      // Try to parse if it's a JSON string
      const parsed = JSON.parse(data)
      return JSON.stringify(parsed, null, 2)
    }
    return JSON.stringify(data, null, 2)
  } catch {
    return String(data)
  }
}

const statusClass = computed(() => `tool-status-${props.toolCall.status}`)

const toolIcon = computed(() => {
  const name = props.toolCall.name.toLowerCase()
  if (name.includes('read') || name.includes('file')) return '&#x1F4C4;'
  if (name.includes('write') || name.includes('edit')) return '&#x270F;'
  if (name.includes('search') || name.includes('grep') || name.includes('find')) return '&#x1F50D;'
  if (name.includes('run') || name.includes('exec') || name.includes('terminal')) return '&#x1F4BB;'
  if (name.includes('ls') || name.includes('list') || name.includes('dir')) return '&#x1F4C1;'
  if (name.includes('delete') || name.includes('rm')) return '&#x1F5D1;'
  if (name.includes('http') || name.includes('fetch') || name.includes('api')) return '&#x1F310;'
  return '&#x1F527;'
})
</script>

<template>
  <div class="tool-call-card" :class="statusClass">
    <!-- Header -->
    <div class="tool-header">
      <span class="tool-icon" v-html="toolIcon"></span>
      <span class="tool-name">{{ toolCall.name }}</span>
      <span class="tool-status-badge" :class="statusClass">
        <template v-if="toolCall.status === 'running'">
          <LoadingSpinner size="sm" />
          Running
        </template>
        <template v-else-if="toolCall.status === 'completed'">
          &#x2713; Done
        </template>
        <template v-else-if="toolCall.status === 'error'">
          &#x2717; Error
        </template>
      </span>
    </div>

    <!-- Input section (expandable) -->
    <div class="tool-section">
      <button class="tool-toggle" @click="toggleInput">
        <span class="tool-toggle-arrow" :class="{ expanded: inputExpanded }">&#x25B6;</span>
        <span>Input Parameters</span>
      </button>
      <pre v-if="inputExpanded" class="tool-json">{{ formatJson(toolCall.input) }}</pre>
    </div>

    <!-- Result section -->
    <div v-if="toolCall.status === 'completed' && toolCall.result !== undefined" class="tool-section">
      <button class="tool-toggle" @click="toggleResult">
        <span class="tool-toggle-arrow" :class="{ expanded: resultExpanded }">&#x25B6;</span>
        <span>Result</span>
      </button>
      <pre v-if="resultExpanded" class="tool-json tool-result-json">{{ formatJson(toolCall.result) }}</pre>
    </div>

    <!-- Error section -->
    <div v-if="toolCall.status === 'error' && toolCall.error" class="tool-error">
      <span class="tool-error-icon">&#x26A0;</span>
      <span>{{ toolCall.error }}</span>
    </div>
  </div>
</template>

<style scoped>
.tool-call-card {
  margin: 8px 0;
  border-radius: 8px;
  border: 1px solid var(--border);
  background-color: var(--bg-primary);
  overflow: hidden;
  font-size: 13px;
}

.tool-status-running {
  border-left: 3px solid #2563eb;
}

.tool-status-completed {
  border-left: 3px solid var(--success);
}

.tool-status-error {
  border-left: 3px solid #ef4444;
}

/* ---- Header ---- */
.tool-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background-color: var(--bg-secondary);
  border-bottom: 1px solid var(--border);
}

.tool-name {
  font-weight: 600;
  color: var(--text-primary);
  font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
  font-size: 12px;
}

.tool-icon {
  font-size: 14px;
}

.tool-status-badge {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
}

.tool-status-running .tool-status-badge {
  background-color: rgba(37, 99, 235, 0.15);
  color: #60a5fa;
}

.tool-status-completed .tool-status-badge {
  background-color: rgba(76, 175, 80, 0.15);
  color: #4ade80;
}

.tool-status-error .tool-status-badge {
  background-color: rgba(239, 68, 68, 0.15);
  color: #f87171;
}

/* ---- Toggle buttons ---- */
.tool-section {
  border-bottom: 1px solid var(--border);
}

.tool-section:last-child {
  border-bottom: none;
}

.tool-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 6px 12px;
  background: none;
  border: none;
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
  text-align: left;
  font-family: inherit;
}

.tool-toggle:hover {
  background-color: rgba(255, 255, 255, 0.03);
}

.tool-toggle-arrow {
  font-size: 8px;
  transition: transform 0.2s;
  display: inline-block;
}

.tool-toggle-arrow.expanded {
  transform: rotate(90deg);
}

/* ---- JSON display ---- */
.tool-json {
  padding: 8px 12px 12px 24px;
  margin: 0;
  font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-primary);
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 300px;
  overflow-y: auto;
  background-color: rgba(0, 0, 0, 0.15);
}

.tool-result-json {
  color: var(--success);
}

/* ---- Error ---- */
.tool-error {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 12px;
  background-color: rgba(239, 68, 68, 0.08);
  color: #f87171;
  font-size: 12px;
}

.tool-error-icon {
  flex-shrink: 0;
}
</style>
