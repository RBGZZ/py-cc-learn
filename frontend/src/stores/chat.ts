import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useSSE, type SSEEvent } from '../utils/sse'

export interface Message {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: number
}

export const useChatStore = defineStore('chat', () => {
  const messages = ref<Message[]>([])
  const isProcessing = ref(false)
  const sessionId = ref<string | null>(null)
  const currentModel = ref<string>('')
  const permissionMode = ref<string>('default')
  const totalCostUsd = ref(0)
  const contextTokens = ref(0)
  const contextLimit = ref(200000)

  let messageIdCounter = 0
  let currentAssistantId = ''

  function generateId(): string {
    messageIdCounter++
    const chars = 'abcdefghijklmnopqrstuvwxyz0123456789'
    let result = ''
    for (let i = 0; i < 12; i++) {
      result += chars.charAt(Math.floor(Math.random() * chars.length))
    }
    return `${result}_${messageIdCounter}`
  }

  function init(): void {
    const { onMessage, onError, onReconnecting } = useSSE()

    onMessage((event: SSEEvent) => {
      handleSSEEvent(event)
    })

    onError((error: Error) => {
      console.error('SSE error:', error)
      addMessage({
        role: 'system',
        content: `Connection error: ${error.message}`,
      })
    })

    onReconnecting((attempt: number) => {
      console.log(`SSE reconnecting attempt ${attempt}`)
    })
  }

  function handleSSEEvent(event: SSEEvent): void {
    switch (event.event) {
      case 'session_id': {
        if (event.data) {
          sessionId.value = event.data
        }
        break
      }
      case 'text_delta': {
        if (event.data) {
          appendToAssistantMessage(event.data)
        }
        break
      }
      case 'tool_use': {
        if (event.data) {
          try {
            const tool = JSON.parse(event.data)
            const toolMsg = `🔧 **${tool.name}**\n\`\`\`json\n${JSON.stringify(tool.input, null, 2)}\n\`\`\``
            appendToAssistantMessage(toolMsg + '\n')
          } catch {
            appendToAssistantMessage(`🔧 Tool call: ${event.data}\n`)
          }
        }
        break
      }
      case 'tool_result': {
        if (event.data) {
          appendToAssistantMessage(`\n📋 Result: ${event.data}\n`)
        }
        break
      }
      case 'status': {
        if (event.data) {
          try {
            const status = JSON.parse(event.data)
            if (status.model) currentModel.value = status.model
            if (status.permission_mode) permissionMode.value = status.permission_mode
            if (status.total_cost_usd !== undefined) totalCostUsd.value = status.total_cost_usd
            if (status.context_tokens !== undefined) contextTokens.value = status.context_tokens
          } catch {}
        }
        break
      }
      case 'result': {
        isProcessing.value = false
        break
      }
      case 'error': {
        if (event.data) {
          addMessage({
            role: 'system',
            content: `Error: ${event.data}`,
          })
        }
        isProcessing.value = false
        break
      }
      case 'disconnect': {
        isProcessing.value = false
        break
      }
    }
  }

  function appendToAssistantMessage(text: string): void {
    const last = messages.value[messages.value.length - 1]
    if (last && last.role === 'assistant' && last.id === currentAssistantId) {
      last.content += text
    } else {
      currentAssistantId = generateId()
      messages.value.push({
        id: currentAssistantId,
        role: 'assistant',
        content: text,
        timestamp: Date.now(),
      })
    }
  }

  function addMessage(msg: Omit<Message, 'id' | 'timestamp'>): void {
    messages.value.push({
      id: generateId(),
      ...msg,
      timestamp: Date.now(),
    })
  }

  function setProcessing(processing: boolean): void {
    isProcessing.value = processing
  }

  function clearMessages(): void {
    messages.value = []
  }

  return {
    messages,
    isProcessing,
    sessionId,
    currentModel,
    permissionMode,
    totalCostUsd,
    contextTokens,
    contextLimit,
    init,
    addMessage,
    setProcessing,
    clearMessages,
  }
})
