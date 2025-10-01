<template>
  <div>
    <el-container>
      <el-header>{{ currentFolderName }}</el-header>
      <el-main>
        <div v-for="(file, index) in currentFileList?.files" :key="index" class="media-item">
          <img
            v-if="file.fileType === 'image'"
            :src="file.fileUrl"
            alt="image"
          />
          <video
            v-else-if="file.fileType === 'video'"
            :src="file.fileUrl"
            controls>
          </video>
        </div>
      </el-main>
    </el-container>
    <CategoryButtonCardComponment
      v-if="categoryButtonCardJSON"
      :currentFolderPath="currentFolderName"
      side="left"
      :buttonCard="categoryButtonCardJSON.left"
      @folderChange="moveFolder"
    />
    <CategoryButtonCardComponment
      v-if="categoryButtonCardJSON"
      :currentFolderPath="currentFolderName"
      side="right"
      :buttonCard="categoryButtonCardJSON.right"
      @folderChange="moveFolder"
    />
  </div>
</template>

<style scoped>

.el-header {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 40px;
  font-size: 20px;
  font-weight: bold;
  /* background-color: aqua; */
  border: 1px solid #eee;
}
.el-main{
  margin: 0px;
  padding: 0px;
}
img {
  display: block;
  max-width: 100%;
  height: auto;
  margin: 0 auto;
  width: auto;
}
video {
  display: block;
  max-width: 100%;
  height: auto;
  margin: 0 auto;
  width: auto;
}
</style>

<script lang="ts" src="@/manga_classifier/views/MangaClassifierView.ts"></script>
