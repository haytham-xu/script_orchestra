<template>
  <div class="dashboard-container">
    <el-card
      class="group-card"
      v-if="photoClassifierStore.defaultGroup.files.length"
      shadow="hover"
      @click="goToDefaultGroup"
    >
      <div class="card-title">Default</div>
      <el-image
        v-if="photoClassifierStore.defaultGroupAvatar"
        :src="photoClassifierStore.defaultGroupAvatar"
        fit="cover"
        class="card-image"
      ></el-image>
    </el-card>

    <el-card
      class="group-card"
      v-for="(group, index) in photoClassifierStore.groupList.groupList"
      :key="index"
      shadow="hover"
      @click="goToGroup(group, index)"
    >
      <div class="card-title">Group {{ index + 1 }}</div>
      <el-image
        v-if="photoClassifierStore.groupAvatar(index)"
        :src="photoClassifierStore.groupAvatar(index)"
        fit="cover"
        class="card-image"
      ></el-image>
    </el-card>
  </div>
</template>

<style scoped>
.dashboard-container {
  display: flex;
  flex-wrap: wrap;
  gap: 20px;
  padding: 20px;
}

.group-card {
  width: 200px;
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
  height: 150px;
  object-fit: cover;
  border-radius: 6px;
}
</style>

<script lang="ts" src="@/photo_classifier/views/PCDashboardView.ts"></script>