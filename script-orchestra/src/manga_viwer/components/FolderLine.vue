<template>
  <div class="folder-line" :class="{ 'marked-for-deletion': isMarkedForDeletion }">
    <!-- Left -->
    <div class="line-left">
      <!-- Name row -->
      <div class="name-row">
        <div v-if="editingNameId === folder.id" class="edit-inline">
          <el-input :ref="setActiveInput" v-model="localEditName" size="small"
            @keyup.enter="commitName" @blur="commitName" />
        </div>
        <div v-else class="name-cell" :title="folder.name">{{ folder.name }}</div>

        <div class="delete-icon-wrapper">
          <el-button :icon="EditPen" circle size="small" type="default"
            @click.stop="$emit('start-edit', folder)" title="Edit name" />
          <el-button :icon="folder.favorite ? StarFilled : Star" circle size="small"
            :type="folder.favorite ? 'warning' : 'default'"
            @click.stop="$emit('toggle-favorite', folder)"
            :title="folder.favorite ? 'Unfavorite' : 'Favorite'" />
          <el-button :icon="FolderIcon" circle size="small" type="default"
            @click.stop="$emit('open-folder', folder.id)" title="Open Folder" />
          <el-button v-if="!isMarkedForDeletion" :icon="Delete" circle size="small" type="danger"
            @click.stop="$emit('mark-delete', folder.id)" title="Mark for deletion" />
          <el-button v-else :icon="RefreshLeft" circle size="small" type="info"
            @click.stop="$emit('unmark-delete', folder.id)" title="Unmark deletion" />
        </div>
      </div>

      <!-- Tags row -->
      <div class="tags-row">
        <div class="tags-group">
          <span class="label">Size:</span>
          <span class="label">{{ Math.round(folder.size / 1024 / 1024) }} MB</span>
        </div>
        <div class="tags-group">
          <span class="label">Number:</span>
          <span class="label">{{ folder.number }}</span>
        </div>
        <div class="tags-group">
          <span class="label">Read:</span>
          <span class="label read-count" :class="{ zero: !(folder.read_count) }">{{ folder.read_count ?? 0 }}</span>
          <el-button v-if="(folder.read_count ?? 0) > 0" size="small" text class="reset-read-btn"
            title="Reset read count to 0" @click.stop="$emit('reset-read-count', folder)">↺</el-button>
        </div>

        <div class="tags-group">
          <span class="label">Mosaic:</span>
          <el-radio-group v-model="folder.tags.mosaic" @change="$emit('commit-edit', 'mosaic', folder)">
            <el-radio size="small" label="None">None</el-radio>
            <el-radio size="small" label="Light">Light</el-radio>
            <el-radio size="small" label="Heavy">Heavy</el-radio>
          </el-radio-group>
        </div>

        <div class="tags-group">
          <span class="label">Category Main:</span>
          <el-radio-group v-model="folder.tags.category_main" @change="$emit('commit-edit', 'category_main', folder)">
            <el-radio v-for="c in mainCategories" :key="c.key" size="small" :label="c.key">{{ c.key }}</el-radio>
          </el-radio-group>
        </div>

        <div class="tags-group">
          <span class="label">Category Sub:</span>
          <el-radio-group v-model="folder.tags.category_sub" @change="$emit('commit-edit', 'category_sub', folder)">
            <el-radio v-for="c in subCategories" :key="c.key" size="small" :label="c.key">{{ c.key }}</el-radio>
          </el-radio-group>
        </div>

        <div class="tags-group">
          <span class="label">Custom:</span>
          <el-tag type="warning" v-for="(t, i) in folder.tags.custom" :key="folder.id + 'custom' + i"
            closable @close="$emit('remove-tag', folder, 'custom', i)">{{ t }}</el-tag>
          <el-input v-if="tagInputVisible" :ref="setTagInputRef" v-model="tagInputValue"
            size="small" class="tag-input"
            @keyup.enter="confirmTag" @blur="confirmTag" />
          <span v-else class="tag placeholder" @click="showTagInput">+</span>
        </div>
      </div>

      <!-- Floating queue buttons -->
      <div class="line-left-actions">
        <template v-if="isInReadQueue || removeLabel">
          <button class="ql-btn ql-remove" :title="removeLabel || 'Remove from read queue'"
            @click.stop="$emit('remove-from-queue', folder.id)">🗑 Remove</button>
        </template>
        <template v-else>
          <button class="ql-btn ql-save"
            title="Save for later"
            @click.stop="$emit('save-for-later', folder.id)">🔖</button>
          <button class="ql-btn ql-snooze" :class="{ active: isInSnoozeQueue }"
            :title="isInSnoozeQueue ? 'Already snoozed' : 'Snooze for 1 week'"
            @click.stop="$emit('snooze', folder.id)">💤</button>
        </template>
      </div>
    </div>

    <!-- Preview (right) -->
    <div class="line-right" @click="openModal">
      <div v-if="previewList.length" class="thumbs">
        <div v-for="(img, i) in previewList" :key="img + i" class="thumb" :title="img">
          <img v-if="getPreviewSrc(img)" :src="getPreviewSrc(img)" />
        </div>
      </div>
      <div v-else class="no-thumb">No preview</div>
    </div>

    <!-- Reader modal (self-contained) -->
    <el-dialog v-model="dialogVisible" :show-close="false" :close-on-click-modal="true"
      :close-on-press-escape="false" width="800px" :title="folder.name" destroy-on-close
      class="manga-center-dialog" top="0vh">
      <div class="dialog-body">
        <template v-for="(p, i) in folder.files" :key="p + i">
          <div v-if="isImage(p)" class="media-item"><img :src="p" :alt="p" /></div>
          <div v-else-if="isPdf(p)" v-for="(pageUrl, pageIdx) in pdfPages[p]"
            :key="p + '-page-' + pageIdx" class="media-item">
            <img :src="pageUrl" :alt="`${p} - Page ${pageIdx + 1}`" />
          </div>
          <div v-else-if="isVideo(p)" class="media-item">
            <video :src="p" controls preload="metadata"></video>
          </div>
          <div v-else class="media-item"><div class="unknown">{{ p }}</div></div>
        </template>
      </div>
    </el-dialog>
  </div>
</template>

<script lang="ts" setup>
import { ref, computed, nextTick, watch, onMounted } from 'vue'
import { ElInput, ElTag, ElRadio, ElRadioGroup, ElButton, ElDialog, ElMessage } from 'element-plus'
import { Delete, RefreshLeft, Folder as FolderIcon, EditPen, Star, StarFilled } from '@element-plus/icons-vue'
import * as pdfjsLib from 'pdfjs-dist'
import pdfjsWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import { fetchFileList, incReadCount } from '@/manga_viwer/service/Service'
import type { FolderModel } from '@/manga_viwer/service/Model'

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfjsWorker

// ── Props & emits ──────────────────────────────────────────────────────────

const props = defineProps<{
  folder: FolderModel
  editingNameId?: string | null
  editValue?: { name: string }
  mainCategories?: { key: string }[]
  subCategories?: { key: string }[]
  isMarkedForDeletion?: boolean
  isInReadQueue?: boolean
  isInSnoozeQueue?: boolean
  removeLabel?: string
}>()

const emit = defineEmits<{
  'start-edit': [folder: FolderModel]
  'commit-edit': [field: string, folder: FolderModel]
  'toggle-favorite': [folder: FolderModel]
  'open-folder': [folderId: string]
  'mark-delete': [folderId: string]
  'unmark-delete': [folderId: string]
  'reset-read-count': [folder: FolderModel]
  'show-tag-input': [folder: FolderModel, group: string]
  'confirm-tag': [folder: FolderModel, group: string]
  'remove-tag': [folder: FolderModel, group: string, index: number]
  'save-for-later': [folderId: string]
  'snooze': [folderId: string]
  'remove-from-queue': [folderId: string]
}>()

// ── Name editing (local mirror of parent's editValue) ──────────────────────

const localEditName = ref(props.editValue?.name ?? '')
watch(() => props.editValue?.name, (v) => { if (v != null) localEditName.value = v })

function commitName() {
  emit('commit-edit', 'name', { ...props.folder, name: localEditName.value })
}

const activeInputEl = ref<any>(null)
function setActiveInput(el: any) {
  activeInputEl.value = el
  if (!el) return
  nextTick(() => {
    if (typeof el.focus === 'function') { el.focus(); return }
    const root = el.$el as HTMLElement | null
    root?.querySelector<HTMLInputElement>('input')?.focus()
  })
}

// ── Tag input (local, per-component) ──────────────────────────────────────

const tagInputVisible = ref(false)
const tagInputValue = ref('')
const tagInputElRef = ref<any>(null)

function setTagInputRef(el: any) {
  tagInputElRef.value = el
  if (el) nextTick(() => {
    if (typeof el.focus === 'function') { el.focus(); return }
    const root = el.$el as HTMLElement | null
    root?.querySelector<HTMLInputElement>('input')?.focus()
  })
}

function showTagInput() {
  tagInputVisible.value = true
  tagInputValue.value = ''
}

function confirmTag() {
  const v = tagInputValue.value.trim()
  tagInputVisible.value = false
  tagInputValue.value = ''
  if (!v) return
  if (!props.folder.tags.custom.includes(v)) {
    props.folder.tags.custom.push(v)
    emit('confirm-tag', props.folder, 'custom')
  }
}

// ── Media helpers ──────────────────────────────────────────────────────────

function isImage(p: string) { return /\.(jpe?g|png|gif|webp|bmp|tiff)$/i.test(p) }
function isVideo(p: string) { return /\.(mp4|webm|mov|mkv|avi|flv)$/i.test(p) }
function isPdf(p: string) { return /\.pdf$/i.test(p) }

const pdfFirstPages = ref<Record<string, string>>({})
const pdfPages = ref<Record<string, string[]>>({})
const videoFirstFrames = ref<Record<string, string>>({})

const previewList = computed<string[]>(() => {
  const exts = ['jpg','jpeg','png','gif','webp','bmp','mp4','webm','mov','mkv','avi','flv','pdf']
  return (props.folder.files || [])
    .filter(p => exts.includes(p.split('.').pop()?.toLowerCase() || ''))
    .slice(0, 3)
})

function getPreviewSrc(url: string): string {
  if (isPdf(url)) return pdfFirstPages.value[url] || ''
  if (isVideo(url)) return videoFirstFrames.value[url] || ''
  return url
}

async function renderVideoFirstFrame(videoUrl: string) {
  if (videoFirstFrames.value[videoUrl]) return
  return new Promise<void>((resolve) => {
    const video = document.createElement('video')
    video.crossOrigin = 'anonymous'
    video.muted = true
    video.preload = 'metadata'
    video.src = videoUrl
    let done = false
    const finish = (dataUrl: string) => {
      if (done) return
      done = true
      if (dataUrl) videoFirstFrames.value[videoUrl] = dataUrl
      video.src = ''
      resolve()
    }
    const capture = () => {
      try {
        const canvas = document.createElement('canvas')
        canvas.width = video.videoWidth || 320
        canvas.height = video.videoHeight || 180
        const ctx = canvas.getContext('2d')
        if (!ctx) { finish(''); return }
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
        finish(canvas.toDataURL('image/jpeg', 0.7))
      } catch { finish('') }
    }
    video.addEventListener('loadeddata', () => {
      try { video.currentTime = Math.min(0.1, (video.duration || 1) / 2) } catch { capture() }
    })
    video.addEventListener('seeked', capture)
    video.addEventListener('error', () => finish(''))
    setTimeout(() => finish(''), 5000)
  })
}

async function renderPdfFirstPage(pdfUrl: string) {
  if (pdfFirstPages.value[pdfUrl]) return
  try {
    const pdf = await pdfjsLib.getDocument(pdfUrl).promise
    const page = await pdf.getPage(1)
    const vp = page.getViewport({ scale: 1.5 })
    const canvas = document.createElement('canvas')
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    canvas.height = vp.height
    canvas.width = vp.width
    await page.render({ canvas, canvasContext: ctx, viewport: vp }).promise
    pdfFirstPages.value[pdfUrl] = canvas.toDataURL()
  } catch {}
}

async function renderPdfAllPages(pdfUrl: string) {
  if (pdfPages.value[pdfUrl]) return
  try {
    const pdf = await pdfjsLib.getDocument(pdfUrl).promise
    const pages: string[] = []
    for (let n = 1; n <= pdf.numPages; n++) {
      const page = await pdf.getPage(n)
      const vp = page.getViewport({ scale: 1.5 })
      const canvas = document.createElement('canvas')
      const ctx = canvas.getContext('2d')
      if (!ctx) continue
      canvas.height = vp.height
      canvas.width = vp.width
      await page.render({ canvas, canvasContext: ctx, viewport: vp }).promise
      pages.push(canvas.toDataURL())
    }
    pdfPages.value[pdfUrl] = pages
  } catch {}
}

// Auto-load files if the folder arrives without them (e.g. from read-queue API)
onMounted(async () => {
  if (!props.folder.files || props.folder.files.length === 0) {
    try {
      props.folder.files = await fetchFileList(props.folder.id)
    } catch {}
  }
})

// Render previews for initial display
watch(previewList, async (list) => {
  for (const url of list) {
    if (isPdf(url)) await renderPdfFirstPage(url)
    if (isVideo(url)) await renderVideoFirstFrame(url)
  }
}, { immediate: true })

// ── Modal (self-contained) ─────────────────────────────────────────────────

const dialogVisible = ref(false)

async function openModal() {
  // Ensure files are loaded
  if (!props.folder.files || props.folder.files.length === 0) {
    try {
      const files = await fetchFileList(props.folder.id)
      props.folder.files = files
    } catch {}
  }
  // Bump read count
  props.folder.read_count = (props.folder.read_count ?? 0) + 1
  incReadCount(props.folder.id).catch(() => {})
  dialogVisible.value = true
  // Render PDFs for reader
  nextTick(async () => {
    for (const p of (props.folder.files || [])) {
      if (isPdf(p)) await renderPdfAllPages(p)
    }
  })
}
</script>

<style scoped>
.folder-line {
  display: flex;
  flex-direction: row;
  gap: 18px;
  border: 1px solid #e3e7ec;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 2px 6px -2px rgba(40, 48, 63, .12);
}
.folder-line.marked-for-deletion {
  border: 2px solid #f56c6c;
  background: #fef0f0;
  opacity: 0.8;
}
.folder-line:hover { box-shadow: 0 4px 14px -4px rgba(40, 48, 63, .22); }

.line-left {
  position: relative;
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 15px;
}
.line-right {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  min-width: 0;
  margin-right: 15px;
}

.name-row { display: flex; align-items: center; gap: 10px; }
.name-cell {
  flex: 1; min-width: 0;
  font-size: 15px; font-weight: 600; color: #313c4c;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  padding-right: 12px;
}
.edit-inline { flex: 1; min-width: 0; }
.edit-inline :deep(.el-input) { width: 100%; }
.delete-icon-wrapper { flex-shrink: 0; }

.tags-row { display: flex; flex-direction: column; gap: 8px; }
.tags-group { display: flex; align-items: center; gap: 6px; }
.label { font-size: 11px; font-weight: 600; color: #66717d; }
.tag {
  font-size: 11px; padding: 3px 8px 4px;
  background: #f0f4f8; border: 1px solid #d9e1e8;
  border-radius: 16px; color: #3f4c5a; line-height: 1.3;
}
.tag.placeholder {
  font-size: 10px; font-weight: 600; padding: 2px 6px 3px;
  line-height: 1; min-width: 22px; text-align: center;
  cursor: pointer; background: #f7f9fb; border: 1px dashed #cfd6dd; color: #54606c;
}
.tag.placeholder:hover { background: #eef3f6; border-color: #b6c1c9; }

.thumbs {
  display: flex; flex-direction: row; gap: 12px;
  align-items: center; height: 250px; max-width: 520px;
}
.thumb {
  height: 250px; width: auto; max-width: 160px; flex: 0 0 auto;
  border: 1px solid #d9e1e8; border-radius: 10px; overflow: hidden;
  background: #fafbfc; display: flex; align-items: center; justify-content: center;
}
.thumb img {
  max-height: 250px; max-width: 100%; width: auto; height: auto;
  object-fit: contain; display: block;
}
.no-thumb {
  font-size: 11px; color: #7d8590; padding: 6px 10px;
  background: #f5f7fa; border: 1px dashed #d3d9df; border-radius: 8px;
}

.read-count { font-weight: 600; color: #67C23A; }
.read-count.zero { color: #909399; font-weight: 400; }
.reset-read-btn {
  margin-left: 4px; padding: 0 4px; min-height: unset;
  height: 20px; font-size: 14px; color: #909399;
}
.reset-read-btn:hover { color: #F56C6C; }

/* Queue floating buttons */
.line-left-actions {
  display: none; position: absolute; bottom: 10px; right: 10px;
  flex-direction: row; gap: 6px; z-index: 10;
}
.folder-line:hover .line-left-actions { display: flex; }
.ql-btn {
  border: none; border-radius: 8px; padding: 5px 10px; font-size: 15px;
  cursor: pointer; background: rgba(255,255,255,0.88);
  box-shadow: 0 1px 6px rgba(0,0,0,0.14);
  transition: background 0.15s, transform 0.1s, opacity 0.15s;
  opacity: 0.75; line-height: 1;
}
.ql-btn:hover { opacity: 1; transform: translateY(-1px); background: #fff; }
.ql-btn.active { opacity: 1; background: #ecf5ff; box-shadow: 0 1px 6px rgba(64,158,255,0.25); }
.ql-remove { background: rgba(255, 240, 240, 0.92); color: #c0392b; font-size: 13px; }
.ql-remove:hover { background: #fef0f0; color: #c0392b; }

/* Dialog */
.manga-center-dialog { padding: 0; }
.dialog-body {
  flex: 1; overflow-y: auto; display: flex; flex-direction: column; scrollbar-width: thin;
}
.dialog-body::-webkit-scrollbar { width: 8px; }
.dialog-body::-webkit-scrollbar-track { background: #f1f3f5; border-radius: 4px; }
.dialog-body::-webkit-scrollbar-thumb { background: #bfc6cc; border-radius: 4px; }
.dialog-body::-webkit-scrollbar-thumb:hover { background: #a5adb4; }
.media-item {
  width: 100%; max-width: 100%; display: flex; justify-content: center;
  align-items: center; overflow: visible; position: relative; min-height: 120px;
}
.media-item img, .media-item video {
  width: 100%; height: auto; object-fit: contain; display: block;
}
.media-item img { height: auto !important; }
.media-item .unknown {
  font-size: 11px; color: #666; text-align: center; padding: 4px; word-break: break-all;
}
</style>
