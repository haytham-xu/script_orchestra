<template>
  <el-container>
    <el-card
      v-for="tool in tools"
      :key="tool.path"
      class="tool-card"
      :data-testid="tool.testid"
      @click="goTo(tool.path)">
      <div class="tool-inner">
        <div class="tool-icon" v-html="toolIcons[tool.key]"></div>
        <div class="tool-name">{{ tool.name }}</div>
      </div>
    </el-card>
  </el-container>
</template>

<script lang="ts" setup>
import { useRouter } from 'vue-router'
import { toolIcons } from '../icons/toolIcons'

const router = useRouter()
function goTo(path: string) {
  router.push(path)
}

// key matches the slug used in toolIcons.
const tools = [
  { key: 'manga-classifier',       name: 'Manga Classifier',       path: '/manga-classifier' },
  { key: 'photo-classifier',       name: 'Photo Classifier',       path: '/photo-classifier' },
  { key: 'manga-viewer',           name: 'Manga Viewer',           path: '/manga-viewer' },
  { key: 'roadmap',                name: 'Roadmap',                path: '/roadmap' },
  { key: 'pdf-converter',          name: 'PDF Converter',          path: '/pdf-converter' },
  { key: 'unzip',                  name: 'Unzip',                  path: '/unzip' },
  { key: 'duplicate-finder',       name: 'Duplicate Finder',       path: '/duplicate-finder', testid: 'duplicate-finder' },
  { key: 'video-duplicate-finder', name: 'Video Duplicate Finder', path: '/video-duplicate-finder', testid: 'video-duplicate-finder' },
  { key: 'clipboard-share',        name: 'Clipboard Share',        path: '/clipboard-share' },
  { key: 'caffeinate',             name: 'Caffeinate',             path: '/caffeinate' },
  { key: 'browser-agent',          name: 'Browser Agent',          path: '/browser-agent' },
  { key: 'assistant',              name: 'Assistant',              path: '/assistant' },
  { key: 'file-git',               name: 'File-Git',               path: '/file-git' },
  { key: 'memory-curve',           name: 'Memory Curve',           path: '/memory-curve' },
  { key: 'knowledge-vault',        name: 'Knowledge Vault',        path: '/knowledge-vault' },
  { key: 'claude-bridge',          name: 'Claude Bridge',          path: '/claude-bridge' },
]
</script>

<style scoped>
.el-container {
  display: flex;
  flex-wrap: wrap;
  gap: 20px;
  padding: 24px;
  max-width: 1240px;
  margin: 0 auto;
  box-sizing: border-box;
}
.tool-card {
  width: 200px;
  height: 176px;
  cursor: pointer;
  transition: all 0.2s;
  border-radius: 14px;
}
.tool-card:hover {
  transform: translateY(-3px) scale(1.02);
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.14);
}
.tool-inner {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  padding-top: 18px;   /* nudge the icon+name group slightly downward */
  box-sizing: border-box;
}
.tool-icon {
  width: 68px;
  height: 68px;
}
.tool-icon :deep(svg) {
  width: 100%;
  height: 100%;
  display: block;
}
.tool-name {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  text-align: center;
}
</style>
