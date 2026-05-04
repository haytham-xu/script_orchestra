<template>
  <div class="pc-batch-select-view">
    <div class="header">
      <div class="header-left">
        <el-button type="primary" @click="goBack">返回</el-button>
        <el-button
          type="success"
          :disabled="selectedFiles.length === 0"
          @click="createNewGroupWithSelected"
        >
          创建新分组 ({{ selectedFiles.length }})
        </el-button>
        <el-button
          type="primary"
          :disabled="selectedFiles.length === 0"
          @click="showGroupSelectDrawer = true"
        >
          添加到分组 ({{ selectedFiles.length }})
        </el-button>
        <el-button @click="clearSelection">清空选择</el-button>
        <el-switch v-model="showUnGroupedOnly" active-text="仅未分组" @change="handleFilterChange" />
      </div>

      <div class="header-right">
        <span class="info-text">
          已选择: {{ selectedFiles.length }} / 总计: {{ allFiles.length }}
        </span>
      </div>
    </div>

    <div class="image-grid">
      <div
        v-for="(file, index) in displayFileList"
        :key="file.filePath"
        class="image-card"
        :class="{
          selected: isSelected(file),
          'in-group': file.fileStatus === 'in_group'
        }"
        @click="handleImageClick(file, index, $event)"
      >
        <div class="image-wrapper">
          <el-image
            :src="file.fileUrl + '&thumbnail=true&size=300'"
            fit="cover"
            class="thumbnail"
            lazy
            :loading="'lazy'"
          >
            <template #placeholder>
              <div class="image-slot">
                <el-icon class="is-loading"><Loading /></el-icon>
              </div>
            </template>
            <template #error>
              <div class="image-slot">
                <el-icon><Picture /></el-icon>
              </div>
            </template>
          </el-image>
          <div v-if="isSelected(file)" class="selection-badge">
            <el-icon><Check /></el-icon>
          </div>
          <div v-if="file.groupId != null" class="group-badge">
            Group {{ file.groupId }}
          </div>
        </div>
      </div>
    </div>

    <!-- Loading indicator -->
    <div v-if="hasMore" class="loading-indicator">
      <el-icon class="is-loading"><Loading /></el-icon>
      <span>滚动加载更多...</span>
    </div>

    <!-- Group Selection Drawer -->
    <el-drawer
      v-model="showGroupSelectDrawer"
      direction="rtl"
      size="20%"
      title="选择目标分组"
    >
      <div class="group-list">
        <div
          v-for="(group, index) in photoClassifierStore.groupList.groupList"
          :key="index"
          class="group-item"
          @click="addSelectedToGroup(index)"
        >
          <el-image
            v-if="photoClassifierStore.groupAvatar(index)"
            :src="photoClassifierStore.groupAvatar(index)"
            fit="cover"
            class="group-thumbnail"
          />
          <div class="group-info">
            <div class="group-title">Group {{ index }}</div>
            <div class="group-count">{{ group.files.length }} 张图片</div>
          </div>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.pc-batch-select-view {
  display: flex;
  flex-direction: column;
  height: 100vh;
}

.header {
  flex-shrink: 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 20px;
  border-bottom: 1px solid #ddd;
  background: #fff;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.header-right {
  display: flex;
  align-items: center;
}

.info-text {
  font-size: 14px;
  color: #606266;
  font-weight: 500;
}

.image-grid {
  flex: 1;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 15px;
  padding: 20px;
  overflow-y: auto;
  background: #f5f5f5;
}

.loading-indicator {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 20px;
  background: #fff;
  border-top: 1px solid #ddd;
  color: #909399;
  font-size: 14px;
}

.loading-indicator .is-loading {
  font-size: 18px;
  animation: rotating 2s linear infinite;
}

.image-card {
  cursor: pointer;
  border-radius: 8px;
  overflow: hidden;
  transition: all 0.2s;
  background: #fff;
  border: 3px solid transparent;
  width: 200px;
  height: 200px;
}

.image-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.image-card.selected {
  border-color: #409eff;
  box-shadow: 0 4px 12px rgba(64, 158, 255, 0.3);
}

.image-card.in-group {
  opacity: 0.7;
}

.image-wrapper {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
}

.thumbnail {
  width: 100%;
  height: 100%;
}

.selection-badge {
  position: absolute;
  top: 10px;
  right: 10px;
  width: 30px;
  height: 30px;
  background: #409eff;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 18px;
}

.group-badge {
  position: absolute;
  bottom: 10px;
  left: 10px;
  padding: 4px 8px;
  background: rgba(0, 0, 0, 0.7);
  color: white;
  border-radius: 4px;
  font-size: 12px;
}

.image-slot {
  display: flex;
  justify-content: center;
  align-items: center;
  width: 100%;
  height: 100%;
  background: #f5f7fa;
  color: #909399;
  font-size: 30px;
}

.image-slot .is-loading {
  animation: rotating 2s linear infinite;
}

@keyframes rotating {
  0% {
    transform: rotate(0deg);
  }
  100% {
    transform: rotate(360deg);
  }
}

.group-list {
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.group-item {
  display: flex;
  align-items: center;
  padding: 10px;
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.group-item:hover {
  background: #f5f7fa;
  border-color: #409eff;
}

.group-thumbnail {
  width: 60px;
  height: 60px;
  border-radius: 4px;
  margin-right: 12px;
}

.group-info {
  flex: 1;
}

.group-title {
  font-weight: bold;
  margin-bottom: 4px;
}

.group-count {
  font-size: 12px;
  color: #909399;
}
</style>

<script lang="ts" src="@/photo_classifier/views/PCBatchSelectView.ts"></script>
