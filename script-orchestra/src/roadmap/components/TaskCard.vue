<template>
  <el-card class="task-card" :class="priorityClass" shadow="hover">
    <template #header>
      <div class="task-header">
        <span class="task-title">{{ task.title }}</span>
        <el-tag :type="priorityTagType" size="small" class="priority-tag">{{ task.priority }}</el-tag>
        <div class="task-actions">
          <el-button text size="small" @click="$emit('edit', task)">
            <el-icon><Edit /></el-icon>
          </el-button>
          <el-button text size="small" type="danger" @click="$emit('delete', task.id)">
            <el-icon><Delete /></el-icon>
          </el-button>
        </div>
      </div>
    </template>

    <div class="task-body">
      <p v-if="task.description" class="task-description">{{ task.description }}</p>
      <div class="task-meta">
        <span class="task-date">{{ formatDate(task.createdAt) }}</span>
      </div>
    </div>
  </el-card>
</template>

<script lang="ts" setup>
import { computed } from 'vue'
import type { Task } from '../models/Task'
import { TaskPriority } from '../models/Task'
import { Edit, Delete } from '@element-plus/icons-vue'

interface Props {
  task: Task
}

const props = defineProps<Props>()

defineEmits<{
  edit: [task: Task]
  delete: [taskId: string]
}>()

const priorityClass = computed(() => {
  return `priority-${props.task.priority}`
})

const priorityTagType = computed(() => {
  switch (props.task.priority) {
    case TaskPriority.HIGH:
      return 'danger'
    case TaskPriority.MEDIUM:
      return 'warning'
    case TaskPriority.LOW:
      return 'info'
    default:
      return ''
  }
})

function formatDate(dateStr: string): string {
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}
</script>

<style scoped>
.task-card {
  margin-bottom: 12px;
  cursor: grab;
  transition: all 0.3s;
}

.task-card:active {
  cursor: grabbing;
}

.task-card.priority-high {
  border-left: 3px solid var(--el-color-danger);
}

.task-card.priority-medium {
  border-left: 3px solid var(--el-color-warning);
}

.task-card.priority-low {
  border-left: 3px solid var(--el-color-info);
}

.task-card :deep(.el-card__header) {
  padding: 10px 12px;
}

.task-card :deep(.el-card__body) {
  padding: 12px;
}

.task-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.task-title {
  font-weight: 500;
  font-size: 14px;
  flex: 1;
  margin-right: 8px;
}

.priority-tag {
  margin: 0;
  padding: 0 6px;
  height: 20px;
  line-height: 20px;
  font-size: 11px;
  flex-shrink: 0;
}

.task-actions {
  display: flex;
  gap: 2px;
  flex-shrink: 0;
}

.task-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.task-description {
  margin: 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
  line-height: 1.4;
  word-break: break-word;
}

.task-meta {
  display: flex;
  justify-content: flex-start;
  align-items: center;
  margin-top: 2px;
}

.task-date {
  font-size: 11px;
  color: var(--el-text-color-placeholder);
}
</style>
