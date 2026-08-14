<template>
  <div class="task-card-wrapper">
    <!-- In Progress Countdown Timer - Overlay -->
    <div v-if="isInProgress && timeRemaining" class="countdown-timer" :class="countdownClass" @click.stop="handleProgressBarClick" title="点击增加30分钟">
      <el-progress
        :percentage="countdownPercentage"
        :color="countdownColor"
        :show-text="false"
        :stroke-width="20"
        class="countdown-progress-bar"
      />
      <div class="countdown-content">
        <el-icon><Clock /></el-icon>
        <span class="countdown-text">{{ formatTimeRemaining }}</span>
      </div>
    </div>

    <el-card
      class="task-card"
      :class="[priorityClass, etaWarningClass, etaAnimationClass, returnedAnimationClass, returnedClass, { 'in-progress-card': isInProgress }]"
      :style="etaWarningStyle"
      shadow="hover"
    >
      <div class="task-container">
        <!-- Content at top -->
        <div class="task-content" @click.stop="$emit('preview', task)" style="cursor: pointer;">
          {{ task.header }}
        </div>

        <!-- Metadata in one row -->
        <div class="task-meta-row">
          <el-tag size="small" class="size-tag">{{ task.size }}</el-tag>
          <span v-if="task.eta" class="eta-text" :class="{ 'eta-overdue': isOverdue, 'eta-today': isToday }">
            {{ formatETA(task.eta) }}
          </span>
          <el-tag :type="priorityTagType" size="small" class="priority-tag">{{ task.priority }}</el-tag>
          <el-button text size="small" type="primary" @click.stop="$emit('edit', task)" class="edit-btn">
            <el-icon><Edit /></el-icon>
          </el-button>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script lang="ts" setup>
import { computed, ref, onMounted, onUnmounted } from 'vue'
import type { Task } from '../models/Task'
import { TaskPriority, TaskStatus } from '../models/Task'
import { Delete, Clock, Edit } from '@element-plus/icons-vue'

interface Props {
  task: Task
}

const props = defineProps<Props>()

const emit = defineEmits<{
  preview: [task: Task]
  edit: [task: Task]
  delete: [taskId: string]
  extendTime: [taskId: string]
}>()

// Handle progress bar click to extend time
function handleProgressBarClick() {
  emit('extendTime', props.task.id)
}

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

// ETA warning logic
const isOverdue = computed(() => {
  if (!props.task.eta) return false
  const eta = new Date(props.task.eta)
  const now = new Date()
  return eta < now
})

const isToday = computed(() => {
  if (!props.task.eta) return false
  const eta = new Date(props.task.eta)
  const today = new Date()
  // Check if same day
  return eta.getFullYear() === today.getFullYear() &&
         eta.getMonth() === today.getMonth() &&
         eta.getDate() === today.getDate()
})

const daysUntilETA = computed(() => {
  if (!props.task.eta) return Infinity
  const eta = new Date(props.task.eta)
  const now = new Date()
  // Calculate days difference considering time
  const diffMs = eta.getTime() - now.getTime()
  return Math.ceil(diffMs / (1000 * 60 * 60 * 24))
})

const etaWarningClass = computed(() => {
  if (!props.task.eta) return ''
  const days = daysUntilETA.value
  if (days < 0) return 'eta-critical'
  if (days === 0) return 'eta-urgent'
  if (days <= 2) return 'eta-warning'
  return ''
})

// Animation class for urgent tasks
const etaAnimationClass = computed(() => {
  if (!props.task.eta || props.task.status === TaskStatus.DONE) return ''

  const eta = new Date(props.task.eta)
  const now = new Date()
  const diffMs = eta.getTime() - now.getTime()
  const diffHours = diffMs / (1000 * 60 * 60)

  // Apply animation for overdue or <= 24 hours
  if (diffHours <= 24) {
    return 'eta-pulse-animation'
  }
  return ''
})

// Animation class for returned from in-progress tasks
const returnedAnimationClass = computed(() => {
  if (!props.task.returnedFromInProgress || !props.task.returnedAt) return ''

  // Check if returned_at is today (after 04:00) or yesterday after 04:00
  const returnedAt = new Date(props.task.returnedAt)
  const now = new Date()

  // Create 04:00 cutoff time for today
  const today4am = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 4, 0, 0)

  // If current time is before 04:00, use yesterday's 04:00 as cutoff
  const cutoff = now < today4am
    ? new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1, 4, 0, 0)
    : today4am

  // Show animation if returned after the cutoff
  return returnedAt >= cutoff ? 'returned-pulse-animation' : ''
})

const etaWarningStyle = computed(() => {
  // Don't show glow for DONE tasks
  if (!props.task.eta || props.task.status === TaskStatus.DONE) return {}

  const eta = new Date(props.task.eta)
  const now = new Date()
  const diffMs = eta.getTime() - now.getTime()
  const diffHours = diffMs / (1000 * 60 * 60)
  const diffDays = diffMs / (1000 * 60 * 60 * 24)

  let boxShadow = ''

  if (diffHours < 0) {
    // Overdue - Deep red glow (reduced spread by half)
    const intensity = Math.min(Math.abs(diffHours) / 24, 1)
    const alpha = 0.85 + intensity * 0.15
    boxShadow = `
      0 0 0 3px rgba(220, 38, 38, 0.7),
      0 0 12px 2px rgba(220, 38, 38, ${alpha}),
      0 4px 6px rgba(0, 0, 0, 0.1)
    `
  } else if (diffHours <= 6) {
    // 0-6 hours - Strong red (reduced spread by half)
    boxShadow = `
      0 0 0 3px rgba(220, 38, 38, 0.7),
      0 0 11px 1.5px rgba(220, 38, 38, 0.9),
      0 4px 6px rgba(0, 0, 0, 0.1)
    `
  } else if (diffHours <= 12) {
    // 6-12 hours - Medium red (reduced spread by half)
    boxShadow = `
      0 0 0 2px rgba(239, 68, 68, 0.6),
      0 0 9px 1.5px rgba(239, 68, 68, 0.85),
      0 4px 6px rgba(0, 0, 0, 0.1)
    `
  } else if (diffHours <= 24) {
    // 12-24 hours - Light red (reduced spread by half)
    boxShadow = `
      0 0 0 2px rgba(248, 113, 113, 0.55),
      0 0 8px 1px rgba(248, 113, 113, 0.75),
      0 4px 6px rgba(0, 0, 0, 0.1)
    `
  } else if (diffDays <= 3) {
    // 1-3 days - Orange yellow (reduced spread by half)
    boxShadow = `
      0 0 0 2px rgba(251, 146, 60, 0.5),
      0 0 6px 1px rgba(251, 146, 60, 0.7),
      0 4px 6px rgba(0, 0, 0, 0.1)
    `
  } else if (diffDays <= 7) {
    // 3-7 days - Light yellow (reduced spread by half)
    boxShadow = `
      0 0 0 2px rgba(253, 224, 71, 0.4),
      0 0 5px 1px rgba(253, 224, 71, 0.6),
      0 4px 6px rgba(0, 0, 0, 0.1)
    `
  } else {
    // 7+ days - Very light yellow (reduced spread by half)
    boxShadow = `
      0 0 0 1px rgba(254, 243, 199, 0.35),
      0 0 4px 0.5px rgba(254, 243, 199, 0.5),
      0 4px 6px rgba(0, 0, 0, 0.1)
    `
  }

  return { 'box-shadow': boxShadow }
})

// Returned from In Progress mark
const returnedClass = computed(() => {
  return props.task.returnedFromInProgress ? 'returned-from-in-progress' : ''
})

// In Progress countdown timer
const isInProgress = computed(() => props.task.status === TaskStatus.IN_PROGRESS)
const timeRemaining = ref(0)

// Import settings service
import { getInProgressTimeoutMs } from '../service/SettingsService'

let countdownInterval: number | null = null

const formatTimeRemaining = computed(() => {
  const totalSeconds = Math.floor(timeRemaining.value / 1000)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
})

const countdownClass = computed(() => {
  const remaining = timeRemaining.value
  const timeout = getInProgressTimeoutMs()
  const percentage = (remaining / timeout) * 100

  if (percentage > 50) {
    return 'countdown-safe'
  } else if (percentage > 25) {
    return 'countdown-good'
  } else if (percentage > 8) {
    return 'countdown-warning'
  } else {
    return 'countdown-critical'
  }
})

const countdownPercentage = computed(() => {
  const percentage = (timeRemaining.value / getInProgressTimeoutMs()) * 100
  return Math.min(100, Math.max(0, percentage)) // Clamp between 0-100
})

const countdownColor = computed(() => {
  const percentage = countdownPercentage.value

  if (percentage > 50) {
    // 50% - 100%: Cyan to Yellow
    const ratio = (percentage - 50) / 50
    const r = Math.round(255 * (1 - ratio) + 0 * ratio)  // 255 -> 0
    const g = Math.round(255)  // 255 (constant)
    const b = Math.round(0 * (1 - ratio) + 255 * ratio)  // 0 -> 255
    return `rgb(${Math.max(0, r)}, ${g}, ${Math.max(0, Math.min(255, b))})`
  } else if (percentage > 25) {
    // 25% - 50%: Yellow to Orange
    const ratio = (percentage - 25) / 25
    const r = Math.round(255)  // 255 (constant)
    const g = Math.round(165 + (255 - 165) * ratio)  // 165 -> 255
    const b = Math.round(0)  // 0 (constant)
    return `rgb(${r}, ${Math.max(0, Math.min(255, g))}, ${b})`
  } else {
    // 0% - 25%: Orange to Red
    const ratio = percentage / 25
    const r = Math.round(245 + (255 - 245) * ratio)  // 245 -> 255
    const g = Math.round(108 + (165 - 108) * ratio)  // 108 -> 165
    const b = Math.round(108)  // 108 (constant)
    return `rgb(${Math.max(0, Math.min(255, r))}, ${Math.max(0, Math.min(255, g))}, ${b})`
  }
})

function updateCountdown() {
  if (!isInProgress.value || !props.task.inProgressAt) {
    timeRemaining.value = 0
    return
  }

  const inProgressAt = new Date(props.task.inProgressAt).getTime()
  const now = Date.now()
  const elapsed = now - inProgressAt
  const timeout = getInProgressTimeoutMs()
  const remaining = timeout - elapsed

  timeRemaining.value = Math.max(0, remaining)
}

onMounted(() => {
  if (isInProgress.value && props.task.inProgressAt) {
    updateCountdown()
    countdownInterval = window.setInterval(updateCountdown, 1000)
  }
})

onUnmounted(() => {
  if (countdownInterval !== null) {
    clearInterval(countdownInterval)
  }
})

function formatETA(dateStr: string): string {
  const date = new Date(dateStr)
  const now = new Date()

  // Calculate time difference in milliseconds
  const diffMs = date.getTime() - now.getTime()
  const diffMins = Math.floor(diffMs / (1000 * 60))
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60))
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))

  if (diffMs < 0) {
    // Overdue
    const absDays = Math.abs(diffDays)
    const absHours = Math.abs(diffHours) % 24

    if (absDays >= 1) {
      return absHours > 0 ? `逾期${absDays}天${absHours}小时` : `逾期${absDays}天`
    } else if (absHours >= 1) {
      return `逾期${absHours}小时`
    } else {
      return `逾期${Math.abs(diffMins)}分钟`
    }
  } else {
    // Future
    const remainingHours = diffHours % 24

    if (diffDays >= 1) {
      return remainingHours > 0 ? `剩余${diffDays}天${remainingHours}小时` : `剩余${diffDays}天`
    } else if (diffHours >= 1) {
      return `剩余${diffHours}小时`
    } else if (diffMins >= 1) {
      return `剩余${diffMins}分钟`
    } else {
      return '即将到期'
    }
  }
}
</script>

<style scoped>
.task-card-wrapper {
  position: relative;
  width: 224px;
  height: 100px;
}

.task-card {
  width: 224px;
  height: 100px;
  margin-bottom: 0;
  cursor: grab;
  transition: all 0.3s;
  border: 1px solid var(--el-border-color);
  user-select: none;
  -webkit-user-select: none;
  -moz-user-select: none;
  -ms-user-select: none;
}

.task-card:active {
  cursor: grabbing;
}

/* Priority border-left removed - using ETA glow only */
/*
.task-card.priority-high {
  border-left: 3px solid var(--el-color-danger);
}

.task-card.priority-medium {
  border-left: 3px solid var(--el-color-warning);
}

.task-card.priority-low {
  border-left: 3px solid var(--el-color-info);
}
*/

/* Returned from In Progress - purple border removed */
/*
.task-card.returned-from-in-progress {
  border: 2px solid #9370db;
  box-shadow: 0 0 8px rgba(147, 112, 219, 0.3);
}
*/

/* ETA pulse animation */
.task-card.eta-pulse-animation {
  animation: eta-glow-pulse 2s ease-in-out infinite;
}

/* Returned from In Progress pulse animation */
.task-card.returned-pulse-animation {
  animation: returned-pulse 2s ease-in-out infinite;
}

.task-card :deep(.el-card__body) {
  padding: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.task-container {
  display: flex;
  flex-direction: column;
  gap: 4px;
  height: 100%;
  overflow: hidden;
  padding: 6px;
  position: relative;
}

/* Countdown Timer - Overlay */
.countdown-timer {
  position: absolute;
  top: -24px;
  left: 0;
  width: 228px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px 4px 0 0;
  font-size: 13px;
  font-weight: bold;
  color: white;
  z-index: 10;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  overflow: hidden;
  border-top: 2px solid rgba(60, 60, 60, 1);
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
}

.countdown-timer:hover {
  transform: scale(1.02);
  box-shadow: 0 3px 6px rgba(0, 0, 0, 0.2);
}

.countdown-timer:active {
  transform: scale(0.98);
}

.countdown-progress-bar {
  position: absolute;
  left: 0;
  top: 0;
  width: 228px;
  height: 100%;
}

.countdown-progress-bar :deep(.el-progress-bar__outer) {
  background-color: rgba(200, 200, 200, 0.3);
  border: none;
  width: 100%;
}

.countdown-progress-bar :deep(.el-progress-bar__inner) {
  transition: width 0.3s ease, background-color 0.5s ease;
}

.countdown-content {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 6px;
  color: #000000;
  font-weight: bold;
}

.countdown-timer .el-icon {
  font-size: 14px;
  color: #000000;
}

.countdown-text {
  font-size: 13px;
  letter-spacing: 1px;
  color: #000000;
}

.countdown-critical {
  animation: countdown-pulse 1s ease-in-out infinite;
}

@keyframes countdown-pulse {
  0%, 100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.9;
    transform: scale(1.02);
  }
}

@keyframes eta-glow-pulse {
  0%, 100% {
    filter: brightness(1) drop-shadow(0 0 0px transparent);
    transform: scale(1);
  }
  50% {
    filter: brightness(1.25) drop-shadow(0 0 8px rgba(220, 38, 38, 0.6));
    transform: scale(1.03);
  }
}

@keyframes returned-pulse {
  0%, 100% {
    transform: scale(1);
    box-shadow:
      0 0 0 0 rgba(147, 112, 219, 0),
      inset 0 0 0 0 rgba(147, 112, 219, 0);
  }
  50% {
    transform: scale(1.02);
    box-shadow:
      0 0 0 2px rgba(147, 112, 219, 0.5),
      inset 0 0 20px 5px rgba(147, 112, 219, 0.15);
  }
}

.task-content {
  font-size: 15px;
  line-height: 1.4;
  color: var(--el-text-color-primary);
  word-break: break-word;
  cursor: default;
  padding: 2px;
  border-radius: 4px;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  user-select: text;
  -webkit-user-select: text;
}

.task-meta-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  padding-top: 2px;
  border-top: 1px solid var(--el-border-color-lighter);
  flex-shrink: 0;
  min-height: 24px;
}

.size-tag {
  font-size: 11px;
  padding: 0 4px;
  height: 20px;
  line-height: 20px;
}

.priority-tag {
  font-size: 11px;
  padding: 0 4px;
  height: 20px;
  line-height: 20px;
  margin-left: auto;
}

.eta-text {
  color: var(--el-text-color-regular);
  font-size: 12px;
  white-space: nowrap;
}

.eta-text.eta-overdue {
  color: var(--el-color-danger);
  font-weight: bold;
}

.eta-text.eta-today {
  color: var(--el-color-warning);
  font-weight: bold;
}

.edit-btn {
  padding: 2px;
  margin-left: 4px;
  font-size: 14px;
}
</style>
