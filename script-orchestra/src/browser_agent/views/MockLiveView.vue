<template>
  <div class="mock-root">
    <!-- Toolbar -->
    <div class="mock-toolbar">
      <el-button size="small" @click="openCreateGroup()">+ Group</el-button>
      <el-button size="small" @click="addTab(-1)">+ Tab Win1</el-button>
      <el-button size="small" @click="addTab(-2)">+ Tab Win2</el-button>
      <el-button size="small" type="warning" @click="resetAll">Reset</el-button>
      <span class="mock-badge">Mock data — no backend calls</span>
    </div>

    <!-- Table -->
    <div class="table-wrap mock-table-wrap" v-if="renderList.some(w => w.tabCount > 0 || w.items.some(i => i.kind === 'group'))">
      <template v-for="win in renderList" :key="win.windowId">
        <div class="window-header-row">
          <span class="window-header-label">Window {{ win.windowId }} &middot; {{ win.tabCount }} tabs</span>
        </div>

        <template v-for="item in win.items" :key="item.dragKey">
          <!-- GROUP ROW -->
          <div
            v-if="item.kind === 'group' && item.ancestorIds.every(id => !collapsedGroups.has(id))"
            class="group-header-row"
            :class="{ 'dnd-drop-into': dndIndicator?.key === item.dragKey && dndIndicator.edge === 'into' }"
            :style="{ paddingLeft: item.depth * 16 + 'px' }"
            v-pdnd-live-row="{
              drag: { type: 'live-group', id: item.group.id },
              dropKey: item.dragKey,
              isGroup: true
            }"
            @click="toggleGroupCollapse(item.group.id)"
          >
            <div v-if="dndIndicator?.key === item.dragKey && dndIndicator.edge === 'top'" class="drop-line drop-line-top" />
            <div v-if="dndIndicator?.key === item.dragKey && dndIndicator.edge === 'bottom'" class="drop-line drop-line-bottom" />
            <span class="group-collapse-icon">{{ collapsedGroups.has(item.group.id) ? '&#9654;' : '&#9660;' }}</span>
            <span class="group-header-name">{{ item.group.name }}</span>
            <span class="group-header-count">{{ item.tabCount }}</span>
            <el-button size="small" text @click.stop="openCollect(item.group, win.windowId)">Collect</el-button>
            <el-button size="small" text @click.stop="openEditGroup(item.group)">Edit</el-button>
            <el-button size="small" text @click.stop="openCreateGroup(item.group.id)">+ Sub</el-button>
            <el-button size="small" text type="danger" @click.stop="deleteGroup(item.group)">Del</el-button>
          </div>

          <!-- TAB ROW -->
          <div
            v-else-if="item.kind === 'tab' && item.ancestorIds.every(id => !collapsedGroups.has(id))"
            class="table-row"
            :class="{
              'row-in-group': item.card.group_id !== null,
              'dnd-drop-into': dndIndicator?.key === item.dragKey && dndIndicator.edge === 'into'
            }"
            :style="{ paddingLeft: item.depth * 16 + 'px' }"
            v-pdnd-live-row="{
              drag: { type: 'live-tab', tabId: item.card.tab_id, groupId: item.card.group_id, windowId: item.card.window_id },
              dropKey: item.dragKey,
              isGroup: false
            }"
          >
            <div v-if="dndIndicator?.key === item.dragKey && dndIndicator.edge === 'top'" class="drop-line drop-line-top" />
            <div v-if="dndIndicator?.key === item.dragKey && dndIndicator.edge === 'bottom'" class="drop-line drop-line-bottom" />
            <span class="drag-handle">&#8942;</span>
            <span class="fav-slot">
              <img v-if="item.card.favicon_url" :src="item.card.favicon_url" class="fav" @error="hideFavicon" />
            </span>
            <!-- Title cell: click to edit custom_header -->
            <div class="title-cell" @click.stop="startEditHeader(item.card)">
              <template v-if="editingHeaderTabId === item.card.tab_id">
                <el-input
                  v-model="editingHeaderValue"
                  size="small"
                  :placeholder="item.card.title || '(no title)'"
                  autofocus
                  @click.stop
                  @keydown.enter.prevent="!$event.isComposing && saveCustomHeader(item.card)"
                  @keydown.esc.prevent="cancelEditHeader()"
                  @blur="saveCustomHeader(item.card)"
                />
              </template>
              <template v-else>
                <span class="title-line" :title="item.card.custom_header || item.card.title">
                  {{ item.card.custom_header || item.card.title || '(no title)' }}
                </span>
                <span class="meta-line">{{ item.card.domain || '-' }}</span>
              </template>
            </div>
            <span class="heat-cell">
              <el-tag :type="heatTagType(item.card.heat_level)" size="small">{{ item.card.heat_level }}</el-tag>
            </span>
            <span class="actions-cell">
              <el-popover trigger="click" placement="left" width="420">
                <template #reference><el-button size="small" text>Details</el-button></template>
                <div class="detail-grid">
                  <div><b>Title</b></div><div>{{ item.card.title || '-' }}</div>
                  <div><b>Custom header</b></div><div>{{ item.card.custom_header || '-' }}</div>
                  <div><b>Domain</b></div><div>{{ item.card.domain || '-' }}</div>
                  <div><b>URL</b></div><div class="mono">{{ item.card.url }}</div>
                  <div><b>Window</b></div><div>{{ item.card.window_id }}</div>
                  <div><b>Group</b></div><div>{{ item.card.group_id ?? '-' }}</div>
                </div>
              </el-popover>
              <el-button size="small" text type="danger" @click.stop="closeTab(item.card.tab_id)">Close</el-button>
            </span>
          </div>
        </template>
      </template>
    </div>
    <el-empty v-else description="No mock data — click Reset to restore" />

    <!-- Action log -->
    <div class="action-log">
      <div class="action-log-title">Action log</div>
      <div v-for="(entry, i) in actionLog" :key="i" class="action-log-entry">{{ entry }}</div>
      <div v-if="actionLog.length === 0" class="action-log-empty">No actions yet — drag, collect, create groups…</div>
    </div>

    <!-- Dialogs -->
    <el-dialog v-model="createGroupVisible" title="Create group" width="400px" @close="cancelCreateGroup">
      <el-form label-width="70px">
        <el-form-item label="Name">
          <el-input
            v-model="createGroupName"
            placeholder="e.g. Work, Research"
            autofocus
            @keydown.enter="!$event.isComposing && createGroupName.trim() && confirmCreateGroup()"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="cancelCreateGroup">Cancel</el-button>
        <el-button type="primary" :disabled="!createGroupName.trim()" @click="confirmCreateGroup">Create</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="editGroupVisible" title="Edit group" width="400px">
      <el-form label-width="70px">
        <el-form-item label="Name">
          <el-input
            v-model="editGroupName"
            autofocus
            @keydown.enter="!$event.isComposing && editGroupName.trim() && confirmEditGroup()"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editGroupVisible = false">Cancel</el-button>
        <el-button type="primary" :disabled="!editGroupName.trim()" @click="confirmEditGroup">Save</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="collectVisible" :title="`Collect into &quot;${collectGroupName}&quot;`" width="480px">
      <el-input
        v-model="collectQuery"
        placeholder="Domain or keyword, e.g. google"
        clearable
        autofocus
        @keydown.enter="!$event.isComposing && collectMatches.length ? runCollect() : undefined"
      />
      <div class="collect-preview">
        <div v-if="!collectQuery.trim()" class="collect-hint">Type a keyword to preview matching ungrouped tabs.</div>
        <div v-else-if="collectMatches.length === 0" class="collect-hint">No ungrouped tabs match.</div>
        <div v-else class="collect-list">
          <div v-for="t in collectMatches" :key="t.tab_id" class="collect-item">
            <img v-if="t.favicon_url" :src="t.favicon_url" class="collect-favicon" @error="hideFavicon" />
            <span class="collect-title">{{ t.title || t.url }}</span>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="collectVisible = false">Cancel</el-button>
        <el-button type="primary" :disabled="collectMatches.length === 0" @click="runCollect">
          Collect {{ collectMatches.length }} tab{{ collectMatches.length !== 1 ? 's' : '' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script lang="ts" src="@/browser_agent/views/MockLiveView.ts"></script>

<style scoped>
.mock-root {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.mock-toolbar {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.mock-badge {
  font-size: 11px;
  color: #7c3aed;
  background: #ede9fe;
  border-radius: 10px;
  padding: 2px 10px;
  font-weight: 600;
  letter-spacing: 0.02em;
  margin-left: 4px;
}
.table-wrap {
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  overflow: hidden;
}
.mock-table-wrap .table-row {
  display: grid;
  grid-template-columns: 20px 24px minmax(220px, 1.4fr) 120px 150px;
  gap: 8px;
  align-items: center;
  padding: 8px 12px;
  border-top: 1px solid #f1f5f9;
  position: relative;
}
.mock-table-wrap .table-row:first-child { border-top: none; }
.selected { background: #f0f9ff; }
.fav-slot {
  width: 16px; height: 16px; border-radius: 3px;
  background: #cbd5e1; overflow: hidden;
}
.fav { display: block; width: 16px; height: 16px; border-radius: 3px; }
.title-cell { display: flex; flex-direction: column; min-width: 0; }
.title-line {
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  color: #0f172a; font-size: 13px;
}
.meta-line {
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  color: #64748b; font-size: 12px;
}
.heat-cell { display: flex; gap: 4px; align-items: center; }
.actions-cell { display: flex; gap: 6px; justify-content: flex-end; }
.drag-handle {
  cursor: grab; color: #94a3b8; font-size: 14px;
  padding: 0 2px; flex-shrink: 0; user-select: none;
}
.drag-handle:active { cursor: grabbing; }
.window-header-row {
  display: flex; align-items: center; gap: 8px;
  padding: 5px 10px; background: #e0f2fe;
  font-weight: 600; font-size: 12px; color: #0c4a6e;
}
.window-header-label { flex: 1; }
.group-header-row {
  padding: 5px 10px;
  background: #eff6ff;
  border-left: 3px solid #3b82f6;
  font-weight: 600; font-size: 12px; color: #1d4ed8;
  display: flex; align-items: center; gap: 6px;
  cursor: pointer; user-select: none; position: relative;
}
.group-header-row:hover { background: #dbeafe; }
.group-collapse-icon { font-size: 9px; width: 12px; flex-shrink: 0; }
.group-header-name { flex: 1; }
.group-header-count {
  font-size: 11px; font-weight: 400; color: #64748b;
  background: #e2e8f0; border-radius: 10px; padding: 1px 7px;
}
.row-in-group { border-left: 2px solid #bfdbfe; }
.dnd-drop-into {
  background: #dbeafe !important;
  outline: 2px dashed #3b82f6;
  outline-offset: -1px;
}
.drop-line {
  position: absolute; left: 0; right: 0; height: 2px;
  background: #3b82f6; pointer-events: none; z-index: 10;
}
.drop-line-top { top: 0; }
.drop-line-bottom { bottom: 0; }
/* DnD edge visual feedback */
.group-header-row[data-edge="top"],
.table-row[data-edge="top"] { border-top: 2px solid #3b82f6; background: #f0f9ff !important; }
.group-header-row[data-edge="bottom"],
.table-row[data-edge="bottom"] { border-bottom: 2px solid #3b82f6; background: #f0f9ff !important; }
.group-header-row[data-drop-over],
.table-row[data-drop-over] {
  background: #dbeafe !important;
  outline: 2px dashed #3b82f6; outline-offset: -1px;
}
[data-dragging] { opacity: 0.45; }
/* Details popover */
.detail-grid {
  display: grid; grid-template-columns: 100px 1fr;
  gap: 5px 8px; font-size: 13px;
}
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; word-break: break-all; }
/* Collect dialog */
.collect-preview { margin-top: 12px; max-height: 260px; overflow-y: auto; }
.collect-hint { color: #94a3b8; font-size: 13px; padding: 8px 0; }
.collect-list { display: flex; flex-direction: column; gap: 4px; }
.collect-item {
  display: flex; align-items: center; gap: 8px;
  padding: 4px 6px; border-radius: 4px; background: #f8fafc; font-size: 13px;
}
.collect-favicon { width: 14px; height: 14px; flex-shrink: 0; }
.collect-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
/* Action log */
.action-log {
  border: 1px solid #e2e8f0; border-radius: 8px;
  background: #f8fafc; padding: 10px 14px;
  max-height: 200px; overflow-y: auto;
}
.action-log-title {
  font-size: 11px; font-weight: 700; color: #7c3aed;
  text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 6px;
}
.action-log-entry { font-size: 12px; color: #334155; line-height: 1.8; font-family: ui-monospace, monospace; }
.action-log-empty { font-size: 12px; color: #94a3b8; }
</style>
