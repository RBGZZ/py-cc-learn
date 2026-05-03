<script setup lang="ts">
import { useConfigStore } from '../stores/config'

const config = useConfigStore()
</script>

<template>
  <aside class="sidebar" :class="{ collapsed: !config.sidebarOpen }">
    <div class="sidebar-header">
      <span class="sidebar-title" v-if="config.sidebarOpen">⚙️ Settings</span>
      <button class="toggle-btn" @click="config.toggleSidebar" :title="config.sidebarOpen ? 'Collapse' : 'Expand'">
        {{ config.sidebarOpen ? '◀' : '▶' }}
      </button>
    </div>

    <div class="sidebar-body" v-if="config.sidebarOpen">
      <!-- Provider Selection -->
      <div class="config-section">
        <label class="config-label">Provider</label>
        <select
          class="config-select"
          :value="config.activeProvider"
          @change="config.setProvider(($event.target as HTMLSelectElement).value)"
        >
          <option
            v-for="p in config.providers"
            :key="p.name"
            :value="p.name"
          >
            {{ p.name.charAt(0).toUpperCase() + p.name.slice(1) }}
          </option>
        </select>
      </div>

      <!-- Model Selection -->
      <div class="config-section">
        <label class="config-label">Model</label>
        <select
          class="config-select"
          :value="config.activeModel"
          @change="config.setModel(($event.target as HTMLSelectElement).value)"
        >
          <option
            v-for="m in config.currentModels()"
            :key="m"
            :value="m"
          >
            {{ m }}
          </option>
        </select>
      </div>

      <!-- API Key -->
      <div class="config-section">
        <label class="config-label">
          {{ config.currentProvider()?.apiKeyEnv ?? 'API Key' }}
        </label>
        <input
          class="config-input"
          type="password"
          :value="config.getApiKey(config.activeProvider)"
          :placeholder="'Enter ' + (config.currentProvider()?.apiKeyEnv ?? 'key')"
          @input="config.setApiKey(config.activeProvider, ($event.target as HTMLInputElement).value)"
        />
      </div>

      <!-- Quick Provider Switcher -->
      <div class="config-section">
        <label class="config-label">Quick Switch</label>
        <div class="provider-chips">
          <button
            v-for="p in config.providers"
            :key="p.name"
            class="provider-chip"
            :class="{ active: config.activeProvider === p.name }"
            @click="config.setProvider(p.name)"
          >
            {{ p.name.slice(0, 4).toUpperCase() }}
          </button>
        </div>
      </div>

      <!-- Info -->
      <div class="config-section info-section">
        <div class="info-row">
          <span class="info-key">Active:</span>
          <span class="info-value">{{ config.activeProvider }} / {{ config.activeModel }}</span>
        </div>
        <div class="info-row">
          <span class="info-key">Base URL:</span>
          <span class="info-value">{{ config.currentProvider()?.baseUrl ?? '-' }}</span>
        </div>
        <div class="info-row">
          <span class="info-key">Key:</span>
          <span class="info-value" :class="{ set: !!config.getApiKey(config.activeProvider) }">
            {{ config.getApiKey(config.activeProvider) ? '••••configured' : 'not set' }}
          </span>
        </div>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  background-color: var(--bg-secondary);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  transition: width 0.2s ease;
  flex-shrink: 0;
  overflow: hidden;
}

.sidebar:not(.collapsed) {
  width: 260px;
  min-width: 260px;
}

.sidebar.collapsed {
  width: 40px;
  min-width: 40px;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.sidebar-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
}

.toggle-btn {
  background: none;
  border: 1px solid var(--border);
  color: var(--text-secondary);
  font-size: 11px;
  cursor: pointer;
  padding: 3px 6px;
  border-radius: 4px;
  flex-shrink: 0;
}

.toggle-btn:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.sidebar-body {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.config-section {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.config-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.config-select,
.config-input {
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 13px;
  padding: 7px 10px;
  outline: none;
  font-family: inherit;
}

.config-select:focus,
.config-input:focus {
  border-color: var(--accent);
}

.config-input::placeholder {
  color: var(--text-secondary);
  opacity: 0.6;
  font-size: 12px;
}

.provider-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.provider-chip {
  background: var(--bg-primary);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 600;
  padding: 4px 8px;
  border-radius: 4px;
  cursor: pointer;
  font-family: inherit;
  transition: all 0.15s;
}

.provider-chip:hover {
  border-color: var(--accent);
  color: var(--text-primary);
}

.provider-chip.active {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}

.info-section {
  margin-top: auto;
  padding-top: 10px;
  border-top: 1px solid var(--border);
}

.info-row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
  font-size: 11px;
}

.info-key {
  color: var(--text-secondary);
  flex-shrink: 0;
}

.info-value {
  color: var(--text-primary);
  text-align: right;
  word-break: break-all;
}

.info-value.set {
  color: var(--success);
}

.sidebar.collapsed .sidebar-header {
  justify-content: center;
  padding: 10px 0;
}
</style>
