<template>
  <div class="duplicate-finder-container">
    <el-card class="main-card">
      <template #header>
        <div class="card-header">
          <div>
            <h2>Duplicate Image Finder</h2>
            <span class="subtitle">Find and remove duplicate images using perceptual hashing</span>
          </div>
          <el-button @click="showWhitelistDrawer = true">⚙️ Settings</el-button>
        </div>
      </template>

      <!-- Action Buttons with Deep Path Delete -->
      <div class="action-section">
        <!-- 3 Phase Workflow Buttons -->
        <div class="action-buttons">
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

          <!-- Phase 2.5: Materialize Groups (manual trigger between Phase 2 and Phase 3) -->
          <el-tooltip
            :content="phase25TooltipContent"
            placement="top"
          >
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
          </el-tooltip>
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
        </div>

        <!-- Deep Path Delete - Compact -->
        <div class="deep-delete-inline">
          <el-tooltip content="Preserve folder structure when deleting. Example: /a/folder1/sub/file.jpg → /to_del/sub/file.jpg" placement="top">
            <el-input
              v-model="deepPathDelete"
              placeholder="Deep Path Delete"
              style="width: 560px;"
              size="default"
              data-testid="deep-delete-path-input"
            />
          </el-tooltip>
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
            <span class="summary-label">Total Files Scanned:</span>
            <span class="summary-value">{{ scanResult.total_files }}</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">Duplicate Groups:</span>
            <span class="summary-value highlight">{{ scanResult.duplicate_groups.length }}</span>
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
            :title="sortOrder === 'desc' ? 'Descending (click to switch to ascending)' : 'Ascending (click to switch to descending)'"
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
                <span class="group-title">Group {{ getActualGroupIndex(groupIndex) + 1 }} ({{ group.length }} similar images)</span>
                <div class="group-actions">
                  <el-button
                    size="small"
                    @click="selectAllInGroup(group)"
                    data-testid="select-all-checkbox"
                  >
                    {{ hasAllSelectedInGroup(group) ? '❎ Deselect All' : '☑️ Select All' }}
                  </el-button>
                  <el-button
                    size="small"
                    @click="addGroupToWhitelist(group, groupIndex)"
                    data-testid="add-to-whitelist-btn"
                  >
                    ✅ Add to Whitelist
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
                    <p class="selected-text">DELETE</p>
                  </div>
                  <div v-if="imageIndex === 0" class="highest-badge">🏆 HIGHEST RESOLUTION</div>
                </div>
                <div class="image-info">
                  <p class="image-filename" :title="image.filename || getFilenameFromPath(image.file_path)">
                    {{ image.filename || getFilenameFromPath(image.file_path) }}
                  </p>
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
                      type="warning"
                      @click.stop="setDeepDeletePath(image.file_path)"
                      class="action-button"
                      data-testid="set-deep-delete-path-btn"
                    >
                      🎯 Deep Delete Path
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

    <!-- Settings Drawer -->
    <el-drawer
      v-model="showWhitelistDrawer"
      title="Settings"
      :size="600"
    >
      <div class="whitelist-content">
        <!-- Folder Configuration -->
        <div class="settings-section-drawer">
          <h3>📁 Scan Folders</h3>
          <div style="margin-bottom: 12px;">
            <el-button size="small" @click="addFolderPath">+ Add Folder</el-button>
          </div>

          <div v-if="settings.folder_paths && settings.folder_paths.length > 0" class="folder-list-drawer">
            <div v-for="(path, index) in settings.folder_paths" :key="index" class="folder-item-drawer">
              <div class="folder-inputs-drawer">
                <el-input
                  v-model="settings.folder_paths[index]"
                  placeholder="Folder Path"
                  size="small"
                />
              </div>
              <el-button
                @click="removeFolderPath(index)"
                type="danger"
                size="small"
                :icon="'Delete'"
              >
                Remove
              </el-button>
            </div>
          </div>
          <div v-else class="no-folders-drawer">
            <p>No folder paths configured.</p>
          </div>
        </div>

        <el-divider />

        <!-- Exclude Folders -->
        <div class="settings-section-drawer">
          <h3>🚫 Exclude Folders</h3>
          <div style="margin-bottom: 12px;">
            <el-button size="small" @click="addExcludeFolderPath">+ Add Exclude Folder</el-button>
          </div>

          <div v-if="settings.exclude_folder_paths && settings.exclude_folder_paths.length > 0" class="folder-list-drawer">
            <div v-for="(path, index) in settings.exclude_folder_paths" :key="index" class="exclude-item-drawer">
              <el-input
                v-model="settings.exclude_folder_paths[index]"
                placeholder="/path/to/exclude/folder"
                size="small"
                style="flex: 1"
              />
              <el-button
                @click="removeExcludeFolderPath(index)"
                type="danger"
                size="small"
                :icon="'Delete'"
              >
                Remove
              </el-button>
            </div>
          </div>
          <div v-else class="no-folders-drawer">
            <p>No exclude folders configured.</p>
          </div>
        </div>

        <el-divider />

        <!-- Advanced Settings -->
        <div class="settings-section-drawer">
          <h3>Advanced Settings</h3>

          <div class="setting-item">
            <label>Delete Target Path</label>
            <el-input v-model="settings.delete_target_path" placeholder="/path/to/delete/folder" />
            <p class="settings-hint">Where deleted files will be moved to</p>
          </div>

          <el-divider />

          <div class="setting-item">
            <label>Similarity Threshold: {{ threshold }}%</label>
            <el-slider
              v-model="threshold"
              :min="60"
              :max="100"
              show-stops
            />
            <p class="settings-hint">Higher = more strict (only very similar images). Range: 60%-100%</p>
          </div>

          <div class="setting-item">
            <label>PHash Database Path</label>
            <el-input v-model="settings.phash_db_path" placeholder="/path/to/phash_cache.db" />
            <p class="settings-hint">Path to the perceptual hash cache database</p>
          </div>

          <div class="setting-item">
            <label>Max CPU Cores: {{ settings.max_cpu_cores || 1 }} / {{ settings.system_cpu_count || '?' }}</label>
            <el-slider
              v-model="settings.max_cpu_cores"
              :min="1"
              :max="settings.system_cpu_count || 12"
              :step="1"
              :marks="getCpuMarks()"
              show-stops
            />
            <p class="settings-hint">
              Number of CPU cores to use for hash computation. Lower values reduce system load.
              Default: 1
            </p>
          </div>

          <div class="setting-item">
            <label>Page Size: {{ settings.page_size || 100 }} groups/page</label>
            <el-input-number
              v-model="settings.page_size"
              :min="20"
              :max="500"
              :step="10"
              controls-position="right"
              style="width: 100%"
            />
            <p class="settings-hint">
              Number of duplicate groups to display per page. Range: 20-500, Default: 100
            </p>
          </div>

          <el-divider />

          <h4 style="margin: 16px 0 12px 0; font-size: 14px; color: #606266;">Performance Settings</h4>
          <p class="settings-hint" style="margin-bottom: 16px;">
            Configure performance parameters for each phase. Add delays to reduce CPU/disk load or test with slower execution.
          </p>

          <!-- Phase 1 Settings -->
          <div class="phase-settings-group">
            <h5>Phase 1: Scan & Compute Hash</h5>
            <div class="performance-inputs-row">
              <div class="performance-input-item">
                <label>Worker Handler Size</label>
                <el-tooltip content="Number of files each worker processes at once. Recommended: 1 (best progress granularity)" placement="top">
                  <el-input-number
                    v-model="settings.phase1.worker_handler_size"
                    :min="1"
                    :max="100"
                    :step="1"
                    size="small"
                    controls-position="right"
                  />
                </el-tooltip>
                <p class="settings-hint-small">Recommended: 1</p>
              </div>

              <div class="performance-input-item">
                <label>DB Commit Batch</label>
                <el-tooltip content="Accumulate N results before committing to database. Recommended: 100 (normal), 1000 (large scale)" placement="top">
                  <el-input-number
                    v-model="settings.phase1.db_commit_batch_size"
                    :min="1"
                    :max="10000"
                    :step="10"
                    size="small"
                    controls-position="right"
                  />
                </el-tooltip>
                <p class="settings-hint-small">Recommended: 100</p>
              </div>

              <div class="performance-input-item">
                <label>Progress Update Interval</label>
                <el-tooltip content="Send progress update every N files. Recommended: 100 (normal), 1000 (large scale)" placement="top">
                  <el-input-number
                    v-model="settings.phase1.progress_update_interval"
                    :min="1"
                    :max="10000"
                    :step="10"
                    size="small"
                    controls-position="right"
                  />
                </el-tooltip>
                <p class="settings-hint-small">Recommended: 100</p>
              </div>

              <div class="performance-input-item">
                <label>IPC Chunk Size</label>
                <el-tooltip content="Batch tasks for IPC optimization. Recommended: 10 (fixed, rarely needs tuning)" placement="top">
                  <el-input-number
                    v-model="settings.phase1.ipc_chunk_size"
                    :min="1"
                    :max="1000"
                    :step="1"
                    size="small"
                    controls-position="right"
                  />
                </el-tooltip>
                <p class="settings-hint-small">Recommended: 10</p>
              </div>

              <div class="performance-input-item">
                <label>Scan Delay (s)</label>
                <el-tooltip content="Delay between file scans. For testing only." placement="top">
                  <el-input-number
                    v-model="settings.phase1.scan_delay"
                    :min="0"
                    :max="5"
                    :step="0.1"
                    :precision="1"
                    size="small"
                    controls-position="right"
                  />
                </el-tooltip>
                <p class="settings-hint-small">0s (no delay)</p>
              </div>

              <div class="performance-input-item">
                <label>Compute Delay (s)</label>
                <el-tooltip content="Delay between hash computations. For testing only." placement="top">
                  <el-input-number
                    v-model="settings.phase1.compute_delay"
                    :min="0"
                    :max="5"
                    :step="0.1"
                    :precision="1"
                    size="small"
                    controls-position="right"
                  />
                </el-tooltip>
                <p class="settings-hint-small">0s (no delay)</p>
              </div>
            </div>
          </div>

          <!-- Phase 2 Settings -->
          <div class="phase-settings-group">
            <h5>Phase 2: Compare Similarities</h5>
            <div class="performance-inputs-row">
              <div class="performance-input-item">
                <label>Worker Handler Size</label>
                <el-tooltip content="Number of files each worker processes at once. Recommended: 1 (best progress granularity)" placement="top">
                  <el-input-number
                    v-model="settings.phase2.worker_handler_size"
                    :min="1"
                    :max="100"
                    :step="1"
                    size="small"
                    controls-position="right"
                  />
                </el-tooltip>
                <p class="settings-hint-small">Recommended: 1</p>
              </div>

              <div class="performance-input-item">
                <label>DB Commit Batch</label>
                <el-tooltip content="Accumulate N results before committing to database. Recommended: 100 (normal), 1000 (large scale)" placement="top">
                  <el-input-number
                    v-model="settings.phase2.db_commit_batch_size"
                    :min="1"
                    :max="10000"
                    :step="10"
                    size="small"
                    controls-position="right"
                  />
                </el-tooltip>
                <p class="settings-hint-small">Recommended: 100</p>
              </div>

              <div class="performance-input-item">
                <label>Progress Update Interval</label>
                <el-tooltip content="Send progress update every N files. Recommended: 100 (normal), 1000 (large scale)" placement="top">
                  <el-input-number
                    v-model="settings.phase2.progress_update_interval"
                    :min="1"
                    :max="10000"
                    :step="10"
                    size="small"
                    controls-position="right"
                  />
                </el-tooltip>
                <p class="settings-hint-small">Recommended: 100</p>
              </div>

              <div class="performance-input-item">
                <label>IPC Chunk Size</label>
                <el-tooltip content="Batch tasks for IPC optimization. Recommended: 10 (fixed, rarely needs tuning)" placement="top">
                  <el-input-number
                    v-model="settings.phase2.ipc_chunk_size"
                    :min="1"
                    :max="1000"
                    :step="1"
                    size="small"
                    controls-position="right"
                  />
                </el-tooltip>
                <p class="settings-hint-small">Recommended: 10</p>
              </div>

              <div class="performance-input-item">
                <label>Compare Delay (s)</label>
                <el-tooltip content="Delay between similarity comparisons. For testing only." placement="top">
                  <el-input-number
                    v-model="settings.phase2.compare_delay"
                    :min="0"
                    :max="5"
                    :step="0.1"
                    :precision="1"
                    size="small"
                    controls-position="right"
                  />
                </el-tooltip>
                <p class="settings-hint-small">0s (no delay)</p>
              </div>
            </div>
          </div>
        </div>

        <el-divider />

        <!-- Auto-Selection Rules -->
        <div class="settings-section-drawer">
          <h3>Auto-Selection Rules</h3>
          <p class="settings-hint-text">
            Automatically mark files for deletion based on common patterns
          </p>

          <div class="rule-item">
            <el-checkbox v-model="settings.auto_selection_rules.auto_mark_numbered_copies">
              Auto-mark numbered copies
            </el-checkbox>
            <p class="rule-description">
              Automatically select files like <code>photo(1).jpg</code>, <code>photo(2).jpg</code> for deletion, keeping only <code>photo.jpg</code>
            </p>
          </div>

          <div class="rule-item">
            <el-checkbox v-model="settings.auto_selection_rules.auto_mark_copy_suffix">
              Auto-mark "copy" suffix
            </el-checkbox>
            <p class="rule-description">
              Automatically select files like <code>photo_copy.jpg</code>, <code>photo-copy.jpg</code>, <code>photo copy.jpg</code> for deletion
            </p>
          </div>

          <div class="rule-item">
            <label>Prefer specific folders</label>
            <p class="rule-description">
              Files in these folders will be kept, others marked for deletion
            </p>
            <div v-if="settings.auto_selection_rules.prefer_folders && settings.auto_selection_rules.prefer_folders.length > 0" class="prefer-folders-list">
              <div v-for="(folder, index) in settings.auto_selection_rules.prefer_folders" :key="index" class="prefer-folder-item">
                <el-input
                  v-model="settings.auto_selection_rules.prefer_folders[index]"
                  placeholder="/path/to/preferred/folder"
                />
                <el-button
                  @click="removePreferFolder(index)"
                  type="danger"
                  size="small"
                >
                  Remove
                </el-button>
              </div>
            </div>
            <el-button size="small" @click="addPreferFolder" style="margin-top: 8px">
              + Add Preferred Folder
            </el-button>
          </div>
        </div>

        <!-- Unified Save Button -->
        <div style="padding: 20px; border-top: 1px solid #dcdfe6; margin-top: 20px; background: #fafafa;">
          <el-button
            type="primary"
            size="large"
            @click="saveAllSettings"
            :loading="isSaving"
            style="width: 100%;"
          >
            💾 Save All Settings
          </el-button>
          <p style="margin-top: 12px; font-size: 12px; color: #909399; text-align: center;">
            ⬆️ Settings above require Save to apply
          </p>
        </div>

        <el-divider />

        <!-- Whitelist Management -->
        <div class="settings-section-drawer">
          <h3>Whitelist Management</h3>
          <p class="whitelist-hint">
            Whitelisted groups will be excluded from future duplicate scans.
            <br>
            <strong>⚡ Changes take effect immediately (no Save needed)</strong>
          </p>

          <el-button
            type="primary"
            @click="loadWhitelistGroups"
            :loading="isLoadingWhitelist"
            style="margin-bottom: 16px"
            data-testid="refresh-whitelist-btn"
          >
            🔄 Refresh List
          </el-button>

          <div v-if="whitelistGroups.length > 0" class="whitelist-groups-list">
            <div
              v-for="(group, index) in whitelistGroups"
              :key="group.group_id"
              class="whitelist-group-card"
            >
              <div class="whitelist-group-header">
                <span class="whitelist-group-title">
                  Group {{ group.group_id }} ({{ group.members.length }} images)
                </span>
                <span class="whitelist-group-time">
                  {{ formatTimestamp(group.added_time) }}
                </span>
                <el-button
                  type="danger"
                  size="small"
                  @click="removeWhitelistGroup(group.group_id, index)"
                  data-testid="remove-whitelist-btn"
                >
                  Remove
                </el-button>
              </div>

              <div class="whitelist-group-members">
                <div
                  v-for="member in group.members"
                  :key="member.image_id"
                  class="whitelist-member-thumbnail"
                >
                  <img
                    :src="getImageUrl(member.file_path)"
                    :alt="member.filename"
                    class="whitelist-thumbnail-img"
                  />
                  <p class="whitelist-member-filename">{{ member.filename }}</p>
                </div>
              </div>
            </div>
          </div>
          <el-empty v-else description="No whitelisted groups" />
        </div>

      </div>
    </el-drawer>

    <!-- Deep Path Delete Confirmation Dialog -->
    <el-dialog
      v-model="showDeepDeleteDialog"
      title="Confirm Global Deep Path Delete"
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

        <div class="deep-delete-info">
          <div class="info-label">Found Files:</div>
          <div class="info-value">{{ deepDeletePreview.matchedCount }} duplicate files</div>
        </div>

        <div class="deep-delete-info">
          <div class="info-label">Under Path:</div>
          <div class="info-value path-value" data-testid="deep-delete-path-display">{{ deepDeletePreview.deepPath }}</div>
        </div>

        <div class="file-list-section">
          <div class="file-list-header">
            <span>File List:</span>
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
      </div>

      <template #footer>
        <div class="dialog-footer">
          <el-button @click="cancelDeepDelete">Cancel</el-button>
          <el-button
            type="danger"
            @click="confirmDeepDelete"
            :loading="isDeleting"
          >
            Delete {{ deepDeletePreview.matchedCount }} Files
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
  </div>
</template>

<script setup lang="ts">
import { CircleCheck } from '@element-plus/icons-vue'
import { useDuplicateFinderView } from './DuplicateFinderView'

const {
  // Data
  selectedFolders,
  threshold,
  deepPathDelete,
  isScanning,
  isSaving,
  isDeleting,
  isCleaning,
  isVerifying,
  scanProgress,
  scanResult,
  selectedForDelete,
  hasResults,
  settings,
  showWhitelistDrawer,
  whitelistGroups,
  isLoadingWhitelist,
  // Pagination
  currentPage,
  pageSize,
  totalPages,
  totalGroupsAll,
  isLoadingPage,
  paginatedGroups,
  // 3-Phase workflow states
  isPhase1Running,
  isPhase2Running,
  isPhase25Running,
  isPhase3Running,
  isBulkWhitelisting,
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
  runPhase25,
  stopPhase25,
  whitelistCurrentPage,
  cancelBulkWhitelist,
  confirmBulkWhitelist,
  showBulkWhitelistDialog,
  bulkWhitelistPreview,
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
  getCpuMarks,
  getActualGroupIndex,
  handlePageChange,
  handlePageSizeChange,
  sortBy,
  sortOrder,
  SORT_OPTIONS,
  handleSortChange,
  toggleSortOrder,
  saveFolderSettings,
  saveAdvancedSettings,
  saveAllSettings,
  addFolderPath,
  removeFolderPath,
  addExcludeFolderPath,
  removeExcludeFolderPath,
  executeDeepPathDelete,
  confirmDeepDelete,
  cancelDeepDelete,
  setDeepDeletePath,
  addGroupToWhitelist,
  loadWhitelistGroups,
  removeWhitelistGroup,
  formatTimestamp,
  cleanupDatabase,
  verifyAndCleanup,
  addPreferFolder,
  removePreferFolder
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
  background: rgba(245, 108, 108, 0.7);
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

.image-filename {
  margin: 0 0 4px 0;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
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
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.image-actions .action-button {
  flex: 1;
  min-width: 0;
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
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}
</style>
