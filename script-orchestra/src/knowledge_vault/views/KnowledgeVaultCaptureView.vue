<template>
  <div class="kv">
    <!-- top bar -->
    <header class="kv-topbar">
      <el-button @click="captureMode === 'organize' ? captureMode = 'fragments' : goBack()" circle size="small"><el-icon><ArrowLeft /></el-icon></el-button>
      <h1>Knowledge Vault</h1>
      <div style="flex:1" />
      <el-button v-if="captureMode === 'fragments'" text size="small" @click="captureMode = 'organize'">Organize</el-button>
      <el-button v-if="captureMode === 'fragments'" text size="small"
        :class="{ 'kv-btn-active': showArchived }" @click="toggleArchived">Archive</el-button>
      <el-button text size="small" :disabled="reindexStatus.running" @click="triggerReindex">
        <el-icon><Refresh /></el-icon>
        <span v-if="reindexStatus.running" style="margin-left:4px;font-size:12px;">{{ reindexStatus.indexed }}/{{ reindexStatus.total }}</span>
      </el-button>
      <el-button text size="small" @click="goSettings"><el-icon><Setting /></el-icon></el-button>
    </header>

    <!-- ==================== FRAGMENTS MODE ==================== -->
    <div v-if="captureMode === 'fragments'" class="kv-capture">

      <!-- left sidebar -->
      <aside class="kv-sidebar">
        <div class="kv-sidebar-head">
          <span class="kv-sidebar-title">Groups</span>
          <el-button text size="small" @click="openCreateGroup()">+ New</el-button>
        </div>
        <div class="sg-row sg-root" :class="{ 'sg-item--active': currentGroupId == null }"
          @click="currentGroupId = null">
          <el-icon class="sg-toggle"><Folder /></el-icon>
          <span class="sg-name">All</span>
        </div>
        <group-tree-node
          v-for="g in treeGroups" :key="g.id"
          :group="g" :current-group-id="currentGroupId"
          @select="currentGroupId = $event"
          @edit="openEditGroup"
          @delete="confirmDeleteGroup"
          @add-sub="openCreateGroup"
        />
      </aside>

      <!-- centre: list -->
      <main class="kv-main">
        <div class="kv-main-head">
          <div class="kv-breadcrumb">
            <span v-if="showArchived" class="kv-bc-archive">Archived</span>
            <span v-if="showArchived && currentGroup" class="kv-bc-sep">›</span>
            <span v-if="currentGroup" class="kv-bc-link" @click="currentGroupId = null">All</span>
            <span v-if="currentGroup" class="kv-bc-sep">›</span>
            <span class="kv-bc-current">{{ currentGroup?.name ?? (showArchived ? '' : 'All fragments') }}</span>
            <span v-if="currentGroup?.note" class="kv-bc-note">{{ currentGroup.note }}</span>
          </div>
          <div class="kv-main-actions">
            <div v-if="currentGroupId == null" class="kv-seg">
              <button class="kv-seg-btn" :class="{ active: viewMode === 'normal' }" @click="viewMode = 'normal'">Normal</button>
              <button class="kv-seg-btn" :class="{ active: viewMode === 'all' }" @click="viewMode = 'all'">All</button>
              <button class="kv-seg-btn" :class="{ active: viewMode === 'ungrouped' }" @click="viewMode = 'ungrouped'">Ungrouped</button>
            </div>
            <el-button v-if="currentGroup" text size="small" @click="openEditGroup(currentGroup)">Edit group</el-button>
            <el-button v-if="!showArchived" type="primary" @click="openAdd">+ Fragment</el-button>
          </div>
        </div>

        <!-- label filter: only at root level in All mode -->
        <div v-if="labels.length && currentGroupId == null && viewMode === 'all'" class="kv-label-filter">
          <span class="kv-lf-label">Filter:</span>
          <el-check-tag
            v-for="l in labels" :key="l.id"
            :checked="filterLabelIds.includes(l.id)"
            @change="filterLabelIds.includes(l.id) ? filterLabelIds.splice(filterLabelIds.indexOf(l.id), 1) : filterLabelIds.push(l.id)"
            :style="filterLabelIds.includes(l.id) ? { background: l.color, borderColor: l.color, color: '#fff' } : {}"
          >{{ l.name }}</el-check-tag>
          <el-button v-if="filterLabelIds.length" text size="small" @click="filterLabelIds = []">Clear</el-button>
        </div>

        <!-- fragment list -->
        <div class="kv-list">
          <el-empty v-if="!filteredFragments.length && !currentSubGroups.length" description="No fragments here" :image-size="60" />

          <!-- group cards (Normal view) -->
          <template v-if="viewMode === 'normal'">
            <div v-for="sg in currentSubGroups" :key="'g'+sg.id"
              class="kv-group-card" @click="currentGroupId = sg.id">
              <div class="kv-gc-left">
                <el-icon class="kv-gc-icon"><Folder /></el-icon>
                <span class="kv-gc-name">{{ sg.name }}</span>
                <span v-if="sg.note" class="kv-gc-note">{{ sg.note }}</span>
              </div>
              <div class="kv-gc-right">
                <span class="kv-gc-count">{{ groupFragmentCount(sg.id) }} items</span>
                <el-icon class="kv-gc-arrow"><ArrowRight /></el-icon>
              </div>
            </div>
          </template>

          <!-- fragment rows -->
          <div v-for="row in filteredFragments" :key="row.id"
            class="kv-row" :class="{ 'kv-row--active': selectedFrag?.id === row.id }"
            @click="openDetail(row)">
            <span class="kv-row-title">{{ fragmentSummary(row) }}</span>
            <div class="kv-row-meta">
              <el-tag size="small" effect="light"
                :type="row.freshness === 'fresh' ? 'success' : row.freshness === 'aging' ? 'warning' : 'danger'">
                {{ row.freshness === 'fresh' ? 'Fresh' : row.freshness === 'aging' ? 'Aging' : 'Outdated' }}
              </el-tag>
              <span class="kv-date">{{ fmtDate(row.created_at) }}</span>
              <el-tag v-for="lid in row.label_ids" :key="lid" size="small"
                :color="labelMap[lid]?.color" class="kv-lbl">{{ labelMap[lid]?.name }}</el-tag>
            </div>
          </div>
        </div>
      </main>

      <!-- right: detail panel -->
      <aside v-if="detailOpen && selectedFrag" class="kv-detail">
        <div class="kv-det-head">
          <div class="kv-det-title-wrap">
            <div class="kv-det-title">
              {{ selectedFrag.header || fragmentSummary(selectedFrag) }}
              <el-button text size="small" class="kv-copy-inline" @click="copyBlock(selectedFrag.header || fragmentSummary(selectedFrag))">Copy</el-button>
            </div>
          </div>
          <div class="kv-det-acts">
            <template v-if="!detailEditing">
              <template v-if="!showArchived">
                <el-button text size="small" @click="startEdit">Edit</el-button>
                <el-button text size="small" @click="openMoveToGroup(selectedFrag)">Move</el-button>
                <el-button text size="small" type="warning" @click="archiveSelected">Archive</el-button>
              </template>
              <template v-else>
                <el-button text size="small" type="primary" @click="unarchiveSelected">Restore</el-button>
                <el-button text size="small" type="danger" @click="deleteSelected">Delete</el-button>
              </template>
            </template>
            <template v-else>
              <el-button text size="small" @click="cancelEdit">Cancel</el-button>
              <el-button type="primary" size="small" @click="saveEdit">Save</el-button>
            </template>
            <el-button text size="small" @click="closeDetail">✕</el-button>
          </div>
        </div>

        <!-- VIEW mode -->
        <div v-if="!detailEditing" class="kv-det-body">
          <div v-if="selectedFrag.note" class="kv-det-note">{{ selectedFrag.note }}</div>
          <div class="kv-det-meta">
            <el-tag size="small" effect="light"
              :type="selectedFrag.freshness === 'fresh' ? 'success' : selectedFrag.freshness === 'aging' ? 'warning' : 'danger'">
              {{ selectedFrag.freshness === 'fresh' ? 'Fresh' : selectedFrag.freshness === 'aging' ? 'Aging' : 'Outdated' }}
            </el-tag>
            <span class="kv-date">{{ fmtDate(selectedFrag.created_at) }}</span>
            <el-tag v-for="lid in selectedFrag.label_ids" :key="lid" size="small"
              :color="labelMap[lid]?.color" class="kv-lbl">{{ labelMap[lid]?.name }}</el-tag>
          </div>

          <div class="kv-blocks">
            <div v-for="(blk, i) in selectedFrag.blocks" :key="i" class="kv-block">
              <div class="kv-blk-bar" :class="blk.type === 'code' ? 'kv-blk-bar--code' : blk.type === 'url' ? 'kv-blk-bar--url' : blk.type === 'long' ? 'kv-blk-bar--long' : 'kv-blk-bar--text'"
                @click="blk.type === 'long' ? toggleLong(blk) : undefined" :style="blk.type === 'long' ? 'cursor:pointer' : ''">
                <span class="kv-blk-subtitle" v-if="blk.subtitle">
                  {{ blk.subtitle }}
                  <el-button text size="small" class="kv-copy-inline" @click.stop="copyBlock(blk.subtitle)">Copy</el-button>
                </span>
                <span v-else-if="blk.type === 'long'" class="kv-blk-subtitle kv-blk-subtitle--long">Long text — click to expand</span>
                <span v-else style="flex:1" />
                <span class="kv-blk-date">{{ fmtDate(selectedFrag.created_at) }}</span>
                <el-button text size="small" @click.stop="copyBlock(blk.body)">Copy</el-button>
                <span v-if="blk.type === 'long'" class="kv-long-chevron" :class="{ expanded: expandedLongs.has(blk) }">›</span>
              </div>
              <div v-if="blk.type === 'text'" class="kv-blk-text-body kv-md" v-html="renderMd(blk.body)" />
              <pre v-else-if="blk.type === 'code'" class="kv-pre">{{ blk.body }}</pre>
              <div v-else-if="blk.type === 'url'" class="kv-url-body">
                <a :href="blk.body" target="_blank" rel="noopener" class="kv-url-link">{{ blk.body }}</a>
              </div>
              <div v-else-if="blk.type === 'long' && expandedLongs.has(blk)" class="kv-blk-text-body kv-md" v-html="renderMd(blk.body)" />
            </div>
          </div>
        </div>

        <!-- EDIT mode -->
        <div v-else class="kv-det-body kv-det-edit">
          <el-input v-model="editingHeader" placeholder="Header — one-line title (required)"
            :class="{ 'kv-input-required': editingHeader !== undefined && !editingHeader.trim() }"
            style="margin-bottom:8px" />
          <el-input v-model="editingNote" placeholder="Note (optional)" style="margin-bottom:8px" />
          <el-select v-model="editingLabelIds" multiple collapse-tags placeholder="Labels" style="width:100%; margin-bottom:12px">
            <el-option v-for="l in labels" :key="l.id" :label="l.name" :value="l.id" />
          </el-select>

          <div class="kv-blocks-edit">
            <div v-for="(blk, i) in editingBlocks" :key="i" class="kv-block-edit">
              <div class="kv-bk-toolbar">
                <div class="kv-bk-type-group">
                  <button v-for="t in ['text','code','url','long']" :key="t"
                    class="kv-bk-type-btn" :class="{ active: blk.type === t }"
                    @click="setBlockType(editingBlocks, i, t)">{{ t }}</button>
                </div>
                <el-input v-if="blk.type === 'code'" v-model="blk.lang" placeholder="lang" size="small" style="width:70px; margin-left:4px" />
                <div style="flex:1" />
                <el-button text size="small" :disabled="i === 0" @click="moveBlock(i, -1)">↑</el-button>
                <el-button text size="small" :disabled="i === editingBlocks.length - 1" @click="moveBlock(i, 1)">↓</el-button>
                <el-button text size="small" type="danger" :disabled="editingBlocks.length <= 1" @click="removeBlock(i)">✕</el-button>
              </div>
              <el-input v-model="blk.subtitle" placeholder="Subtitle (optional)" size="small" style="margin-top:4px" />
              <el-input v-model="blk.body" type="textarea"
                :autosize="{ minRows: blk.type === 'url' ? 2 : 3 }"
                :placeholder="blk.type === 'code' ? 'Code...' : blk.type === 'url' ? 'https://...' : 'Text...'"
                :class="blk.type === 'code' ? 'kv-textarea-mono' : ''"
                style="margin-top:4px" />
            </div>
            <div class="kv-add-block-bar">
              <el-button text size="small" @click="addBlock('text')">+ Text</el-button>
              <el-button text size="small" @click="addBlock('code')">+ Code</el-button>
              <el-button text size="small" @click="addBlock('url')">+ URL</el-button>
              <el-button text size="small" @click="addBlock('long')">+ Long</el-button>
            </div>
          </div>
        </div>
      </aside>
    </div>

    <!-- ==================== ORGANIZE MODE ==================== -->
    <div v-else class="kv-organize-wrap">

      <!-- left: list + toolbar -->
      <div class="kv-org-left">
        <div class="kv-org-toolbar">
          <div class="kv-org-toolbar-left">
            <el-checkbox
              :model-value="organizeSelected.size === organizeFragments.length && organizeFragments.length > 0"
              :indeterminate="organizeSelected.size > 0 && organizeSelected.size < organizeFragments.length"
              @change="organizeToggleAll"
            />
            <span class="kv-org-count">{{ organizeSelected.size > 0 ? `${organizeSelected.size} selected` : `${organizeFragments.length} fragments` }}</span>
          </div>
          <div class="kv-org-toolbar-right">
            <el-select v-model="organizeBulkGroupId" placeholder="Move to…" clearable style="width:180px">
              <el-option label="— Remove from group" :value="null" />
              <el-option v-for="opt in flatGroupOptions" :key="opt.id" :label="opt.label" :value="opt.id" />
            </el-select>
            <el-button type="primary" size="small" :loading="organizeSaving" :disabled="!organizeSelected.size" @click="organizeBulkMove">
              Move ({{ organizeSelected.size }})
            </el-button>
            <el-button type="danger" size="small" :loading="organizeSaving" :disabled="!organizeSelected.size" @click="organizeDeleteSelected">
              Delete ({{ organizeSelected.size }})
            </el-button>
          </div>
        </div>

        <el-empty v-if="!organizeFragments.length" description="No fragments" :image-size="60" style="margin-top:40px" />

        <div v-else class="kv-org-list">
          <div v-for="row in organizeFragments" :key="row.id" class="kv-org-row"
            :class="{ 'kv-org-row--selected': organizeSelected.has(row.id), 'kv-org-row--active': organizeSelectedFrag?.id === row.id }"
            @click="organizeSelectedFrag = organizeSelectedFrag?.id === row.id ? null : row">
            <el-checkbox :model-value="organizeSelected.has(row.id)" @change="organizeToggle(row.id)" @click.stop />
            <div class="kv-org-main">
              <span class="kv-org-title">{{ fragmentSummary(row) }}</span>
              <div class="kv-org-meta">
                <el-tag v-if="row.group_id" size="small" effect="plain">{{ flatGroupOptions.find(o => o.id === row.group_id)?.label ?? 'grouped' }}</el-tag>
                <el-tag v-else size="small" type="info" effect="plain">no group</el-tag>
                <el-tag v-for="lid in row.label_ids" :key="lid" size="small" :color="labelMap[lid]?.color" class="kv-lbl">{{ labelMap[lid]?.name }}</el-tag>
                <span class="kv-date">{{ fmtDate(row.created_at) }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- right: detail panel -->
      <aside v-if="organizeSelectedFrag" class="kv-org-detail">
        <div class="kv-det-head">
          <div class="kv-det-title-wrap">
            <div class="kv-det-title">{{ organizeSelectedFrag.header || fragmentSummary(organizeSelectedFrag) }}</div>
          </div>
          <div class="kv-det-acts">
            <el-select
              :model-value="organizeSelectedFrag.group_id ?? null"
              placeholder="Group…"
              clearable size="small" style="width:160px"
              @change="(v) => organizeSelectedFrag && organizeQuickMove(organizeSelectedFrag, v)"
            >
              <el-option label="No group" :value="null" />
              <el-option v-for="opt in flatGroupOptions" :key="opt.id" :label="opt.label" :value="opt.id" />
            </el-select>
            <el-button text size="small" type="danger" @click="organizeDeleteOne(organizeSelectedFrag)">Delete</el-button>
            <el-button text size="small" @click="organizeSelectedFrag = null">✕</el-button>
          </div>
        </div>
        <div class="kv-det-body">
          <div v-if="organizeSelectedFrag.note" class="kv-det-note">{{ organizeSelectedFrag.note }}</div>
          <div class="kv-det-meta">
            <el-tag size="small" effect="light"
              :type="organizeSelectedFrag.freshness === 'fresh' ? 'success' : organizeSelectedFrag.freshness === 'aging' ? 'warning' : 'danger'">
              {{ organizeSelectedFrag.freshness === 'fresh' ? 'Fresh' : organizeSelectedFrag.freshness === 'aging' ? 'Aging' : 'Outdated' }}
            </el-tag>
            <span class="kv-date">{{ fmtDate(organizeSelectedFrag.created_at) }}</span>
            <el-tag v-for="lid in organizeSelectedFrag.label_ids" :key="lid" size="small"
              :color="labelMap[lid]?.color" class="kv-lbl">{{ labelMap[lid]?.name }}</el-tag>
          </div>
          <div class="kv-blocks">
            <div v-for="(blk, i) in organizeSelectedFrag.blocks" :key="i" class="kv-block">
              <div class="kv-blk-bar" :class="blk.type === 'code' ? 'kv-blk-bar--code' : blk.type === 'url' ? 'kv-blk-bar--url' : blk.type === 'long' ? 'kv-blk-bar--long' : 'kv-blk-bar--text'"
                @click="blk.type === 'long' ? toggleLong(blk) : undefined" :style="blk.type === 'long' ? 'cursor:pointer' : ''">
                <span class="kv-blk-subtitle" v-if="blk.subtitle">
                  {{ blk.subtitle }}
                  <el-button text size="small" class="kv-copy-inline" @click.stop="copyBlock(blk.subtitle)">Copy</el-button>
                </span>
                <span v-else-if="blk.type === 'long'" class="kv-blk-subtitle kv-blk-subtitle--long">Long text — click to expand</span>
                <span v-else style="flex:1" />
                <span class="kv-blk-date">{{ fmtDate(organizeSelectedFrag.created_at) }}</span>
                <el-button text size="small" @click.stop="copyBlock(blk.body)">Copy</el-button>
                <span v-if="blk.type === 'long'" class="kv-long-chevron" :class="{ expanded: expandedLongs.has(blk) }">›</span>
              </div>
              <div v-if="blk.type === 'text'" class="kv-blk-text-body kv-md" v-html="renderMd(blk.body)" />
              <pre v-else-if="blk.type === 'code'" class="kv-pre">{{ blk.body }}</pre>
              <div v-else-if="blk.type === 'url'" class="kv-url-body">
                <a :href="blk.body" target="_blank" rel="noopener" class="kv-url-link">{{ blk.body }}</a>
              </div>
              <div v-else-if="blk.type === 'long' && expandedLongs.has(blk)" class="kv-blk-text-body kv-md" v-html="renderMd(blk.body)" />
            </div>
          </div>
        </div>
      </aside>
    </div>

    <!-- ==================== DIALOGS ==================== -->

    <!-- Add fragment -->
    <el-dialog v-model="addDialog" title="Add a fragment" width="640px">
      <el-input v-model="draftHeader" placeholder="Header — one-line title (required)"
          :class="{ 'kv-input-required': draftHeaderTouched && !draftHeader.trim() }"
          @blur="draftHeaderTouched = true"
          style="margin-bottom:8px" />
      <el-input v-model="draftNote" placeholder="Note (optional)" style="margin-bottom:8px" />
      <el-select v-model="draftLabelIds" multiple collapse-tags placeholder="Labels (optional)" style="width:100%; margin-bottom:8px">
        <el-option v-for="l in labels" :key="l.id" :label="l.name" :value="l.id" />
      </el-select>
      <el-select v-model="draftGroupId" placeholder="Group (optional)" clearable style="width:100%; margin-bottom:12px">
        <el-option label="null" :value="null" />
        <el-option label="/" :value="ROOT_GROUP_ID" />
        <el-option v-for="opt in flatGroupOptions" :key="opt.id" :label="opt.label" :value="opt.id" />
      </el-select>
      <div class="kv-blocks-edit">
        <div v-for="(blk, i) in draftBlocks" :key="i" class="kv-block-edit">
          <div class="kv-bk-toolbar">
            <div class="kv-bk-type-group">
              <button v-for="t in ['text','code','url','long']" :key="t"
                class="kv-bk-type-btn" :class="{ active: blk.type === t }"
                @click="setBlockType(draftBlocks, i, t)">{{ t }}</button>
            </div>
            <el-input v-if="blk.type === 'code'" v-model="blk.lang" placeholder="lang" size="small" style="width:80px; margin-left:6px" />
            <div style="flex:1" />
            <el-button text size="small" type="danger" :disabled="draftBlocks.length <= 1" @click="removeDraftBlock(i)">✕</el-button>
          </div>
          <el-input v-model="blk.subtitle" placeholder="Subtitle (optional)" size="small" style="margin-top:4px" />
          <el-input v-model="blk.body" type="textarea"
            :autosize="{ minRows: blk.type === 'url' ? 2 : 3 }"
            :placeholder="blk.type === 'code' ? 'Code...' : blk.type === 'url' ? 'https://...' : 'Text...'"
            :class="blk.type === 'code' ? 'kv-textarea-mono' : ''"
            style="margin-top:4px" />
        </div>
        <div class="kv-add-block-bar">
          <el-button text size="small" @click="addDraftBlock('text')">+ Text</el-button>
          <el-button text size="small" @click="addDraftBlock('code')">+ Code</el-button>
          <el-button text size="small" @click="addDraftBlock('url')">+ URL</el-button>
          <el-button text size="small" @click="addDraftBlock('long')">+ Long</el-button>
        </div>
      </div>
      <template #footer>
        <el-button @click="addDialog = false">Cancel</el-button>
        <el-button type="primary" :loading="saving" @click="addFragment">Save</el-button>
      </template>
    </el-dialog>

    <!-- Group CRUD -->
    <el-dialog v-model="groupDialog" :title="editingGroup.id == null ? 'New group' : 'Edit group'" width="400px">
      <el-input v-model="editingGroup.name" placeholder="Group name (required)" style="margin-bottom:8px" @keyup.enter="saveGroup" />
      <el-input v-model="editingGroup.note" placeholder="Note (optional)" style="margin-bottom:8px" />
      <el-select v-model="editingGroup.parent_id" placeholder="Parent group (optional)" clearable style="width:100%">
        <el-option v-for="g in groups.filter(g => g.id !== editingGroup.id)" :key="g.id" :label="g.name" :value="g.id" />
      </el-select>
      <template #footer>
        <el-button @click="groupDialog = false">Cancel</el-button>
        <el-button type="primary" :loading="savingGroup" @click="saveGroup">Save</el-button>
      </template>
    </el-dialog>

    <!-- Move to group -->
    <el-dialog v-model="groupMemberDialog" title="Move to group" width="400px">
      <el-select v-model="targetGroupId" style="width:100%">
        <el-option label="null" :value="null" />
        <el-option label="/" :value="ROOT_GROUP_ID" />
        <el-option v-for="opt in flatGroupOptions" :key="opt.id" :label="opt.label" :value="opt.id" />
      </el-select>
      <template #footer>
        <el-button @click="groupMemberDialog = false">Cancel</el-button>
        <el-button type="primary" @click="confirmMoveToGroup">
          {{ targetGroupId == null ? 'Ungroup' : targetGroupId === ROOT_GROUP_ID ? 'Move to top level' : 'Move' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script lang="ts" src="@/knowledge_vault/views/KnowledgeVaultCaptureView.ts"></script>

<style scoped>
.kv {
  height: 100vh; display: flex; flex-direction: column; overflow: hidden;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
  background: #f5f5f7; color: #1d1d1f;
}

/* topbar */
.kv-topbar {
  display: flex; align-items: center; gap: 12px;
  padding: 8px 20px; background: #fff;
  border-bottom: 1px solid rgba(0,0,0,0.07); flex-shrink: 0;
}
.kv-topbar h1 { margin: 0; font-size: 17px; font-weight: 600; white-space: nowrap; }

/* capture: 3-col */
.kv-capture { flex: 1; display: flex; overflow: hidden; min-height: 0; }

/* sidebar */
.kv-sidebar {
  width: 200px; flex-shrink: 0;
  background: #fff; border-right: 1px solid rgba(0,0,0,0.07);
  overflow-y: auto; padding: 12px 8px;
}
.kv-sidebar-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 4px 8px; font-size: 11px; font-weight: 600;
  color: #86868b; text-transform: uppercase; letter-spacing: .05em;
}
.sg-root {
  display: flex; align-items: center; gap: 4px;
  padding: 5px 8px; border-radius: 6px; cursor: pointer; margin-bottom: 2px;
  transition: background .1s;
}
.sg-root:hover { background: rgba(10,132,255,0.08); }
.sg-root.sg-item--active { background: rgba(10,132,255,0.14); }
.sg-root.sg-item--active .sg-name { color: #0a84ff; font-weight: 600; }

/* main list */
.kv-main { flex: 1; min-width: 0; overflow-y: auto; padding: 14px 16px; }
.kv-main-head {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 10px; flex-wrap: wrap; gap: 8px;
}
.kv-main-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.kv-breadcrumb { display: flex; align-items: center; gap: 6px; font-size: 14px; }
.kv-bc-link { color: #0a84ff; cursor: pointer; }
.kv-bc-link:hover { text-decoration: underline; }
.kv-bc-sep { color: #c7c7cc; }
.kv-bc-current { font-weight: 600; }
.kv-bc-note { font-size: 12px; color: #86868b; }
.kv-bc-archive { font-weight: 600; color: #ff9f0a; }
.kv-btn-active { color: #ff9f0a !important; }

/* segment */
.kv-seg { display: flex; border: 1px solid #dcdfe6; border-radius: 6px; overflow: hidden; }
.kv-seg-btn {
  padding: 3px 10px; font-size: 12px; border: none; background: transparent;
  cursor: pointer; color: #606266; transition: background .12s, color .12s;
}
.kv-seg-btn.active { background: #0a84ff; color: #fff; }
.kv-seg-btn:not(.active):hover { background: rgba(10,132,255,0.07); }

/* label filter */
.kv-label-filter {
  display: flex; align-items: center; flex-wrap: wrap; gap: 5px;
  padding: 5px 8px; margin-bottom: 10px;
  background: #f8f9fa; border-radius: 6px;
}
.kv-lf-label { font-size: 11px; color: #909399; white-space: nowrap; }

/* group cards */
.kv-group-card {
  display: flex; align-items: center; justify-content: space-between;
  padding: 9px 14px; margin-bottom: 4px;
  background: #eef4ff; border: 1px solid rgba(10,132,255,0.18);
  border-left: 3px solid #0a84ff;
  border-radius: 8px; cursor: pointer; transition: box-shadow .12s, background .12s;
}
.kv-group-card:hover { background: #e0ecff; box-shadow: 0 2px 8px rgba(10,132,255,0.12); }
.kv-gc-left { display: flex; align-items: center; gap: 8px; min-width: 0; }
.kv-gc-icon { color: #0a84ff; font-size: 16px; flex-shrink: 0; }
.kv-gc-name { font-size: 13px; font-weight: 600; color: #1d1d1f; }
.kv-gc-note { font-size: 11px; color: #86868b; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 120px; }
.kv-gc-right { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
.kv-gc-count { font-size: 11px; color: #86868b; }
.kv-gc-arrow { color: #0a84ff; font-size: 12px; }

/* fragment rows */
.kv-list { display: flex; flex-direction: column; gap: 3px; }
.kv-row {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  padding: 7px 12px; background: #fff;
  border: 1px solid transparent; border-radius: 7px;
  cursor: pointer; transition: border-color .1s, background .1s;
}
.kv-row:hover { background: rgba(10,132,255,0.03); border-color: rgba(10,132,255,0.18); }
.kv-row--active { background: rgba(10,132,255,0.07) !important; border-color: rgba(10,132,255,0.35) !important; }
.kv-row-title {
  flex: 1; min-width: 0; font-size: 13px; color: #1d1d1f;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.kv-row-meta { display: flex; align-items: center; flex-wrap: nowrap; gap: 5px; flex-shrink: 0; }
.kv-date { font-size: 11px; color: #86868b; white-space: nowrap; }
.kv-lbl { color: #fff !important; border: none !important; }

/* detail panel */
.kv-detail {
  flex: 1; min-width: 0;
  background: #fff; border-left: 1px solid rgba(0,0,0,0.07);
  display: flex; flex-direction: column; overflow: hidden;
}
.kv-det-head {
  display: flex; align-items: flex-start; gap: 6px;
  padding: 12px 14px; border-bottom: 1px solid rgba(0,0,0,0.06); flex-shrink: 0;
}
.kv-det-title-wrap { flex: 1; min-width: 0; }
.kv-det-title {
  font-size: 13px; font-weight: 600;
  word-break: break-word; line-height: 1.4;
  display: flex; align-items: center; gap: 4px; flex-wrap: wrap;
}
.kv-copy-inline { opacity: 0.5; padding: 0 4px !important; height: auto !important; font-size: 11px !important; }
.kv-copy-inline:hover { opacity: 1; }
.kv-det-acts { display: flex; gap: 2px; flex-shrink: 0; flex-wrap: wrap; justify-content: flex-end; }
.kv-det-body { flex: 1; overflow-y: auto; padding: 12px 14px; }
.kv-det-note { font-size: 13px; color: #3a3a3c; margin-bottom: 8px; line-height: 1.5; }
.kv-det-meta { display: flex; align-items: center; flex-wrap: wrap; gap: 5px; margin-bottom: 14px; }
.kv-det-edit { overflow-y: auto; }

/* blocks view */
.kv-blocks { display: flex; flex-direction: column; gap: 8px; }
.kv-block { border-radius: 7px; overflow: hidden; border: 1px solid rgba(0,0,0,0.07); }
.kv-blk-bar {
  display: flex; align-items: center; justify-content: space-between; padding: 4px 10px;
}
.kv-blk-bar--text { background: #f5f5f7; }
.kv-blk-bar--code { background: #2d2d2d; }
.kv-blk-bar--url { background: #f0f7ff; }
.kv-blk-bar--long { background: #f5f0ff; }
.kv-block:has(.kv-blk-bar--code) { background: #1e1e1e; }
.kv-blk-date { font-size: 11px; color: #86868b; white-space: nowrap; flex-shrink: 0; }
.kv-blk-bar--code .kv-blk-date { color: #888; }
.kv-blk-text-body {
  padding: 8px 12px; font-size: 13px; color: #1d1d1f;
  white-space: pre-wrap; word-break: break-word; line-height: 1.6;
}
.kv-md { white-space: normal; }
.kv-md :deep(p) { margin: 0 0 6px; }
.kv-md :deep(p:last-child) { margin-bottom: 0; }
.kv-md :deep(ul), .kv-md :deep(ol) { margin: 4px 0 6px; padding-left: 20px; }
.kv-md :deep(li) { margin: 2px 0; }
.kv-md :deep(h1), .kv-md :deep(h2), .kv-md :deep(h3) { margin: 8px 0 4px; font-size: 14px; font-weight: 600; }
.kv-md :deep(code) { background: #f0f2f5; border-radius: 3px; padding: 1px 4px; font-size: 12px; font-family: ui-monospace, monospace; }
.kv-md :deep(pre) { background: #1e1e1e; color: #d4d4d4; border-radius: 6px; padding: 10px 12px; overflow-x: auto; margin: 6px 0; }
.kv-md :deep(pre code) { background: none; padding: 0; color: inherit; }
.kv-md :deep(blockquote) { border-left: 3px solid #d0d0d0; margin: 6px 0; padding: 2px 10px; color: #555; }
.kv-md :deep(a) { color: #0a84ff; text-decoration: none; }
.kv-md :deep(a:hover) { text-decoration: underline; }
.kv-md :deep(hr) { border: none; border-top: 1px solid #e0e0e0; margin: 8px 0; }
.kv-md :deep(table) { border-collapse: collapse; font-size: 12px; }
.kv-md :deep(th), .kv-md :deep(td) { border: 1px solid #ddd; padding: 4px 8px; }
.kv-pre {
  margin: 0; padding: 10px 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px; color: #d4d4d4; overflow-x: auto; white-space: pre;
}
.kv-url-body { padding: 6px 12px 10px; }
.kv-url-link { font-size: 12px; color: #0a84ff; word-break: break-all; text-decoration: none; }
.kv-url-link:hover { text-decoration: underline; }
.kv-blk-subtitle {
  flex: 1; font-size: 12px; color: #555; font-style: italic;
  display: flex; align-items: center; gap: 4px; min-width: 0;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.kv-blk-subtitle--long { color: #7c4dbd; }
.kv-blk-bar--code .kv-blk-subtitle { color: #bbb; }
.kv-blk-bar--code .kv-copy-inline { color: #bbb !important; }
.kv-long-chevron {
  font-size: 16px; color: #7c4dbd; font-style: normal; margin-left: 4px;
  display: inline-block; transform: rotate(0deg); transition: transform .2s;
}
.kv-long-chevron.expanded { transform: rotate(90deg); }

/* blocks edit */
.kv-blocks-edit { display: flex; flex-direction: column; gap: 10px; }
.kv-block-edit { background: #f8f9fa; border: 1px solid rgba(0,0,0,0.07); border-radius: 8px; padding: 8px 10px; }
.kv-bk-toolbar { display: flex; align-items: center; gap: 4px; margin-bottom: 2px; }
.kv-bk-type-group { display: flex; border: 1px solid #dcdfe6; border-radius: 5px; overflow: hidden; }
.kv-bk-type-btn {
  padding: 2px 9px; font-size: 12px; border: none; background: transparent;
  cursor: pointer; color: #606266; transition: background .1s, color .1s;
}
.kv-bk-type-btn.active { background: #0a84ff; color: #fff; }
.kv-bk-type-btn:not(.active):hover { background: rgba(10,132,255,0.08); }
.kv-add-block-bar { display: flex; gap: 6px; padding-top: 4px; }
:deep(.kv-textarea-mono textarea) { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
:deep(.kv-input-required .el-input__wrapper) { box-shadow: 0 0 0 1px #f56c6c inset; }
:deep(.kv-input-required .el-input__wrapper:hover) { box-shadow: 0 0 0 1px #f56c6c inset; }

/* organize: 2-col layout */
.kv-organize-wrap { flex: 1; display: flex; overflow: hidden; min-height: 0; }
.kv-org-left {
  flex: 1; min-width: 0; display: flex; flex-direction: column;
  overflow: hidden; padding: 14px 16px; gap: 10px;
}
.kv-org-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  flex-wrap: wrap; gap: 8px; padding: 8px 14px;
  background: #fff; border: 1px solid rgba(0,0,0,0.07); border-radius: 8px; flex-shrink: 0;
}
.kv-org-toolbar-left { display: flex; align-items: center; gap: 10px; }
.kv-org-toolbar-right { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.kv-org-count { font-size: 13px; color: #606266; }
.kv-org-list { display: flex; flex-direction: column; gap: 3px; overflow-y: auto; }
.kv-org-row {
  display: flex; align-items: center; gap: 10px;
  padding: 7px 12px; background: #fff;
  border: 1px solid transparent; border-radius: 7px;
  cursor: pointer; transition: border-color .1s, background .1s;
}
.kv-org-row:hover { background: rgba(10,132,255,0.03); border-color: rgba(10,132,255,0.18); }
.kv-org-row--selected { background: rgba(10,132,255,0.05) !important; }
.kv-org-row--active { background: rgba(10,132,255,0.07) !important; border-color: rgba(10,132,255,0.35) !important; }
.kv-org-main { flex: 1; min-width: 0; }
.kv-org-title { font-size: 13px; color: #1d1d1f; display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kv-org-meta { display: flex; align-items: center; gap: 5px; flex-wrap: wrap; margin-top: 3px; }
.kv-org-detail {
  flex: 1; min-width: 0;
  background: #fff; border-left: 1px solid rgba(0,0,0,0.07);
  display: flex; flex-direction: column; overflow: hidden;
}
</style>
