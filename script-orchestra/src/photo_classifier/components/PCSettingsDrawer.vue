<template>
  <el-drawer
    v-model="visible"
    title="Photo Classifier Settings"
    direction="rtl"
    size="400px"
    :show-close="true"
  >
    <div class="settings-container">
      <el-form label-position="top">
        <el-form-item label="Root Path">
          <el-input
            v-model="localRootPath"
            type="textarea"
            :rows="3"
            placeholder="Enter the root folder path for photo classification"
          />
          <div class="help-text">
            Example: /Users/username/Photos/to_classify
          </div>
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            @click="handleSave"
            :loading="saving"
            style="width: 100%"
          >
            Save and Reload
          </el-button>
        </el-form-item>

        <el-divider />

        <div class="current-path" v-if="currentPath">
          <div class="label">Current Path:</div>
          <div class="path">{{ currentPath }}</div>
        </div>
      </el-form>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { getRootPath, setRootPath, loadRootPathFromBackend } from '../config/settings'
import { useRouter } from 'vue-router'

const props = defineProps<{
  modelValue: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'pathChanged'): void
}>()

const router = useRouter()
const visible = ref(props.modelValue)
const localRootPath = ref('')
const currentPath = ref('')
const saving = ref(false)

// Sync with props
watch(() => props.modelValue, async (newVal) => {
  visible.value = newVal
  if (newVal) {
    // Load current path from backend when drawer opens
    try {
      currentPath.value = await loadRootPathFromBackend()
      localRootPath.value = currentPath.value
    } catch (error) {
      // Fallback to cached/localStorage value
      currentPath.value = getRootPath()
      localRootPath.value = currentPath.value
    }
  }
})

// Sync back to parent
watch(visible, (newVal) => {
  emit('update:modelValue', newVal)
})

const handleSave = async () => {
  const trimmedPath = localRootPath.value.trim()

  if (!trimmedPath) {
    ElMessage.warning('Please enter a valid path')
    return
  }

  saving.value = true

  try {
    // Save to backend (will also update localStorage)
    await setRootPath(trimmedPath)
    ElMessage.success('Settings saved successfully')

    // Close drawer
    visible.value = false

    // Emit event and redirect
    emit('pathChanged')

    // Redirect to photo-classifier route
    router.push('/photo-classifier')
  } catch (error) {
    ElMessage.error('Failed to save settings. Please check if the path exists.')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.settings-container {
  padding: 20px;
}

.help-text {
  font-size: 12px;
  color: #909399;
  margin-top: 8px;
}

.current-path {
  background-color: #f5f7fa;
  padding: 12px;
  border-radius: 4px;
}

.current-path .label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}

.current-path .path {
  font-size: 14px;
  color: #606266;
  word-break: break-all;
}
</style>
