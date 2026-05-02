<script setup lang="ts">
import { computed } from 'vue'
import { useChatStore } from '../stores/chat'

const store = useChatStore()

const hasMessages = computed(() => store.messages.length > 0)
</script>

<template>
  <div class="chat-messages" ref="messagesContainer">
    <div v-if="!hasMessages" class="empty-state">
      <p>Start a conversation by typing a message below.</p>
    </div>
    <div v-for="msg in store.messages" :key="msg.id" class="message-item" :class="`message-${msg.role}`">
      <div class="message-role">{{ msg.role }}</div>
      <div class="message-content">{{ msg.content }}</div>
    </div>
    <div v-if="store.isProcessing" class="message-indicator">
      <span class="loading-dot"></span>
      <span class="loading-dot"></span>
      <span class="loading-dot"></span>
    </div>
  </div>
</template>

<style scoped>
.chat-messages {
  padding: 16px 0;
  min-height: 100%;
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-secondary);
  font-size: 14px;
}

.message-item {
  margin-bottom: 16px;
  padding: 12px;
  border-radius: 8px;
}

.message-user {
  background-color: var(--bg-tertiary);
  margin-left: 24px;
}

.message-assistant {
  background-color: var(--bg-secondary);
  margin-right: 24px;
  border: 1px solid var(--border);
}

.message-system {
  background-color: transparent;
  border: 1px dashed var(--border);
  color: var(--text-secondary);
  font-style: italic;
}

.message-role {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  color: var(--text-secondary);
  margin-bottom: 4px;
}

.message-content {
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.message-indicator {
  display: flex;
  gap: 4px;
  padding: 8px 12px;
}

.loading-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: var(--accent);
  animation: pulse 1.4s ease-in-out infinite;
}

.loading-dot:nth-child(2) {
  animation-delay: 0.2s;
}

.loading-dot:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes pulse {
  0%, 80%, 100% {
    opacity: 0.3;
    transform: scale(0.8);
  }
  40% {
    opacity: 1;
    transform: scale(1);
  }
}
</style>
