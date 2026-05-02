<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useChatStore } from '../stores/chat'
import ChatMessage from './ChatMessage.vue'
import LoadingSpinner from './LoadingSpinner.vue'

const store = useChatStore()

const MESSAGES_PER_PAGE = 50

const messagesContainer = ref<HTMLDivElement | null>(null)
const isScrolledUp = ref(false)
const visibleCount = ref(MESSAGES_PER_PAGE)
const isAutoScroll = ref(true)

const hasMessages = computed(() => store.messages.length > 0)
const totalMessages = computed(() => store.messages.length)

// Virtual scrolling: only show last N messages
const visibleMessages = computed(() => {
  const all = store.messages
  if (all.length <= visibleCount.value) return all
  return all.slice(all.length - visibleCount.value)
})

const hasMoreMessages = computed(() => visibleMessages.value.length < store.messages.length)

function loadMore(): void {
  const prevCount = visibleCount.value
  visibleCount.value = Math.min(visibleCount.value + MESSAGES_PER_PAGE, totalMessages.value)
  // Maintain scroll position after loading older messages
  nextTick(() => {
    if (messagesContainer.value) {
      const added = visibleCount.value - prevCount
      // Approximate: keep scroll position by scrolling down a bit to compensate
      messagesContainer.value.scrollTop += added * 60 // rough estimate per message
    }
  })
}

// Auto-scroll to bottom when new messages arrive
watch(
  () => store.messages.length,
  (newLen, oldLen) => {
    // If new message added (not initial load)
    if (newLen > oldLen && oldLen > 0) {
      // If user is at the bottom or auto-scroll enabled, scroll down
      if (!isScrolledUp.value || isAutoScroll.value) {
        visibleCount.value = totalMessages.value
        scrollToBottom()
      }
    }
  }
)

// Also auto-scroll when processing state changes to stream content
watch(
  () => {
    const msgs = store.messages
    if (msgs.length === 0) return ''
    return msgs[msgs.length - 1].content
  },
  () => {
    // Streaming content: scroll to bottom if near bottom
    if (!isScrolledUp.value) {
      scrollToBottom()
    }
  }
)

function scrollToBottom(): void {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
      isScrolledUp.value = false
    }
  })
}

function handleScroll(): void {
  if (!messagesContainer.value) return
  const el = messagesContainer.value
  const threshold = 120 // pixels from bottom
  isScrolledUp.value = el.scrollHeight - el.scrollTop - el.clientHeight > threshold
}

onMounted(() => {
  if (messagesContainer.value) {
    messagesContainer.value.addEventListener('scroll', handleScroll, { passive: true })
  }
  // Initial scroll to bottom if there are messages
  if (hasMessages.value) {
    scrollToBottom()
  }
})

onBeforeUnmount(() => {
  if (messagesContainer.value) {
    messagesContainer.value.removeEventListener('scroll', handleScroll)
  }
})
</script>

<template>
  <div class="chat-messages" ref="messagesContainer">
    <!-- Empty state -->
    <div v-if="!hasMessages && !store.isProcessing" class="empty-state">
      <div class="empty-state-icon">&#x1F4AC;</div>
      <h3 class="empty-state-title">No messages yet</h3>
      <p class="empty-state-desc">Start a conversation by typing a message below.</p>
      <p class="empty-state-hint">Press Enter to send, Shift+Enter for a new line.</p>
    </div>

    <!-- Load more button -->
    <div v-if="hasMoreMessages" class="load-more-wrapper">
      <button class="load-more-btn" @click="loadMore">
        Load older messages ({{ totalMessages - visibleMessages.length }} hidden)
      </button>
    </div>

    <!-- Message list -->
    <template v-for="msg in visibleMessages" :key="msg.id">
      <ChatMessage :message="msg" />
    </template>

    <!-- Processing indicator -->
    <div v-if="store.isProcessing" class="processing-indicator">
      <LoadingSpinner size="sm" text="AI is thinking..." />
    </div>

    <!-- Scroll to bottom button -->
    <Transition name="scroll-fade">
      <button
        v-if="isScrolledUp && hasMessages"
        class="scroll-to-bottom"
        @click="scrollToBottom"
        title="Scroll to bottom"
      >
        <span class="scroll-arrow">&#x2193;</span>
      </button>
    </Transition>
  </div>
</template>

<style scoped>
.chat-messages {
  position: relative;
  height: 100%;
  overflow-y: auto;
  padding: 16px 0;
  scroll-behavior: smooth;
}

/* ---- Empty state ---- */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 300px;
  color: var(--text-secondary);
  text-align: center;
  padding: 20px;
}

.empty-state-icon {
  font-size: 48px;
  margin-bottom: 16px;
  opacity: 0.5;
}

.empty-state-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 8px;
}

.empty-state-desc {
  font-size: 14px;
  margin: 0 0 6px;
  color: var(--text-secondary);
}

.empty-state-hint {
  font-size: 12px;
  color: var(--text-secondary);
  opacity: 0.6;
}

/* ---- Load more ---- */
.load-more-wrapper {
  text-align: center;
  padding: 8px 0 16px;
}

.load-more-btn {
  padding: 6px 16px;
  background-color: var(--bg-secondary);
  color: var(--accent);
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
  font-family: inherit;
  transition: background-color 0.15s;
}

.load-more-btn:hover {
  background-color: var(--bg-tertiary);
}

/* ---- Processing indicator ---- */
.processing-indicator {
  display: flex;
  justify-content: center;
  padding: 16px 0;
}

/* ---- Scroll to bottom ---- */
.scroll-to-bottom {
  position: sticky;
  bottom: 16px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  background-color: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border);
  border-radius: 50%;
  cursor: pointer;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
  transition: background-color 0.15s, transform 0.15s;
  z-index: 10;
  margin-top: -52px;
}

.scroll-to-bottom:hover {
  background-color: var(--accent);
  color: #fff;
  transform: translateX(-50%) scale(1.1);
}

.scroll-arrow {
  font-size: 18px;
  line-height: 1;
}

/* ---- Transition ---- */
.scroll-fade-enter-active,
.scroll-fade-leave-active {
  transition: opacity 0.2s, transform 0.2s;
}

.scroll-fade-enter-from,
.scroll-fade-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(10px);
}
</style>
