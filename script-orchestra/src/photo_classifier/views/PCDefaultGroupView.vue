<template>
  <div class="pc-default-group-view">
    <div class="header">
      <div class="header-left">
        <el-button type="primary" @click="goBack">返回</el-button>
        <el-button type="success" @click="applyGroup">Apply</el-button>
        <el-button @click="drawerVisible = true">显示Group</el-button>
        <el-switch v-model="showFiltered" active-text="未标识" @change="updateDisplayFiles" />
      </div>
      <div class="header-right">
        <span v-if="currentFile?.categoryTag!=null">Category: {{ currentFile?.categoryTag }}   | </span>
        <span v-if="currentFile?.groupId!=null">Group: {{ currentFile?.groupId }}</span>
      </div>
    </div>

    <div class="main-image">
       <MediaComponment v-if="currentFile" :url="currentFile.fileUrl" :type="currentFile.fileType"/>
    </div>


    <el-drawer
      v-model="drawerVisible"
      direction="ltr"
      size="15%"
      :modal=false
      :show-close=false
      :with-header=false
      :resizable="true"
    >
      <div class="group-list">
        <div
          v-for="(group, index) in photoClassifierStore.groupList.groupList"
          :key="index"
          class="group-card"
        >
          <div class="group-header">
            <!-- <span>{{ index }}</span> -->
            <el-button v-if="currentFile" size="small" type="success" @click="addToGroup(currentFile, index)">Add</el-button>
          </div>
      
          <el-image
            v-if="photoClassifierStore.groupAvatar(index)"
            :src="photoClassifierStore.groupAvatar(index)"
            fit="contain"
            class="group-avatar"
            @click="goToGroup(index)"
          />
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>

.pc-default-group-view {
  display: flex;
  flex-direction: column;
  height: 100vh;
}

.header {
  flex-shrink: 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px;
  border-bottom: 1px solid #ddd;
}

.header-left > * {
  margin-right: 10px;
}

.header-right {
  margin-left: 20px;
}

.main-image {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background: #000;
}
/* --------- */


.group-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

 .group-list {
  display: flex;
  flex-direction: column;
  gap: 20px;
  overflow-y: auto;
}

.group-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 8px;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  cursor: pointer;
}

.group-avatar {
  max-width: 100%;
  /* max-height: 120px; */
  object-fit: contain;
  border-radius: 4px;
}
</style>

<script lang="ts" src="@/photo_classifier/views/PCDefaultGroupView.ts"></script>
