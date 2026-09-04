<template>
  <div class="mc">
    <header class="mc-topbar">
      <el-button @click="goBack" circle size="small"><el-icon><ArrowLeft /></el-icon></el-button>
      <h1>Memory Curve</h1>
      <div class="mc-mode">
        <span>Card mode:</span>
        <el-radio-group :model-value="settings.card_mode" size="small"
                        @change="(v: any) => toggleMode(v)">
          <el-radio-button label="qa">Q / A</el-radio-button>
          <el-radio-button label="single">Single</el-radio-button>
        </el-radio-group>
      </div>
    </header>

    <el-tabs v-model="activeTab" class="mc-tabs">
      <!-- Review -->
      <el-tab-pane label="Review" name="review">
        <div class="mc-review">
          <template v-if="currentCard && !reviewDone">
            <div class="mc-card">
              <div class="mc-face">{{ currentCard.front }}</div>
              <template v-if="isQa">
                <el-divider v-if="answerShown" />
                <div v-if="answerShown" class="mc-face mc-back">{{ currentCard.back }}</div>
              </template>
            </div>

            <div class="mc-actions">
              <el-button v-if="isQa && !answerShown" type="primary" @click="showAnswer">
                Show Answer
              </el-button>
              <template v-else>
                <el-button @click="rate('again')">Again</el-button>
                <el-button type="warning" @click="rate('hard')">Hard</el-button>
                <el-button type="success" @click="rate('good')">Good</el-button>
                <el-button type="primary" @click="rate('easy')">Easy</el-button>
              </template>
            </div>
            <div class="mc-progress">{{ reviewIndex + 1 }} / {{ dueCards.length }}</div>
          </template>

          <el-empty v-else description="No cards due — you're all caught up 🎉">
            <el-button @click="loadDue">Refresh</el-button>
          </el-empty>
        </div>
      </el-tab-pane>

      <!-- Manage -->
      <el-tab-pane label="Cards" name="manage">
        <div class="mc-manage">
          <el-button type="primary" @click="openNew">+ New Card</el-button>
          <el-table :data="cards" style="width: 100%; margin-top: 12px;" size="small">
            <el-table-column prop="front" :label="isQa ? 'Front' : 'Content'" show-overflow-tooltip />
            <el-table-column v-if="isQa" prop="back" label="Back" show-overflow-tooltip />
            <el-table-column prop="due_date" label="Due" width="110" />
            <el-table-column prop="interval" label="Interval(d)" width="100" />
            <el-table-column prop="reps" label="Reps" width="70" />
            <el-table-column label="Actions" width="130">
              <template #default="{ row }">
                <el-button size="small" @click="openEdit(row)">Edit</el-button>
                <el-button size="small" type="danger" @click="removeCard(row)">Del</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- Editor dialog -->
    <el-dialog v-model="showEditor" :title="editing ? 'Edit Card' : 'New Card'" width="520">
      <el-form label-position="top">
        <el-form-item :label="isQa ? 'Front (question)' : 'Content'">
          <el-input v-model="draft.front" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item v-if="isQa" label="Back (answer)">
          <el-input v-model="draft.back" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="Deck (optional)">
          <el-input v-model="draft.deck" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditor = false">Cancel</el-button>
        <el-button type="primary" @click="saveDraft">Save</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script lang="ts" src="@/memory_curve/views/MemoryCurveView.ts"></script>

<style scoped>
.mc { min-height: 100vh; background: #f5f5f7; color: #1d1d1f;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; }
.mc-topbar { display: flex; align-items: center; justify-content: space-between;
  padding: 16px 24px; border-bottom: 1px solid rgba(0,0,0,0.06); background: #fff; }
.mc-topbar h1 { margin: 0; font-size: 20px; font-weight: 600; }
.mc-mode { display: flex; align-items: center; gap: 10px; font-size: 13px; color: #86868b; }
.mc-tabs { padding: 0 24px; }
.mc-review { max-width: 640px; margin: 40px auto; text-align: center; }
.mc-card { background: #fff; border-radius: 12px; box-shadow: 0 1px 4px rgba(0,0,0,0.08);
  padding: 40px 24px; min-height: 160px; margin-bottom: 24px; }
.mc-face { font-size: 20px; line-height: 1.5; white-space: pre-wrap; }
.mc-back { color: #0071e3; }
.mc-actions { display: flex; gap: 10px; justify-content: center; }
.mc-progress { margin-top: 16px; font-size: 12px; color: #86868b; }
.mc-manage { padding: 16px 0; }
</style>
