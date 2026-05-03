<script setup lang="ts">
import { ref } from 'vue'

export interface ToolItem {
  name: string
  input: any
  status: string
}

const props = defineProps<{
  tools: ToolItem[]
}>()

const expanded = ref(false)

function toggle(): void {
  expanded.value = !expanded.value
}

function statusEmoji(status: string): string {
  switch (status) {
    case 'running':
      return '\u23F3'
    case 'completed':
      return '\u2705'
    case 'error':
      return '\u274C'
    default:
      return '\u2753'
  }
}
</script>

<template>
  <div class="grouped-card">
    <!-- Header -->
    <button class="group-toggle" @click="toggle">
      <span class="group-toggle-arrow" :class="{ expanded }">&#x25B6;</span>
      <span class="group-icon">&#x1F527;</span>
      <span class="group-title">{{ tools.length }} tools in group</span>
    </button>

    <!-- Expandable tool list -->
    <div v-if="expanded" class="group-body">
      <div v-for="(tool, idx) in tools" :key="idx" class="group-item">
        <span class="group-item-status">{{ statusEmoji(tool.status) }}</span>
        <span class="group-item-name">{{ tool.name }}</span>
        <span class="group-item-status-text">{{ tool.status }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.grouped-card {
  margin: 8px 0;
  border-radius: 8px;
  border: 1px solid var(--border);
  background-color: var(--bg-primary);
  overflow: hidden;
  font-size: 13px;
  border-left: 3px solid #8b5cf6;
}

/* ---- Toggle header ---- */
.group-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 12px;
  background-color: var(--bg-secondary);
  border: none;
  border-bottom: 1px solid var(--border);
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
  text-align: left;
  font-family: inherit;
}

.group-toggle:hover {
  background-color: rgba(139, 92, 246, 0.05);
}

.group-toggle-arrow {
  font-size: 8px;
  transition: transform 0.2s;
  display: inline-block;
  color: var(--text-secondary);
}

.group-toggle-arrow.expanded {
  transform: rotate(90deg);
}

.group-icon {
  font-size: 14px;
}

.group-title {
  font-weight: 600;
}

/* ---- Body ---- */
.group-body {
  padding: 4px 0;
}

.group-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px 6px 28px;
  font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
  font-size: 12px;
  border-bottom: 1px solid var(--border);
}

.group-item:last-child {
  border-bottom: none;
}

.group-item-status {
  font-size: 12px;
  flex-shrink: 0;
}

.group-item-name {
  color: var(--text-primary);
  flex: 1;
}

.group-item-status-text {
  color: var(--text-secondary);
  font-size: 11px;
  text-transform: capitalize;
}
</style>
