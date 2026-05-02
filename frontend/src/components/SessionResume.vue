<script setup lang="ts">
import { ref } from 'vue'
import { useSSE } from '../utils/sse'

const emit = defineEmits<{
  (e: 'resume', sessionId: string): void
  (e: 'close'): void
}>()

const { connect } = useSSE()
const sessionId = ref('')
const loading = ref(false)
const error = ref('')

async function handleResume(): void {
  const id = sessionId.value.trim()
  if (!id) return

  loading.value = true
  error.value = ''
  try {
    emit('resume', id)
  } catch (e: any) {
    error.value = e?.message || 'Failed to resume session'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="session-resume">
    <div class="session-resume-header">
      <h3>Resume Session</h3>
      <button class="btn-close" @click="emit('close')">&times;</button>
    </div>
    <div class="session-resume-body">
      <p class="hint">Enter a session ID to resume a previous conversation.</p>
      <input
        v-model="sessionId"
        type="text"
        class="session-input"
        placeholder="Session ID (e.g. abc123...)"
        :disabled="loading"
        @keyup.enter="handleResume"
      />
      <div v-if="error" class="error-message">{{ error }}</div>
      <button class="btn-resume" :disabled="loading || !sessionId.trim()" @click="handleResume">
        {{ loading ? 'Resuming...' : 'Resume' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.session-resume {
  background-color: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
  margin: 12px 0;
}

.session-resume-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.session-resume-header h3 {
  margin: 0;
  font-size: 14px;
  color: var(--text-primary);
}

.btn-close {
  background: none;
  border: none;
  color: var(--text-secondary);
  font-size: 18px;
  cursor: pointer;
}

.session-resume-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.hint {
  font-size: 12px;
  color: var(--text-secondary);
  margin: 0;
}

.session-input {
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background-color: var(--bg-primary);
  color: var(--text-primary);
  font-size: 13px;
}

.error-message {
  color: var(--warning);
  font-size: 12px;
}

.btn-resume {
  align-self: flex-end;
  padding: 6px 16px;
  background-color: var(--accent);
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
}

.btn-resume:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}
</style>
