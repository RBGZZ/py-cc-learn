import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

export interface ProviderConfig {
  name: string
  models: string[]
  apiKeyEnv: string
  baseUrl: string
}

const PROVIDERS: ProviderConfig[] = [
  {
    name: 'deepseek',
    models: ['deepseek-v4-flash', 'deepseek-chat', 'deepseek-coder'],
    apiKeyEnv: 'DEEPSEEK_API_KEY',
    baseUrl: 'https://api.deepseek.com',
  },
  {
    name: 'openai',
    models: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'o3-mini'],
    apiKeyEnv: 'OPENAI_API_KEY',
    baseUrl: 'https://api.openai.com',
  },
  {
    name: 'anthropic',
    models: ['claude-sonnet-4-20250514', 'claude-opus-4-20250514', 'claude-haiku-4-20250514'],
    apiKeyEnv: 'ANTHROPIC_API_KEY',
    baseUrl: 'https://api.anthropic.com',
  },
  {
    name: 'qwen',
    models: ['qwen-plus', 'qwen-max', 'qwen-turbo', 'qwen-coder-plus'],
    apiKeyEnv: 'QWEN_API_KEY',
    baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode',
  },
  {
    name: 'google',
    models: ['gemini-2.0-flash', 'gemini-2.0-pro', 'gemini-1.5-pro'],
    apiKeyEnv: 'GOOGLE_API_KEY',
    baseUrl: 'https://generativelanguage.googleapis.com',
  },
]

const STORAGE_KEY = 'pycc_config'

interface SavedConfig {
  provider: string
  model: string
  apiKeys: Record<string, string>
}

function loadFromStorage(): SavedConfig | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return JSON.parse(raw)
  } catch {}
  return null
}

function saveToStorage(config: SavedConfig): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(config))
}

export const useConfigStore = defineStore('config', () => {
  const saved = loadFromStorage()

  const providers = ref<ProviderConfig[]>(PROVIDERS)
  const activeProvider = ref<string>(saved?.provider ?? 'deepseek')
  const activeModel = ref<string>(saved?.model ?? 'deepseek-v4-flash')
  const apiKeys = ref<Record<string, string>>(saved?.apiKeys ?? {})
  const sidebarOpen = ref<boolean>(true)

  function currentProvider(): ProviderConfig | undefined {
    return providers.value.find(p => p.name === activeProvider.value)
  }

  function currentModels(): string[] {
    return currentProvider()?.models ?? []
  }

  function setProvider(name: string) {
    const prov = providers.value.find(p => p.name === name)
    if (prov) {
      activeProvider.value = name
      activeModel.value = prov.models[0]
      persist()
    }
  }

  function setModel(model: string) {
    activeModel.value = model
    persist()
  }

  function setApiKey(provider: string, key: string) {
    apiKeys.value[provider] = key
    persist()
  }

  function getApiKey(provider: string): string {
    return apiKeys.value[provider] ?? ''
  }

  function persist() {
    saveToStorage({
      provider: activeProvider.value,
      model: activeModel.value,
      apiKeys: apiKeys.value,
    })
  }

  function toggleSidebar() {
    sidebarOpen.value = !sidebarOpen.value
  }

  return {
    providers,
    activeProvider,
    activeModel,
    apiKeys,
    sidebarOpen,
    currentProvider,
    currentModels,
    setProvider,
    setModel,
    setApiKey,
    getApiKey,
    toggleSidebar,
  }
})
