<template>
  <div class="duplicate-finder-container">
    <el-card class="main-card">
      <template #header>
        <div class="card-header">
          <div style="display:flex;flex-direction:row;align-items:center;gap:10px;flex-shrink:0">
            <el-button @click="goBack" circle size="small"><el-icon><ArrowLeft /></el-icon></el-button>
            <div>
              <h2>Duplicate Image Finder</h2>
              <span class="subtitle">Find and remove duplicate images using perceptual hashing</span>
            </div>
          </div>
          <el-button @click="goToSettings">⚙️ Settings</el-button>
        </div>
      </template>

      <!-- Action Buttons with Deep Path Delete -->
      <div class="action-section">
        <!-- 3 Phase Workflow Buttons -->
        <div class="action-buttons">
          <!-- Run Full Pipeline (Phase 1 → 2 → 2.5 → Compare All) -->
          <el-button
            type="success"
            size="large"
            :disabled="!settings.folder_paths || settings.folder_paths.length === 0"
            :loading="isFullPipelineRunning"
            @click="runFullPipeline"
            data-testid="run-full-pipeline-btn"
          >
            ⚡ Run All
          </el-button>

          <!-- Phase 1 -->
          <el-button
            type="primary"
            size="large"
            :disabled="!settings.folder_paths || settings.folder_paths.length === 0 || isPhase1Running"
            :loading="isPhase1Running"
            @click="runPhase1"
          >
            {{ isPhase1Running ? 'Phase 1 Running...' : '1️⃣ Refresh Images' }}
          </el-button>
          <el-button
            v-if="isPhase1Running"
            type="warning"
            size="large"
            @click="stopPhase1"
          >
            ⏹️ Stop
          </el-button>

          <!-- Phase 2 -->
          <el-button
            type="success"
            size="large"
            :disabled="isPhase2Running"
            :loading="isPhase2Running"
            @click="runPhase2"
          >
            {{ isPhase2Running ? 'Phase 2 Running...' : '2️⃣ Build Similarities' }}
          </el-button>
          <el-button
            v-if="isPhase2Running"
            type="warning"
            size="large"
            @click="stopPhase2"
          >
            ⏹️ Stop
          </el-button>
          <el-button
            v-if="!isPhase2Running"
            type="warning"
            size="large"
            :disabled="isPhase2Running"
            @click="forceRerunPhase2"
          >
            🔄 Force Re-run
          </el-button>

          <!-- Phase 2.5: Materialize Groups (manual trigger between Phase 2 and Phase 3) -->
          <el-button
            :type="phase25NeedsAttention ? 'warning' : 'primary'"
            size="large"
            :disabled="isPhase25Running"
            :loading="isPhase25Running"
            @click="runPhase25"
            data-testid="phase25-materialize-btn"
          >
            {{ isPhase25Running ? 'Phase 2.5 Running...' : '🧮 Materialize Groups' }}
          </el-button>
          <el-button
            v-if="isPhase25Running"
            type="warning"
            size="large"
            @click="stopPhase25"
          >
            ⏹️ Stop
          </el-button>

          <!-- Phase 3 -->
          <el-button
            type="info"
            size="large"
            :disabled="isPhase3Running"
            :loading="isPhase3Running"
            @click="runPhase3"
          >
            {{ isPhase3Running ? 'Phase 3 Running...' : '3️⃣ Get Duplicates' }}
          </el-button>
          <el-button
            v-if="isPhase3Running"
            type="warning"
            size="large"
            @click="stopPhase3"
          >
            ⏹️ Stop
          </el-button>
          <el-button
            type="primary"
            plain
            size="large"
            :loading="isCompareAllRunning"
            @click="runCompareAllFolders"
            data-testid="compare-all-folders-btn"
          >
            🔍 Compare All Folders
          </el-button>
          <el-button
            type="warning"
            plain
            size="large"
            :loading="gapAnalysisLoading"
            @click="triggerGapAnalysis('global')"
          >
            🔎 Gap Analysis
          </el-button>
        </div>

        <!-- Deep Path Delete - Compact -->
        <div class="deep-delete-inline">
          <el-input
            v-model="deepPathDelete"
            placeholder="Deep Path Delete"
            style="width: 560px;"
            size="default"
            data-testid="deep-delete-path-input"
          />
          <el-button
            type="danger"
            @click="executeDeepPathDelete"
            :loading="isDeleting"
            size="default"
            data-testid="deep-delete-btn"
          >
            🗑️ Delete
          </el-button>
        </div>
      </div>

      <!-- Phase Progress Display -->
      <div v-if="phaseProgress.phase > 0" class="phase-progress-display" data-testid="phase-progress">
        <p class="phase-message">{{ phaseProgress.message }}</p>
        <el-progress
          :percentage="phaseProgress.percentage"
          :status="phaseProgress.percentage === 100 ? 'success' : undefined"
        />
        <p class="phase-details">{{ phaseProgress.details }}</p>
      </div>

      <!-- Phase 1 Summary (when complete) -->
      <el-card v-if="phase1Summary" class="summary-card" style="margin-top: 20px;" data-testid="phase1-report">
        <template #header>
          <div style="display: flex; align-items: center; justify-content: space-between;">
            <span>📊 Phase 1 Summary</span>
            <el-button
              type="text"
              size="small"
              @click="phase1Summary = null"
            >
              ✕
            </el-button>
          </div>
        </template>
        <div class="summary-content">
          <div class="summary-item">
            <span class="summary-label">Images Added:</span>
            <span class="summary-value highlight">+{{ phase1Summary.added }}</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">Images Removed:</span>
            <span class="summary-value">-{{ phase1Summary.removed }}</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">Images Skipped:</span>
            <span class="summary-value">{{ phase1Summary.skipped }}</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">Time Elapsed:</span>
            <span class="summary-value">{{ phase1Summary.elapsed }}s</span>
          </div>
        </div>
      </el-card>

      <!-- Phase 2 Summary (when complete) -->
      <el-card v-if="phase2Summary" class="summary-card" style="margin-top: 20px;" data-testid="phase2-report">
        <template #header>
          <div style="display: flex; align-items: center; justify-content: space-between;">
            <span>📊 Phase 2 Summary</span>
            <el-button
              type="text"
              size="small"
              @click="phase2Summary = null"
            >
              ✕
            </el-button>
          </div>
        </template>
        <div class="summary-content">
          <div class="summary-item">
            <span class="summary-label">Images Processed:</span>
            <span class="summary-value highlight">{{ phase2Summary.processed }}</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">Similarities Found:</span>
            <span class="summary-value highlight">{{ phase2Summary.similarities_found }}</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">Time Elapsed:</span>
            <span class="summary-value">{{ phase2Summary.elapsed }}s</span>
          </div>
        </div>
      </el-card>

      <!-- Progress Section -->
      <div v-if="isScanning" class="progress-section">
        <el-progress
          :percentage="scanProgress.percentage"
          :status="scanProgress.percentage === 100 ? 'success' : undefined"
        />
        <p class="progress-message">{{ scanProgress.message }}</p>
        <p class="progress-count">{{ scanProgress.current }} / {{ scanProgress.total }}</p>
      </div>
    </el-card>

    <!-- Results Section -->
    <div v-if="hasResults && scanResult" class="results-section">
      <!-- Summary Card -->
      <el-card class="summary-card">
        <div class="summary-content">
          <div class="summary-item">
            <span class="summary-label">Total Files in DB:</span>
            <span class="summary-value">{{ totalFilesInDb }}</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">Duplicate Groups:</span>
            <span class="summary-value highlight">{{ totalGroupsAll }}</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">Total Duplicates:</span>
            <span class="summary-value highlight" data-testid="duplicate-count">{{ scanResult.duplicate_count }}</span>
          </div>
        </div>
      </el-card>

      <!-- Duplicate Groups with Pagination -->
      <div class="duplicate-groups-header">
        <el-pagination
          v-model:current-page="currentPage"
          :page-size="pageSize"
          :total="totalGroupsAll"
          layout="total, prev, pager, next, jumper, sizes"
          :page-sizes="[10, 20, 50, 100]"
          @current-change="handlePageChange"
          @size-change="handlePageSizeChange"
          data-testid="pagination"
        />

        <div class="sort-controls" style="display: inline-flex; align-items: center; gap: 8px; margin-left: 16px;">
          <span style="font-size: 13px; color: #606266;">Sort by:</span>
          <el-select
            v-model="sortBy"
            size="small"
            style="width: 220px;"
            @change="handleSortChange"
            data-testid="phase3-sort-by"
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
            @click="toggleSortOrder"
            data-testid="phase3-sort-order"
          >
            {{ sortOrder === 'desc' ? '↓ Desc' : '↑ Asc' }}
          </el-button>
        </div>

        <el-button
          v-if="scanResult && scanResult.duplicate_groups && scanResult.duplicate_groups.length > 0"
          type="warning"
          plain
          size="small"
          :loading="isBulkWhitelisting"
          @click="whitelistCurrentPage"
          data-testid="whitelist-current-page-btn"
          style="margin-left: 12px;"
        >
          ⚪ Whitelist all on this page ({{ scanResult.duplicate_groups.length }} groups)
        </el-button>
      </div>

      <div class="duplicate-groups-container">
        <div
          v-for="(group, groupIndex) in paginatedGroups"
          :key="`group-${getActualGroupIndex(groupIndex)}`"
          class="duplicate-group"
        >
          <el-card>
            <template #header>
              <div class="group-header">
                <div class="group-actions-left">
                  <span class="group-title">Group {{ getActualGroupIndex(groupIndex) + 1 }} ({{ group.length }} similar images)</span>
                  <el-button
                    size="small"
                    @click="selectAllInGroup(group)"
                    data-testid="select-all-checkbox"
                  >
                    {{ hasAllSelectedInGroup(group) ? '❎ Deselect All' : '☑️ Select All' }}
                  </el-button>
                  <el-button
                    size="small"
                    :disabled="group.length > 3"
                    @click="openGroupPreview(group, groupIndex)"
                    data-testid="preview-group-btn"
                  >
                    🖼️ Preview
                  </el-button>
                  <el-button
                    size="small"
                    type="primary"
                    plain
                    :loading="isComparingFolder"
                    @click="compareFolderForGroup(group)"
                    data-testid="compare-folder-btn"
                  >
                    🔍 Compare Folder
                  </el-button>
                  <el-button
                    size="small"
                    type="warning"
                    plain
                    :loading="gapAnalysisLoading"
                    @click.stop="triggerGapAnalysis('group', undefined, group[0]?.group_id)"
                  >
                    🔎 Gap
                  </el-button>
                </div>
                <div class="group-actions-right">
                  <el-button
                    size="small"
                    @click="addGroupToWhitelist(group, groupIndex)"
                    data-testid="add-to-whitelist-btn"
                  >
                    ✅ Add to Whitelist
                  </el-button>
                  <el-button
                    size="small"
                    type="warning"
                    plain
                    :disabled="group.length !== 2 || getSelectedCountInGroup(group) !== 1"
                    @click="replaceInGroup(group, groupIndex)"
                    data-testid="replace-btn"
                  >
                    🔄 Replace
                  </el-button>
                  <el-button
                    size="small"
                    type="warning"
                    plain
                    :disabled="getSelectedCountInGroup(group) === 0 || getSelectedCountInGroup(group) === group.length"
                    @click="splitGroup(group, groupIndex)"
                  >
                    ✂️ Split Selected ({{ getSelectedCountInGroup(group) }})
                  </el-button>
                  <el-button
                    size="small"
                    type="danger"
                    :disabled="!hasSelectedInGroup(group)"
                    @click="deleteSelectedInGroup(group, groupIndex)"
                  >
                    🗑️ Delete Selected ({{ getSelectedCountInGroup(group) }})
                  </el-button>
                </div>
              </div>
            </template>

            <div class="image-grid">
              <div
                v-for="(image, imageIndex) in group"
                :key="image.file_path"
                :class="['image-item', { selected: selectedForDelete.has(image.file_path) }]"
                @click="toggleFileSelection(image.file_path)"
                style="cursor: pointer;"
              >
                <div class="image-wrapper">
                  <img
                    :src="getImageUrl(image.file_path)"
                    :alt="image.file_path"
                    loading="lazy"
                  />
                  <div v-if="selectedForDelete.has(image.file_path)" class="selected-overlay">
                    <el-icon :size="32"><CircleCheck /></el-icon>
                    <p class="selected-text">SELECTED</p>
                  </div>
                  <div v-if="imageIndex === 0" class="highest-badge">🏆 HIGHEST RESOLUTION</div>
                </div>
                <div class="image-info">
                  <div class="image-filename-row">
                    <p class="image-filename" :title="image.filename || getFilenameFromPath(image.file_path)">
                      {{ image.filename || getFilenameFromPath(image.file_path) }}
                    </p>
                    <span
                      class="image-folder-counts"
                      :title="`${image.folder_dup ?? 0} duplicate file(s) in this folder / ${image.folder_total ?? 0} total file(s) in this folder`"
                    >
                      {{ image.folder_dup ?? 0 }}/{{ image.folder_total ?? 0 }}
                    </span>
                  </div>
                  <p class="image-path" :title="image.display_path || image.file_path">
                    {{ image.display_path || getRelativePath(image.file_path) }}
                  </p>
                  <div class="image-meta">
                    <span>{{ image.resolution }}</span>
                    <span>{{ formatFileSize(image.filesize) }}</span>
                  </div>
                  <div class="image-actions">
                    <el-button
                      size="small"
                      @click.stop="openFolder(image.file_path)"
                      class="action-button"
                      data-testid="open-folder-btn"
                    >
                      📁 Open Folder
                    </el-button>
                    <el-button
                      size="small"
                      type="success"
                      @click.stop="deepWhitelistPath(image.file_path)"
                      class="action-button"
                      data-testid="deep-whitelist-path-btn"
                    >
                      🛡️ Deep Whitelist
                    </el-button>
                    <el-button
                      size="small"
                      type="warning"
                      plain
                      @click.stop="deepReplacePath(image.file_path)"
                      class="action-button"
                      data-testid="deep-replace-path-btn"
                    >
                      🔄 Deep Replace
                    </el-button>
                    <el-button
                      size="small"
                      type="warning"
                      @click.stop="setDeepDeletePath(image.file_path)"
                      class="action-button"
                      data-testid="set-deep-delete-path-btn"
                    >
                      🎯 Deep Delete
                    </el-button>
                  </div>
                </div>
              </div>
            </div>
          </el-card>
        </div>
      </div>
    </div>

    <!-- No Results -->
    <el-card v-else-if="scanResult && scanResult.duplicate_groups.length === 0" class="no-results-card">
      <el-empty description="No duplicates found">
        <template #image>
          <el-icon :size="64" color="#67c23a"><CircleCheck /></el-icon>
        </template>
      </el-empty>
    </el-card>

    <!-- Deep Path Delete Confirmation Dialog -->
    <el-dialog
      v-model="showDeepDeleteDialog"
      :title="deepDeletePreview.folderMoves && deepDeletePreview.folderMoves.length > 0
        ? `Confirm Global Deep Path Delete — ${deepDeletePreview.folderMoves.length} folder(s) will be moved as a unit`
        : 'Confirm Global Deep Path Delete'"
      width="700px"
      :close-on-click-modal="false"
    >
      <div class="deep-delete-dialog">
        <el-alert
          type="warning"
          :closable="false"
          style="margin-bottom: 16px;"
        >
          <template #title>
            <div style="font-size: 14px; font-weight: 600;">
              ⚠️ This action cannot be undone
            </div>
          </template>
          <div style="font-size: 13px; margin-top: 8px;">
            Files will be moved to the delete target folder while preserving their relative structure.
          </div>
        </el-alert>

        <!-- Folder-move banner -->
        <el-alert
          v-if="deepDeletePreview.folderMoves && deepDeletePreview.folderMoves.length > 0"
          type="info"
          :closable="false"
          style="margin-bottom: 16px;"
        >
          <template #title>
            <div style="font-size: 14px; font-weight: 600;">
              📁 Folder-level move detected
            </div>
          </template>
          <div style="font-size: 13px; margin-top: 6px;">
            {{ deepDeletePreview.folderMoves.length }} folder(s) contain only duplicate images and will be
            <strong>moved as a whole unit</strong> instead of file-by-file.
            {{ deepDeletePreview.folderMoves.reduce((s, f) => s + f.file_count, 0) }} files covered this way.
          </div>
        </el-alert>

        <div class="deep-delete-info">
          <div class="info-label">Found Files:</div>
          <div class="info-value">{{ deepDeletePreview.matchedCount }} duplicate files</div>
        </div>

        <div class="deep-delete-info">
          <div class="info-label">Under Path:</div>
          <div class="info-value path-value" data-testid="deep-delete-path-display">{{ deepDeletePreview.deepPath }}</div>
        </div>

        <!-- Folder-level moves section -->
        <div v-if="deepDeletePreview.folderMoves && deepDeletePreview.folderMoves.length > 0" class="file-list-section">
          <div class="file-list-header">
            <span>Folders moved entirely:</span>
            <span class="file-count">({{ deepDeletePreview.folderMoves.length }} folders)</span>
          </div>
          <div class="file-list-container">
            <div
              v-for="(fm, index) in deepDeletePreview.folderMoves"
              :key="index"
              class="file-list-item folder-move-item"
            >
              <span class="file-icon">📁</span>
              <span class="file-path">{{ fm.dir }}</span>
              <span class="folder-file-count">({{ fm.file_count }} files)</span>
            </div>
          </div>
        </div>

        <div v-if="deepDeleteFileListRelative.length > 0" class="file-list-section">
          <div class="file-list-header">
            <span>Individual files:</span>
            <span class="file-count">({{ deepDeleteFileListRelative.length }} files)</span>
          </div>
          <div class="file-list-container">
            <div
              v-for="(file, index) in deepDeleteFileListRelative"
              :key="index"
              class="file-list-item"
            >
              <span class="file-icon">📄</span>
              <span class="file-path">{{ file }}</span>
            </div>
          </div>
        </div>

        <!-- Gap pairs from automatic analysis (when selection_rate >= threshold) -->
        <div v-if="deepDeletePreview.gapPairs && deepDeletePreview.gapPairs.length > 0" class="file-list-section">
          <div class="file-list-header" style="color: #e6a23c;">
            <span>🔎 Possible missed duplicates</span>
            <span class="file-count">({{ deepDeletePreview.gapPairs.length }} pairs)</span>
          </div>
          <p style="font-size:12px;color:#909399;margin:4px 0 8px;">
            Check pairs to include their undetected images in this delete operation.
          </p>
          <div class="file-list-container">
            <div
              v-for="pair in deepDeletePreview.gapPairs"
              :key="pair.gap_id + '-' + pair.candidate_id"
              class="file-list-item"
            >
              <el-checkbox v-model="pair.checked" @click.stop />
              <span class="file-icon">🖼️</span>
              <span class="file-path">{{ pair.gap_file }}</span>
              <span
                class="folder-file-count"
                :style="pair.similarity_pct >= 80 ? 'color:#67c23a' : pair.similarity_pct >= 70 ? 'color:#e6a23c' : 'color:#d4ac0d'"
              >
                {{ pair.similarity_pct.toFixed(1) }}%
              </span>
            </div>
          </div>
        </div>
      </div>

      <template #footer>
        <div class="dialog-footer">
          <el-button @click="cancelDeepDelete">Cancel</el-button>
          <el-button
            type="danger"
            @click="confirmDeepDelete"
            :loading="isDeleting"
          >
            Move {{ deepDeletePreview.matchedCount }} Files
            <template v-if="deepDeletePreview.folderMoves && deepDeletePreview.folderMoves.length > 0">
              ({{ deepDeletePreview.folderMoves.length }} folder{{ deepDeletePreview.folderMoves.length > 1 ? 's' : '' }} + {{ deepDeleteFileListRelative.length }} individual)
            </template>
          </el-button>
        </div>
      </template>
    </el-dialog>

    <!-- Bulk Whitelist Confirmation Dialog -->
    <el-dialog
      v-model="showBulkWhitelistDialog"
      title="Confirm Bulk Whitelist"
      width="900px"
      :close-on-click-modal="false"
    >
      <div class="bulk-whitelist-dialog">
        <el-alert
          type="warning"
          :closable="false"
          style="margin-bottom: 16px;"
        >
          <template #title>
            <div style="font-size: 14px; font-weight: 600;">
              ⚠️ These groups will be marked as "OK" and stop appearing as duplicates
            </div>
          </template>
          <div style="font-size: 13px; margin-top: 8px;">
            Files stay on disk. To undo, remove the group(s) from the Whitelist drawer.
          </div>
        </el-alert>

        <div class="deep-delete-info">
          <div class="info-label">Groups:</div>
          <div class="info-value">{{ bulkWhitelistPreview.groupCount }}</div>
        </div>
        <div class="deep-delete-info">
          <div class="info-label">Total images:</div>
          <div class="info-value">{{ bulkWhitelistPreview.imageCount }}</div>
        </div>

        <div class="file-list-section">
          <div class="file-list-header">
            <span>Preview:</span>
            <span class="file-count">({{ bulkWhitelistPreview.groups.length }} groups)</span>
          </div>
          <div class="bulk-whitelist-preview-list">
            <div
              v-for="(group, gIdx) in bulkWhitelistPreview.groups"
              :key="gIdx"
              class="bulk-whitelist-group"
            >
              <div class="bulk-whitelist-group-header">
                Group {{ gIdx + 1 }}
                <span class="file-count">({{ group.length }} images)</span>
              </div>
              <div class="bulk-whitelist-thumbs">
                <div
                  v-for="(img, iIdx) in group"
                  :key="iIdx"
                  class="bulk-whitelist-thumb"
                  :title="img.file_path"
                >
                  <img
                    :src="getImageUrl(img.file_path)"
                    :alt="img.filename || ''"
                    loading="lazy"
                  />
                  <div class="bulk-whitelist-thumb-label">
                    {{ img.filename || getFilenameFromPath(img.file_path) }}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <template #footer>
        <div class="dialog-footer">
          <el-button @click="cancelBulkWhitelist">Cancel</el-button>
          <el-button
            type="warning"
            @click="confirmBulkWhitelist"
            :loading="isBulkWhitelisting"
            data-testid="bulk-whitelist-confirm-btn"
          >
            Whitelist {{ bulkWhitelistPreview.groupCount }} Groups
          </el-button>
        </div>
      </template>
    </el-dialog>

    <!-- Group Preview Dialog — large side-by-side view (≤3 images only) -->
    <el-dialog
      v-model="showGroupPreviewDialog"
      :title="`Group ${groupPreviewData.actualIndex + 1} Preview (${groupPreviewData.group.length} image${groupPreviewData.group.length > 1 ? 's' : ''})`"
      width="92%"
      top="3vh"
      :close-on-click-modal="true"
      @close="closeGroupPreview"
    >
      <div
        class="group-preview-strip"
        :class="`count-${groupPreviewData.group.length}`"
      >
        <div
          v-for="(img, idx) in groupPreviewData.group"
          :key="idx"
          class="group-preview-cell"
        >
          <div class="group-preview-imgwrap">
            <img
              :src="getImageUrl(img.file_path)"
              :alt="img.filename || img.file_path"
              loading="lazy"
            />
          </div>
          <div class="group-preview-meta">
            <div class="group-preview-filename" :title="img.filename || img.file_path">
              {{ idx === 0 ? '🏆 ' : '' }}{{ img.filename || getFilenameFromPath(img.file_path) }}
            </div>
            <div class="group-preview-detail">
              {{ img.resolution }} · {{ formatFileSize(img.filesize) }}
            </div>
            <div class="group-preview-path" :title="img.file_path">
              {{ img.file_path }}
            </div>
          </div>
        </div>
      </div>

      <template #footer>
        <div class="dialog-footer">
          <el-button @click="closeGroupPreview">Close</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- Deep Replace Confirmation Dialog -->
    <el-dialog
      v-model="showDeepReplaceDialog"
      title="Confirm Deep Replace"
      width="900px"
      :close-on-click-modal="false"
    >
      <div class="deep-replace-dialog">
        <el-alert
          v-if="deepReplacePreview.badGroups.length > 0"
          type="error"
          :closable="false"
          style="margin-bottom: 12px;"
        >
          <template #title>
            <div style="font-size: 14px; font-weight: 700;">
              ❌ Blocked: {{ deepReplacePreview.badGroups.length }} group(s) have a size other than 2
            </div>
          </template>
          <div style="font-size: 13px; margin-top: 6px;">
            Deep Replace can only run when every matched group has exactly 2 images.
            Resolve the blocking groups below (e.g. delete extras, add to whitelist),
            then re-open Deep Replace.
          </div>
        </el-alert>

        <el-alert
          v-else
          type="warning"
          :closable="false"
          style="margin-bottom: 12px;"
        >
          <template #title>
            <div style="font-size: 14px; font-weight: 600;">
              ⚠️ Batch Replace across {{ deepReplacePreview.operations.length }} group(s)
            </div>
          </template>
          <div style="font-size: 13px; margin-top: 8px;">
            For each pair: KEEP's content is copied into ANCHOR's folder with the
            anchor's basename + KEEP's extension. Both originals are backed up to
            the delete target.
          </div>
        </el-alert>

        <div class="deep-delete-info">
          <div class="info-label">Source folder:</div>
          <div class="info-value path-value">{{ deepReplacePreview.folderPath }}</div>
        </div>
        <div class="deep-delete-info">
          <div class="info-label">Total matched groups:</div>
          <div class="info-value">
            {{ deepReplacePreview.operations.length + deepReplacePreview.badGroups.length }}
            <span style="color: #67c23a;"> ({{ deepReplacePreview.operations.length }} ready)</span>
            <span v-if="deepReplacePreview.badGroups.length" style="color: #f56c6c;">
              ({{ deepReplacePreview.badGroups.length }} blocked)
            </span>
          </div>
        </div>

        <!-- Bad groups section — listed FIRST so user notices the blockers -->
        <div v-if="deepReplacePreview.badGroups.length" class="file-list-section">
          <div class="file-list-header" style="color: #f56c6c;">
            <span>❌ Blocking groups (size ≠ 2):</span>
            <span class="file-count">({{ deepReplacePreview.badGroups.length }})</span>
          </div>
          <div class="deep-replace-list">
            <div
              v-for="(g, idx) in deepReplacePreview.badGroups"
              :key="'bad-' + idx"
              class="deep-replace-bad-group"
            >
              <div class="deep-replace-bad-header" style="display:flex;align-items:center;justify-content:space-between;">
                <span>Group with {{ g.length }} images (cannot Replace)</span>
                <el-button
                  size="small"
                  type="warning"
                  plain
                  :disabled="g.filter((img: any) => selectedForDelete.has(img.file_path)).length === 0 || g.filter((img: any) => selectedForDelete.has(img.file_path)).length === g.length"
                  @click.stop="deepReplaceSplitGroup(g, idx)"
                >
                  ✂️ Split Selected ({{ g.filter((img: any) => selectedForDelete.has(img.file_path)).length }})
                </el-button>
              </div>
              <div class="deep-replace-bad-thumbs">
                <div
                  v-for="(img, i) in g"
                  :key="i"
                  class="deep-replace-thumb"
                  :style="{ cursor: 'pointer', opacity: selectedForDelete.has(img.file_path) ? 1 : 0.75 }"
                  @click.stop="toggleFileSelection(img.file_path)"
                >
                  <img
                    :src="getImageUrl(img.file_path)"
                    :alt="img.filename || ''"
                    loading="lazy"
                    :style="selectedForDelete.has(img.file_path) ? 'outline: 3px solid #409eff; border-radius: 4px;' : ''"
                  />
                  <div class="deep-replace-thumb-label" :title="img.file_path">
                    {{ img.filename || getFilenameFromPath(img.file_path) }}
                  </div>
                  <div v-if="selectedForDelete.has(img.file_path)" style="font-size:10px;color:#409eff;font-weight:700;">✔ Selected</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Good groups (operations) section -->
        <div v-if="deepReplacePreview.operations.length" class="file-list-section">
          <div class="file-list-header" style="color: #67c23a;">
            <span>✓ Ready to Replace:</span>
            <span class="file-count">({{ deepReplacePreview.operations.length }} pairs)</span>
          </div>
          <div class="deep-replace-list">
            <div
              v-for="(op, idx) in deepReplacePreview.operations"
              :key="'good-' + idx"
              class="deep-replace-pair"
            >
              <div class="deep-replace-pair-header">Pair {{ idx + 1 }}</div>
              <div class="deep-replace-pair-thumbs">
                <div class="deep-replace-thumb deep-replace-thumb-keep">
                  <div class="deep-replace-thumb-tag">KEEP (content)</div>
                  <img :src="getImageUrl(op.selected.file_path)" :alt="op.selected.filename || ''" loading="lazy" />
                  <div class="deep-replace-thumb-label" :title="op.selected.file_path">
                    {{ op.selected.filename || getFilenameFromPath(op.selected.file_path) }}
                  </div>
                </div>
                <div class="deep-replace-arrow">→</div>
                <div class="deep-replace-thumb deep-replace-thumb-anchor">
                  <div class="deep-replace-thumb-tag">ANCHOR (location + name)</div>
                  <img :src="getImageUrl(op.anchor.file_path)" :alt="op.anchor.filename || ''" loading="lazy" />
                  <div class="deep-replace-thumb-label" :title="op.anchor.file_path">
                    {{ op.anchor.filename || getFilenameFromPath(op.anchor.file_path) }}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <template #footer>
        <div class="dialog-footer">
          <el-button @click="cancelDeepReplace">Cancel</el-button>
          <el-button
            type="warning"
            @click="confirmDeepReplace"
            :loading="isDeepReplacing"
            :disabled="deepReplacePreview.badGroups.length > 0 || deepReplacePreview.operations.length === 0"
            data-testid="deep-replace-confirm-btn"
          >
            {{ deepReplacePreview.badGroups.length > 0
              ? `Replace blocked (${deepReplacePreview.badGroups.length} bad)`
              : `Replace ${deepReplacePreview.operations.length} Pair(s)` }}
          </el-button>
        </div>
      </template>
    </el-dialog>

    <!-- Gap Analysis Dialog -->
    <GapAnalysisDialog
      v-model="showGapDialog"
      :pairs="gapPairs"
      :context="gapDialogContext"
      @close="showGapDialog = false"
      @confirm="(includeInDelete) => submitConfirmGapPairs(includeInDelete)"
    />
  </div>

  <el-backtop :right="24" :bottom="64" :visibility-height="300" />
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { CircleCheck } from '@element-plus/icons-vue'
import { useDuplicateFinderView } from './DuplicateFinderView'
import GapAnalysisDialog from './GapAnalysisDialog.vue'

const router = useRouter()
function goBack() { router.push('/') }
function goToSettings() { router.push('/duplicate-finder/settings') }

const {
  // Data
  selectedFolders,
  threshold,
  deepPathDelete,
  isScanning,
  isSaving,
  isDeleting,
  isVerifying,
  scanProgress,
  scanResult,
  selectedForDelete,
  hasResults,
  settings,
  // Pagination
  currentPage,
  pageSize,
  totalPages,
  totalGroupsAll,
  totalFilesInDb,
  isLoadingPage,
  paginatedGroups,
  // 3-Phase workflow states
  isPhase1Running,
  isPhase2Running,
  isPhase25Running,
  isPhase3Running,
  isBulkWhitelisting,
  isComparingFolder,
  phase25NeedsAttention,
  phase25TooltipContent,
  phaseProgress,
  phase1Summary,
  phase2Summary,
  // Deep delete dialog
  showDeepDeleteDialog,
  deepDeletePreview,
  deepDeleteFileListRelative,
  // Helper functions
  getFilenameFromPath,
  splitPath,
  // Methods
  startScan,
  stopScan,
  rescanFromCache,
  // 3-Phase workflow methods
  runPhase1,
  stopPhase1,
  runPhase2,
  stopPhase2,
  forceRerunPhase2,
  runPhase25,
  stopPhase25,
  whitelistCurrentPage,
  cancelBulkWhitelist,
  confirmBulkWhitelist,
  showBulkWhitelistDialog,
  bulkWhitelistPreview,
  deepWhitelistPath,
  compareFolderForGroup,
  runCompareAllFolders,
  isCompareAllRunning,
  runFullPipeline,
  isFullPipelineRunning,
  showGroupPreviewDialog,
  groupPreviewData,
  openGroupPreview,
  closeGroupPreview,
  replaceInGroup,
  deepReplacePath,
  showDeepReplaceDialog,
  deepReplacePreview,
  isDeepReplacing,
  cancelDeepReplace,
  confirmDeepReplace,
  deepReplaceSplitGroup,
  runPhase3,
  stopPhase3,
  toggleFileSelection,
  hasSelectedInGroup,
  hasAllSelectedInGroup,
  selectAllInGroup,
  getSelectedCountInGroup,
  deleteSelectedInGroup,
  openFolder,
  getImageUrl,
  getRelativePath,
  formatFileSize,
  getActualGroupIndex,
  handlePageChange,
  handlePageSizeChange,
  sortBy,
  sortOrder,
  SORT_OPTIONS,
  handleSortChange,
  toggleSortOrder,
  executeDeepPathDelete,
  confirmDeepDelete,
  cancelDeepDelete,
  setDeepDeletePath,
  // Gap Analysis
  showGapDialog,
  gapPairs,
  gapAnalysisLoading,
  gapDialogContext,
  triggerGapAnalysis,
  submitConfirmGapPairs,
  addGroupToWhitelist,
  verifyAndCleanup,
  splitGroup,
} = useDuplicateFinderView()
</script>

<style scoped>
/* Pagination Styles */
.duplicate-groups-header {
  margin-bottom: 20px;
  display: flex;
  justify-content: center;
}

/* Virtual Scroller Styles */
.duplicate-groups-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.duplicate-finder-container {
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

.card-header > div {
  display: flex;
  flex-direction: column;
  gap: 5px;
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

/* Input Section */
.input-section {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* Settings Section */
.settings-section h3,
.folder-section h3 {
  margin: 0 0 16px 0;
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.settings-section {
  padding: 20px;
  background: #f5f7fa;
  border-radius: 8px;
}

.settings-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 20px;
}

.setting-item label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
  font-size: 14px;
  color: #606266;
}

.settings-hint {
  margin: 4px 0 0 0;
  font-size: 12px;
  color: #909399;
}

.settings-hint-small {
  margin: 4px 0 0 0;
  font-size: 11px;
  color: #909399;
}

.performance-inputs-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.performance-input-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 0 0 auto;
}

.performance-input-item label {
  font-size: 12px;
  font-weight: 500;
  color: #606266;
  margin: 0;
  white-space: nowrap;
}

.performance-input-item .el-input-number {
  width: 100px;
}

.phase-settings-group {
  margin-bottom: 20px;
  padding: 15px;
  background: #f5f7fa;
  border-radius: 4px;
}

.phase-settings-group h5 {
  margin: 0 0 12px 0;
  font-size: 14px;
  color: #606266;
  font-weight: 600;
}

/* Settings Container with Collapse */
.settings-container {
  padding: 20px;
  background: #f5f7fa;
  border-radius: 8px;
}

.settings-collapse {
  background: transparent;
}

.settings-collapse :deep(.el-collapse-item__header) {
  font-size: 15px;
  font-weight: 500;
  background: white;
  padding: 12px 16px;
  border-radius: 6px;
  margin-bottom: 8px;
}

.settings-collapse :deep(.el-collapse-item__content) {
  padding: 16px;
  background: white;
  border-radius: 0 0 6px 6px;
  margin-top: -8px;
  margin-bottom: 8px;
}

.collapse-content {
  padding: 0;
}

/* Folder Section - Keep for other uses */
.folder-section {
  padding: 20px;
  background: #f5f7fa;
  border-radius: 8px;
}

.folder-section h3 {
  margin: 0 0 20px 0;
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}

.folder-section h4 {
  margin: 16px 0 12px 0;
  font-size: 14px;
  font-weight: 600;
  color: #606266;
}

.folder-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.folder-list-edit {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.folder-item-with-root {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 12px;
  background: #fafafa;
  border-radius: 6px;
  border: 1px solid #e4e7ed;
}

.folder-item {
  display: flex;
  gap: 12px;
  align-items: center;
}

.folder-checkbox {
  flex: 0 0 auto;
  margin: 0;
}

.folder-input-group {
  flex: 1;
  display: flex;
  gap: 12px;
}

.folder-path-input {
  flex: 1;
  min-width: 0;
}

.root-path-input {
  flex: 1;
  min-width: 0;
}

.no-folders {
  padding: 20px;
  text-align: center;
  color: #909399;
  font-size: 14px;
  background: #fafafa;
  border-radius: 6px;
  border: 1px dashed #dcdfe6;
}

/* Action Section */
.action-section {
  display: flex;
  align-items: center;
  gap: 24px;
  flex-wrap: wrap;
}

/* Action Buttons - 3 Phase Workflow */
.action-buttons {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  flex: 1;
}

/* Deep Path Delete Inline */
.deep-delete-inline {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background: #fef0f0;
  border-radius: 6px;
  border: 1px solid #fde2e2;
}

/* Remove old styles that are no longer used */
.folder-row {
  display: none;
}

.folder-label {
  display: none;
}

.root-path-row {
  display: none;
}

.root-path-label {
  display: none;
}

.folder-item {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 12px;
  background: white;
  border-radius: 6px;
  border: 1px solid #dcdfe6;
}

.folder-item .el-checkbox {
  flex: 1;
  margin: 0;
}

.folder-item .el-checkbox :deep(.el-checkbox__label) {
  width: 100%;
  overflow: visible;
}

.folder-item .el-input {
  margin-left: 8px;
  flex: 1;
}

.no-folders {
  padding: 16px;
  text-align: center;
  background: white;
  border-radius: 6px;
  color: #909399;
  margin-bottom: 0;
}

.no-folders p {
  margin: 0;
  font-size: 13px;
}

.hint {
  margin: 0;
  color: #909399;
  font-size: 13px;
}

.scan-button {
  flex: 0 0 auto;
}

/* Progress Section */
.progress-section {
  margin-top: 20px;
  padding: 20px;
  background: #f5f7fa;
  border-radius: 8px;
}

.progress-message {
  margin-top: 12px;
  margin-bottom: 4px;
  font-size: 14px;
  color: #606266;
}

.progress-count {
  margin: 0;
  font-size: 13px;
  color: #909399;
}

/* Results Section */
.results-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.tips-card {
  background: #f0f9ff;
  border: 1px solid #409eff;
}

.tips-card h3 {
  margin: 0;
  font-size: 16px;
  color: #409eff;
}

.tips-list {
  margin: 8px 0 0 0;
  padding-left: 20px;
  list-style: disc;
}

.tips-list li {
  margin: 8px 0;
  font-size: 14px;
  line-height: 1.6;
}

.summary-card {
  position: sticky;
  top: 0;
  z-index: 10;
}

.summary-content {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 16px;
}

.summary-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.summary-label {
  font-size: 13px;
  color: #909399;
}

.summary-value {
  font-size: 24px;
  font-weight: 600;
}

.summary-value.highlight {
  color: #409eff;
}

.summary-value.warning {
  color: #f56c6c;
}

.delete-button {
  width: 100%;
}

.no-results-card {
  margin-top: 20px;
}

/* Duplicate Groups */
.duplicate-group {
  margin-bottom: 16px;
}

.group-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.group-actions-left {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.group-actions-right {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
  margin-left: auto;
}

.group-actions {
  display: flex;
  gap: 8px;
}

.group-title {
  font-weight: 600;
  font-size: 16px;
}

.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
  gap: 16px;
}

.image-item {
  cursor: pointer;
  border: 2px solid transparent;
  border-radius: 8px;
  overflow: hidden;
  transition: all 0.2s;
  background: #fff;
  width: 400px;
}

.image-item:hover {
  border-color: #409eff;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}

.image-item.selected {
  border-color: #f56c6c;
  background: #fef0f0;
}

.image-item.first {
  border-color: #67c23a;
}

.image-wrapper {
  position: relative;
  width: 400px;
  height: 300px;
  overflow: hidden;
  background: #f5f7fa;
}

.image-wrapper img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.selected-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(64, 158, 255, 0.7);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: white;
}

.selected-text {
  margin: 8px 0 0 0;
  font-size: 16px;
  font-weight: 700;
}

.highest-badge {
  position: absolute;
  top: 8px;
  right: 8px;
  background: #67c23a;
  color: white;
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}

.first-badge {
  position: absolute;
  top: 8px;
  right: 8px;
  background: #67c23a;
  color: white;
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}

.image-info {
  padding: 12px;
}

.image-filename-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  margin: 0 0 4px 0;
}

.image-filename {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  min-width: 0;
}

.image-folder-counts {
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 600;
  color: #606266;
  font-variant-numeric: tabular-nums;
  padding: 1px 6px;
  background: #f4f4f5;
  border-radius: 3px;
  white-space: nowrap;
}

.image-path {
  margin: 0 0 8px 0;
  font-size: 11px;
  color: #909399;
  word-break: break-all;
  line-height: 1.4;
  max-height: 2.8em;
  overflow: hidden;
  font-family: monospace;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.image-meta {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
}

.image-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px;
}

.image-actions .action-button {
  margin: 0;
  width: 100%;
}

/* Settings Drawer */
.whitelist-content {
  padding: 0 20px;
}

.settings-section-drawer {
  margin-bottom: 24px;
}

.settings-section-drawer h3 {
  margin: 0 0 16px 0;
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}

.settings-section-drawer .setting-item {
  margin-bottom: 20px;
}

.settings-section-drawer .setting-item label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
  font-size: 14px;
  color: #606266;
}

/* Folder List in Drawer */
.folder-list-drawer {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.folder-item-drawer {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 12px;
  background: #fafafa;
  border-radius: 6px;
  border: 1px solid #e4e7ed;
}

.folder-inputs-drawer {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.exclude-item-drawer {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 8px;
  background: #fafafa;
  border-radius: 6px;
  border: 1px solid #e4e7ed;
}

.no-folders-drawer {
  padding: 16px;
  text-align: center;
  color: #909399;
  font-size: 13px;
  background: #fafafa;
  border-radius: 6px;
  border: 1px dashed #dcdfe6;
}

.settings-hint-text {
  margin: 0 0 16px 0;
  padding: 12px;
  background: #f0f9ff;
  border-radius: 6px;
  color: #606266;
  font-size: 14px;
}

.rule-item {
  margin-bottom: 20px;
  padding: 16px;
  background: #f5f7fa;
  border-radius: 8px;
}

.rule-item label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
  font-size: 14px;
  color: #606266;
}

.rule-description {
  margin: 8px 0 0 24px;
  font-size: 13px;
  color: #909399;
  line-height: 1.5;
}

.rule-description code {
  padding: 2px 6px;
  background: #e4e7ed;
  border-radius: 3px;
  font-family: 'Monaco', 'Menlo', 'Courier New', monospace;
  font-size: 12px;
  color: #303133;
}

.prefer-folders-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 8px;
}

.prefer-folder-item {
  display: flex;
  gap: 8px;
  align-items: center;
}

.prefer-folder-item .el-input {
  flex: 1;
}

.whitelist-hint {
  margin: 0 0 16px 0;
  padding: 12px;
  background: #f0f9ff;
  border-radius: 6px;
  color: #606266;
  font-size: 14px;
}

.whitelist-groups-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.whitelist-group-card {
  padding: 16px;
  background: #f5f7fa;
  border-radius: 8px;
  border: 1px solid #dcdfe6;
}

.whitelist-group-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid #e4e7ed;
}

.whitelist-group-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  flex: 1;
}

.whitelist-group-time {
  font-size: 12px;
  color: #909399;
}

.whitelist-group-members {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
  gap: 12px;
}

.whitelist-member-thumbnail {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.whitelist-thumbnail-img {
  width: 100%;
  height: 80px;
  object-fit: cover;
  border-radius: 4px;
  margin-bottom: 6px;
  border: 1px solid #dcdfe6;
}

.whitelist-member-filename {
  margin: 0;
  font-size: 11px;
  color: #606266;
  text-align: center;
  word-break: break-word;
  line-height: 1.3;
}

/* Action Buttons */

/* Phase Progress Display */
.phase-progress-display {
  margin-top: 20px;
  padding: 16px;
  background: #f0f9ff;
  border-radius: 8px;
  border-left: 4px solid #409eff;
}

.phase-message {
  margin: 0 0 8px 0;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.phase-details {
  margin: 0;
  font-size: 13px;
  color: #606266;
  font-family: 'Monaco', 'Menlo', 'Courier New', monospace;
}

/* Deep Delete Dialog */
.deep-delete-dialog {
  padding: 0;
}

.deep-delete-info {
  display: flex;
  align-items: flex-start;
  margin-bottom: 16px;
  padding: 12px;
  background: #f5f7fa;
  border-radius: 6px;
}

.info-label {
  font-weight: 600;
  color: #606266;
  min-width: 120px;
  font-size: 14px;
}

.info-value {
  flex: 1;
  color: #303133;
  font-size: 14px;
}

.path-value {
  font-family: 'Monaco', 'Menlo', 'Courier New', monospace;
  font-size: 12px;
  word-break: break-all;
  background: #fff;
  padding: 8px;
  border-radius: 4px;
  border: 1px solid #dcdfe6;
}

.file-list-section {
  margin-top: 20px;
}

.bulk-whitelist-dialog .deep-delete-info {
  margin-bottom: 8px;
}

.bulk-whitelist-preview-list {
  max-height: 480px;
  overflow-y: auto;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  padding: 8px;
  background: #fafafa;
}

.bulk-whitelist-group {
  border-bottom: 1px dashed #dcdfe6;
  padding: 8px 0;
}
.bulk-whitelist-group:last-child {
  border-bottom: none;
}

.bulk-whitelist-group-header {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 6px;
}

.bulk-whitelist-thumbs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.bulk-whitelist-thumb {
  width: 100px;
  display: flex;
  flex-direction: column;
  align-items: center;
  font-size: 11px;
  color: #606266;
}

/* ===== Group Preview Dialog ===== */
.group-preview-strip {
  display: grid;
  gap: 12px;
  width: 100%;
}
.group-preview-strip.count-1 { grid-template-columns: 1fr; }
.group-preview-strip.count-2 { grid-template-columns: 1fr 1fr; }
.group-preview-strip.count-3 { grid-template-columns: 1fr 1fr 1fr; }

.group-preview-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 0;
}

.group-preview-imgwrap {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #1e1e1e;
  border-radius: 6px;
  overflow: hidden;
  /* dialog top=3vh; subtract footer/header/meta ≈ ~22vh */
  height: 70vh;
}
.group-preview-imgwrap img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  display: block;
}

.group-preview-meta {
  width: 100%;
  margin-top: 8px;
  font-size: 12px;
  color: #606266;
  text-align: center;
}
.group-preview-filename {
  font-weight: 600;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.group-preview-detail {
  margin-top: 2px;
  font-size: 11px;
  color: #909399;
}
.group-preview-path {
  margin-top: 2px;
  font-size: 11px;
  color: #c0c4cc;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  direction: rtl;  /* show the tail (filename end) when truncating */
  text-align: left;
}

/* ===== Deep Replace Dialog ===== */
.deep-replace-list {
  max-height: 480px;
  overflow-y: auto;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  padding: 8px;
  background: #fafafa;
}
.deep-replace-pair {
  border-bottom: 1px dashed #dcdfe6;
  padding: 8px 0;
}
.deep-replace-pair:last-child { border-bottom: none; }
.deep-replace-pair-header {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 6px;
}
.deep-replace-pair-thumbs {
  display: flex;
  align-items: center;
  gap: 12px;
}
.deep-replace-thumb {
  width: 140px;
  display: flex;
  flex-direction: column;
  align-items: center;
  font-size: 11px;
  color: #606266;
}
.deep-replace-thumb img {
  width: 140px;
  height: 140px;
  object-fit: cover;
  border-radius: 4px;
  border: 1px solid #dcdfe6;
  background: #fff;
}
.deep-replace-thumb-tag {
  font-size: 10px;
  font-weight: 700;
  margin-bottom: 4px;
  padding: 2px 6px;
  border-radius: 3px;
}
.deep-replace-thumb-keep .deep-replace-thumb-tag {
  background: #67c23a;
  color: white;
}
.deep-replace-thumb-anchor .deep-replace-thumb-tag {
  background: #e6a23c;
  color: white;
}
.deep-replace-thumb-label {
  width: 100%;
  text-align: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-top: 2px;
}
.deep-replace-arrow {
  font-size: 24px;
  color: #909399;
}

.deep-replace-bad-group {
  border: 1px solid #f56c6c;
  background: #fef0f0;
  border-radius: 4px;
  padding: 8px;
  margin-bottom: 8px;
}
.deep-replace-bad-group:last-child { margin-bottom: 0; }
.deep-replace-bad-header {
  font-size: 13px;
  font-weight: 700;
  color: #f56c6c;
  margin-bottom: 6px;
}
.deep-replace-bad-thumbs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.bulk-whitelist-thumb img {
  width: 100px;
  height: 100px;
  object-fit: cover;
  border-radius: 4px;
  border: 1px solid #dcdfe6;
  background: #fff;
}

.bulk-whitelist-thumb-label {
  width: 100%;
  text-align: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-top: 2px;
}

.file-list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  font-weight: 600;
  color: #303133;
  font-size: 14px;
}

.file-count {
  color: #909399;
  font-weight: normal;
  font-size: 13px;
}

.file-list-container {
  max-height: 400px;
  overflow-y: auto;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  background: #fff;
}

.file-list-item {
  display: flex;
  align-items: center;
  padding: 10px 12px;
  border-bottom: 1px solid #f0f0f0;
  transition: background 0.2s;
}

.file-list-item:last-child {
  border-bottom: none;
}

.file-list-item:hover {
  background: #f5f7fa;
}

.file-icon {
  margin-right: 8px;
  font-size: 14px;
  flex-shrink: 0;
}

.file-path {
  font-family: 'Monaco', 'Menlo', 'Courier New', monospace;
  font-size: 12px;
  color: #606266;
  word-break: break-all;
  line-height: 1.5;
  flex: 1;
}

.folder-move-item {
  background: #f0f9ff;
}

.folder-file-count {
  font-size: 11px;
  color: #909399;
  margin-left: 6px;
  flex-shrink: 0;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}
</style>
