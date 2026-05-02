<script setup lang="ts">
import { computed } from 'vue'
import MarkdownRenderer from './MarkdownRenderer.vue'

export interface ChatMessageData {
  id?: string
  type?: string
  role?: string
  content?: string
  message?: {
    content?: string
  }
  timestamp?: number
}

const props = defineProps<{
  message: ChatMessageData
}>()

function formatTime(ts: number): string {
  const d = new Date(ts)
  return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
}

const messageType = computed(() => {
  // Use explicit type, or infer from role
  if (props.message.type) return props.message.type
  if (props.message.role) return props.message.role
  return 'unknown'
})

const displayContent = computed(() => {
  // Extract content from various nesting patterns
  if (props.message.content !== undefined && props.message.content !== null) {
    return String(props.message.content)
  }
  if (props.message.message?.content !== undefined && props.message.message?.content !== null) {
    return String(props.message.message.content)
  }
  return ''
})

const showTimestamp = computed(() => {
  return props.message.timestamp !== undefined && props.message.timestamp > 0
})

const avatarLabel = computed(() => {
  switch (messageType.value) {
    case 'user': return 'You'
    case 'assistant': return 'AI'
    case 'system': return 'Sys'
    default: return '?'
  }
})
</script>

<template>
  <div class="chat-message" :class="`msg-${messageType}`">
    <!-- User messages: right-aligned -->
    <template v-if="messageType === 'user'">
      <div class="msg-wrapper msg-user-wrapper">
        <div class="msg-bubble msg-user-bubble">
          <div class="msg-content">{{ displayContent }}</div>
          <div v-if="showTimestamp" class="msg-time">{{ formatTime(message.timestamp!) }}</div>
        </div>
        <div class="msg-avatar msg-user-avatar">{{ avatarLabel }}</div>
      </div>
    </template>

    <!-- Assistant messages: left-aligned with Markdown -->
    <template v-else-if="messageType === 'assistant'">
      <div class="msg-wrapper msg-assistant-wrapper">
        <div class="msg-avatar msg-assistant-avatar">{{ avatarLabel }}</div>
        <div class="msg-bubble msg-assistant-bubble">
          <div class="msg-content">
            <MarkdownRenderer :content="displayContent" />
          </div>
          <div v-if="showTimestamp" class="msg-time">{{ formatTime(message.timestamp!) }}</div>
        </div>
      </div>
    </template>

    <!-- System messages: centered, muted -->
    <template v-else-if="messageType === 'system'">
      <div class="msg-system-inner">
        <span class="msg-system-text">{{ displayContent }}</span>
        <span v-if="showTimestamp" class="msg-system-time">{{ formatTime(message.timestamp!) }}</span>
      </div>
    </template>

    <!-- Progress / tool / other messages -->
    <template v-else>
      <div class="msg-wrapper msg-assistant-wrapper">
        <div class="msg-avatar msg-progress-avatar">?</div>
        <div class="msg-bubble msg-progress-bubble">
          <div class="msg-content">
            <MarkdownRenderer :content="displayContent" />
          </div>
          <div v-if="showTimestamp" class="msg-time">{{ formatTime(message.timestamp!) }}</div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.chat-message {
  margin-bottom: 4px;
}

/* ---- Wrappers ---- */
.msg-wrapper {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  max-width: 85%;
}

.msg-user-wrapper {
  margin-left: auto;
  flex-direction: row-reverse;
}

.msg-assistant-wrapper {
  margin-right: auto;
}

/* ---- Avatars ---- */
.msg-avatar {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  line-height: 1;
}

.msg-user-avatar {
  background-color: #2563eb;
  color: #fff;
}

.msg-assistant-avatar {
  background-color: #e94560;
  color: #fff;
}

.msg-progress-avatar {
  background-color: var(--border);
  color: var(--text-secondary);
}

/* ---- Bubbles ---- */
.msg-bubble {
  padding: 8px 12px;
  border-radius: 10px;
  position: relative;
  min-width: 0;
}

.msg-user-bubble {
  background-color: #2563eb;
  color: #fff;
  border-bottom-right-radius: 4px;
}

.msg-user-bubble .msg-time {
  color: rgba(255, 255, 255, 0.6);
}

.msg-assistant-bubble {
  background-color: var(--bg-secondary);
  color: var(--text-primary);
  border: 1px solid var(--border);
  border-bottom-left-radius: 4px;
}

.msg-progress-bubble {
  background-color: var(--bg-secondary);
  color: var(--text-secondary);
  border: 1px dashed var(--border);
  border-bottom-left-radius: 4px;
  font-style: italic;
}

/* ---- Content ---- */
.msg-content {
  font-size: 14px;
  line-height: 1.6;
  overflow-wrap: break-word;
  word-break: break-word;
}

.msg-user-bubble .msg-content {
  white-space: pre-wrap;
}

/* ---- Timestamp ---- */
.msg-time {
  font-size: 10px;
  color: var(--text-secondary);
  margin-top: 4px;
  text-align: right;
}

/* ---- System ---- */
.msg-system {
  text-align: center;
  padding: 4px 12px;
}

.msg-system-inner {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 4px 12px;
  background-color: var(--bg-secondary);
  border: 1px dashed var(--border);
  border-radius: 6px;
  color: var(--text-secondary);
  font-size: 12px;
  font-style: italic;
}

.msg-system-text {
  opacity: 0.75;
}

.msg-system-time {
  font-size: 10px;
  opacity: 0.5;
}
</style>
