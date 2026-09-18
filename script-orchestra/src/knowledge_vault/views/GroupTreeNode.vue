<template>
  <div class="sg-item" :class="{ 'sg-item--active': currentGroupId === group.id }">
    <div class="sg-row" @click="$emit('select', group.id)">
      <el-icon class="sg-toggle" @click.stop="expanded = !expanded">
        <ArrowRight v-if="!expanded && hasChildren" />
        <ArrowDown v-else-if="expanded && hasChildren" />
        <span v-else class="sg-leaf" />
      </el-icon>
      <span class="sg-name">{{ group.name }}</span>
      <span v-if="group.note" class="sg-note">{{ group.note }}</span>
      <div class="sg-actions">
        <el-button text size="small" @click.stop="$emit('add-sub', group.id)">+</el-button>
        <el-button text size="small" @click.stop="$emit('edit', group)">⋯</el-button>
        <el-button text size="small" type="danger" @click.stop="$emit('delete', group)">✕</el-button>
      </div>
    </div>
    <div v-if="expanded && hasChildren" class="sg-children">
      <group-tree-node
        v-for="child in group.children"
        :key="child.id"
        :group="child"
        :current-group-id="currentGroupId"
        @select="$emit('select', $event)"
        @edit="$emit('edit', $event)"
        @delete="$emit('delete', $event)"
        @add-sub="$emit('add-sub', $event)"
      />
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, computed } from 'vue'
import type { PropType } from 'vue'
import type { FragmentGroup } from '../service/Model'
import { ArrowRight, ArrowDown } from '@element-plus/icons-vue'

export default defineComponent({
  name: 'GroupTreeNode',
  components: { ArrowRight, ArrowDown },
  props: {
    group: { type: Object as PropType<FragmentGroup>, required: true },
    currentGroupId: { type: Number as PropType<number | null>, default: null },
  },
  emits: ['select', 'edit', 'delete', 'add-sub'],
  setup(props) {
    const expanded = ref(true)
    const hasChildren = computed(() => (props.group.children?.length ?? 0) > 0)
    return { expanded, hasChildren }
  },
})
</script>

<style scoped>
.sg-item { user-select: none; }
.sg-row {
  display: flex; align-items: center; gap: 4px;
  padding: 5px 8px; border-radius: 6px; cursor: pointer;
  transition: background .1s;
}
.sg-row:hover { background: rgba(10,132,255,0.08); }
.sg-item--active > .sg-row { background: rgba(10,132,255,0.14); color: #0a84ff; }
.sg-item--active > .sg-row .sg-name { color: #0a84ff; font-weight: 600; }
.sg-toggle { font-size: 10px; color: #909399; flex-shrink: 0; width: 14px; }
.sg-leaf { display: inline-block; width: 14px; }
.sg-name { font-size: 13px; color: #1d1d1f; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sg-note { font-size: 11px; color: #b0b0b8; max-width: 80px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sg-actions { display: flex; gap: 0; opacity: 0; transition: opacity .15s; flex-shrink: 0; }
.sg-row:hover .sg-actions { opacity: 1; }
.sg-children { padding-left: 14px; }
</style>
