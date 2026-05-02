<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  content: string
}>()

// LRU-based rendering cache (max 500 entries)
const MAX_CACHE_SIZE = 500
const renderCache = new Map<string, string>()
const cacheAccessOrder: string[] = []

function getCached(key: string): string | undefined {
  if (!renderCache.has(key)) return undefined
  // Move to end (most recently used)
  const idx = cacheAccessOrder.indexOf(key)
  if (idx !== -1) {
    cacheAccessOrder.splice(idx, 1)
    cacheAccessOrder.push(key)
  }
  return renderCache.get(key)
}

function setCache(key: string, value: string): void {
  if (renderCache.has(key)) {
    const idx = cacheAccessOrder.indexOf(key)
    if (idx !== -1) cacheAccessOrder.splice(idx, 1)
    cacheAccessOrder.push(key)
    renderCache.set(key, value)
    return
  }
  // Evict oldest if at capacity
  while (cacheAccessOrder.length >= MAX_CACHE_SIZE) {
    const oldest = cacheAccessOrder.shift()!
    renderCache.delete(oldest)
  }
  cacheAccessOrder.push(key)
  renderCache.set(key, value)
}

// Escape HTML entities
function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

// Basic syntax highlighting for code
function highlightCode(code: string, lang: string): string {
  const escaped = escapeHtml(code.trimEnd())
  
  const keywords = /\b(import|export|from|const|let|var|function|return|if|else|for|while|switch|case|break|continue|class|extends|new|this|super|try|catch|throw|async|await|yield|typeof|instanceof|void|delete|in|of|default|true|false|null|undefined|type|interface|enum|readonly|private|public|protected|static|abstract|implements|extends|as|is|keyof|infer|never|unknown|any|string|number|boolean|symbol|object|Promise|Array|Map|Set)\b/g
  
  const strings = /(&quot;(?:[^&]|&(?!quot;))*&quot;|'[^']*'|`[^`]*`)/g
  const comments = /(\/\/.*$|\/\*[\s\S]*?\*\/|#.*$)/gm
  const numbers = /\b(\d+\.?\d*)\b/g
  const functions = /\b([a-zA-Z_]\w*)\s*\(/g
  
  let highlighted = escaped
    // Comments first (line comments)
    .replace(comments, '<span class="code-comment">$1</span>')
    // Strings
    .replace(strings, '<span class="code-string">$1</span>')
    // Keywords
    .replace(keywords, '<span class="code-keyword">$1</span>')
    // Numbers
    .replace(numbers, '<span class="code-number">$1</span>')
  
  // Function calls after keywords to avoid false matches
  highlighted = highlighted.replace(functions, '<span class="code-function">$1</span>(')

  return `<code class="language-${lang}">${highlighted}</code>`
}

function renderMarkdown(raw: string): string {
  if (!raw) return ''

  // Check cache
  const cached = getCached(raw)
  if (cached) return cached

  let html = raw

  // ---- Pre-processing: Extract and protect code blocks ----
  const codeBlocks: string[] = []
  html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, (_match, lang, code) => {
    const idx = codeBlocks.length
    codeBlocks.push(`<pre class="code-block"><code class="language-${escapeHtml(lang || 'plaintext')}">${highlightCode(code, lang)}</code></pre>`)
    return `%%CODEBLOCK_${idx}%%`
  })

  // ---- Protect inline code ----
  const inlineCodes: string[] = []
  html = html.replace(/`([^`]+)`/g, (_match, code) => {
    const idx = inlineCodes.length
    inlineCodes.push(`<code class="inline-code">${escapeHtml(code)}</code>`)
    return `%%INLINECODE_${idx}%%`
  })

  // ---- Escape remaining HTML ----
  html = escapeHtml(html)

  // ---- Headers (must be before bold/italic) ----
  html = html.replace(/^###### (.+)$/gm, '<h6>$1</h6>')
  html = html.replace(/^##### (.+)$/gm, '<h5>$1</h5>')
  html = html.replace(/^#### (.+)$/gm, '<h4>$1</h4>')
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>')
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>')
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>')

  // ---- Horizontal rules ----
  html = html.replace(/^(---|\*\*\*|___)\s*$/gm, '<hr>')

  // ---- Blockquotes ----
  html = html.replace(/^&gt; (.*)$/gm, '<blockquote>$1</blockquote>')
  // Merge consecutive blockquotes
  html = html.replace(/<\/blockquote>\n<blockquote>/g, '\n')

  // ---- Bold and Italic ----
  html = html.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>')
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>')
  html = html.replace(/___(.+?)___/g, '<strong><em>$1</em></strong>')
  html = html.replace(/__(.+?)__/g, '<strong>$1</strong>')
  html = html.replace(/_(.+?)_/g, '<em>$1</em>')

  // ---- Links ----
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')

  // ---- Images ----
  html = html.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img src="$2" alt="$1">')

  // ---- Unordered lists ----
  html = html.replace(/^[\*\-] (.+)$/gm, '<li>$1</li>')
  // Wrap consecutive <li> in <ul>
  html = html.replace(/((?:<li>.*<\/li>\n?)+)/g, '<ul>$1</ul>')

  // ---- Ordered lists ----
  html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>')
  // Wrap consecutive <li> in <ol> (avoid double wrapping with ul)
  html = html.replace(/(?<!<\/ul>\n)((?:<li>[^<]*<\/li>\n?)+)/g, (match) => {
    if (match.includes('<ul>')) return match
    return `<ol>${match}</ol>`
  })

  // ---- Line breaks & paragraphs ----
  // Double newlines become paragraph breaks
  const parts = html.split(/\n\n+/)
  html = parts.map(part => {
    const trimmed = part.trim()
    if (!trimmed) return ''
    // Don't wrap block-level elements
    if (/^<(h[1-6]|ul|ol|pre|blockquote|hr|li|table)/.test(trimmed)) {
      return trimmed
    }
    return `<p>${trimmed.replace(/\n/g, '<br>')}</p>`
  }).join('\n')

  // ---- Restore code blocks and inline code ----
  html = html.replace(/%%CODEBLOCK_(\d+)%%/g, (_m, idx) => codeBlocks[parseInt(idx)])
  html = html.replace(/%%INLINECODE_(\d+)%%/g, (_m, idx) => inlineCodes[parseInt(idx)])

  // ---- Cleanup ----
  html = html.replace(/\n/g, '')
  html = html.replace(/<p>\s*<\/p>/g, '')

  // Cache the result
  setCache(raw, html)

  return html
}

const renderedHtml = computed(() => renderMarkdown(props.content))
</script>

<template>
  <div class="markdown-renderer" v-html="renderedHtml"></div>
</template>

<style scoped>
.markdown-renderer {
  font-size: 14px;
  line-height: 1.7;
  color: var(--text-primary);
  word-break: break-word;
}

.markdown-renderer :deep(h1) {
  font-size: 1.6em;
  font-weight: 700;
  margin: 0.8em 0 0.4em;
  padding-bottom: 0.3em;
  border-bottom: 1px solid var(--border);
}

.markdown-renderer :deep(h2) {
  font-size: 1.4em;
  font-weight: 600;
  margin: 0.7em 0 0.3em;
  padding-bottom: 0.2em;
  border-bottom: 1px solid var(--border);
}

.markdown-renderer :deep(h3) {
  font-size: 1.2em;
  font-weight: 600;
  margin: 0.6em 0 0.3em;
}

.markdown-renderer :deep(h4),
.markdown-renderer :deep(h5),
.markdown-renderer :deep(h6) {
  font-size: 1em;
  font-weight: 600;
  margin: 0.5em 0 0.25em;
}

.markdown-renderer :deep(p) {
  margin: 0.4em 0;
}

.markdown-renderer :deep(strong) {
  font-weight: 700;
}

.markdown-renderer :deep(em) {
  font-style: italic;
}

.markdown-renderer :deep(ul),
.markdown-renderer :deep(ol) {
  margin: 0.4em 0;
  padding-left: 1.5em;
}

.markdown-renderer :deep(li) {
  margin: 0.15em 0;
}

.markdown-renderer :deep(a) {
  color: #58a6ff;
  text-decoration: none;
}

.markdown-renderer :deep(a:hover) {
  text-decoration: underline;
}

.markdown-renderer :deep(blockquote) {
  margin: 0.5em 0;
  padding: 0.3em 0.8em;
  border-left: 3px solid var(--accent);
  color: var(--text-secondary);
  background-color: rgba(233, 69, 96, 0.05);
}

.markdown-renderer :deep(code.inline-code) {
  background-color: var(--bg-tertiary);
  color: #f0a060;
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
  font-size: 0.9em;
}

.markdown-renderer :deep(pre.code-block) {
  margin: 0.6em 0;
  padding: 12px 16px;
  background-color: #0d1117;
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow-x: auto;
  font-size: 13px;
  line-height: 1.5;
}

.markdown-renderer :deep(pre.code-block code) {
  font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
  color: #c9d1d9;
  white-space: pre;
  tab-size: 2;
}

.markdown-renderer :deep(.code-keyword) {
  color: #ff7b72;
}

.markdown-renderer :deep(.code-string) {
  color: #a5d6ff;
}

.markdown-renderer :deep(.code-comment) {
  color: #8b949e;
  font-style: italic;
}

.markdown-renderer :deep(.code-number) {
  color: #79c0ff;
}

.markdown-renderer :deep(.code-function) {
  color: #d2a8ff;
}

.markdown-renderer :deep(hr) {
  border: none;
  border-top: 1px solid var(--border);
  margin: 1em 0;
}

.markdown-renderer :deep(img) {
  max-width: 100%;
  border-radius: 4px;
  margin: 0.5em 0;
}
</style>
