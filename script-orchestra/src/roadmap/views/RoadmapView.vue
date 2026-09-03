<template>
  <div class="roadmap-container" @click="handleClickOutside">
    <el-header class="header">
      <h1>Roadmap - Multi-Dimension Kanban Board</h1>
      <el-button :icon="Setting" circle @click="openSettings" />
    </el-header>

    <el-main class="main-content">
      <div class="kanban-board" v-loading="store.loading">
        <!-- Main Content Area (4 Categories + In Progress) -->
        <div class="main-area">
          <!-- In Progress Row -->
          <div class="in-progress-row">
            <div class="in-progress-body">
              <draggable
                :model-value="store.inProgressTasks"
                :group="{ name: 'tasks', pull: true, put: true }"
                item-key="id"
                class="task-list-horizontal"
                data-column-id="in-progress"
                :data-status="TaskStatus.IN_PROGRESS"
                animation="200"
                @change="handleDragChange($event, TaskStatus.IN_PROGRESS, null)"
              >
                <template #item="{ element }">
                  <div :data-task-id="element.id">
                    <TaskCard
                      :task="element"
                      @preview="openPreviewForm"
                      @edit="openEditForm"
                      @delete="deleteTask"
                      @extend-time="extendInProgressTime"
                    />
                  </div>
                </template>
              </draggable>
            </div>
          </div>

          <!-- Category Headers -->
          <div class="category-headers">
            <div
              v-for="col in store.categoryColumns"
              :key="col.category"
              class="category-header-cell"
            >
              <h3 v-if="editingCategoryKey !== col.category" @click="startEditCategory(col.category)" style="cursor: pointer;">
                {{ categoryNames[col.category] }}
              </h3>
              <el-input
                v-else
                v-model="editingCategoryName"
                @blur="saveCategoryName"
                @keyup.enter="saveCategoryName"
                @keyup.esc="cancelEditCategory"
                size="small"
                style="flex: 1;"
                ref="categoryInput"
              />
              <el-button
                type="primary"
                size="small"
                :icon="Plus"
                @click="openCreateForm(TaskStatus.TODO, col.category)"
                class="add-category-btn"
              />
            </div>
          </div>

          <!-- Todo Row -->
          <div class="category-row todo-row">
            <div
              v-for="col in store.categoryColumns"
              :key="`todo-${col.category}`"
              class="category-cell"
            >
              <div class="cell-body">
                <draggable
                  :model-value="col.todoTasks"
                  :group="{ name: 'tasks', pull: true, put: true }"
                  item-key="id"
                  class="task-list"
                  :data-column-id="`todo-${col.category}`"
                  :data-status="TaskStatus.TODO"
                  :data-category="col.category"
                  animation="200"
                  @change="handleDragChange($event, TaskStatus.TODO, col.category)"
                >
                  <template #item="{ element }">
                    <div :data-task-id="element.id">
                      <TaskCard
                        :task="element"
                        @preview="openPreviewForm"
                        @edit="openEditForm"
                        @delete="deleteTask"
                      />
                    </div>
                  </template>
                </draggable>
              </div>
            </div>
          </div>

          <!-- Block Row -->
          <div class="category-row block-row">
            <div
              v-for="col in store.categoryColumns"
              :key="`block-${col.category}`"
              class="category-cell"
            >
              <div class="cell-body">
                <draggable
                  :model-value="col.blockTasks"
                  :group="{ name: 'tasks', pull: true, put: true }"
                  item-key="id"
                  class="task-list"
                  :data-column-id="`block-${col.category}`"
                  :data-status="TaskStatus.BLOCK"
                  :data-category="col.category"
                  animation="200"
                  @change="handleDragChange($event, TaskStatus.BLOCK, col.category)"
                >
                  <template #item="{ element }">
                    <div :data-task-id="element.id">
                      <TaskCard
                        :task="element"
                        @preview="openPreviewForm"
                        @edit="openEditForm"
                        @delete="deleteTask"
                      />
                    </div>
                  </template>
                </draggable>
              </div>
            </div>
          </div>

          <!-- Done Row -->
          <div class="done-row">
            <div class="done-body">
              <draggable
                :model-value="store.doneTasks"
                :group="{ name: 'tasks', pull: true, put: true }"
                item-key="id"
                class="task-list-done"
                data-column-id="done"
                :data-status="TaskStatus.DONE"
                animation="200"
                @change="handleDragChange($event, TaskStatus.DONE, null)"
              >
                <template #item="{ element }">
                  <div :data-task-id="element.id">
                    <TaskCard
                      :task="element"
                      @edit="openEditForm"
                      @delete="deleteTask"
                    />
                  </div>
                </template>
              </draggable>
            </div>
          </div>
        </div>
      </div>

      <!-- Task Detail Dialog -->
      <el-dialog
        v-model="showDetailDialog"
        title="Task Details"
        width="600px"
        @close="closeDetail"
      >
        <div v-if="detailTask" class="task-detail">
          <h3 class="detail-header">{{ detailTask.header }}</h3>
          <div v-if="detailTask.content" class="detail-content markdown-preview" v-html="renderMarkdown(detailTask.content)">
          </div>
          <div v-else class="detail-content-empty">
            No detailed content
          </div>

          <div class="detail-meta">
            <el-tag :type="getPriorityTagType(detailTask.priority)" size="small">{{ detailTask.priority }}</el-tag>
            <el-tag size="small">{{ detailTask.size }}</el-tag>
            <el-tag size="small">{{ detailTask.category }}</el-tag>
            <span v-if="detailTask.eta" class="detail-eta">
              ETA: {{ formatDetailETA(detailTask.eta) }}
            </span>
          </div>
        </div>
        <template #footer>
          <el-button @click="closeDetail">Close</el-button>
          <el-button type="primary" @click="editFromDetail">Edit</el-button>
        </template>
      </el-dialog>

      <!-- Edit Form Dialog -->
      <el-dialog
        v-model="showEditDialog"
        title="Edit Task"
        width="900px"
        @close="handleEditDialogClose"
      >
        <div style="padding: 10px 30px 30px;">
          <el-input
            v-model="taskForm.header"
            placeholder="What needs to be done?"
            maxlength="50"
            show-word-limit
            size="large"
            style="margin-bottom: 16px;"
          />

          <!-- Markdown Editor with Tabs -->
          <el-tabs v-model="activeTab" style="margin-bottom: 20px;">
            <el-tab-pane label="Edit" name="edit">
              <el-input
                v-model="taskForm.content"
                type="textarea"
                :rows="22"
                placeholder="Add more details... (Supports Markdown - use [ ] for checkboxes)"
                style="font-family: monospace;"
              />
            </el-tab-pane>
            <el-tab-pane label="Preview" name="preview">
              <div class="markdown-preview" v-html="renderedMarkdown"></div>
            </el-tab-pane>
          </el-tabs>

          <div style="display: grid; grid-template-columns: 2fr 1fr; gap: 16px; margin-bottom: 20px;">
            <el-button-group style="width: 100%; display: flex;">
              <el-button
                :type="taskForm.priority === TaskPriority.LOW ? 'primary' : ''"
                @click="taskForm.priority = TaskPriority.LOW"
                style="flex: 1;"
              >Low</el-button>
              <el-button
                :type="taskForm.priority === TaskPriority.MEDIUM ? 'primary' : ''"
                @click="taskForm.priority = TaskPriority.MEDIUM"
                style="flex: 1;"
              >Medium</el-button>
              <el-button
                :type="taskForm.priority === TaskPriority.HIGH ? 'primary' : ''"
                @click="taskForm.priority = TaskPriority.HIGH"
                style="flex: 1;"
              >High</el-button>
            </el-button-group>

            <el-button-group style="width: 100%; display: flex;">
              <el-button
                :type="taskForm.size === TaskSize.SMALL ? 'primary' : ''"
                @click="taskForm.size = TaskSize.SMALL"
                style="flex: 1;"
              >S</el-button>
              <el-button
                :type="taskForm.size === TaskSize.MEDIUM ? 'primary' : ''"
                @click="taskForm.size = TaskSize.MEDIUM"
                style="flex: 1;"
              >M</el-button>
              <el-button
                :type="taskForm.size === TaskSize.BIG ? 'primary' : ''"
                @click="taskForm.size = TaskSize.BIG"
                style="flex: 1;"
              >B</el-button>
            </el-button-group>
          </div>

          <div style="display: flex; gap: 6px; margin-bottom: 20px; flex-wrap: wrap; justify-content: center;">
            <el-button
              :type="etaPreset === 'today' ? 'primary' : ''"
              @click="handleEtaPresetChange('today')"
              size="default"
            >今天</el-button>
            <el-button
              :type="etaPreset === 'tomorrow' ? 'primary' : ''"
              @click="handleEtaPresetChange('tomorrow')"
              size="default"
            >明天</el-button>
            <el-button
              :type="etaPreset === 'dayafter' ? 'primary' : ''"
              @click="handleEtaPresetChange('dayafter')"
              size="default"
            >后天</el-button>
            <el-button
              :type="etaPreset === 'thisweek' ? 'primary' : ''"
              @click="handleEtaPresetChange('thisweek')"
              size="default"
            >本周内</el-button>
            <el-button
              :type="etaPreset === 'custom' ? 'primary' : ''"
              @click="handleEtaPresetChange('custom')"
              size="default"
            >自定义</el-button>
            <el-button
              :type="etaPreset === 'none' ? 'primary' : ''"
              @click="handleEtaPresetChange('none')"
              size="default"
            >不设置</el-button>
          </div>

          <div v-if="etaPreset === 'custom'" style="display: flex; gap: 12px; margin-bottom: 20px;">
            <el-date-picker
              v-model="taskFormEta"
              type="date"
              placeholder="Select due date"
              style="flex: 2;"
              size="large"
              format="YYYY-MM-DD"
            />
            <el-time-select
              v-model="taskFormTime"
              placeholder="Select time"
              style="flex: 1;"
              size="large"
              start="00:00"
              step="00:30"
              end="23:30"
            />
          </div>

          <div style="display: flex; gap: 10px;">
            <el-button
              :type="taskForm.category === TaskCategory.A ? 'primary' : ''"
              @click="taskForm.category = TaskCategory.A"
              style="flex: 1;"
            >{{ categoryNames[TaskCategory.A] }}</el-button>
            <el-button
              :type="taskForm.category === TaskCategory.B ? 'primary' : ''"
              @click="taskForm.category = TaskCategory.B"
              style="flex: 1;"
            >{{ categoryNames[TaskCategory.B] }}</el-button>
            <el-button
              :type="taskForm.category === TaskCategory.C ? 'primary' : ''"
              @click="taskForm.category = TaskCategory.C"
              style="flex: 1;"
            >{{ categoryNames[TaskCategory.C] }}</el-button>
            <el-button
              :type="taskForm.category === TaskCategory.D ? 'primary' : ''"
              @click="taskForm.category = TaskCategory.D"
              style="flex: 1;"
            >{{ categoryNames[TaskCategory.D] }}</el-button>
          </div>
        </div>

        <template #footer>
          <div style="padding: 0 20px 10px; display: flex; justify-content: space-between; align-items: center;">
            <el-button type="danger" @click="handleDeleteInEdit()" size="large" style="min-width: 100px;">Delete</el-button>
            <div style="display: flex; gap: 12px;">
              <el-button @click="cancelEdit" size="large" style="min-width: 100px;">Cancel</el-button>
              <el-button type="primary" @click="saveTask" size="large" style="min-width: 120px;">Save Changes</el-button>
            </div>
          </div>
        </template>
      </el-dialog>

      <!-- Create Form Dialog -->
      <el-dialog
        v-model="showCreateDialog"
        title="Create New Task"
        width="900px"
        :close-on-click-modal="false"
        @close="cancelCreate"
      >
        <div style="padding: 10px 30px 30px;">
          <el-input
            v-model="taskForm.header"
            placeholder="What needs to be done?"
            maxlength="50"
            show-word-limit
            size="large"
            style="margin-bottom: 16px;"
          />

          <!-- Markdown Editor with Tabs -->
          <el-tabs v-model="activeTab" style="margin-bottom: 20px;">
            <el-tab-pane label="Edit" name="edit">
              <el-input
                v-model="taskForm.content"
                type="textarea"
                :rows="10"
                placeholder="Add more details... (Supports Markdown - use [ ] for checkboxes)"
                style="font-family: monospace;"
              />
            </el-tab-pane>
            <el-tab-pane label="Preview" name="preview">
              <div class="markdown-preview" v-html="renderedMarkdown"></div>
            </el-tab-pane>
          </el-tabs>

          <div style="display: grid; grid-template-columns: 2fr 1fr; gap: 16px; margin-bottom: 20px;">
            <el-button-group style="width: 100%; display: flex;">
              <el-button
                :type="taskForm.priority === TaskPriority.LOW ? 'primary' : ''"
                @click="taskForm.priority = TaskPriority.LOW"
                style="flex: 1;"
              >Low</el-button>
              <el-button
                :type="taskForm.priority === TaskPriority.MEDIUM ? 'primary' : ''"
                @click="taskForm.priority = TaskPriority.MEDIUM"
                style="flex: 1;"
              >Medium</el-button>
              <el-button
                :type="taskForm.priority === TaskPriority.HIGH ? 'primary' : ''"
                @click="taskForm.priority = TaskPriority.HIGH"
                style="flex: 1;"
              >High</el-button>
            </el-button-group>

            <el-button-group style="width: 100%; display: flex;">
              <el-button
                :type="taskForm.size === TaskSize.SMALL ? 'primary' : ''"
                @click="taskForm.size = TaskSize.SMALL"
                style="flex: 1;"
              >S</el-button>
              <el-button
                :type="taskForm.size === TaskSize.MEDIUM ? 'primary' : ''"
                @click="taskForm.size = TaskSize.MEDIUM"
                style="flex: 1;"
              >M</el-button>
              <el-button
                :type="taskForm.size === TaskSize.BIG ? 'primary' : ''"
                @click="taskForm.size = TaskSize.BIG"
                style="flex: 1;"
              >B</el-button>
            </el-button-group>
          </div>

          <div style="display: flex; gap: 6px; margin-bottom: 20px; flex-wrap: wrap; justify-content: center;">
            <el-button
              :type="etaPreset === 'today' ? 'primary' : ''"
              @click="handleEtaPresetChange('today')"
              size="default"
            >今天</el-button>
            <el-button
              :type="etaPreset === 'tomorrow' ? 'primary' : ''"
              @click="handleEtaPresetChange('tomorrow')"
              size="default"
            >明天</el-button>
            <el-button
              :type="etaPreset === 'dayafter' ? 'primary' : ''"
              @click="handleEtaPresetChange('dayafter')"
              size="default"
            >后天</el-button>
            <el-button
              :type="etaPreset === 'thisweek' ? 'primary' : ''"
              @click="handleEtaPresetChange('thisweek')"
              size="default"
            >本周内</el-button>
            <el-button
              :type="etaPreset === 'custom' ? 'primary' : ''"
              @click="handleEtaPresetChange('custom')"
              size="default"
            >自定义</el-button>
            <el-button
              :type="etaPreset === 'none' ? 'primary' : ''"
              @click="handleEtaPresetChange('none')"
              size="default"
            >不设置</el-button>
          </div>

          <div v-if="etaPreset === 'custom'" style="display: flex; gap: 12px; margin-bottom: 20px;">
            <el-date-picker
              v-model="taskFormEta"
              type="date"
              placeholder="Select due date"
              style="flex: 2;"
              size="large"
              format="YYYY-MM-DD"
            />
            <el-time-select
              v-model="taskFormTime"
              placeholder="Select time"
              style="flex: 1;"
              size="large"
              start="00:00"
              step="00:30"
              end="23:30"
            />
          </div>

          <div style="display: flex; gap: 10px;">
            <el-button
              :type="taskForm.category === TaskCategory.A ? 'primary' : ''"
              @click="taskForm.category = TaskCategory.A"
              style="flex: 1;"
            >{{ categoryNames[TaskCategory.A] }}</el-button>
            <el-button
              :type="taskForm.category === TaskCategory.B ? 'primary' : ''"
              @click="taskForm.category = TaskCategory.B"
              style="flex: 1;"
            >{{ categoryNames[TaskCategory.B] }}</el-button>
            <el-button
              :type="taskForm.category === TaskCategory.C ? 'primary' : ''"
              @click="taskForm.category = TaskCategory.C"
              style="flex: 1;"
            >{{ categoryNames[TaskCategory.C] }}</el-button>
            <el-button
              :type="taskForm.category === TaskCategory.D ? 'primary' : ''"
              @click="taskForm.category = TaskCategory.D"
              style="flex: 1;"
            >{{ categoryNames[TaskCategory.D] }}</el-button>
          </div>
        </div>

        <template #footer>
          <div style="padding: 0 20px 10px; display: flex; justify-content: flex-end; gap: 12px;">
            <el-button @click="cancelCreate" size="large" style="min-width: 100px;">Cancel</el-button>
            <el-button type="primary" @click="saveTask" size="large" style="min-width: 120px;">Create Task</el-button>
          </div>
        </template>
      </el-dialog>

      <!-- Settings Drawer -->
      <el-drawer
        v-model="showSettingsDrawer"
        title="Settings"
        direction="rtl"
        size="400px"
      >
        <div class="settings-content">
          <div class="setting-item">
            <div class="setting-label">
              <h4>In Progress Timeout</h4>
              <p>Tasks in "In Progress" will automatically return to their original status after this time.</p>
            </div>
            <div class="setting-control">
              <el-input-number
                v-model="settings.inProgressTimeoutHours"
                :min="0.5"
                :max="72"
                :step="0.5"
                :precision="1"
                style="width: 150px;"
              />
              <span class="unit">hours</span>
            </div>
          </div>

          <el-divider />

          <div class="setting-item">
            <div class="setting-label">
              <h4>Done Auto-Remove</h4>
              <p>Tasks in "Done" will be automatically hidden after this time. Set to 0 to disable.</p>
            </div>
            <div class="setting-control">
              <el-input-number
                v-model="settings.doneAutoRemoveDays"
                :min="0"
                :max="365"
                :step="1"
                style="width: 150px;"
              />
              <span class="unit">days (0 = never)</span>
            </div>
          </div>

          <el-divider />

          <div class="setting-actions">
            <el-button @click="resetSettings">Reset to Defaults</el-button>
            <el-button type="primary" @click="saveSettings">Save Settings</el-button>
          </div>
        </div>
      </el-drawer>
    </el-main>
  </div>
</template>

<script lang="ts" src="@/roadmap/views/RoadmapView.ts"></script>

<style scoped>
.roadmap-container {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background-color: #f5f7fa;
}

.header {
  background: white;
  padding: 12px 30px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 48px;
}

.header h1 {
  margin: 0;
  font-size: 16px;
  font-weight: 500;
}

.main-content {
  flex: 1;
  overflow-x: auto;
  overflow-y: hidden;
  padding: 10px;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.kanban-board {
  display: flex;
  gap: 20px;
  height: 100%;
  align-items: flex-start;
  /* Fixed content width: narrow viewport scrolls horizontally, wide viewport
     centers the board with side margins. */
  width: 2010px;
  margin: 0 auto;
  flex-shrink: 0;
}

/* Main Area */
.main-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 100%;
  height: 100%;
  min-height: 0;
}

/* Category Headers */
.category-headers {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.category-header-cell {
  background: white;
  padding: 12px;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.category-header-cell h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  text-align: left;
  flex: 1;
}

.add-category-btn {
  flex-shrink: 0;
  border-radius: 6px;
}

/* Category Rows */
.category-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.todo-row {
  height: 450px;
  flex-shrink: 0;
}

.todo-row .category-cell {
  background: linear-gradient(135deg, #fffffa 0%, #fffef5 100%);
  border: 1px solid #fef3c7;
}

.block-row {
  height: 235px;
  flex-shrink: 0;
}

.block-row .category-cell {
  background: linear-gradient(135deg, #e8e9eb 0%, #f1f2f4 100%);
  border: 2px solid #9ca3af;
}

.category-cell {
  background: #f9fafb;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

.cell-body {
  flex: 1;
  padding: 12px;
  overflow-y: auto;
  min-height: 0;
}

/* Grid layout for task cards in category cells - 2 columns */
.category-cell .task-list {
  display: grid;
  grid-template-columns: repeat(2, 224px);
  grid-auto-rows: max-content;
  align-content: start;
  gap: 10px 16px; /* row-gap column-gap */
  min-height: 100%;
}

/* In Progress Row */
.in-progress-row {
  background: linear-gradient(135deg, #e6f4ff 0%, #f0f5ff 100%);
  border-radius: 8px;
  padding: 14px 0 0 16px;
  border: 2px solid #1890ff;
  height: 140px;
  flex-shrink: 0;
  animation: pulse-progress 2s ease-in-out infinite;
  position: relative;
  overflow: visible;
}

.in-progress-row::before {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(24, 144, 255, 0.2), transparent);
  animation: slide-progress 3s ease-in-out infinite;
}

@keyframes pulse-progress {
  0%, 100% {
    border-color: #1890ff;
    box-shadow: 0 0 10px rgba(24, 144, 255, 0.4);
    transform: scale(1);
  }
  50% {
    border-color: #40a9ff;
    box-shadow: 0 0 25px rgba(24, 144, 255, 0.6);
    transform: scale(1.005);
  }
}

@keyframes slide-progress {
  0% {
    left: -100%;
  }
  100% {
    left: 100%;
  }
}

/* Done Row */
.done-row {
  background: linear-gradient(135deg, #f5f5f5 0%, #e8e8e8 100%);
  border-radius: 8px;
  padding: 8px;
  border: 2px solid #9ca3af;
  flex: 1;
  min-height: 0;
  position: relative;
  overflow: hidden;
}

.done-row::before {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(156, 163, 175, 0.1), transparent);
  animation: slide-done 4s ease-in-out infinite;
}

@keyframes pulse-done {
  0%, 100% {
    border-color: #9ca3af;
    box-shadow: 0 0 8px rgba(156, 163, 175, 0.2);
    transform: scale(1);
  }
  50% {
    border-color: #6b7280;
    box-shadow: 0 0 15px rgba(156, 163, 175, 0.3);
    transform: scale(1.002);
  }
}

@keyframes slide-done {
  0% {
    left: -100%;
  }
  100% {
    left: 100%;
  }
}

.done-body {
  overflow-y: auto;
  overflow-x: hidden;
  height: 100%;
  padding: 12px;
}

.task-list-done {
  display: grid;
  grid-template-columns: repeat(auto-fill, 224px);
  grid-auto-rows: max-content;
  gap: 10px 16px;
  justify-content: start;
  min-height: 100%;
}

.in-progress-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.in-progress-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #1890ff;
}

.in-progress-body {
  overflow: hidden;
  display: flex;
  align-items: center;
  height: 100%;
}

.task-list {
  min-height: 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.task-list-horizontal {
  display: flex;
  gap: 16px;
  flex-wrap: nowrap;
  overflow: visible;
  width: 100%;
}

.task-list-horizontal > div {
  flex-shrink: 0;
}

/* Task Detail Dialog */
.task-detail {
  padding: 12px 0;
}

.detail-header {
  margin: 0 0 16px 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.detail-content {
  background: var(--el-fill-color-light);
  padding: 12px;
  border-radius: 6px;
  white-space: pre-wrap;
  word-break: break-word;
  min-height: 60px;
  margin-bottom: 16px;
  line-height: 1.6;
}

.detail-content-empty {
  background: var(--el-fill-color-lighter);
  padding: 12px;
  border-radius: 6px;
  text-align: center;
  color: var(--el-text-color-secondary);
  margin-bottom: 16px;
  font-style: italic;
}

.detail-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.detail-eta {
  color: var(--el-text-color-regular);
  font-size: 13px;
  margin-left: auto;
}

/* Markdown Preview Styles */
.markdown-preview {
  background: var(--el-fill-color-light);
  padding: 16px;
  border-radius: 6px;
  min-height: 300px;
  max-height: 450px;
  overflow-y: auto;
  border: 1px solid var(--el-border-color-lighter);
  line-height: 1.6;
}

.markdown-preview h1,
.markdown-preview h2,
.markdown-preview h3,
.markdown-preview h4,
.markdown-preview h5,
.markdown-preview h6 {
  margin-top: 16px;
  margin-bottom: 8px;
  font-weight: 600;
  line-height: 1.25;
}

.markdown-preview h1 {
  font-size: 24px;
  border-bottom: 1px solid var(--el-border-color-light);
  padding-bottom: 8px;
}

.markdown-preview h2 {
  font-size: 20px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  padding-bottom: 6px;
}

.markdown-preview h3 {
  font-size: 18px;
}

.markdown-preview p {
  margin: 8px 0;
}

.markdown-preview ul,
.markdown-preview ol {
  margin: 8px 0;
  padding-left: 24px;
}

/* Remove bullet points from task list items (those containing checkboxes) */
.markdown-preview ul li:has(> input[type="checkbox"]) {
  list-style: none;
  margin-left: -20px;
}

/* Fallback for browsers that don't support :has() */
.markdown-preview .task-list-item {
  list-style: none;
  margin-left: -20px;
}

.markdown-preview li {
  margin: 4px 0;
}

.markdown-preview input[type="checkbox"] {
  margin-right: 6px;
  cursor: pointer;
  width: 16px;
  height: 16px;
  vertical-align: middle;
}

.markdown-preview input[type="checkbox"]:hover {
  transform: scale(1.1);
}

.markdown-preview code {
  background: var(--el-fill-color);
  padding: 2px 6px;
  border-radius: 3px;
  font-family: 'Courier New', Courier, monospace;
  font-size: 0.9em;
}

.markdown-preview pre {
  background: var(--el-fill-color);
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 8px 0;
}

.markdown-preview pre code {
  background: none;
  padding: 0;
}

.markdown-preview blockquote {
  border-left: 4px solid var(--el-color-primary);
  padding-left: 12px;
  margin: 8px 0;
  color: var(--el-text-color-regular);
}

.markdown-preview table {
  border-collapse: collapse;
  width: 100%;
  margin: 8px 0;
}

.markdown-preview table th,
.markdown-preview table td {
  border: 1px solid var(--el-border-color-light);
  padding: 8px 12px;
  text-align: left;
}

.markdown-preview table th {
  background: var(--el-fill-color);
  font-weight: 600;
}

.markdown-preview a {
  color: var(--el-color-primary);
  text-decoration: none;
}

.markdown-preview a:hover {
  text-decoration: underline;
}

.markdown-preview .empty-preview,
.markdown-preview .error-preview {
  color: var(--el-text-color-secondary);
  font-style: italic;
  text-align: center;
  padding: 20px;
}

.markdown-preview .error-preview {
  color: var(--el-color-danger);
}

/* Settings Drawer Styles */
.settings-content {
  padding: 20px;
}

.setting-item {
  margin-bottom: 24px;
}

.setting-label h4 {
  margin: 0 0 8px 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.setting-label p {
  margin: 0 0 12px 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}

.setting-control {
  display: flex;
  align-items: center;
  gap: 12px;
}

.setting-control .unit {
  font-size: 13px;
  color: var(--el-text-color-regular);
}

.setting-actions {
  display: flex;
  justify-content: space-between;
  margin-top: 32px;
  padding-top: 20px;
  border-top: 1px solid var(--el-border-color-light);
}
</style>
