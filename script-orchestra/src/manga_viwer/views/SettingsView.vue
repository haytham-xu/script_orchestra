<template>
  <div class="settings-root">
    <div class="header-bar">
      <el-button type="default" size="small" @click="goBack">← Back</el-button>
      <h2>Manga Viewer Settings</h2>
      <div class="header-actions">
        <el-button type="primary" size="small" @click="handleSave">Save Settings</el-button>
      </div>
    </div>

    <div class="settings-content" v-if="settings">
      <!-- Random Settings -->
      <el-card class="settings-card">
        <template #header>
          <div class="card-header">
            <span>🎲 Random Settings</span>
          </div>
        </template>
        <el-form label-width="150px">
          <el-form-item label="Random Count">
            <el-input-number v-model="settings.random.count" :min="1" :max="100" />
            <span class="form-hint">Number of folders to randomly select</span>
          </el-form-item>
          <el-form-item label="Enable Random">
            <el-switch v-model="settings.random.enabled" />
          </el-form-item>
        </el-form>
      </el-card>

      <!-- Category Settings -->
      <el-card class="settings-card">
        <template #header>
          <div class="card-header">
            <span>📁 Category Settings</span>
          </div>
        </template>

        <h4>Main Categories</h4>
        <div v-for="(cat, index) in settings.categories.main" :key="'main-' + index" class="category-item">
          <el-input v-model="cat.id" placeholder="ID" style="width: 100px;" />
          <el-input v-model="cat.label" placeholder="Label" style="width: 150px;" />
          <el-input v-model="cat.target_folder" placeholder="Target Folder" style="flex: 1;" />
          <el-button type="danger" size="small" @click="removeMainCategory(index)">Remove</el-button>
        </div>
        <el-button type="primary" size="small" @click="addMainCategory">+ Add Main Category</el-button>

        <el-divider />

        <h4>Sub Categories</h4>
        <div v-for="(cat, index) in settings.categories.sub" :key="'sub-' + index" class="category-item">
          <el-input v-model="cat.id" placeholder="ID" style="width: 100px;" />
          <el-input v-model="cat.label" placeholder="Label" style="flex: 1;" />
          <el-button type="danger" size="small" @click="removeSubCategory(index)">Remove</el-button>
        </div>
        <el-button type="primary" size="small" @click="addSubCategory">+ Add Sub Category</el-button>
      </el-card>

      <!-- Display Settings -->
      <el-card class="settings-card">
        <template #header>
          <div class="card-header">
            <span>🖥️ Display Settings</span>
          </div>
        </template>
        <el-form label-width="220px">
          <el-form-item label="Page Size">
            <el-input-number v-model="settings.display.page_size" :min="5" :max="100" />
            <span class="form-hint">Items per page</span>
          </el-form-item>

          <el-divider />
          <h4 style="margin: 10px 0;">Manga Viewer Default Filters</h4>

          <el-form-item label="Show Uninitialized Only">
            <el-switch v-model="settings.display.show_uninitialized_only" />
            <span class="form-hint">Show only folders without tags (uninitialized)</span>
          </el-form-item>

          <el-form-item label="Size Sort Enabled">
            <el-switch v-model="settings.display.size_sort_enabled" />
            <span class="form-hint">Sort folders by size (largest first)</span>
          </el-form-item>

          <el-form-item label="Name Sort Enabled">
            <el-switch v-model="settings.display.name_sort_enabled" />
            <span class="form-hint">Sort folders by name (alphabetical)</span>
          </el-form-item>

          <el-divider />

          <el-form-item label="Default Sort">
            <el-select v-model="settings.display.default_sort">
              <el-option label="Name" value="name" />
              <el-option label="Size" value="size" />
              <el-option label="Date" value="date" />
            </el-select>
          </el-form-item>
        </el-form>
      </el-card>

      <!-- Path Settings -->
      <el-card class="settings-card">
        <template #header>
          <div class="card-header">
            <span>📂 Path Settings</span>
          </div>
        </template>
        <el-form label-width="200px">
          <el-form-item label="Root Path">
            <el-input v-model="settings.paths.root_path" placeholder="/path/to/root" />
            <span class="form-hint">Base path for all manga files</span>
          </el-form-item>
          <el-form-item label="Index Path">
            <el-input v-model="settings.paths.index_path" placeholder="/path/to/index" />
            <span class="form-hint">Directory to store manga_index.json</span>
          </el-form-item>
          <el-form-item label="Category Paths">
            <el-input v-model="settings.paths.category_paths" placeholder="/path/to/categories" />
            <span class="form-hint">Target directory for categorized folders</span>
          </el-form-item>
          <el-form-item label="Delete Paths">
            <el-input v-model="settings.paths.delete_paths" placeholder="/path/to/deleted" />
            <span class="form-hint">Directory for deleted folders</span>
          </el-form-item>
          <el-form-item label="Import Path">
            <el-input v-model="settings.paths.import_path" placeholder="/path/to/import" />
            <span class="form-hint">Default path for importing new manga folders</span>
          </el-form-item>

          <el-form-item label="Scan Folders">
            <div class="array-input-group">
              <div v-for="(folder, index) in settings.paths.scan_folders" :key="'scan-' + index" class="array-item">
                <el-input v-model="settings.paths.scan_folders[index]" placeholder="/path/to/scan" />
                <el-button type="danger" size="small" @click="removeScanFolder(index)">Remove</el-button>
              </div>
              <el-button type="primary" size="small" @click="addScanFolder">+ Add Scan Folder</el-button>
            </div>
            <span class="form-hint">Folders to scan for manga content</span>
          </el-form-item>

          <el-form-item label="Ignore Scan Folders">
            <div class="array-input-group">
              <div v-for="(folder, index) in settings.paths.ignore_scan_folders" :key="'ignore-' + index" class="array-item">
                <el-input v-model="settings.paths.ignore_scan_folders[index]" placeholder="/path/to/ignore" />
                <el-button type="danger" size="small" @click="removeIgnoreScanFolder(index)">Remove</el-button>
              </div>
              <el-button type="primary" size="small" @click="addIgnoreScanFolder">+ Add Ignore Folder</el-button>
            </div>
            <span class="form-hint">Folders to exclude from scanning</span>
          </el-form-item>
        </el-form>
      </el-card>
    </div>
  </div>
</template>

<script lang="ts" src="@/manga_viwer/views/SettingsView.ts"></script>

<style scoped>
.settings-root {
  padding: 20px;
  max-width: 1200px;
  margin: 0 auto;
}

.header-bar {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 16px;
  background: #fff;
  border: 1px solid #e2e6eb;
  border-radius: 8px;
  margin-bottom: 20px;
}

.header-bar h2 {
  flex: 1;
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}

.header-actions {
  display: flex;
  gap: 12px;
}

.settings-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.settings-card {
  border-radius: 8px;
}

.card-header {
  font-size: 16px;
  font-weight: 600;
}

.form-hint {
  margin-left: 12px;
  font-size: 12px;
  color: #909399;
}

.category-item {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 12px;
}

.array-input-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

.array-item {
  display: flex;
  gap: 12px;
  align-items: center;
}

.array-item .el-input {
  flex: 1;
}

h4 {
  margin: 16px 0 12px 0;
  font-size: 14px;
  font-weight: 600;
  color: #606266;
}
</style>
