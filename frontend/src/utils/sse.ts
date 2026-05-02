export interface SSEEvent {
  event?: string
  id?: string
  data?: string
}

export interface SSEOptions {
  endpoint?: string
  onMessage?: (event: SSEEvent) => void
  onError?: (error: Error) => void
  onReconnecting?: (attempt: number) => void
  onDisconnect?: () => void
}

const DEFAULT_ENDPOINT = '/api/v1/chat'
const RECONNECT_BASE_DELAY_MS = 1000
const RECONNECT_MAX_DELAY_MS = 30000
const RECONNECT_MAX_ATTEMPTS = 5
const KEEPALIVE_TIMEOUT_MS = 45000

class SSEConnection {
  private abortController: AbortController | null = null
  private reconnectAttempt = 0
  private keepaliveTimer: ReturnType<typeof setTimeout> | null = null
  private reader: ReadableStreamDefaultReader<Uint8Array> | null = null
  private options: SSEOptions
  private endpoint: string
  private isDestroyed = false

  constructor(options: SSEOptions = {}) {
    this.options = options
    this.endpoint = options.endpoint || DEFAULT_ENDPOINT
  }

  async connect(body: string): Promise<void> {
    this.isDestroyed = false
    this.reconnectAttempt = 0
    await this.startConnection(body)
  }

  private async startConnection(body: string): Promise<void> {
    if (this.isDestroyed) return

    this.abortController = new AbortController()

    try {
      const response = await fetch(this.endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'text/event-stream',
        },
        body,
        signal: this.abortController.signal,
      })

      if (!response.ok) {
        const error = new Error(`SSE connection failed: ${response.status}`)
        this.options.onError?.(error)
        return
      }

      if (!response.body) {
        this.options.onError?.(new Error('SSE: response body is null'))
        return
      }

      this.reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      this.resetKeepalive()

      while (true) {
        if (this.isDestroyed) break

        const { done, value } = await this.reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })

        const { frames, remaining } = parseSSEFrames(buffer)
        buffer = remaining

        for (const frame of frames) {
          this.resetKeepalive()

          if (frame.event === 'close' || frame.event === 'result') {
            this.options.onMessage?.(frame)
            this.disconnect()
            return
          }

          this.options.onMessage?.(frame)
        }
      }

      if (!this.isDestroyed) {
        this.options.onDisconnect?.()
      }
    } catch (err: any) {
      if (err.name === 'AbortError') return
      this.options.onError?.(err)
      if (!this.isDestroyed) {
        await this.attemptReconnect(body)
      }
    }
  }

  private async attemptReconnect(body: string): Promise<void> {
    if (this.isDestroyed) return

    const delay = Math.min(
      RECONNECT_BASE_DELAY_MS * Math.pow(2, this.reconnectAttempt),
      RECONNECT_MAX_DELAY_MS
    )

    this.reconnectAttempt++
    this.options.onReconnecting?.(this.reconnectAttempt)

    if (this.reconnectAttempt > RECONNECT_MAX_ATTEMPTS) {
      this.options.onError?.(new Error('SSE: max reconnection attempts reached'))
      return
    }

    await new Promise((resolve) => setTimeout(resolve, delay))
    await this.startConnection(body)
  }

  private resetKeepalive(): void {
    if (this.keepaliveTimer) {
      clearTimeout(this.keepaliveTimer)
    }
    this.keepaliveTimer = setTimeout(() => {
      this.disconnect()
    }, KEEPALIVE_TIMEOUT_MS)
  }

  disconnect(): void {
    this.isDestroyed = true
    this.reconnectAttempt = 0

    if (this.keepaliveTimer) {
      clearTimeout(this.keepaliveTimer)
      this.keepaliveTimer = null
    }

    if (this.reader) {
      this.reader.cancel().catch(() => {})
      this.reader = null
    }

    if (this.abortController) {
      this.abortController.abort()
      this.abortController = null
    }
  }
}

function parseSSEFrames(buffer: string): {
  frames: SSEEvent[]
  remaining: string
} {
  const frames: SSEEvent[] = []
  let pos = 0

  while (true) {
    const idx = buffer.indexOf('\n\n', pos)
    if (idx === -1) break

    const rawFrame = buffer.slice(pos, idx)
    pos = idx + 2

    if (!rawFrame.trim()) continue

    const frame: SSEEvent = {}
    let isComment = false

    for (const line of rawFrame.split('\n')) {
      if (line.startsWith(':')) {
        isComment = true
        continue
      }

      const colonIdx = line.indexOf(':')
      if (colonIdx === -1) continue

      const field = line.slice(0, colonIdx)
      const value =
        line[colonIdx + 1] === ' '
          ? line.slice(colonIdx + 2)
          : line.slice(colonIdx + 1)

      switch (field) {
        case 'event':
          frame.event = value
          break
        case 'id':
          frame.id = value
          break
        case 'data':
          frame.data = frame.data ? frame.data + '\n' + value : value
          break
      }
    }

    if (frame.data || isComment) {
      frames.push(frame)
    }
  }

  return { frames, remaining: buffer.slice(pos) }
}

let sseConnection: SSEConnection | null = null
const messageHandlers = new Set<(event: SSEEvent) => void>()
const errorHandlers = new Set<(error: Error) => void>()
const reconnectHandlers = new Set<(attempt: number) => void>()

export function useSSE() {
  function connect(prompt: string): void {
    if (sseConnection) {
      sseConnection.disconnect()
    }

    sseConnection = new SSEConnection({
      endpoint: DEFAULT_ENDPOINT,
      onMessage: (event) => {
        messageHandlers.forEach((h) => h(event))
      },
      onError: (error) => {
        errorHandlers.forEach((h) => h(error))
      },
      onReconnecting: (attempt) => {
        reconnectHandlers.forEach((h) => h(attempt))
      },
      onDisconnect: () => {
        const event: SSEEvent = { event: 'disconnect' }
        messageHandlers.forEach((h) => h(event))
      },
    })

    const body = JSON.stringify({ prompt })
    sseConnection.connect(body).catch((err) => {
      errorHandlers.forEach((h) => h(err))
    })
  }

  function disconnect(): void {
    sseConnection?.disconnect()
    sseConnection = null
  }

  function onMessage(handler: (event: SSEEvent) => void): () => void {
    messageHandlers.add(handler)
    return () => messageHandlers.delete(handler)
  }

  function onError(handler: (error: Error) => void): () => void {
    errorHandlers.add(handler)
    return () => errorHandlers.delete(handler)
  }

  function onReconnecting(handler: (attempt: number) => void): () => void {
    reconnectHandlers.add(handler)
    return () => reconnectHandlers.delete(handler)
  }

  return { connect, disconnect, onMessage, onError, onReconnecting }
}

export { SSEConnection, parseSSEFrames }
export default useSSE
