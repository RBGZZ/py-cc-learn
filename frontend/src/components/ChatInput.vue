<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'

const props = defineProps<{
  disabled?: boolean
}>()

const emit = defineEmits<{
  (e: 'submit', text: string): void
  (e: 'stop'): void
}>()

const inputText = ref('')
const textareaRef = ref<HTMLTextAreaElement | null>(null)

onMounted(() => {
  nextTick(() => {
    textareaRef.value?.focus()
  })
})

function handleSubmit(): void {
  const text = inputText.value.trim()
  if (!text || props.disabled) return
  emit('submit', text)
  inputText.value = ''
}

function handleKeydown(e: KeyboardEvent): void {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSubmit()
  }
}

function handleStop(): void {
  emit('stop')
}

function autoResize(): void {
  const el = textareaRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 200) + 'px'
}
</script>

<template>
  <div class="chat-input-container">
    <textarea
      ref="textareaRef"
      v-model="inputText"
      class="chat-input"
      :disabled="disabled"
      placeholder="Type a message... (Enter to send, Shift+Enter for new line)"
      rows="1"
      @keydown="handleKeydown"
      @input="autoResize"
    ></textarea>
    <div class="chat-input-actions">
      <button
        v-if="!disabled"
        class="btn-send"
        :disabled="!inputText.trim()"
        @click="handleSubmit"
      >
        Send
      </button>
      <button
        v-else
        class="btn-stop"
        @click="handleStop"
      >
        Stop
      </button>
    </div>
  </div>
</template>

<style scoped>
.chat-input-container {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  padding: 12px 16px;
}

.chat-input {
  flex: 1;
  resize: none;
  background-color: var(--bg-primary);
  color: var(--text-primary);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 14px;
  font-family: inherit;
  font-size: 14px;
  line-height: 1.5;
  min-height: 44px;
  max-height: 200px;
  outline: none;
  transition: border-color 0.2s;
}

.chat-input:focus {
  border-color: var(--accent);
}

.chat-input:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.chat-input::placeholder {
  color: var(--text-secondary);
}

.btn-send,
.btn-stop {
  padding: 10px 20px;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: background-color 0.2s;
  white-space: nowrap;
}

.btn-send {
  background-color: var(--accent);
  color: white;
}

.btn-send:hover:not(:disabled) {
  background-color: var(--accent-hover);
}

.btn-send:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.btn-stop {
  background-color: var(--warning);
  color: white;
}

.btn-stop:hover {
  filter: brightness(1.1);
}
</style>
