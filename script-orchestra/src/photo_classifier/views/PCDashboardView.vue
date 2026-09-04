<template>
  <div class="dashboard-wrapper">
    <!-- Header -->
    <div class="header">
      <div class="header-left">
        <el-button @click="goBack" circle size="small"><el-icon><ArrowLeft /></el-icon></el-button>
        <span class="header-title">Photo Classifier</span>
      </div>
      <div class="header-right">
        <el-button
          type="primary"
          @click="goToBatchSelect"
        >
          批量选择
        </el-button>
        <el-button
          type="danger"
          @click="handleReset"
        >
          重置
        </el-button>
        <el-button
          type="primary"
          :icon="Setting"
          @click="settingsDrawerVisible = true"
        >
          Settings
        </el-button>
      </div>
    </div>

    <!-- Dashboard Content -->
    <div class="dashboard-container">
    <el-card
      class="group-card"
      v-if="photoClassifierStore.defaultGroup.files.length"
      shadow="hover"
      @click="goToDefaultGroup"
    >
      <template v-if="photoClassifierStore.defaultGroupAvatar">
        <video
          v-if="isVideoUrl(photoClassifierStore.defaultGroupAvatar)"
          :src="photoClassifierStore.defaultGroupAvatar"
          class="card-image"
          muted
          preload="metadata"
        />
        <el-image
          v-else
          :src="photoClassifierStore.defaultGroupAvatar"
          fit="contain"
          class="card-image"
        ></el-image>
      </template>
    </el-card>

    <el-card
      class="group-card"
      v-for="(group, index) in photoClassifierStore.groupList.groupList"
      :key="index"
      shadow="hover"
      @click="goToGroup(group, index)"
    >
      <template v-if="photoClassifierStore.groupAvatar(index)">
        <video
          v-if="isVideoUrl(photoClassifierStore.groupAvatar(index))"
          :src="photoClassifierStore.groupAvatar(index)"
          class="card-image"
          muted
          preload="metadata"
        />
        <el-image
          v-else
          :src="photoClassifierStore.groupAvatar(index)"
          fit="contain"
          class="card-image"
        ></el-image>
      </template>
    </el-card>
    </div>

    <!-- Settings Drawer -->
    <PCSettingsDrawer
      v-model="settingsDrawerVisible"
      @path-changed="handlePathChanged"
    />
  </div>
</template>

<style scoped>
.dashboard-wrapper {
  display: flex;
  flex-direction: column;
  height: 100%;
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
}

.header-title {
  font-size: 18px;
  font-weight: bold;
  color: #333;
}

.header-right {
  display: flex;
  align-items: center;
}

.dashboard-container {
  flex: 1;
  display: flex;
  flex-wrap: wrap;
  gap: 20px;
  padding: 20px;
  overflow-y: auto;
}

.group-card {
  width: 400px;
  cursor: pointer;
  transition: all 0.2s;
}

.group-card:hover {
  transform: scale(1.05);
}

.card-title {
  font-weight: bold;
  margin-bottom: 10px;
  text-align: center;
}

.card-image {
  width: 100%;
  height: 300px;
  object-fit: contain;  /* Changed from cover to contain - show full image */
  border-radius: 6px;
}
</style>

<script lang="ts" src="@/photo_classifier/views/PCDashboardView.ts"></script>