<template>
  <div class="lp">
    <div class="lp-grid" @dragover.prevent @drop="onGridDrop">
      <div
        v-for="(cell, index) in cells"
        :key="cell.type === 'tool' ? cell.key : cell.id"
        class="lp-cell"
        :class="{ 'lp-over': overCell === index }"
        draggable="true"
        @dragstart="onDragStart($event, index)"
        @dragover="onDragOver($event, index)"
        @dragleave="onDragLeave(index)"
        @drop.stop="onDrop($event, index)"
        @dragend="onDragEnd">
        <!-- tool -->
        <div v-if="cell.type === 'tool'" class="lp-item"
             :data-testid="toolOf(cell.key)?.testid"
             @click="goTo(toolOf(cell.key)?.path)">
          <div class="lp-icon" v-html="toolIcons[cell.key]"></div>
          <div class="lp-name">{{ toolOf(cell.key)?.name }}</div>
        </div>
        <!-- folder -->
        <div v-else class="lp-item lp-folder-cell" @click="openFolderView(cell.id)">
          <div class="lp-folder-thumb">
            <div v-for="k in cell.keys.slice(0, 9)" :key="k" class="lp-folder-mini"
                 v-html="toolIcons[k]"></div>
          </div>
          <div class="lp-name">{{ cell.name }}</div>
        </div>
      </div>
    </div>

    <!-- Folder overlay -->
    <div v-if="openFolder" class="lp-overlay" @click.self="closeFolder">
      <div class="lp-folder-panel">
        <div class="lp-folder-head">
          <span class="lp-folder-title" @click="renameFolder(openFolder)">{{ openFolder.name }}</span>
          <span class="lp-folder-hint">click name to rename · × to move a tool out</span>
        </div>
        <div class="lp-folder-grid">
          <div v-for="k in openFolder.keys" :key="k" class="lp-cell">
            <div class="lp-item" @click="goTo(toolOf(k)?.path)">
              <div class="lp-icon" v-html="toolIcons[k]"></div>
              <div class="lp-name">{{ toolOf(k)?.name }}</div>
            </div>
            <button class="lp-folder-remove" title="Move out of folder"
                    @click.stop="removeFromFolder(openFolder, k)">×</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts" src="@/dashboard/views/OrchestraView.ts"></script>

<style scoped>
.lp { min-height: 100vh; padding: 32px 24px; box-sizing: border-box; }
.lp-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, 150px);
  gap: 28px 20px;
  justify-content: center;
  max-width: 1400px;
  margin: 0 auto;
}
.lp-cell { position: relative; border-radius: 20px; }
.lp-cell.lp-over { background: rgba(10,132,255,0.12); outline: 2px dashed rgba(10,132,255,0.5); }
.lp-item {
  width: 150px; height: 150px;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 12px; cursor: pointer; border-radius: 20px;
  transition: transform 0.15s, background 0.15s;
}
.lp-item:hover { transform: translateY(-2px); background: rgba(0,0,0,0.03); }
.lp-icon { width: 72px; height: 72px; pointer-events: none; }
.lp-icon :deep(svg) { width: 100%; height: 100%; display: block; }
.lp-name { font-size: 13px; font-weight: 600; color: #303133; text-align: center;
  max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  pointer-events: none; }
.lp-folder-cell .lp-folder-thumb {
  width: 72px; height: 72px; border-radius: 18px;
  background: rgba(120,120,128,0.16);
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 3px; padding: 8px; box-sizing: border-box;
  pointer-events: none;
}
.lp-folder-mini { width: 100%; height: 100%; overflow: hidden; }
.lp-folder-mini :deep(svg) { width: 100%; height: 100%; display: block; }

.lp-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.35);
  backdrop-filter: blur(8px); display: flex; align-items: center; justify-content: center; z-index: 2000; }
.lp-folder-panel { background: rgba(255,255,255,0.92); border-radius: 20px; padding: 24px 28px;
  min-width: 520px; max-width: 80vw; max-height: 80vh; overflow: auto;
  box-shadow: 0 20px 60px rgba(0,0,0,0.25); }
.lp-folder-head { display: flex; align-items: baseline; gap: 12px; margin-bottom: 18px; }
.lp-folder-title { font-size: 20px; font-weight: 700; cursor: text; }
.lp-folder-title:hover { text-decoration: underline dotted; }
.lp-folder-hint { font-size: 12px; color: #86868b; }
.lp-folder-grid { display: grid; grid-template-columns: repeat(auto-fill, 150px); gap: 20px; }
.lp-folder-remove {
  position: absolute; top: 4px; right: 4px; width: 20px; height: 20px; border: none;
  border-radius: 50%; background: rgba(0,0,0,0.45); color: #fff; cursor: pointer;
  font-size: 14px; line-height: 20px; opacity: 0; transition: opacity 0.15s; }
.lp-cell:hover .lp-folder-remove { opacity: 1; }
</style>
