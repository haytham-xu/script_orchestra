<template>
  <div class="pc-group-view">
    <div class="header">
      <div class="header-buttons">
        <el-button type="primary" @click="$router.push('/photo-classifier')">返回列表</el-button>
        <el-button @click="goPrevGroup">上一组</el-button>
        <el-button @click="goNextGroup">下一组</el-button>
        <el-button type="success" @click="applyGroup">Apply</el-button>
      </div>
      <div class="header-tags">
         <span v-if="currentFile?.categoryTag!=null">Category: {{ currentFile?.categoryTag }}</span>
      </div>
    </div>

    <div class="main-image">
       <MediaComponment v-if="currentFile" :url="currentFile.fileUrl" :type="currentFile.fileType"/>
    </div>

  </div>
</template>

<style scoped>
.main-image {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background: #000;
}

/* ---------------- */
.pc-group-view {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #f8f8f8;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #ffffff;
  padding: 10px 20px;
  border-bottom: 1px solid #ddd;
}

.header-buttons {
  display: flex;
  gap: 10px;
}

.header-tags {
  font-size: 14px;
  color: #333;
}

</style>

<script lang="ts" src="@/photo_classifier/views/PCGroupView.ts"></script>
