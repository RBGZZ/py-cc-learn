<script setup lang="ts">
import { ref, computed } from 'vue'

export interface TodoItem {
  id: string
  content: string
  status: 'pending' | 'in_progress' | 'completed'
  priority: 'high' | 'medium' | 'low'
}

const props = defineProps<{
  todos: TodoItem[]
}>()

const completedCollapsed = ref(true)

const statusGroups = computed(() => {
  const groups: Record<string, TodoItem[]> = {
    in_progress: [],
    pending: [],
    completed: [],
  }
  for (const todo of props.todos) {
    if (groups[todo.status]) {
      groups[todo.status].push(todo)
    }
  }
  return groups
})

const hasTodos = computed(() => props.todos.length > 0)

function toggleCompleted(): void {
  completedCollapsed.value = !completedCollapsed.value
}

function priorityClass(priority: string): string {
  switch (priority) {
    case 'high': return 'priority-high'
    case 'medium': return 'priority-medium'
    case 'low': return 'priority-low'
    default: return 'priority-low'
  }
}

function statusLabel(status: string): string {
  switch (status) {
    case 'in_progress': return 'In Progress'
    case 'pending': return 'Pending'
    case 'completed': return 'Completed'
    default: return status
  }
}

function statusIcon(status: string): string {
  switch (status) {
    case 'in_progress': return '&#x25CF;'
    case 'pending': return '&#x25CB;'
    case 'completed': return '&#x2713;'
    default: return '&#x25CB;'
  }
}
</script>

<template>
  <div class="todo-panel">
    <h3 class="todo-title">Tasks</h3>

    <!-- Empty state -->
    <div v-if="!hasTodos" class="todo-empty">
      <span class="todo-empty-icon">&#x1F4CB;</span>
      <span>No todos yet</span>
    </div>

    <!-- Todo groups -->
    <template v-else>
      <!-- In Progress -->
      <div v-if="statusGroups.in_progress.length" class="todo-group">
        <div class="todo-group-header in-progress-header">
          <span class="todo-group-dot in-progress-dot"></span>
          <span class="todo-group-label">{{ statusLabel('in_progress') }}</span>
          <span class="todo-group-count">{{ statusGroups.in_progress.length }}</span>
        </div>
        <div
          v-for="todo in statusGroups.in_progress"
          :key="todo.id"
          class="todo-item"
          :class="priorityClass(todo.priority)"
        >
          <span class="todo-status-icon in-progress-icon" v-html="statusIcon(todo.status)"></span>
          <span class="todo-content">{{ todo.content }}</span>
          <span class="todo-priority-badge" :class="priorityClass(todo.priority)">{{ todo.priority }}</span>
        </div>
      </div>

      <!-- Pending -->
      <div v-if="statusGroups.pending.length" class="todo-group">
        <div class="todo-group-header pending-header">
          <span class="todo-group-dot pending-dot"></span>
          <span class="todo-group-label">{{ statusLabel('pending') }}</span>
          <span class="todo-group-count">{{ statusGroups.pending.length }}</span>
        </div>
        <div
          v-for="todo in statusGroups.pending"
          :key="todo.id"
          class="todo-item"
          :class="priorityClass(todo.priority)"
        >
          <span class="todo-status-icon pending-icon" v-html="statusIcon(todo.status)"></span>
          <span class="todo-content">{{ todo.content }}</span>
          <span class="todo-priority-badge" :class="priorityClass(todo.priority)">{{ todo.priority }}</span>
        </div>
      </div>

      <!-- Completed (collapsible) -->
      <div v-if="statusGroups.completed.length" class="todo-group">
        <div class="todo-group-header completed-header" @click="toggleCompleted">
          <span class="todo-group-arrow" :class="{ collapsed: completedCollapsed }">&#x25B6;</span>
          <span class="todo-group-dot completed-dot"></span>
          <span class="todo-group-label">{{ statusLabel('completed') }}</span>
          <span class="todo-group-count">{{ statusGroups.completed.length }}</span>
        </div>
        <div v-if="!completedCollapsed" class="todo-completed-list">
          <div
            v-for="todo in statusGroups.completed"
            :key="todo.id"
            class="todo-item todo-completed-item"
          >
            <span class="todo-status-icon completed-icon" v-html="statusIcon(todo.status)"></span>
            <span class="todo-content completed-content">{{ todo.content }}</span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.todo-panel {
  padding: 12px;
  background-color: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 13px;
}

.todo-title {
  font-size: 14px;
  font-weight: 600;
  margin: 0 0 10px;
  color: var(--text-primary);
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border);
}

/* ---- Empty state ---- */
.todo-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 20px 0;
  color: var(--text-secondary);
}

.todo-empty-icon {
  font-size: 24px;
  opacity: 0.5;
}

/* ---- Todo groups ---- */
.todo-group {
  margin-bottom: 8px;
}

.todo-group-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  cursor: default;
}

.completed-header {
  cursor: pointer;
}

.completed-header:hover {
  opacity: 0.8;
}

.todo-group-arrow {
  font-size: 8px;
  transition: transform 0.2s;
  color: var(--text-secondary);
}

.todo-group-arrow.collapsed {
  transform: rotate(0deg);
}

.todo-group-arrow:not(.collapsed) {
  transform: rotate(90deg);
}

.todo-group-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.in-progress-dot {
  background-color: #2563eb;
}

.pending-dot {
  background-color: var(--warning);
}

.completed-dot {
  background-color: var(--success);
}

.todo-group-label {
  color: var(--text-secondary);
}

.todo-group-count {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 8px;
  background-color: var(--bg-primary);
  color: var(--text-secondary);
}

/* ---- Todo items ---- */
.todo-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 5px 8px 5px 20px;
  border-left: 2px solid transparent;
}

.todo-item.priority-high {
  border-left-color: #ef4444;
}

.todo-item.priority-medium {
  border-left-color: #eab308;
}

.todo-item.priority-low {
  border-left-color: #6b7280;
}

.todo-completed-item {
  opacity: 0.6;
}

.todo-status-icon {
  flex-shrink: 0;
  font-size: 12px;
  margin-top: 2px;
}

.in-progress-icon {
  color: #2563eb;
}

.pending-icon {
  color: var(--text-secondary);
}

.completed-icon {
  color: var(--success);
}

.todo-content {
  flex: 1;
  color: var(--text-primary);
  line-height: 1.4;
}

.completed-content {
  text-decoration: line-through;
  color: var(--text-secondary);
}

.todo-priority-badge {
  flex-shrink: 0;
  font-size: 9px;
  padding: 1px 6px;
  border-radius: 4px;
  text-transform: uppercase;
  font-weight: 600;
  letter-spacing: 0.3px;
}

.priority-high .todo-priority-badge,
.todo-priority-badge.priority-high {
  background-color: rgba(239, 68, 68, 0.2);
  color: #ef4444;
}

.priority-medium .todo-priority-badge,
.todo-priority-badge.priority-medium {
  background-color: rgba(234, 179, 8, 0.2);
  color: #eab308;
}

.priority-low .todo-priority-badge,
.todo-priority-badge.priority-low {
  background-color: rgba(107, 114, 128, 0.2);
  color: #9ca3af;
}

.todo-completed-list {
  animation: slideDown 0.2s ease;
}

@keyframes slideDown {
  from { opacity: 0; max-height: 0; }
  to { opacity: 1; max-height: 500px; }
}
</style>
