<template>
  <el-container>
    <el-card @click="goTo('/manga-classifier')">
      <template #header>Manga Classifier</template>
      <!-- <p>Here is content</p> -->
    </el-card>
    <el-card @click="goTo('/photo-classifier')">
      <template #header>Photo Classifier</template>
      <!-- <p>Here is content</p> -->
    </el-card>
    <el-card @click="goTo('/manga-viewer')">
      <template #header>Manga Viewer</template>
      <!-- <p>Here is content</p> -->
    </el-card>
    <el-card @click="goTo('/roadmap')">
      <template #header>Roadmap</template>
      <!-- <p>Here is content</p> -->
    </el-card>
    <el-card @click="goTo('/pdf-converter')">
      <template #header>PDF Converter</template>
      <!-- <p>Here is content</p> -->
    </el-card>
    <el-card @click="goTo('/unzip')">
      <template #header>Unzip</template>
      <!-- <p>Here is content</p> -->
    </el-card>
    <el-card @click="goTo('/duplicate-finder')">
      <template #header>Duplicate Finder</template>
      <!-- <p>Here is content</p> -->
    </el-card>
    <el-card @click="goTo('/file-git')">
      <template #header>File-Git</template>
      <!-- <p>Here is content</p> -->
    </el-card>
  </el-container>
</template>

<script lang="ts" setup>
import { useRouter } from 'vue-router'
const router = useRouter()
function goTo(path: string) {
  router.push(path)
}
</script>

<style scoped>
.el-container {
  display: flex;
  flex-wrap: wrap;
  gap: 20px;
  padding: 20px;
}
.el-card {
  width: 385px;
  height: 240px;
  cursor: pointer;
  transition: all 0.2s;
}
.el-card:hover {
  transform: scale(1.02);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}
</style>
