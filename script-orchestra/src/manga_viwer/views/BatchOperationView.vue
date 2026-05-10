<template>
  <div class="batch-root">
    <!-- Header -->
    <div class="top-bar">
      <el-button text @click="goBack" class="back-btn">
        <span class="back-icon">←</span> Back
      </el-button>
      <div class="actions">
        <span v-if="changeCount > 0" class="badge">{{ changeCount }}</span>
        <el-button type="primary" @click="applyChanges" :disabled="changeCount === 0" round>
          Apply
        </el-button>
      </div>
    </div>

    <!-- Search -->
    <div class="search-box">
      <el-input
        v-model="searchKeyword"
        placeholder="Search folders..."
        size="large"
        @keyup.enter="performSearch"
        clearable
      >
        <template #prefix>
          <span class="search-icon">🔍</span>
        </template>
      </el-input>
      <el-button type="primary" @click="performSearch" size="large" round>Search</el-button>
    </div>

    <!-- Results Info -->
    <div v-if="searchResults.length > 0" class="results-header">
      <el-checkbox
        :model-value="allSelected"
        :indeterminate="someSelected"
        @change="toggleSelectAll"
      >
        {{ selectedFolders.size }} of {{ searchResults.length }} selected
      </el-checkbox>
    </div>

    <!-- Operations -->
    <div v-if="selectedFolders.size > 0" class="operations">
      <div class="op-card">
        <div class="op-row replace-row">
          <el-input v-model="batchOperations.replaceFrom" placeholder="Find" size="small" />
          <span class="op-arrow">→</span>
          <el-input v-model="batchOperations.replaceTo" placeholder="Replace" size="small" />
          <el-button @click="applyReplace" size="small" round>Go</el-button>
        </div>
      </div>

      <div class="op-card">
        <div class="op-row">
          <el-input v-model="batchOperations.prefix" placeholder="Add prefix..." size="small" />
          <el-button @click="applyPrefix" size="small" round>Go</el-button>
        </div>
      </div>

      <div class="op-card">
        <div class="op-row">
          <el-input v-model="batchOperations.suffix" placeholder="Add suffix..." size="small" />
          <el-button @click="applySuffix" size="small" round>Go</el-button>
        </div>
      </div>

      <div class="op-card">
        <div class="op-row">
          <el-input v-model="batchOperations.customTag" placeholder="Add tag..." size="small" />
          <el-button @click="applyCustomTag" size="small" round>Go</el-button>
        </div>
      </div>
    </div>

    <!-- Results -->
    <div v-if="searchResults.length > 0" class="results">
      <div
        v-for="folder in searchResults"
        :key="folder.id"
        class="result-card"
        :class="{ selected: isSelected(folder.id) }"
        @click="toggleSelect(folder.id)"
      >
        <div class="checkbox-col">
          <el-checkbox :model-value="isSelected(folder.id)" @click.stop />
        </div>
        <div class="info-col">
          <div class="name">{{ folder.name }}</div>
          <div class="meta">
            <span>{{ Math.round(folder.size / 1024 / 1024) }} MB</span>
            <span>•</span>
            <span>{{ folder.number }} files</span>
          </div>
          <div v-if="folder.tags && (folder.tags.auth.length || folder.tags.custom.length)" class="tags">
            <el-tag v-for="(tag, i) in folder.tags.auth" :key="'a' + i" size="small" round>{{ tag }}</el-tag>
            <el-tag v-for="(tag, i) in folder.tags.custom" :key="'c' + i" size="small" type="warning" round>{{ tag }}</el-tag>
          </div>
        </div>
      </div>
    </div>

    <!-- Empty -->
    <el-empty
      v-if="searchResults.length === 0 && searchKeyword"
      description="No results"
      :image-size="100"
    />
  </div>
</template>

<script lang="ts" src="@/manga_viwer/views/BatchOperationView.ts"></script>

<style scoped>
.batch-root {
  min-height: 100vh;
  background: #f5f5f7;
  padding: 20px;
}

.top-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 32px;
}

.back-btn {
  font-size: 15px;
  color: #06c;
  padding: 8px 0;
}

.back-icon {
  font-size: 18px;
  margin-right: 4px;
}

.actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 24px;
  height: 24px;
  padding: 0 8px;
  background: #ff3b30;
  color: white;
  border-radius: 12px;
  font-size: 13px;
  font-weight: 600;
}

.search-box {
  display: flex;
  gap: 12px;
  margin-bottom: 24px;
  max-width: 800px;
  margin-left: auto;
  margin-right: auto;
}

.search-icon {
  font-size: 16px;
}

.results-header {
  margin-bottom: 20px;
  padding: 12px 20px;
  background: white;
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

.operations {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 24px;
  max-width: 1400px;
  margin-left: auto;
  margin-right: auto;
}

.op-card {
  background: white;
  padding: 12px;
  border-radius: 10px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

.op-row {
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: center;
  gap: 6px;
}

.replace-row {
  display: grid;
  grid-template-columns: 1fr auto 1fr auto;
  align-items: center;
  gap: 6px;
}

.op-arrow {
  color: #86868b;
  font-size: 14px;
  text-align: center;
}

.results {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-width: 1400px;
  margin-left: auto;
  margin-right: auto;
}

.result-card {
  display: flex;
  gap: 16px;
  padding: 16px 20px;
  background: white;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

.result-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.result-card.selected {
  background: #f0f8ff;
  border: 1px solid #06c;
  box-shadow: 0 2px 8px rgba(0, 102, 204, 0.15);
}

.checkbox-col {
  display: flex;
  align-items: center;
}

.info-col {
  flex: 1;
  min-width: 0;
}

.name {
  font-size: 15px;
  font-weight: 500;
  color: #1d1d1f;
  margin-bottom: 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.meta {
  display: flex;
  gap: 8px;
  font-size: 13px;
  color: #86868b;
  margin-bottom: 8px;
}

.tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

@media (max-width: 1200px) {
  .operations {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .operations {
    grid-template-columns: 1fr;
  }

  .op-row {
    flex-direction: column;
  }
}
</style>
