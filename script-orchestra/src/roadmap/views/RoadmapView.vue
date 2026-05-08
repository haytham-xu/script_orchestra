<template>
  <div class="roadmap-container">
    <el-header class="header">
      <h1>Roadmap - Kanban Board</h1>
    </el-header>

    <el-main class="main-content">
      <div class="kanban-board" v-loading="store.loading">
        <div
          v-for="column in store.columns"
          :key="column.id"
          class="kanban-column"
        >
          <div class="column-header">
            <h3>{{ column.name }}</h3>
            <span class="task-count">{{ column.tasks.length }}</span>
          </div>

          <div class="column-body">
            <draggable
              :model-value="column.tasks"
              :group="{ name: 'tasks', pull: true, put: true }"
              item-key="id"
              class="task-list"
              :data-column-id="column.id"
              animation="200"
              @end="handleDragEnd"
            >
              <template #item="{ element }">
                <div :data-task-id="element.id">
                  <!-- Edit Form -->
                  <div v-if="editingTaskId === element.id" class="inline-edit-form">
                    <el-input
                      v-model="taskForm.title"
                      placeholder="Task title..."
                      class="title-input"
                      @keyup.enter="saveTask"
                      @keyup.esc="cancelEdit"
                    />
                    <el-input
                      v-model="taskForm.description"
                      type="textarea"
                      placeholder="Description (optional)..."
                      :rows="2"
                      class="desc-input"
                    />
                    <div class="form-actions">
                      <el-radio-group v-model="taskForm.priority" size="small">
                        <el-radio-button :label="TaskPriority.LOW">Low</el-radio-button>
                        <el-radio-button :label="TaskPriority.MEDIUM">Med</el-radio-button>
                        <el-radio-button :label="TaskPriority.HIGH">High</el-radio-button>
                      </el-radio-group>
                      <div class="action-buttons">
                        <el-button size="small" @click="cancelEdit">Cancel</el-button>
                        <el-button size="small" type="primary" @click="saveTask">Save</el-button>
                      </div>
                    </div>
                  </div>

                  <!-- Task Card -->
                  <TaskCard
                    v-else
                    :task="element"
                    @edit="openEditForm"
                    @delete="deleteTask"
                  />
                </div>
              </template>
            </draggable>

            <!-- Inline Create Form -->
            <div v-if="createFormColumn === column.id" class="inline-create-form">
              <el-input
                v-model="taskForm.title"
                placeholder="Task title..."
                class="title-input"
                @keyup.enter="saveTask"
                @keyup.esc="cancelCreate"
                ref="titleInput"
              />
              <el-input
                v-model="taskForm.description"
                type="textarea"
                placeholder="Description (optional)..."
                :rows="2"
                class="desc-input"
              />
              <div class="form-actions">
                <el-radio-group v-model="taskForm.priority" size="small">
                  <el-radio-button :label="TaskPriority.LOW">Low</el-radio-button>
                  <el-radio-button :label="TaskPriority.MEDIUM">Med</el-radio-button>
                  <el-radio-button :label="TaskPriority.HIGH">High</el-radio-button>
                </el-radio-group>
                <div class="action-buttons">
                  <el-button size="small" @click="cancelCreate">Cancel</el-button>
                  <el-button size="small" type="primary" @click="saveTask">Add</el-button>
                </div>
              </div>
            </div>

            <!-- Add Task Button (只在Todo列显示) -->
            <el-button
              v-if="column.id === 'todo' && createFormColumn !== column.id"
              text
              class="add-task-btn"
              @click="openCreateForm(column.id)"
            >
              <el-icon><Plus /></el-icon>
              Add Task
            </el-button>
          </div>
        </div>
      </div>
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
  padding: 20px 30px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  display: flex;
  align-items: center;
}

.header h1 {
  margin: 0;
  font-size: 24px;
  font-weight: 500;
}

.main-content {
  flex: 1;
  overflow: auto;
  padding: 20px;
}

.kanban-board {
  display: flex;
  gap: 20px;
  min-height: calc(100vh - 140px);
  align-items: flex-start;
}

.kanban-column {
  flex: 1;
  min-width: 300px;
  background: #f9fafb;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  max-height: calc(100vh - 140px);
}

.column-header {
  padding: 16px;
  border-bottom: 2px solid #e5e7eb;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: white;
  border-radius: 8px 8px 0 0;
}

.column-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  flex: 1;
}

.task-count {
  background: #e5e7eb;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 12px;
  margin-right: 8px;
}

.column-body {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
}

.task-list {
  min-height: 100px;
  margin-bottom: 12px;
}

.inline-create-form,
.inline-edit-form {
  background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
  border-radius: 12px;
  padding: 16px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08), 0 0 0 1px rgba(0, 0, 0, 0.02);
  margin-bottom: 12px;
  border: 1px solid #e5e7eb;
  transition: all 0.3s ease;
}

.inline-create-form:hover,
.inline-edit-form:hover {
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.12), 0 0 0 1px rgba(0, 0, 0, 0.03);
  transform: translateY(-1px);
}

.inline-create-form .title-input,
.inline-edit-form .title-input {
  margin-bottom: 10px;
}

.inline-create-form .title-input :deep(.el-input__wrapper),
.inline-edit-form .title-input :deep(.el-input__wrapper) {
  font-size: 15px;
  font-weight: 500;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
  transition: all 0.2s;
}

.inline-create-form .title-input :deep(.el-input__wrapper:hover),
.inline-edit-form .title-input :deep(.el-input__wrapper:hover) {
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.08);
}

.inline-create-form .title-input :deep(.el-input__wrapper.is-focus),
.inline-edit-form .title-input :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.2);
}

.inline-create-form .desc-input,
.inline-edit-form .desc-input {
  margin-bottom: 12px;
}

.inline-create-form .desc-input :deep(.el-textarea__inner),
.inline-edit-form .desc-input :deep(.el-textarea__inner) {
  font-size: 13px;
  line-height: 1.5;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
  transition: all 0.2s;
}

.inline-create-form .desc-input :deep(.el-textarea__inner:hover),
.inline-edit-form .desc-input :deep(.el-textarea__inner:hover) {
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.08);
}

.inline-create-form .desc-input :deep(.el-textarea__inner:focus),
.inline-edit-form .desc-input :deep(.el-textarea__inner:focus) {
  box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.2);
}

.form-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 4px;
}

.form-actions :deep(.el-radio-group) {
  background: #f3f4f6;
  padding: 2px;
  border-radius: 8px;
  box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.05);
}

.form-actions :deep(.el-radio-button__inner) {
  border-radius: 6px !important;
  border: none;
  font-size: 12px;
  padding: 5px 12px;
  transition: all 0.2s;
}

.form-actions :deep(.el-radio-button.is-active .el-radio-button__inner) {
  background: white;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.action-buttons {
  display: flex;
  gap: 8px;
}

.action-buttons .el-button {
  border-radius: 8px;
  font-weight: 500;
  transition: all 0.2s;
}

.action-buttons .el-button:hover {
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}

.action-buttons .el-button--primary {
  background: linear-gradient(135deg, #409eff 0%, #3a8ee6 100%);
  border: none;
}

.add-task-btn {
  width: 100%;
  justify-content: center;
  padding: 8px;
  color: var(--el-text-color-secondary);
  border: 1px dashed var(--el-border-color);
  border-radius: 4px;
  transition: all 0.3s;
}

.add-task-btn:hover {
  color: var(--el-color-primary);
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}
</style>
