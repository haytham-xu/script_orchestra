<template>
  <el-popover
    :visible="visible"
    @update:visible="$emit('update:visible', $event)"
    trigger="click"
    placement="bottom-end"
    :width="440"
    popper-class="fg-progress-popper"
  >
    <template #reference>
      <el-badge :value="activeCount" :hidden="activeCount === 0" :max="99">
        <el-button
          :icon="triggerIcon"
          circle
          size="small"
          :class="['fg-progress-btn', triggerClass]"
          :title="triggerTitle"
        />
      </el-badge>
    </template>

    <div class="fg-progress-panel">
      <div class="fg-progress-header">
        <span>Progress</span>
        <el-tag size="small" type="info">{{ items.length }}</el-tag>
        <el-progress
          v-if="items.length > 0"
          :percentage="donePercent"
          :status="hasError ? 'exception' : donePercent === 100 ? 'success' : undefined"
          style="flex:1; margin-left:12px"
          :stroke-width="6"
        />
      </div>
      <div v-if="items.length === 0" class="fg-progress-empty">No activity yet.</div>
      <ul v-else class="fg-progress-list">
        <li v-for="item in items" :key="item.path" class="fg-progress-item">
          <el-icon :class="['fg-progress-icon', `fg-pi-${item.status}`]">
            <Loading v-if="item.status === 'active'" class="is-loading" />
            <CircleCheck v-else-if="item.status === 'done'" />
            <CircleClose v-else-if="item.status === 'error'" />
            <Clock v-else />
          </el-icon>
          <span class="fg-progress-path mono" :title="item.path">{{ item.path }}</span>
          <el-tag size="small" :type="actionTagType(item.action)" class="fg-progress-action">
            {{ item.action }}
          </el-tag>
          <span v-if="item.detail" class="fg-progress-detail">{{ item.detail }}</span>
        </li>
      </ul>
    </div>
  </el-popover>
</template>

<script lang="ts" setup>
import { computed } from 'vue'
import { Loading, CircleCheck, CircleClose, Clock, Finished, WarningFilled, Timer } from '@element-plus/icons-vue'
import type { ProgressItem } from '../views/FileGitRepoDetailView'

const props = defineProps<{
  visible: boolean
  items: ProgressItem[]
}>()

defineEmits<{ 'update:visible': [val: boolean] }>()

const activeCount = computed(() => props.items.filter(i => i.status === 'active').length)
const hasError = computed(() => props.items.some(i => i.status === 'error'))
const doneCount = computed(() => props.items.filter(i => i.status === 'done' || i.status === 'error').length)
const donePercent = computed(() =>
  props.items.length > 0 ? Math.round((doneCount.value / props.items.length) * 100) : 0
)

const triggerIcon = computed(() => {
  if (activeCount.value > 0) return Loading
  if (props.items.length === 0) return Timer
  if (hasError.value) return WarningFilled
  return Finished
})

const triggerClass = computed(() => {
  if (activeCount.value > 0) return 'fg-progress-btn--active'
  if (hasError.value) return 'fg-progress-btn--error'
  if (props.items.length > 0) return 'fg-progress-btn--done'
  return ''
})

const triggerTitle = computed(() => {
  if (activeCount.value > 0) return `${activeCount.value} item(s) in progress`
  if (hasError.value) return 'Completed with errors'
  if (props.items.length > 0) return 'All done'
  return 'No activity'
})

function actionTagType(action: string): '' | 'success' | 'warning' | 'danger' | 'info' {
  if (action === 'UPLOAD') return 'success'
  if (action === 'DOWNLOAD') return ''
  if (action === 'REMOTE_TRASH' || action === 'REMOTE_DELETE') return 'warning'
  if (action === 'LOCAL_DELETE') return 'danger'
  return 'info'
}
</script>

<style scoped>
.fg-progress-btn--active :deep(.el-icon) { animation: spin 1s linear infinite; color: var(--el-color-primary); }
.fg-progress-btn--done :deep(.el-icon)   { color: var(--el-color-success); }
.fg-progress-btn--error :deep(.el-icon)  { color: var(--el-color-danger); }

@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

.fg-progress-panel { display: flex; flex-direction: column; gap: 8px; }

.fg-progress-header {
  display: flex; align-items: center; gap: 8px;
  font-weight: 600; font-size: 13px;
}

.fg-progress-empty { color: var(--el-text-color-secondary); font-size: 13px; padding: 8px 0; }

.fg-progress-list {
  list-style: none; margin: 0; padding: 0;
  max-height: 340px; overflow-y: auto;
  display: flex; flex-direction: column; gap: 4px;
}

.fg-progress-item {
  display: flex; align-items: center; gap: 6px;
  font-size: 12px; padding: 3px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.fg-progress-item:last-child { border-bottom: none; }

.fg-progress-icon { flex-shrink: 0; font-size: 14px; }
.fg-pi-active  { color: var(--el-color-primary); }
.fg-pi-done    { color: var(--el-color-success); }
.fg-pi-error   { color: var(--el-color-danger); }
.fg-pi-pending { color: var(--el-text-color-placeholder); }

.fg-progress-path {
  flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  color: var(--el-text-color-primary);
}

.fg-progress-action { flex-shrink: 0; }

.fg-progress-detail {
  flex-shrink: 0; color: var(--el-text-color-secondary); font-size: 11px;
  max-width: 80px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
</style>
