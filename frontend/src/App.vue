<script setup lang="ts">
import { onMounted } from 'vue'
import { useChatStore } from './stores/chat'
import { useSSE } from './utils/sse'
import ChatMessages from './components/ChatMessages.vue'
import ChatInput from './components/ChatInput.vue'
import StatusBar from './components/StatusBar.vue'

const store = useChatStore()
const { connect, disconnect } = useSSE()

onMounted(() => {
  store.init()
})

function handleSubmit(text: string) {
  if (!text.trim() || store.isProcessing) return
  store.addMessage({ role: 'user', content: text })
  store.setProcessing(true)
  connect(text)
}

function handleStop() {
  disconnect()
  store.setProcessing(false)
}
</script>

<template>
  <div class="app-container">
    <header class="app-header">
      <h1>py-cc-learn</h1>
      <span class="app-subtitle">AI Coding Assistant</span>
    </header>
    <StatusBar />
    <main class="app-main">
      <ChatMessages />
    </main>
    <footer class="app-footer">
      <ChatInput
        :disabled="store.isProcessing"
        @submit="handleSubmit"
        @stop="handleStop"
      />
    </footer>
  </div>
</template>

<style>
*,
*::before,
*::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

:root {
  --bg-primary: #1a1a2e;
  --bg-secondary: #16213e;
  --bg-tertiary: #0f3460;
  --text-primary: #e0e0e0;
  --text-secondary: #a0a0b0;
  --accent: #e94560;
  --accent-hover: #ff6b81;
  --border: #2a2a4a;
  --success: #4caf50;
  --warning: #ff9800;
}

html, body {
  height: 100%;
  margin: 0;
  padding: 0;
  font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
  background-color: var(--bg-primary);
  color: var(--text-primary);
  overflow: hidden;
}

#app {
  height: 100%;
}

.app-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  max-width: 960px;
  margin: 0 auto;
}

.app-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  background-color: var(--bg-secondary);
  flex-shrink: 0;
}

.app-header h1 {
  font-size: 18px;
  font-weight: 600;
  color: var(--accent);
}

.app-subtitle {
  font-size: 12px;
  color: var(--text-secondary);
}

.app-main {
  flex: 1;
  overflow-y: auto;
  padding: 0 16px;
}

.app-footer {
  flex-shrink: 0;
  border-top: 1px solid var(--border);
  background-color: var(--bg-secondary);
}
</style>
