<template>
  <div class="fd-wrap">

    <!-- ── Header ────────────────────────────────────────────────────────── -->
    <el-card class="fd-header-card">
      <div class="fd-header-row">
        <div>
          <h2 class="fd-title">File Duplicate Finder</h2>
          <p class="fd-subtitle">Find exact duplicate files across multiple backup roots</p>
        </div>
        <el-button @click="showSettings = true">⚙ Settings</el-button>
      </div>
    </el-card>

    <!-- ── Stats overview ────────────────────────────────────────────────── -->
    <div v-if="stats" class="fd-stats-row">
      <el-card class="fd-stat-card">
        <div class="fd-stat-num">{{ stats.total_files.toLocaleString() }}</div>
        <div class="fd-stat-label">Files Indexed</div>
      </el-card>
      <el-card class="fd-stat-card">
        <div class="fd-stat-num">{{ stats.group_stats.total_groups.toLocaleString() }}</div>
        <div class="fd-stat-label">Duplicate Groups</div>
      </el-card>
      <el-card class="fd-stat-card fd-stat-warn">
        <div class="fd-stat-num">{{ formatBytes(stats.group_stats.wasted_bytes) }}</div>
        <div class="fd-stat-label">Wasted Space</div>
      </el-card>
    </div>

    <!-- ── Per-root duplicate stats ─────────────────────────────────────── -->
    <el-card v-if="stats && stats.root_dup_stats.length" class="fd-root-stats-card">
      <template #header><span class="fd-section-title">Duplicate breakdown by root</span></template>
      <el-table :data="stats.root_dup_stats" size="small" style="width:100%">
        <el-table-column prop="root_path" label="Root" min-width="220">
          <template #default="{ row }">
            <span :style="{ color: rootColorOf(row.root_id) }">●</span>
            {{ row.root_path }}
          </template>
        </el-table-column>
        <el-table-column label="Root name" min-width="120">
          <template #default="{ row }">{{ rootNameOf(row.root_id) }}</template>
        </el-table-column>
        <el-table-column prop="dup_file_count" label="Dup files" width="100" align="right" />
        <el-table-column label="Dup size" width="120" align="right">
          <template #default="{ row }">{{ formatBytes(row.dup_total_size) }}</template>
        </el-table-column>
        <el-table-column label="Action" width="120" align="center">
          <template #default="{ row }">
            <el-button size="small" type="warning"
              @click="rootFilter = row.root_id; loadGroupsPage(1)">
              Filter
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ── Phase controls ────────────────────────────────────────────────── -->
    <el-card class="fd-phases-card">
      <div class="fd-phases-row">
        <el-button type="primary" :loading="isFullPipelineRunning"
                   :disabled="isPhase1Running || isPhase2Running || isPhase3Running"
                   @click="runFullPipeline">
          ⚡ Run All
        </el-button>

        <el-button-group>
          <el-button :loading="isPhase1Running"
                     :disabled="isPhase2Running || isPhase3Running || isFullPipelineRunning"
                     @click="runPhase1">
            1️⃣ Index Files
          </el-button>
          <el-button v-if="isPhase1Running" type="danger" @click="stopAll">Stop</el-button>
        </el-button-group>

        <el-button-group>
          <el-button :loading="isPhase2Running"
                     :disabled="isPhase1Running || isPhase3Running || isFullPipelineRunning"
                     @click="runPhase2">
            2️⃣ Hash Files
          </el-button>
          <el-button v-if="isPhase2Running" type="danger" @click="stopAll">Stop</el-button>
        </el-button-group>

        <el-button :loading="isPhase3Running"
                   :disabled="isPhase1Running || isPhase2Running || isFullPipelineRunning"
                   @click="runPhase3().then(() => loadGroupsPage(1).then(loadStats))">
          3️⃣ Build Groups
        </el-button>

        <el-button v-if="hasResults"
                   :disabled="isPhase1Running || isPhase2Running || isPhase3Running"
                   @click="loadGroupsPage(1)">
          🔄 Refresh
        </el-button>
      </div>

      <!-- Progress bar -->
      <div v-if="phaseProgress" class="fd-progress">
        <el-progress
          :percentage="phaseProgress.percentage"
          :status="phaseProgress.percentage === 100 ? 'success' : undefined"
          :striped="true"
          :striped-flow="true"
          :duration="10"
        />
        <div class="fd-progress-msg">{{ phaseProgress.message }}</div>
      </div>
    </el-card>

    <!-- ── Indexing status bar ────────────────────────────────────────────── -->
    <el-card v-if="stats" class="fd-index-status-card">
      <div class="fd-index-status-row">
        <span class="fd-status-item">
          Total files: <strong>{{ stats.total_files.toLocaleString() }}</strong>
        </span>
        <span v-if="stats.counts" class="fd-status-item">
          Fully hashed: <strong>{{ (stats.counts['full'] || 0).toLocaleString() }}</strong>
        </span>
        <span v-if="stats.counts" class="fd-status-item">
          Pending: <strong>{{ (stats.counts['pending'] || 0).toLocaleString() }}</strong>
        </span>
        <span v-if="rootFilter !== null" class="fd-filter-badge">
          Filtering: {{ rootNameOf(rootFilter) }}
          <el-button size="small" text @click="rootFilter = null; loadGroupsPage(1)">✕ Clear</el-button>
        </span>
      </div>
    </el-card>

    <!-- ── Results ───────────────────────────────────────────────────────── -->
    <div v-if="hasResults">

      <!-- Pagination + sort header -->
      <div class="fd-results-header">
        <el-pagination
          v-model:current-page="currentPage"
          :page-size="pageSize"
          :total="totalGroups"
          layout="prev, pager, next, total"
          @current-change="loadGroupsPage"
        />
        <div class="fd-sort-row">
          <span class="fd-sort-label">Sort:</span>
          <el-select v-model="sortBy" size="small" style="width:140px" @change="onSortChange">
            <el-option label="File size" value="filesize" />
            <el-option label="Member count" value="member_count" />
          </el-select>
          <el-button size="small" text @click="sortOrder = sortOrder === 'desc' ? 'asc' : 'desc'; onSortChange()">
            {{ sortOrder === 'desc' ? '▼' : '▲' }}
          </el-button>
        </div>
      </div>

      <!-- Group cards -->
      <el-card
        v-for="group in groups"
        :key="group.group_hash"
        class="fd-group-card"
      >
        <template #header>
          <div class="fd-group-header">
            <span class="fd-group-title">
              {{ group.member_count }} copies · {{ formatBytes(group.filesize) }} each
              · Hash: <code class="fd-hash">{{ group.group_hash.substring(0, 8) }}…</code>
            </span>
            <div class="fd-group-actions">
              <el-button size="small" @click="selectAllExceptFirst(group)">
                Auto-select extras
              </el-button>
              <el-button size="small" @click="deselectAll(group.group_hash)">
                Deselect all
              </el-button>
              <el-button size="small" type="primary" @click="openResolveDialog(group)">
                Resolve
              </el-button>
              <el-button size="small" type="danger"
                         :disabled="selectedCount(group.group_hash) === 0"
                         @click="trashSelected(group)">
                Trash selected ({{ selectedCount(group.group_hash) }})
              </el-button>
            </div>
          </div>
        </template>

        <div class="fd-members">
          <div
            v-for="member in group.members"
            :key="member.id"
            class="fd-member"
            :class="{ 'fd-member-selected': isSelected(group.group_hash, member.id) }"
            @click="toggleSelect(group.group_hash, member.id)"
          >
            <div class="fd-member-check">
              <el-checkbox
                :model-value="isSelected(group.group_hash, member.id)"
                @change="toggleSelect(group.group_hash, member.id)"
                @click.stop
              />
            </div>
            <div class="fd-member-info">
              <div class="fd-member-name">{{ member.filename }}</div>
              <div class="fd-member-path">{{ member.relative_path }}</div>
              <div class="fd-member-meta">
                <span
                  class="fd-root-badge"
                  :style="{ background: rootColorOf(member.root_id) }"
                >
                  {{ rootNameOf(member.root_id) }}
                </span>
                <span class="fd-member-size">{{ formatBytes(member.filesize) }}</span>
                <span class="fd-member-date">{{ formatDate(member.mtime) }}</span>
              </div>
            </div>
          </div>
        </div>
      </el-card>

      <!-- Bottom pagination -->
      <div class="fd-bottom-pagination">
        <el-pagination
          v-model:current-page="currentPage"
          :page-size="pageSize"
          :total="totalGroups"
          layout="prev, pager, next"
          @current-change="loadGroupsPage"
        />
      </div>
    </div>

    <!-- Empty state -->
    <el-card v-else-if="!isPhase1Running && !isPhase2Running && !isPhase3Running" class="fd-empty">
      <p>No duplicate groups found yet. Configure your scan roots in Settings, then run the pipeline.</p>
    </el-card>

    <!-- ── Resolve dialog ────────────────────────────────────────────────── -->
    <el-dialog v-model="showResolveDialog" title="Resolve Duplicate Group" width="700px">
      <div v-if="resolveGroup">
        <p class="fd-dialog-hint">
          Check the files you want to <strong>trash</strong>. Unchecked files will be kept.
        </p>
        <div class="fd-resolve-members">
          <div
            v-for="member in resolveGroup.members"
            :key="member.id"
            class="fd-resolve-row"
            :class="{
              'fd-resolve-keep': !isSelected(resolveGroup.group_hash, member.id),
              'fd-resolve-trash': isSelected(resolveGroup.group_hash, member.id)
            }"
          >
            <el-checkbox
              :model-value="isSelected(resolveGroup.group_hash, member.id)"
              @change="toggleSelect(resolveGroup.group_hash, member.id)"
            />
            <span
              class="fd-root-badge"
              :style="{ background: rootColorOf(member.root_id) }"
            >{{ rootNameOf(member.root_id) }}</span>
            <span class="fd-resolve-path">{{ member.file_path }}</span>
            <span class="fd-resolve-date">{{ formatDate(member.mtime) }}</span>
            <el-tag v-if="!isSelected(resolveGroup.group_hash, member.id)" type="success" size="small">KEEP</el-tag>
            <el-tag v-else type="danger" size="small">TRASH</el-tag>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="showResolveDialog = false">Cancel</el-button>
        <el-button type="danger" @click="confirmResolve">
          Trash {{ resolveGroup ? selectedCount(resolveGroup.group_hash) : 0 }} file(s)
        </el-button>
      </template>
    </el-dialog>

    <!-- ── Settings drawer ───────────────────────────────────────────────── -->
    <el-drawer v-model="showSettings" title="File Duplicate Settings" size="600px">
      <div class="fd-settings">

        <el-divider content-position="left">Scan Roots</el-divider>
        <p class="fd-settings-hint">Lower priority number = keep files from this root (priority 1 = most important).</p>
        <el-table :data="settings.scan_roots" size="small">
          <el-table-column prop="name" label="Name" min-width="120">
            <template #default="{ row }">
              <el-input v-model="row.name" size="small" />
            </template>
          </el-table-column>
          <el-table-column prop="path" label="Path" min-width="200">
            <template #default="{ row }">
              <el-input v-model="row.path" size="small" />
            </template>
          </el-table-column>
          <el-table-column prop="priority" label="Priority" width="90">
            <template #default="{ row }">
              <el-input-number v-model="row.priority" :min="1" :max="100" size="small" controls-position="right" />
            </template>
          </el-table-column>
          <el-table-column label="" width="60">
            <template #default="{ row }">
              <el-button size="small" type="danger" text @click="removeRoot(row.id)">✕</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="fd-add-row">
          <el-input v-model="newRootName" placeholder="Name" size="small" style="width:130px" />
          <el-input v-model="newRootPath" placeholder="/path/to/backup" size="small" style="flex:1" />
          <el-input-number v-model="newRootPriority" :min="1" :max="100" size="small"
                           style="width:90px" controls-position="right" />
          <el-button size="small" type="primary" @click="addRoot">+ Add</el-button>
        </div>

        <el-divider content-position="left">Trash Path</el-divider>
        <el-input v-model="settings.trash_path" placeholder="/path/to/trash" />

        <el-divider content-position="left">File Types (leave empty = all files)</el-divider>
        <div class="fd-tags-row">
          <el-tag
            v-for="ext in settings.include_extensions"
            :key="ext"
            closable
            @close="removeExtension(ext)"
          >.{{ ext }}</el-tag>
        </div>
        <div class="fd-add-row">
          <el-input v-model="newExtension" placeholder="e.g. pdf, jpg, docx" size="small" style="flex:1"
                    @keyup.enter="addExtension" />
          <el-button size="small" @click="addExtension">+ Add</el-button>
        </div>

        <el-divider content-position="left">Exclude Patterns</el-divider>
        <div class="fd-tags-row">
          <el-tag
            v-for="p in settings.exclude_patterns"
            :key="p"
            closable
            @close="removeExcludePattern(p)"
          >{{ p }}</el-tag>
        </div>
        <div class="fd-add-row">
          <el-input v-model="newExcludePattern" placeholder="e.g. .git, node_modules" size="small" style="flex:1"
                    @keyup.enter="addExcludePattern" />
          <el-button size="small" @click="addExcludePattern">+ Add</el-button>
        </div>

        <el-divider content-position="left">Performance</el-divider>
        <el-form label-width="160px" size="small">
          <el-form-item label="Max workers">
            <el-input-number v-model="settings.max_workers" :min="1" :max="16" controls-position="right" />
          </el-form-item>
          <el-form-item label="Hash batch size">
            <el-input-number v-model="settings.hash_batch_size" :min="50" :max="2000"
                             :step="50" controls-position="right" />
          </el-form-item>
          <el-form-item label="Page size">
            <el-input-number v-model="settings.page_size" :min="5" :max="100"
                             :step="5" controls-position="right" />
          </el-form-item>
        </el-form>

        <div class="fd-settings-save">
          <el-button type="primary" @click="saveSettings">Save Settings</el-button>
        </div>
      </div>
    </el-drawer>

  </div>
</template>

<script lang="ts" src="./FileDuplicateView.ts"></script>

<style scoped>
.fd-wrap { max-width: 1100px; margin: 0 auto; padding: 20px; display: flex; flex-direction: column; gap: 16px; }

.fd-header-card {}
.fd-header-row { display: flex; justify-content: space-between; align-items: center; }
.fd-title { margin: 0 0 4px; font-size: 1.4rem; }
.fd-subtitle { margin: 0; color: #888; font-size: 0.9rem; }

.fd-stats-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.fd-stat-card { text-align: center; }
.fd-stat-num { font-size: 2rem; font-weight: 700; color: #409eff; }
.fd-stat-warn .fd-stat-num { color: #e6a23c; }
.fd-stat-label { color: #888; font-size: 0.85rem; margin-top: 4px; }

.fd-root-stats-card {}
.fd-section-title { font-weight: 600; }

.fd-phases-card {}
.fd-phases-row { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
.fd-progress { margin-top: 14px; }
.fd-progress-msg { font-size: 0.85rem; color: #888; margin-top: 6px; }

.fd-index-status-card {}
.fd-index-status-row { display: flex; flex-wrap: wrap; gap: 16px; align-items: center; font-size: 0.9rem; }
.fd-status-item { color: #555; }
.fd-filter-badge { background: #ecf5ff; border-radius: 4px; padding: 2px 8px; color: #409eff; }

.fd-results-header { display: flex; justify-content: space-between; align-items: center; padding: 4px 0; }
.fd-sort-row { display: flex; align-items: center; gap: 6px; }
.fd-sort-label { font-size: 0.85rem; color: #888; }

.fd-group-card { margin-bottom: 0; }
.fd-group-header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; }
.fd-group-title { font-weight: 600; font-size: 0.95rem; }
.fd-group-actions { display: flex; gap: 6px; flex-wrap: wrap; }
.fd-hash { font-size: 0.8rem; background: #f5f5f5; padding: 1px 4px; border-radius: 3px; }

.fd-members { display: flex; flex-direction: column; gap: 8px; }
.fd-member {
  display: flex; align-items: flex-start; gap: 10px; padding: 10px 12px;
  border-radius: 6px; border: 1px solid #e4e7ed; cursor: pointer;
  transition: background 0.15s;
}
.fd-member:hover { background: #f5f7fa; }
.fd-member-selected { background: #fef0f0 !important; border-color: #fbc4c4; }
.fd-member-check { padding-top: 2px; }
.fd-member-info { flex: 1; min-width: 0; }
.fd-member-name { font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.fd-member-path { font-size: 0.82rem; color: #888; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-top: 2px; }
.fd-member-meta { display: flex; gap: 10px; align-items: center; margin-top: 4px; flex-wrap: wrap; }
.fd-root-badge { display: inline-block; padding: 1px 7px; border-radius: 10px; color: #fff; font-size: 0.78rem; }
.fd-member-size { font-size: 0.82rem; color: #555; }
.fd-member-date { font-size: 0.82rem; color: #aaa; }

.fd-bottom-pagination { display: flex; justify-content: center; padding: 8px 0; }
.fd-empty { text-align: center; color: #aaa; padding: 40px 0; }

/* Resolve dialog */
.fd-dialog-hint { margin-bottom: 12px; color: #555; }
.fd-resolve-members { display: flex; flex-direction: column; gap: 8px; }
.fd-resolve-row {
  display: flex; align-items: center; gap: 10px; padding: 8px 12px;
  border-radius: 6px; border: 1px solid #e4e7ed;
}
.fd-resolve-keep { background: #f0f9eb; border-color: #b3e19d; }
.fd-resolve-trash { background: #fef0f0; border-color: #fbc4c4; }
.fd-resolve-path { flex: 1; font-size: 0.85rem; word-break: break-all; }
.fd-resolve-date { font-size: 0.82rem; color: #aaa; white-space: nowrap; }

/* Settings drawer */
.fd-settings { padding: 0 4px; }
.fd-settings-hint { font-size: 0.85rem; color: #888; margin-bottom: 8px; }
.fd-add-row { display: flex; gap: 8px; align-items: center; margin-top: 8px; }
.fd-tags-row { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 6px; }
.fd-settings-save { margin-top: 24px; text-align: right; }
</style>
