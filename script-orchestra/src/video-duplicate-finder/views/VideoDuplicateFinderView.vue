<template>
  <div class="vdf-container">
    <!-- ================================================================== -->
    <!-- Top main card: title + phase buttons + deep path delete + progress  -->
    <!-- ================================================================== -->
    <el-card class="main-card">
      <template #header>
        <div class="card-header">
          <div style="display:flex;flex-direction:row;align-items:center;gap:10px;flex-shrink:0">
            <el-button @click="goBack" circle size="small"><el-icon><ArrowLeft /></el-icon></el-button>
            <div>
              <h2>Video Duplicate Finder</h2>
              <span class="subtitle">
                N-frame perceptual hash · finds and removes duplicate videos
              </span>
            </div>
          </div>
          <div class="header-buttons">
            <el-button
              type="warning"
              plain
              :disabled="isLoadingWhitelist"
              @click="showWhitelistDrawer = true; loadWhitelistGroups()"
            >⚪ Whitelist ({{ whitelistGroups.length }})</el-button>
            <el-button
              type="primary"
              plain
              @click="showSettingsDrawer = true"
            >⚙️ Settings</el-button>
          </div>
        </div>
      </template>

      <!-- Action Section: phase buttons + inline deep-path-delete -->
      <div class="action-section">
        <div class="action-buttons">
          <el-tooltip content="Run Phase 1 → Phase 2 → Phase 2.5 → Phase 3 in sequence" placement="top">
            <el-button
              type="success"
              size="large"
              :disabled="!settings.folder_paths || settings.folder_paths.length === 0
                        || isFullPipelineRunning || isPhase1Running || isPhase2Running
                        || isPhase25Running || isPhase3Running"
              :loading="isFullPipelineRunning"
              @click="runFullPipeline"
              data-testid="run-full-pipeline-btn"
            >⚡ Run All</el-button>
          </el-tooltip>

          <!-- Phase 1 -->
          <el-button
            type="primary"
            size="large"
            :disabled="!settings.folder_paths || settings.folder_paths.length === 0
                      || isFullPipelineRunning || isPhase1Running"
            :loading="isPhase1Running"
            @click="runPhase1"
          >{{ isPhase1Running ? 'Phase 1 Running…' : '1️⃣ Refresh Videos' }}</el-button>
          <el-button
            v-if="isPhase1Running"
            type="warning"
            size="large"
            @click="stopPhase1"
          >⏹ Stop</el-button>

          <!-- Phase 2 -->
          <el-button
            type="success"
            size="large"
            :disabled="isFullPipelineRunning || isPhase2Running"
            :loading="isPhase2Running"
            @click="runPhase2"
          >{{ isPhase2Running ? 'Phase 2 Running…' : '2️⃣ Build Similarities' }}</el-button>
          <el-button
            v-if="isPhase2Running"
            type="warning"
            size="large"
            @click="stopPhase2"
          >⏹ Stop</el-button>

          <!-- Phase 2.5 -->
          <el-tooltip :content="phase25TooltipContent" placement="top">
            <el-button
              :type="phase25NeedsAttention ? 'danger' : 'primary'"
              size="large"
              :disabled="isFullPipelineRunning || isPhase25Running"
              :loading="isPhase25Running"
              @click="runPhase25(true)"
            >{{ isPhase25Running ? 'Phase 2.5 Running…' : '🧮 Materialize Groups' }}</el-button>
          </el-tooltip>
          <el-button
            v-if="isPhase25Running"
            type="warning"
            size="large"
            @click="stopPhase25"
          >⏹ Stop</el-button>

          <!-- Phase 3 -->
          <el-button
            type="info"
            size="large"
            :disabled="isFullPipelineRunning || isPhase3Running"
            :loading="isPhase3Running"
            @click="runPhase3"
          >{{ isPhase3Running ? 'Phase 3 Running…' : '3️⃣ Get Duplicates' }}</el-button>
          <el-button
            v-if="isPhase3Running"
            type="warning"
            size="large"
            @click="stopPhase3"
          >⏹ Stop</el-button>

          <!-- Compare all folders -->
          <el-tooltip
            content="Run Compare Folder for every folder that has files in any duplicate group (skips 4+ folder clusters)"
            placement="top"
          >
            <el-button
              type="primary"
              plain
              size="large"
              :loading="isCompareAllRunning"
              :disabled="isCompareAllRunning || isComparingFolder
                        || isPhase1Running || isPhase2Running
                        || isPhase25Running || isPhase3Running || isFullPipelineRunning"
              @click="runCompareAllFolders(false)"
            >🔍 Compare All Folders</el-button>
          </el-tooltip>
        </div>

        <!-- Deep Path Delete inline widget -->
        <div class="deep-delete-inline">
          <el-tooltip
            content="Enter a folder path — every DUPLICATE file under it is moved to the delete target (mirrors folder structure, keeps companions)"
            placement="top"
          >
            <el-input
              v-model="deepPathDelete"
              placeholder="🎯 Deep Path Delete — enter or click on a video's Deep Delete"
              class="deep-delete-input"
              size="default"
              clearable
            />
          </el-tooltip>
          <el-button
            type="danger"
            :loading="isDeleting"
            @click="executeDeepPathDelete"
            size="default"
          >🗑️ Delete</el-button>
        </div>
      </div>

      <!-- Threshold slider -->
      <div class="controls-row">
        <span class="control-label">Similarity threshold:</span>
        <el-slider
          v-model="threshold"
          :min="80"
          :max="100"
          :step="5"
          :marks="{ 80: '80', 90: '90', 95: '95', 100: '100' }"
          :disabled="isPhase1Running || isPhase2Running || isPhase25Running
                    || isPhase3Running || isFullPipelineRunning"
          style="flex: 1; max-width: 500px"
        />
        <span class="threshold-value">{{ threshold }}%</span>
      </div>

      <!-- Phase progress bar -->
      <div v-if="phaseProgress.phase > 0" class="phase-progress-display">
        <p class="phase-message"><strong>{{ phaseProgress.message }}</strong></p>
        <el-progress
          :percentage="phaseProgress.percentage"
          :status="phaseProgress.percentage === 100 ? 'success' : undefined"
          :stroke-width="12"
        />
        <p class="phase-details">{{ phaseProgress.details }}</p>
      </div>

      <!-- Dismissible Phase Summary cards -->
      <el-card v-if="phase1Summary" class="summary-report-card" shadow="never">
        <template #header>
          <div class="report-header">
            <span>📊 Phase 1 Summary</span>
            <el-button link @click="phase1Summary = null">✕</el-button>
          </div>
        </template>
        <div class="report-grid">
          <div class="report-item">
            <span class="report-label">Videos Added</span>
            <span class="report-value highlight">+{{ phase1Summary.added }}</span>
          </div>
          <div class="report-item">
            <span class="report-label">Videos Removed</span>
            <span class="report-value">−{{ phase1Summary.removed }}</span>
          </div>
          <div class="report-item">
            <span class="report-label">Videos Skipped</span>
            <span class="report-value">{{ phase1Summary.skipped }}</span>
          </div>
          <div class="report-item">
            <span class="report-label">Elapsed</span>
            <span class="report-value">{{ phase1Summary.elapsed }}s</span>
          </div>
        </div>
      </el-card>

      <el-card v-if="phase2Summary" class="summary-report-card" shadow="never">
        <template #header>
          <div class="report-header">
            <span>📊 Phase 2 Summary</span>
            <el-button link @click="phase2Summary = null">✕</el-button>
          </div>
        </template>
        <div class="report-grid">
          <div class="report-item">
            <span class="report-label">Processed</span>
            <span class="report-value">{{ phase2Summary.processed }}</span>
          </div>
          <div class="report-item">
            <span class="report-label">Similarities Found</span>
            <span class="report-value highlight">{{ phase2Summary.similarities_found }}</span>
          </div>
          <div class="report-item">
            <span class="report-label">Elapsed</span>
            <span class="report-value">{{ phase2Summary.elapsed }}s</span>
          </div>
        </div>
      </el-card>

      <el-card v-if="phase25Summary" class="summary-report-card" shadow="never">
        <template #header>
          <div class="report-header">
            <span>📊 Phase 2.5 Summary</span>
            <el-button link @click="phase25Summary = null">✕</el-button>
          </div>
        </template>
        <div class="report-grid">
          <div class="report-item">
            <span class="report-label">Groups Materialized</span>
            <span class="report-value highlight">{{ phase25Summary.groups_count }}</span>
          </div>
          <div class="report-item">
            <span class="report-label">Members</span>
            <span class="report-value">{{ phase25Summary.members_count }}</span>
          </div>
          <div class="report-item">
            <span class="report-label">Elapsed</span>
            <span class="report-value">{{ phase25Summary.elapsed }}s</span>
          </div>
        </div>
      </el-card>
    </el-card>

    <!-- ================================================================== -->
    <!-- Results section: sticky top summary + pagination + groups -->
    <!-- ================================================================== -->
    <div v-if="hasResults && scanResult" class="results-section">
      <!-- Sticky summary card -->
      <el-card class="results-summary-card">
        <div class="results-summary-content">
          <div class="summary-item">
            <span class="summary-label">Total Files in DB</span>
            <span class="summary-value">{{ totalFilesInDb }}</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">Duplicate Groups</span>
            <span class="summary-value highlight">{{ totalGroupsAll }}</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">Total Duplicates</span>
            <span class="summary-value highlight" data-testid="duplicate-count">
              {{ scanResult.total_duplicates }}
            </span>
          </div>
          <div class="summary-item">
            <span class="summary-label">Threshold Materialized</span>
            <span class="summary-value">{{ phase25Meta.materialized_threshold || '?' }}%</span>
          </div>
          <div class="summary-item summary-actions-item">
            <el-button
              type="warning"
              plain
              :loading="isBulkWhitelisting"
              :disabled="!hasResults"
              @click="whitelistCurrentPage"
            >⚪ Whitelist page ({{ paginatedGroups.length }})</el-button>
            <el-button
              type="danger"
              plain
              :loading="isDeleting"
              :disabled="selectedCount === 0"
              @click="deleteAllSelected"
            >🗑️ Delete selected ({{ selectedCount }})</el-button>
            <el-button
              plain
              :loading="isVerifying"
              @click="verifyAndCleanup"
            >✓ Verify Files</el-button>
          </div>
        </div>
      </el-card>

      <!-- Pagination + Sort centered header -->
      <div class="duplicate-groups-header">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :total="totalGroupsAll"
          :page-sizes="[10, 20, 50, 100, 200, 500]"
          :disabled="isLoadingPage || isPhase3Running"
          layout="total, prev, pager, next, jumper, sizes"
          background
          @current-change="handlePageChange"
          @size-change="handlePageSizeChange"
        />

        <div class="sort-controls">
          <span class="sort-label">Sort by:</span>
          <el-select
            v-model="sortBy"
            size="small"
            style="width: 240px"
            :disabled="isLoadingPage || isPhase3Running"
            @change="handleSortChange"
          >
            <el-option
              v-for="opt in SORT_OPTIONS"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
          <el-button
            size="small"
            :type="sortOrder === 'desc' ? 'primary' : 'default'"
            :disabled="isLoadingPage || isPhase3Running"
            @click="toggleSortOrder"
            :title="sortOrder === 'desc' ? 'Descending (click to switch)' : 'Ascending (click to switch)'"
          >{{ sortOrder === 'desc' ? '↓ Desc' : '↑ Asc' }}</el-button>
        </div>
      </div>

      <!-- Duplicate groups list -->
      <div v-loading="isLoadingPage" class="duplicate-groups-container">
        <div
          v-for="(group, groupIndex) in paginatedGroups"
          :key="`group-${getActualGroupIndex(groupIndex)}`"
          class="duplicate-group"
        >
          <el-card>
            <template #header>
              <div class="group-header">
                <div class="group-actions-left">
                  <span class="group-title">
                    Group {{ getActualGroupIndex(groupIndex) + 1 }} ({{ group.length }} similar videos)
                  </span>
                  <el-button
                    size="small"
                    @click="selectAllInGroup(group)"
                  >
                    {{ hasAllSelectedInGroup(group) ? '❎ Deselect All' : '☑️ Select All' }}
                  </el-button>
                  <el-tooltip
                    content="Reset and re-run compare over the folders containing this group's videos"
                    placement="top"
                  >
                    <el-button
                      size="small"
                      type="primary"
                      plain
                      :loading="isComparingFolder"
                      @click="compareFolderForGroup(group)"
                    >🔍 Compare Folder</el-button>
                  </el-tooltip>
                </div>
                <div class="group-actions-right">
                  <el-button
                    size="small"
                    @click="addGroupToWhitelist(group, groupIndex)"
                  >✅ Add to Whitelist</el-button>
                  <el-tooltip
                    :content="group.length !== 2
                      ? 'Replace only works on groups with exactly 2 videos'
                      : (getSelectedCountInGroup(group) === 1
                          ? 'Keep selected video (copied to the other one\'s folder + basename with selected extension); originals backed up'
                          : 'Replace requires exactly 1 selected video')"
                    placement="top"
                  >
                    <span>
                      <el-button
                        size="small"
                        type="warning"
                        plain
                        :loading="isReplacing"
                        :disabled="group.length !== 2 || getSelectedCountInGroup(group) !== 1"
                        @click="replaceInGroup(group, groupIndex)"
                      >🔄 Replace</el-button>
                    </span>
                  </el-tooltip>
                  <el-button
                    size="small"
                    type="danger"
                    :disabled="!hasSelectedInGroup(group)"
                    @click="deleteSelectedInGroup(group, groupIndex)"
                  >🗑️ Delete Selected ({{ getSelectedCountInGroup(group) }})</el-button>
                </div>
              </div>
            </template>

            <div class="video-grid">
              <div
                v-for="(video, vIdx) in group"
                :key="video.file_path"
                :class="[
                  'video-item',
                  {
                    selected: selectedForDelete.has(video.file_path),
                    anchor:   vIdx === 0,
                    suggested: video.auto_delete_suggestion,
                  }
                ]"
                @click="toggleFileSelection(video.file_path)"
              >
                <div class="video-wrapper">
                  <img
                    :src="getThumbnailUrl(video.file_path)"
                    :alt="video.filename"
                    loading="lazy"
                  />
                  <!-- Selected overlay -->
                  <div v-if="selectedForDelete.has(video.file_path)" class="selected-overlay">
                    <el-icon :size="40"><CircleCheck /></el-icon>
                    <p class="selected-text">SELECTED</p>
                  </div>
                  <!-- Anchor badge -->
                  <div v-if="vIdx === 0" class="anchor-badge">🏆 ANCHOR</div>
                  <!-- Auto-delete suggestion badge (visible only when not selected) -->
                  <div
                    v-if="video.auto_delete_suggestion && !selectedForDelete.has(video.file_path)"
                    class="suggested-badge"
                  >❌ AUTO-DELETE</div>
                  <!-- Duration overlay bottom-right -->
                  <span v-if="video.duration != null" class="duration-badge">
                    {{ formatDuration(video.duration) }}
                  </span>
                </div>

                <div class="video-info">
                  <div class="video-filename-row">
                    <span class="video-filename" :title="video.filename">
                      {{ video.filename }}
                    </span>
                    <span
                      class="video-folder-counts"
                      :title="`${video.folder_dup ?? 0} duplicates / ${video.folder_total ?? 0} total in this folder`"
                    >
                      {{ video.folder_dup ?? 0 }}/{{ video.folder_total ?? 0 }}
                    </span>
                  </div>
                  <p class="video-path" :title="video.file_path">
                    {{ video.display_path || '/' }}
                  </p>
                  <div class="video-meta">
                    <span>{{ formatResolutionLabel(video.width, video.height) }}</span>
                    <span v-if="video.vcodec">{{ video.vcodec }}</span>
                    <span v-if="video.bitrate">{{ formatBitrate(video.bitrate) }}</span>
                    <span v-if="video.fps">{{ video.fps.toFixed(0) }}fps</span>
                    <span>{{ formatFileSize(video.filesize) }}</span>
                  </div>
                  <div class="video-actions" @click.stop>
                    <el-button size="small" @click.stop="openVideoPreview(video)">
                      ▶ Play
                    </el-button>
                    <el-button size="small" @click.stop="openFolder(video.file_path)">
                      📁 Folder
                    </el-button>
                    <el-button
                      size="small"
                      type="success"
                      @click.stop="deepWhitelistPath(video.file_path)"
                    >🛡️ Deep WL</el-button>
                    <el-button
                      v-if="group.length === 2"
                      size="small"
                      type="warning"
                      plain
                      :loading="isDeepReplacing"
                      @click.stop="deepReplacePath(video.file_path)"
                    >🔄 Deep Replace</el-button>
                    <el-button
                      size="small"
                      type="warning"
                      @click.stop="setDeepDeletePath(video.file_path)"
                    >🎯 Deep Delete</el-button>
                  </div>
                </div>
              </div>
            </div>
          </el-card>
        </div>
      </div>

      <!-- Bottom pagination for long pages -->
      <div v-if="paginatedGroups.length > 3" class="bottom-pagination">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :total="totalGroupsAll"
          :page-sizes="[10, 20, 50, 100, 200, 500]"
          :disabled="isLoadingPage || isPhase3Running"
          layout="total, prev, pager, next, jumper, sizes"
          background
          @current-change="handlePageChange"
          @size-change="handlePageSizeChange"
        />
      </div>
    </div>

    <!-- Empty state -->
    <el-card
      v-else-if="!isPhase1Running && !isPhase2Running && !isPhase25Running && !isPhase3Running"
      class="main-card empty-state"
    >
      <el-empty description="No duplicate groups loaded">
        <template #image>
          <span style="font-size: 64px">🎬</span>
        </template>
        <div class="empty-hint">
          Configure scan folders in <strong>⚙️ Settings</strong> and click <strong>⚡ Run All</strong>
          to scan → compare → materialize → view groups.
        </div>
      </el-empty>
    </el-card>

    <!-- ================================================================== -->
    <!-- Settings drawer -->
    <!-- ================================================================== -->
    <el-drawer
      v-model="showSettingsDrawer"
      title="⚙️ Settings"
      direction="rtl"
      size="600px"
    >
      <el-form label-width="200px" size="default">
        <el-divider content-position="left">📁 Folders</el-divider>

        <el-form-item label="Delete target path">
          <el-input v-model="settings.delete_target_path" placeholder="/path/to/trash" />
        </el-form-item>

        <el-form-item label="Scan folders">
          <div v-for="(_, idx) in (settings.folder_paths || [])" :key="`fp-${idx}`" class="path-row">
            <el-input
              v-model="settings.folder_paths![idx]"
              placeholder="/path/to/videos"
              size="default"
              style="flex: 1"
            />
            <el-button type="danger" plain size="default" @click="removeFolderPath(idx)">✕</el-button>
          </div>
          <el-button plain size="default" @click="addFolderPath">+ Add folder</el-button>
        </el-form-item>

        <el-form-item label="Exclude folders">
          <div v-for="(_, idx) in (settings.exclude_folder_paths || [])" :key="`ex-${idx}`" class="path-row">
            <el-input
              v-model="settings.exclude_folder_paths![idx]"
              placeholder="/path/to/exclude"
              size="default"
              style="flex: 1"
            />
            <el-button type="danger" plain size="default" @click="removeExcludeFolderPath(idx)">✕</el-button>
          </div>
          <el-button plain size="default" @click="addExcludeFolderPath">+ Add exclude</el-button>
        </el-form-item>

        <el-divider content-position="left">🎯 Auto-Selection Rules</el-divider>

        <el-form-item label="Mark lower resolution">
          <el-switch v-model="settings.auto_selection_rules!.auto_mark_lower_resolution" />
        </el-form-item>
        <el-form-item label="Mark lower bitrate">
          <el-switch v-model="settings.auto_selection_rules!.auto_mark_lower_bitrate" />
        </el-form-item>
        <el-form-item label="Mark smaller filesize">
          <el-switch v-model="settings.auto_selection_rules!.auto_mark_smaller_filesize" />
        </el-form-item>
        <el-form-item label="Mark older codec">
          <el-switch v-model="settings.auto_selection_rules!.auto_mark_older_codec" />
        </el-form-item>
        <el-form-item label="Mark numbered copies">
          <el-switch v-model="settings.auto_selection_rules!.auto_mark_numbered_copies" />
        </el-form-item>

        <el-form-item label="Prefer folders">
          <div
            v-for="(_, idx) in (settings.auto_selection_rules!.prefer_folders || [])"
            :key="`pf-${idx}`"
            class="path-row"
          >
            <el-input
              v-model="settings.auto_selection_rules!.prefer_folders![idx]"
              placeholder="/path/to/prefer"
              size="default"
              style="flex: 1"
            />
            <el-button type="danger" plain size="default" @click="removePreferFolder(idx)">✕</el-button>
          </div>
          <el-button plain size="default" @click="addPreferFolder">+ Add folder</el-button>
        </el-form-item>

        <el-divider content-position="left">🎞️ Companion Extensions</el-divider>

        <el-form-item label="Sidecar file extensions">
          <div
            v-for="(_, idx) in (settings.companion_extensions || [])"
            :key="`ce-${idx}`"
            class="path-row"
          >
            <el-input
              v-model="settings.companion_extensions![idx]"
              placeholder=".srt"
              size="default"
              style="flex: 1"
            />
            <el-button type="danger" plain size="default" @click="removeCompanionExtension(idx)">✕</el-button>
          </div>
          <el-button plain size="default" @click="addCompanionExtension">+ Add ext</el-button>
        </el-form-item>

        <el-divider content-position="left">⚡ Performance</el-divider>

        <el-form-item label="Max CPU cores">
          <el-input-number
            v-model="settings.max_cpu_cores"
            :min="1"
            :max="settings.system_cpu_count || 16"
          />
          <span class="hint">of {{ settings.system_cpu_count || '?' }}</span>
        </el-form-item>
        <el-form-item label="N frames per video">
          <el-input-number v-model="settings.n_frames" :min="1" :max="32" />
        </el-form-item>
        <el-form-item label="Thumbnail position (%)">
          <el-input-number v-model="settings.thumbnail_position_percent" :min="0" :max="100" :step="5" />
        </el-form-item>
        <el-form-item label="Page size">
          <el-input-number v-model="settings.page_size" :min="20" :max="500" :step="10" />
        </el-form-item>

        <el-divider />

        <el-form-item label="Advanced paths">
          <el-input v-model="settings.video_db_path"       placeholder="video_hash_cache.db path (blank = default)" style="margin-bottom: 8px" />
          <el-input v-model="settings.thumbnail_cache_dir"  placeholder="Thumbnails dir (blank = default)" style="margin-bottom: 8px" />
          <el-input v-model="settings.ffmpeg_path"         placeholder="ffmpeg path (blank = imageio_ffmpeg bundled)" disabled />
        </el-form-item>

        <el-divider />

        <div class="form-actions">
          <el-button type="primary" size="large" :loading="isSaving" @click="saveAllSettings">
            💾 Save Settings
          </el-button>
          <el-button plain size="large" :loading="isCleaningDb" :disabled="isCleaningDb" @click="cleanupDatabase">
            🧹 Cleanup DB (missing files)
          </el-button>
        </div>
      </el-form>
    </el-drawer>

    <!-- ================================================================== -->
    <!-- Whitelist drawer -->
    <!-- ================================================================== -->
    <el-drawer
      v-model="showWhitelistDrawer"
      title="⚪ Whitelist Groups"
      direction="rtl"
      size="600px"
    >
      <div v-loading="isLoadingWhitelist">
        <p v-if="whitelistGroups.length === 0" class="empty-hint">
          No whitelist groups. Add them from the results view.
        </p>
        <div
          v-for="(wl, idx) in whitelistGroups"
          :key="wl.group_id"
          class="whitelist-group-card"
        >
          <div class="whitelist-group-header">
            <strong>Group #{{ wl.group_id }}</strong>
            <span class="subtitle"> · {{ wl.members.length }} videos · {{ formatTimestamp(wl.added_time) }}</span>
            <el-button
              type="danger"
              plain
              size="small"
              style="margin-left: auto"
              @click="removeWhitelistGroup(wl.group_id, idx)"
            >✕ Remove</el-button>
          </div>
          <ul class="whitelist-members">
            <li v-for="m in wl.members" :key="m.video_id" :title="m.file_path">
              {{ m.filename }} · {{ formatFileSize(m.filesize) }}
              <span v-if="m.duration != null"> · {{ formatDuration(m.duration) }}</span>
            </li>
          </ul>
        </div>
      </div>
    </el-drawer>

    <!-- ================================================================== -->
    <!-- Video preview dialog -->
    <!-- ================================================================== -->
    <el-dialog
      v-model="showVideoPreviewDialog"
      :title="previewVideo?.filename || 'Video Preview'"
      width="80%"
      top="5vh"
      destroy-on-close
      @closed="closeVideoPreview"
    >
      <div v-if="previewVideo" class="video-preview-body">
        <video
          :src="previewVideoUrl"
          controls
          autoplay
          preload="metadata"
          style="width: 100%; max-height: 70vh; background: #000"
        />
        <div class="video-preview-meta">
          <p><strong>Path:</strong> <code>{{ previewVideo.file_path }}</code></p>
          <p>
            <strong>Metadata:</strong>
            {{ formatResolutionLabel(previewVideo.width, previewVideo.height) }}
            <span v-if="previewVideo.duration != null"> · {{ formatDuration(previewVideo.duration) }}</span>
            <span v-if="previewVideo.fps"> · {{ previewVideo.fps.toFixed(0) }} fps</span>
            <span v-if="previewVideo.vcodec"> · {{ previewVideo.vcodec }}</span>
            <span v-if="previewVideo.bitrate"> · {{ formatBitrate(previewVideo.bitrate) }}</span>
            <span v-if="previewVideo.filesize"> · {{ formatFileSize(previewVideo.filesize) }}</span>
          </p>
        </div>
      </div>
    </el-dialog>

    <!-- ================================================================== -->
    <!-- Deep-delete-by-path preview dialog -->
    <!-- ================================================================== -->
    <el-dialog
      v-model="showDeepDeleteDialog"
      title="🎯 Deep Delete By Path"
      width="720px"
    >
      <div>
        <p>
          Under folder:
          <code class="code-block">{{ deepDeletePreview.deepPath }}</code>
        </p>
        <p>
          <strong>{{ deepDeletePreview.matchedCount }}</strong>
          duplicate video(s) will be moved to the delete target
          (plus their companion sidecars, plus empty parent dirs pruned).
        </p>
        <el-alert type="warning" :closable="false" show-icon>
          This affects ALL matched duplicates under this folder — not just the currently visible page.
          Companions travel with their video.
        </el-alert>
        <el-divider content-position="left">Files to move ({{ deepDeleteFileListRelative.length }})</el-divider>
        <div class="file-list-scroll">
          <div
            v-for="(rel, idx) in deepDeleteFileListRelative.slice(0, 200)"
            :key="idx"
            class="file-list-item"
          >{{ rel }}</div>
          <div v-if="deepDeleteFileListRelative.length > 200" class="file-list-more">
            … and {{ deepDeleteFileListRelative.length - 200 }} more
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="cancelDeepDelete">Cancel</el-button>
        <el-button
          type="danger"
          :loading="isDeleting"
          @click="confirmDeepDelete"
        >🗑️ Delete {{ deepDeletePreview.matchedCount }} File(s)</el-button>
      </template>
    </el-dialog>

    <!-- ================================================================== -->
    <!-- Deep replace preview dialog -->
    <!-- ================================================================== -->
    <el-dialog
      v-model="showDeepReplaceDialog"
      title="🔄 Deep Replace"
      width="720px"
    >
      <div>
        <p>
          Under folder:
          <code class="code-block">{{ deepReplacePreview.folderPath }}</code>
        </p>
        <p>
          <strong>{{ deepReplacePreview.operations.length }}</strong> replace op(s) on this page —
          for each size-2 group, the video under this folder is KEPT and the other is moved to trash.
        </p>
        <el-alert
          v-if="deepReplacePreview.badGroups.length > 0"
          type="error"
          :closable="false"
          show-icon
          style="margin-bottom:12px"
        >
          Replace is BLOCKED — {{ deepReplacePreview.badGroups.length }} matched group(s) have size ≠ 2.
          Replace only works on exact 2-video groups. Resolve them (delete or whitelist) and retry.
        </el-alert>
        <el-divider content-position="left">Operations preview</el-divider>
        <div class="file-list-scroll">
          <div
            v-for="(op, idx) in deepReplacePreview.operations.slice(0, 50)"
            :key="idx"
            class="op-preview-item"
          >
            <div class="op-preview-idx">Op #{{ idx + 1 }}</div>
            <div><strong>Keep + rename:</strong> {{ op.selected.filename }}</div>
            <div><strong>Anchor:</strong> {{ op.anchor.filename }}</div>
          </div>
          <div v-if="deepReplacePreview.operations.length > 50" class="file-list-more">
            … and {{ deepReplacePreview.operations.length - 50 }} more
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="cancelDeepReplace">Cancel</el-button>
        <el-button
          type="primary"
          :loading="isDeepReplacing"
          :disabled="deepReplacePreview.badGroups.length > 0 || deepReplacePreview.operations.length === 0"
          @click="confirmDeepReplace"
        >🔄 Replace {{ deepReplacePreview.operations.length }} Op(s)</el-button>
      </template>
    </el-dialog>

    <!-- ================================================================== -->
    <!-- Bulk-whitelist confirmation dialog -->
    <!-- ================================================================== -->
    <el-dialog
      v-model="showBulkWhitelistDialog"
      title="⚪ Bulk Whitelist Confirmation"
      width="600px"
    >
      <div>
        <p>Scope: <strong>{{ bulkWhitelistPreview.contextLabel }}</strong></p>
        <p>
          About to whitelist <strong>{{ bulkWhitelistPreview.groupCount }} groups</strong>
          ({{ bulkWhitelistPreview.videoCount }} videos total).
        </p>
        <el-alert type="info" :closable="false" show-icon>
          These groups will not appear in future Phase 2.5 materializations.
          Remove them later from the Whitelist drawer.
        </el-alert>
      </div>
      <template #footer>
        <el-button @click="cancelBulkWhitelist">Cancel</el-button>
        <el-button
          type="warning"
          :loading="isBulkWhitelisting"
          @click="confirmBulkWhitelist"
        >Confirm Whitelist</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { CircleCheck } from '@element-plus/icons-vue'
import { useVideoDuplicateFinderView } from './VideoDuplicateFinderView'

const router = useRouter()
function goBack() { router.push('/') }

// Settings drawer visibility is local to the .vue (not stateful across app)
const showSettingsDrawer = ref(false)

const {
  // state
  threshold,
  scanResult, hasResults, paginatedGroups,
  isPhase1Running, isPhase2Running, isPhase25Running, isPhase3Running,
  isFullPipelineRunning, isDeleting, isVerifying, isSaving,
  isBulkWhitelisting, isLoadingWhitelist, isLoadingPage,
  isCleaningDb,
  phaseProgress,
  phase1Summary, phase2Summary, phase25Summary,
  phase25Meta, phase25NeedsAttention, phase25TooltipContent,
  currentPage, pageSize, totalGroupsAll, totalFilesInDb,
  sortBy, sortOrder, SORT_OPTIONS,
  selectedForDelete, selectedCount,
  settings,
  showVideoPreviewDialog, previewVideo, previewVideoUrl,
  showWhitelistDrawer, whitelistGroups,
  showBulkWhitelistDialog, bulkWhitelistPreview,
  // S6 compare
  isComparingFolder, isCompareAllRunning,
  compareFolderForGroup, runCompareAllFolders,
  // S7.2 replace
  isReplacing, isDeepReplacing,
  replaceInGroup,
  deepReplacePath, cancelDeepReplace, confirmDeepReplace,
  showDeepReplaceDialog, deepReplacePreview,
  // S7.3 deep delete
  deepPathDelete,
  showDeepDeleteDialog, deepDeletePreview, deepDeleteFileListRelative,
  setDeepDeletePath, executeDeepPathDelete, confirmDeepDelete, cancelDeepDelete,
  // helpers
  formatFileSize, formatDuration, formatBitrate, formatTimestamp, formatResolutionLabel,
  // phase methods
  runPhase1, stopPhase1,
  runPhase2, stopPhase2,
  runPhase25, stopPhase25,
  runPhase3, stopPhase3,
  runFullPipeline,
  // paging/sort
  handlePageChange, handlePageSizeChange, handleSortChange, toggleSortOrder,
  getActualGroupIndex,
  // selection
  toggleFileSelection, hasSelectedInGroup, hasAllSelectedInGroup,
  getSelectedCountInGroup, selectAllInGroup,
  // actions
  deleteSelectedInGroup, deleteAllSelected,
  addGroupToWhitelist,
  whitelistCurrentPage, deepWhitelistPath,
  confirmBulkWhitelist, cancelBulkWhitelist,
  loadWhitelistGroups, removeWhitelistGroup,
  verifyAndCleanup, cleanupDatabase,
  openVideoPreview, closeVideoPreview,
  getThumbnailUrl,
  openFolder,
  saveAllSettings,
  addFolderPath, removeFolderPath,
  addExcludeFolderPath, removeExcludeFolderPath,
  addPreferFolder, removePreferFolder,
  addCompanionExtension, removeCompanionExtension,
} = useVideoDuplicateFinderView()
</script>

<style scoped>
/* ============================================================================
   Container + top card
   ============================================================================ */
.vdf-container {
  padding: 20px;
  max-width: 1800px;
  margin: 0 auto;
}

.main-card {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-header > div:first-child {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.card-header h2 {
  margin: 0;
  font-size: 24px;
}

.subtitle {
  color: #909399;
  font-size: 14px;
}

.header-buttons {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* ============================================================================
   Action section (phase buttons + inline deep-path-delete)
   ============================================================================ */
.action-section {
  display: flex;
  align-items: center;
  gap: 20px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.action-buttons {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  flex: 1;
}

.deep-delete-inline {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  background: #fef0f0;
  border-radius: 6px;
  border: 1px solid #fde2e2;
}

.deep-delete-input {
  width: 520px;
}

/* ============================================================================
   Threshold slider row
   ============================================================================ */
.controls-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  background: #f5f7fa;
  border-radius: 6px;
  margin-bottom: 12px;
}

.control-label {
  font-weight: 500;
  color: #606266;
  min-width: 150px;
}

.threshold-value {
  font-weight: 700;
  color: #409eff;
  min-width: 44px;
  text-align: right;
  font-size: 16px;
}

.hint {
  color: #909399;
  font-size: 12px;
  margin-left: 8px;
}

/* ============================================================================
   Phase progress
   ============================================================================ */
.phase-progress-display {
  margin-top: 16px;
  padding: 14px 16px;
  background: #ecf5ff;
  border-radius: 6px;
  border: 1px solid #d9ecff;
}

.phase-message {
  margin: 0 0 8px 0;
  color: #303133;
  font-size: 14px;
}

.phase-details {
  margin: 8px 0 0 0;
  color: #606266;
  font-size: 13px;
}

/* ============================================================================
   Phase summary report cards
   ============================================================================ */
.summary-report-card {
  margin-top: 16px;
  background: #f0f9ff;
  border: 1px solid #b3e0ff;
}

.summary-report-card :deep(.el-card__header) {
  padding: 10px 16px;
  background: rgba(64, 158, 255, 0.06);
}

.report-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
  color: #303133;
}

.report-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 16px;
}

.report-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.report-label {
  font-size: 12px;
  color: #909399;
}

.report-value {
  font-size: 22px;
  font-weight: 700;
  color: #303133;
}

.report-value.highlight {
  color: #409eff;
}

/* ============================================================================
   Results summary card (sticky)
   ============================================================================ */
.results-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.results-summary-card {
  position: sticky;
  top: 0;
  z-index: 10;
  border: 1px solid #dcdfe6;
}

.results-summary-content {
  display: flex;
  gap: 32px;
  align-items: center;
  flex-wrap: wrap;
}

.summary-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 100px;
}

.summary-label {
  font-size: 12px;
  color: #909399;
}

.summary-value {
  font-size: 24px;
  font-weight: 700;
  color: #303133;
}

.summary-value.highlight {
  color: #409eff;
}

.summary-actions-item {
  flex-direction: row;
  gap: 8px;
  align-items: center;
  margin-left: auto;
  flex-wrap: wrap;
}

/* ============================================================================
   Pagination + Sort header (centered)
   ============================================================================ */
.duplicate-groups-header {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 20px;
  flex-wrap: wrap;
  padding: 12px 0;
}

.sort-controls {
  display: flex;
  gap: 8px;
  align-items: center;
}

.sort-label {
  font-size: 13px;
  color: #606266;
}

/* ============================================================================
   Duplicate groups container
   ============================================================================ */
.duplicate-groups-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 200px;
}

.duplicate-group {
  margin-bottom: 4px;
}

.group-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.group-actions-left,
.group-actions-right {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.group-title {
  font-weight: 600;
  font-size: 16px;
  color: #303133;
}

/* ============================================================================
   Video grid + video item (whole-card-click to select)
   ============================================================================ */
.video-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
  gap: 16px;
}

.video-item {
  cursor: pointer;
  border: 2px solid transparent;
  border-radius: 8px;
  overflow: hidden;
  transition: all 0.2s;
  background: #fff;
}

.video-item:hover {
  border-color: #409eff;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}

.video-item.selected {
  border-color: #f56c6c;
  background: #fef0f0;
}

.video-item.anchor {
  border-color: #67c23a;
}

.video-item.anchor.selected {
  border-color: #f56c6c;
}

.video-item.suggested::after {
  content: '';
  position: absolute;
  inset: 0;
  border: 2px solid transparent;
  pointer-events: none;
}

/* Thumbnail wrapper */
.video-wrapper {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  background: #000;
}

.video-wrapper img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.selected-overlay {
  position: absolute;
  inset: 0;
  background: rgba(245, 108, 108, 0.72);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: white;
  animation: overlay-fade-in 0.15s ease-out;
}

@keyframes overlay-fade-in {
  from { opacity: 0; }
  to   { opacity: 1; }
}

.selected-text {
  margin: 8px 0 0 0;
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 2px;
}

.anchor-badge {
  position: absolute;
  top: 8px;
  right: 8px;
  background: #67c23a;
  color: white;
  padding: 5px 10px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.5px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
  z-index: 2;
}

.suggested-badge {
  position: absolute;
  top: 8px;
  left: 8px;
  background: #e6a23c;
  color: white;
  padding: 5px 10px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.5px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
  z-index: 2;
}

.duration-badge {
  position: absolute;
  bottom: 8px;
  right: 8px;
  background: rgba(0, 0, 0, 0.75);
  color: #fff;
  padding: 3px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-family: monospace;
  font-weight: 600;
  z-index: 1;
}

/* Info section below thumbnail */
.video-info {
  padding: 10px 12px;
}

.video-filename-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
}

.video-filename {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  min-width: 0;
}

.video-folder-counts {
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 600;
  color: #909399;
  padding: 2px 6px;
  background: #f5f7fa;
  border-radius: 3px;
}

.video-path {
  margin: 0 0 6px 0;
  font-size: 12px;
  color: #909399;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.video-meta {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  font-size: 12px;
  color: #606266;
  margin-bottom: 8px;
}

.video-meta > span {
  padding: 2px 6px;
  background: #f5f7fa;
  border-radius: 3px;
  font-family: monospace;
}

.video-actions {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

/* Bottom pagination */
.bottom-pagination {
  margin-top: 24px;
  display: flex;
  justify-content: center;
}

/* ============================================================================
   Empty state
   ============================================================================ */
.empty-state {
  text-align: center;
}

.empty-hint {
  color: #909399;
  margin-top: 12px;
  font-size: 14px;
}

/* ============================================================================
   Drawers (settings + whitelist)
   ============================================================================ */
.path-row {
  display: flex;
  gap: 6px;
  margin-bottom: 6px;
}

.form-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}

.whitelist-group-card {
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 12px;
  margin-bottom: 12px;
  background: #fafafa;
}

.whitelist-group-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.whitelist-members {
  margin: 0;
  padding-left: 20px;
  color: #606266;
  font-size: 13px;
}

.whitelist-members li {
  padding: 2px 0;
}

/* ============================================================================
   Dialogs
   ============================================================================ */
.video-preview-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.video-preview-meta {
  font-size: 13px;
  color: #606266;
}

.video-preview-meta code {
  background: #f5f7fa;
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 12px;
}

.code-block {
  background: #f5f7fa;
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 12px;
  font-family: monospace;
}

.file-list-scroll {
  max-height: 320px;
  overflow: auto;
  background: #f5f7fa;
  padding: 10px;
  border-radius: 4px;
  font-family: monospace;
  font-size: 12px;
}

.file-list-item {
  padding: 3px 0;
  border-bottom: 1px solid #ebeef5;
}

.file-list-more {
  color: #909399;
  padding-top: 8px;
  font-size: 12px;
}

.op-preview-item {
  border: 1px solid #ebeef5;
  border-radius: 4px;
  padding: 8px 10px;
  margin-bottom: 8px;
  background: #fff;
}

.op-preview-idx {
  color: #909399;
  font-size: 11px;
  margin-bottom: 4px;
}
</style>
