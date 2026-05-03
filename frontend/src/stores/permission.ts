import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface PermissionRequest {
  id: string
  type: string
  toolName: string
  toolInput: Record<string, any>
  assistantMessage: string
}

export type PermissionBehavior = 'allow' | 'deny' | 'always_allow'

export interface AlwaysAllowRule {
  toolName: string
  commandPattern?: string
}

export const usePermissionStore = defineStore('permission', () => {
  const pendingRequests = ref<PermissionRequest[]>([])
  const permissionMode = ref<string>('default')
  const alwaysAllowRules = ref<AlwaysAllowRule[]>([])

  function addRequest(request: PermissionRequest): void {
    pendingRequests.value.push(request)
  }

  function removeRequest(id: string): void {
    pendingRequests.value = pendingRequests.value.filter((r) => r.id !== id)
  }

  function setPermissionMode(mode: string): void {
    permissionMode.value = mode
  }

  function respondToRequest(id: string, behavior: PermissionBehavior): void {
    const idx = pendingRequests.value.findIndex((r) => r.id === id)
    if (idx === -1) return

    const request = pendingRequests.value[idx]

    if (behavior === 'always_allow') {
      const rule: AlwaysAllowRule = { toolName: request.toolName }
      // For bash commands, store the command as a pattern
      if (request.toolName === 'Bash' && request.toolInput?.command) {
        rule.commandPattern = request.toolInput.command
      }
      alwaysAllowRules.value.push(rule)
    }

    // The caller handles the actual response to the backend;
    // here we just clean up the pending request.
    removeRequest(id)
  }

  return {
    pendingRequests,
    permissionMode,
    alwaysAllowRules,
    addRequest,
    removeRequest,
    setPermissionMode,
    respondToRequest,
  }
})
