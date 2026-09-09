<template>
  <div class="mv-hub">
    <div class="mv-header">
      <el-button type="default" size="small" @click="$router.push('/manga-viewer')">← Back</el-button>
      <h2 class="mv-title">Manga Viewer Tools</h2>
    </div>
    <div class="mv-grid">
      <div v-for="t in tools" :key="t.key" class="mv-cell" @click="$router.push(t.path)">
        <div class="mv-icon" v-html="t.icon"></div>
        <div class="mv-name">{{ t.name }}</div>
        <div class="mv-desc">{{ t.desc }}</div>
      </div>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { useRouter } from 'vue-router'
import { ElButton } from 'element-plus'

const router = useRouter()

const tools = [
  {
    key: 'batch-edit',
    name: 'Batch Edit',
    desc: 'Search & bulk rename, tag folders',
    path: '/manga-viewer/batch/edit',
    icon: `<svg viewBox="0 0 80 80" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect width="80" height="80" rx="20" fill="#ecf5ff"/>
      <rect x="16" y="22" width="48" height="8" rx="4" fill="#409eff"/>
      <rect x="16" y="36" width="36" height="8" rx="4" fill="#a0cfff"/>
      <rect x="16" y="50" width="42" height="8" rx="4" fill="#a0cfff"/>
      <circle cx="60" cy="56" r="10" fill="#409eff"/>
      <path d="M56 56l3 3 5-5" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>`,
  },
  {
    key: 'read-queue',
    name: 'Read Queue',
    desc: 'Folders saved for later reading',
    path: '/manga-viewer/read-queue',
    icon: `<svg viewBox="0 0 80 80" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect width="80" height="80" rx="20" fill="#f0f9eb"/>
      <path d="M24 20h32a4 4 0 014 4v32l-8-6-8 6-8-6-8 6V24a4 4 0 014-4z" fill="#67c23a"/>
      <rect x="30" y="30" width="20" height="3" rx="1.5" fill="white" opacity=".85"/>
      <rect x="30" y="37" width="14" height="3" rx="1.5" fill="white" opacity=".6"/>
    </svg>`,
  },
  {
    key: 'snooze-queue',
    name: 'Snooze Queue',
    desc: 'Hidden from random for 1 week',
    path: '/manga-viewer/snooze-queue',
    icon: `<svg viewBox="0 0 80 80" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect width="80" height="80" rx="20" fill="#fdf6ec"/>
      <circle cx="40" cy="40" r="20" fill="#e6a23c"/>
      <path d="M40 28v12l7 7" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M28 18l4 4M52 18l-4 4" stroke="#e6a23c" stroke-width="2.5" stroke-linecap="round"/>
    </svg>`,
  },
  {
    key: 'settings',
    name: 'Settings',
    desc: 'Categories, paths, display options',
    path: '/manga-viewer/settings',
    icon: `<svg viewBox="0 0 80 80" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect width="80" height="80" rx="20" fill="#f4f4f5"/>
      <circle cx="40" cy="40" r="10" fill="#909399"/>
      <path d="M40 20v6M40 54v6M20 40h6M54 40h6M25.86 25.86l4.24 4.24M49.9 49.9l4.24 4.24M54.14 25.86l-4.24 4.24M30.1 49.9l-4.24 4.24" stroke="#909399" stroke-width="3" stroke-linecap="round"/>
    </svg>`,
  },
  {
    key: 'manga-classifier',
    name: 'Manga Classifier',
    desc: 'Classify & move manga folders',
    path: '/manga-classifier',
    icon: `<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
      <rect x="4" y="4" width="56" height="56" rx="14" fill="#6366f1"/>
      <rect x="15" y="16" width="14" height="20" rx="2" fill="#fff"/>
      <rect x="35" y="16" width="14" height="20" rx="2" fill="#c7d2fe"/>
      <path d="M18 44h28" stroke="#fff" stroke-width="3" stroke-linecap="round"/>
      <path d="M22 50h20" stroke="#c7d2fe" stroke-width="3" stroke-linecap="round"/>
    </svg>`,
  },
  {
    key: 'unzip',
    name: 'Unzip',
    desc: 'Extract archive files',
    path: '/unzip',
    icon: `<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
      <rect x="4" y="4" width="56" height="56" rx="14" fill="#8b5cf6"/>
      <path d="M16 28l16-8 16 8v18l-16 8-16-8z" fill="#fff"/>
      <path d="M16 28l16 8 16-8M32 36v18" stroke="#8b5cf6" stroke-width="2" fill="none"/>
      <path d="M28 16h8v8h-8z" fill="#ddd6fe"/>
    </svg>`,
  },
  {
    key: 'duplicate-finder',
    name: 'Duplicate Finder',
    desc: 'Find duplicate image files',
    path: '/duplicate-finder',
    icon: `<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
      <rect x="4" y="4" width="56" height="56" rx="14" fill="#14b8a6"/>
      <rect x="18" y="14" width="22" height="28" rx="3" fill="#99f6e4"/>
      <rect x="26" y="22" width="22" height="28" rx="3" fill="#fff"/>
    </svg>`,
  },
  {
    key: 'video-duplicate-finder',
    name: 'Video Dedup',
    desc: 'Find duplicate video files',
    path: '/video-duplicate-finder',
    icon: `<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
      <rect x="4" y="4" width="56" height="56" rx="14" fill="#db2777"/>
      <rect x="16" y="18" width="28" height="20" rx="3" fill="#fbcfe8"/>
      <rect x="24" y="26" width="26" height="20" rx="3" fill="#fff"/>
      <path d="M34 32l8 5-8 5z" fill="#db2777"/>
    </svg>`,
  },
]
</script>

<style scoped>
.mv-hub { min-height: 100vh; padding: 32px; box-sizing: border-box; }
.mv-header { display: flex; align-items: center; gap: 16px; margin-bottom: 32px; }
.mv-title { margin: 0; font-size: 22px; font-weight: 600; }
.mv-grid { display: flex; flex-wrap: wrap; gap: 24px; }
.mv-cell {
  width: 200px;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 10px; cursor: pointer; border-radius: 20px; padding: 24px 16px;
  border: 1px solid #ebeef5;
  background: #fff;
  box-shadow: 0 2px 8px rgba(0,0,0,0.05);
  transition: transform 0.15s, box-shadow 0.15s;
}
.mv-cell:hover { transform: translateY(-3px); box-shadow: 0 6px 18px rgba(0,0,0,0.1); }
.mv-icon { width: 80px; height: 80px; pointer-events: none; }
.mv-icon :deep(svg) { width: 100%; height: 100%; display: block; }
.mv-name { font-size: 15px; font-weight: 600; color: #303133; text-align: center; pointer-events: none; }
.mv-desc { font-size: 12px; color: #909399; text-align: center; pointer-events: none; line-height: 1.4; }
</style>
