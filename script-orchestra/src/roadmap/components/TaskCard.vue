<template>
  <el-card class="task-card" :class="priorityClass" shadow="hover">
    <div class="task-container">
      <div class="task-content" @click="$emit('edit', task)">
        {{ task.content }}
      </div>
      <div class="task-footer">
        <span class="task-date">{{ formatDate(task.createdAt) }}</span>
        <div class="task-actions">
          <el-tag :type="priorityTagType" size="small" class="priority-tag">{{ task.priority }}</el-tag>
          <el-button text size="small" type="danger" @click.stop="$emit('delete', task.id)" class="delete-btn">
            <el-icon><Delete /></el-icon>
          </el-button>
        </div>
      </div>
    </div>
  </el-card>
</template>

<script lang="ts" setup>
import { computed } from 'vue'
import type { Task } from '../models/Task'
import { TaskPriority } from '../models/Task'
import { Delete } from '@element-plus/icons-vue'

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

.task-card :deep(.el-card__body) {
  padding: 12px;
}

.task-container {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.task-content {
  font-size: 14px;
  line-height: 1.5;
  color: var(--el-text-color-primary);
  word-break: break-word;
  white-space: pre-wrap;
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  transition: background-color 0.2s;
  min-height: 40px;
}

.task-content:hover {
  background-color: var(--el-fill-color-light);
}

.task-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 4px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.task-date {
  font-size: 11px;
  color: var(--el-text-color-placeholder);
}

.task-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.priority-tag {
  margin: 0;
  padding: 0 6px;
  height: 20px;
  line-height: 20px;
  font-size: 11px;
}

.delete-btn {
  padding: 4px;
}
</style>
