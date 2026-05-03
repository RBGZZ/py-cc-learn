<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{
  count: number
  files: string[]
}>()

const expanded = ref(false)

function toggle(): void {
  expanded.value = !expanded.value
}
</script>

<template>
  <div class="collapsed-search-card">
    <!-- Header -->
    <button class="search-toggle" @click="toggle">
      <span class="search-toggle-arrow" :class="{ expanded }">&#x25B6;</span>
      <span class="search-icon">&#x1F50D;</span>
      <span class="search-title">Searched {{ count }} files</span>
    </button>

    <!-- Expandable file list -->
    <div v-if="expanded" class="search-body">
      <div v-for="(file, idx) in files" :key="idx" class="search-item">
        <span class="search-item-icon">&#x1F4C4;</span>
        <span class="search-item-name">{{ file }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.collapsed-search-card {
  margin: 8px 0;
  border-radius: 8px;
  border: 1px solid var(--border);
  background-color: var(--bg-primary);
  overflow: hidden;
  font-size: 13px;
  border-left: 3px solid #f59e0b;
}

/* ---- Toggle header ---- */
.search-toggle {
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

.search-toggle:hover {
  background-color: rgba(245, 158, 11, 0.05);
}

.search-toggle-arrow {
  font-size: 8px;
  transition: transform 0.2s;
  display: inline-block;
  color: var(--text-secondary);
}

.search-toggle-arrow.expanded {
  transform: rotate(90deg);
}

.search-icon {
  font-size: 14px;
}

.search-title {
  font-weight: 600;
}

/* ---- Body ---- */
.search-body {
  padding: 4px 0;
}

.search-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 12px 5px 28px;
  font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
  font-size: 12px;
  border-bottom: 1px solid var(--border);
}

.search-item:last-child {
  border-bottom: none;
}

.search-item-icon {
  font-size: 12px;
  flex-shrink: 0;
}

.search-item-name {
  color: var(--text-primary);
  word-break: break-all;
}
</style>
