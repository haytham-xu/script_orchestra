<template>
  <el-container> 
    <el-card @click="goTo('/manga-classifier')">
      <template #header>Manga Classifier</template>
      <p>Here is content</p>
    </el-card>
    <el-card @click="goTo('/photo-classifier')">
      <template #header>Photo Classifier</template>
      <p>Here is content</p>
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
  padding: 10px;
}
.el-card {
  margin: 20px;
  width: 400px;
  height: 247px;
  max-width: 480px;
  cursor: pointer;
}
</style>
