<template>
  <el-dialog
    v-model="visible"
    title="Gap Analysis — Possible Missed Duplicates"
    width="860px"
    :close-on-click-modal="false"
    @close="$emit('close')"
  >
    <div class="gap-dialog-body">
      <el-alert type="info" :closable="false" style="margin-bottom: 16px;">
        <template #title>
          These images were NOT flagged as duplicates but are visually similar to images
          already identified. Check the pairs you want to confirm.
        </template>
      </el-alert>

      <div v-if="pairs.length === 0" class="no-pairs">No missed duplicates found.</div>

      <div v-else class="pair-list">
        <div v-for="(pair, idx) in pairs" :key="pair.gap_id + '-' + pair.candidate_id" class="pair-card">
          <el-checkbox v-model="pair.checked" class="pair-checkbox" />

          <div class="pair-images">
            <!-- Gap image (undetected) -->
            <div class="image-side">
              <div class="image-label">Undetected</div>
              <img :src="getImageUrl(pair.gap_file)" class="thumb" loading="lazy" />
              <div class="image-path" :title="pair.gap_file">{{ basename(pair.gap_file) }}</div>
            </div>

            <!-- Similarity badge -->
            <div class="similarity-badge" :class="badgeClass(pair.similarity_pct)">
              {{ pair.similarity_pct.toFixed(1) }}%
            </div>

            <!-- Candidate image (known duplicate) -->
            <div class="image-side">
              <div class="image-label">Known duplicate</div>
              <img :src="getImageUrl(pair.candidate_file)" class="thumb" loading="lazy" />
              <div class="image-path" :title="pair.candidate_file">{{ basename(pair.candidate_file) }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="$emit('close')">Cancel</el-button>
        <el-button type="primary" :disabled="checkedCount === 0" @click="$emit('confirm', false)">
          Add {{ checkedCount }} pair(s) to DB
        </el-button>
        <el-button
          v-if="context === 'deep_path'"
          type="danger"
          :disabled="checkedCount === 0"
          @click="$emit('confirm', true)"
        >
          Add to DB + Include in Delete
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { GapPair } from '../service/Model'
import { DuplicateFinderService } from '../service/DuplicateFinderService'

const props = defineProps<{
  modelValue: boolean
  pairs: GapPair[]
  context: 'global' | 'deep_path' | 'group'
}>()

defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'close'): void
  (e: 'confirm', includeInDelete: boolean): void
}>()

const visible = computed(() => props.modelValue)

const checkedCount = computed(() => props.pairs.filter(p => p.checked).length)

function getImageUrl(path: string) {
  return DuplicateFinderService.getImageUrl(path)
}

function basename(path: string) {
  return path.replace(/\\/g, '/').split('/').pop() || path
}

function badgeClass(sim: number) {
  if (sim >= 80) return 'badge-green'
  if (sim >= 70) return 'badge-orange'
  return 'badge-yellow'
}
</script>

<style scoped>
.gap-dialog-body {
  max-height: 60vh;
  overflow-y: auto;
}

.no-pairs {
  text-align: center;
  color: #909399;
  padding: 32px;
}

.pair-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.pair-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  background: #fafafa;
}

.pair-card:hover {
  background: #f0f9ff;
  border-color: #b3d8ff;
}

.pair-checkbox {
  flex-shrink: 0;
}

.pair-images {
  display: flex;
  align-items: center;
  gap: 16px;
  flex: 1;
}

.image-side {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  width: 160px;
}

.image-label {
  font-size: 11px;
  color: #909399;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.thumb {
  width: 140px;
  height: 100px;
  object-fit: cover;
  border-radius: 4px;
  border: 1px solid #ddd;
  background: #f5f5f5;
}

.image-path {
  font-size: 11px;
  color: #606266;
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: center;
}

.similarity-badge {
  flex-shrink: 0;
  padding: 4px 10px;
  border-radius: 12px;
  font-size: 13px;
  font-weight: 600;
}

.badge-green {
  background: #f0f9eb;
  color: #67c23a;
  border: 1px solid #c2e7b0;
}

.badge-orange {
  background: #fdf6ec;
  color: #e6a23c;
  border: 1px solid #f5dab1;
}

.badge-yellow {
  background: #fef9e7;
  color: #d4ac0d;
  border: 1px solid #ede27a;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
