<template>
  <div class="kvs">
    <!-- top bar -->
    <header class="kvs-topbar">
      <el-button @click="goBack" circle size="small"><el-icon><ArrowLeft /></el-icon></el-button>
      <h1>Knowledge Vault — Settings</h1>
    </header>

    <div class="kvs-body">

      <!-- Labels card -->
      <div class="kvs-card">
        <div class="kvs-card-title">Labels</div>
        <div class="kvs-card-divider" />

        <!-- new label form -->
        <div class="kvs-label-form">
          <div class="kvs-swatches">
            <button v-for="c in labelPresetColors" :key="c"
              class="kvs-swatch" :style="{ background: c }"
              :class="{ 'kvs-swatch--active': newLabel.color === c }"
              @click="newLabel.color = c" />
          </div>
          <div class="kvs-label-form-row">
            <span class="kvs-dot" :style="{ background: newLabel.color }" />
            <el-input v-model="newLabel.name" placeholder="Label name" @keyup.enter="addLabel" />
            <el-button type="primary" @click="addLabel">Add</el-button>
          </div>
        </div>

        <!-- existing labels -->
        <div class="kvs-label-list">
          <el-empty v-if="!labels.length" description="No labels yet" :image-size="50" />
          <template v-for="l in labels" :key="l.id">
            <!-- view -->
            <div v-if="editingLabelId !== l.id" class="kvs-label-row">
              <span class="kvs-dot" :style="{ background: l.color }" />
              <span class="kvs-label-name">{{ l.name }}</span>
              <el-button text size="small" @click="startEditLabel(l)">Edit</el-button>
              <el-button text size="small" type="danger" @click="removeLabel(l)">✕</el-button>
            </div>
            <!-- inline edit -->
            <div v-else class="kvs-label-row kvs-label-row--editing">
              <div class="kvs-edit-swatches">
                <button v-for="c in labelPresetColors" :key="c"
                  class="kvs-swatch kvs-swatch--sm" :style="{ background: c }"
                  :class="{ 'kvs-swatch--active': editingLabelColor === c }"
                  @click="editingLabelColor = c" />
              </div>
              <span class="kvs-dot" :style="{ background: editingLabelColor }" />
              <el-input v-model="editingLabelName" size="small" style="width:130px" @keyup.enter="saveEditLabel" />
              <el-button type="primary" size="small" @click="saveEditLabel">Save</el-button>
              <el-button size="small" @click="cancelEditLabel">Cancel</el-button>
            </div>
          </template>
        </div>
      </div>

      <!-- AI Model card -->
      <div class="kvs-card">
        <div class="kvs-card-title">AI Model</div>
        <div class="kvs-card-divider" />
        <div class="kvs-field-row">
          <el-input v-model="settings.ai_model" placeholder="model id" @keyup.enter="saveAiModel" />
          <el-button type="primary" @click="saveAiModel">Save</el-button>
        </div>
        <p class="kvs-hint">Used by AI features (Claude model ID)</p>
      </div>

      <!-- Embed Model card -->
      <div class="kvs-card">
        <div class="kvs-card-title">Embedding Model</div>
        <div class="kvs-card-divider" />
        <div class="kvs-field-row">
          <el-input v-model="settings.embed_model" placeholder="sentence-transformers model name" @keyup.enter="saveEmbedModel" />
          <el-button type="primary" @click="saveEmbedModel">Save</el-button>
        </div>
        <p class="kvs-hint">sentence-transformers model for semantic search. After changing, rebuild the search index from the Capture page.</p>
      </div>

    </div>
  </div>
</template>

<script lang="ts" src="@/knowledge_vault/views/KnowledgeVaultSettingsView.ts"></script>

<style scoped>
.kvs {
  height: 100vh; display: flex; flex-direction: column; overflow: hidden;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
  background: #f5f5f7; color: #1d1d1f;
}

/* topbar */
.kvs-topbar {
  display: flex; align-items: center; gap: 12px;
  padding: 8px 20px; background: #fff;
  border-bottom: 1px solid rgba(0,0,0,0.07); flex-shrink: 0;
}
.kvs-topbar h1 { margin: 0; font-size: 17px; font-weight: 600; }

/* body: centered, scrollable */
.kvs-body {
  flex: 1; overflow-y: auto;
  padding: 32px 20px;
  display: flex; flex-direction: column; align-items: center; gap: 20px;
}

/* card */
.kvs-card {
  width: 100%; max-width: 640px;
  background: #fff; border: 1px solid rgba(0,0,0,0.07);
  border-radius: 14px; padding: 22px 24px;
}
.kvs-card-title { font-size: 16px; font-weight: 600; color: #1d1d1f; margin-bottom: 14px; }
.kvs-card-divider { height: 1px; background: rgba(0,0,0,0.07); margin-bottom: 18px; }

/* label form */
.kvs-label-form { margin-bottom: 16px; }
.kvs-swatches { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 10px; }
.kvs-swatch {
  width: 24px; height: 24px; border-radius: 50%; border: 2px solid transparent;
  cursor: pointer; transition: transform .1s, border-color .1s;
}
.kvs-swatch:hover { transform: scale(1.15); }
.kvs-swatch--active { border-color: rgba(0,0,0,0.3); transform: scale(1.2); }
.kvs-swatch--sm { width: 18px; height: 18px; }
.kvs-label-form-row { display: flex; align-items: center; gap: 8px; }

/* label list */
.kvs-label-list { display: flex; flex-direction: column; gap: 6px; }
.kvs-label-row {
  display: flex; align-items: center; gap: 8px;
  padding: 7px 10px; border-radius: 8px; background: #f8f9fa;
  transition: background .1s;
}
.kvs-label-row:hover { background: #f0f2f5; }
.kvs-label-row--editing { flex-direction: column; align-items: flex-start; gap: 8px; padding: 10px; }
.kvs-label-row--editing > :not(.kvs-edit-swatches) { align-self: center; }
.kvs-label-row--editing { flex-direction: row; flex-wrap: wrap; align-items: center; }
.kvs-edit-swatches { display: flex; gap: 4px; flex-wrap: wrap; width: 100%; }
.kvs-label-name { flex: 1; font-size: 13px; color: #1d1d1f; }
.kvs-dot { width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }

/* AI model + reindex */
.kvs-field-row { display: flex; gap: 10px; align-items: center; }
.kvs-hint { font-size: 12px; color: #86868b; margin: 8px 0 0; }
.kvs-progress-wrap { display: flex; align-items: center; gap: 10px; margin-top: 12px; }
</style>
