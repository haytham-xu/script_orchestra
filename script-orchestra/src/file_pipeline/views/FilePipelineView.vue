<template>
  <div class="fp-root">
    <div class="fp-header">
      <el-button type="default" size="small" @click="$router.back()">← Back</el-button>
      <h2 class="fp-title">File Pipeline</h2>
    </div>

    <el-tabs v-model="activeTab" class="fp-tabs">

      <!-- ===== Tab 1: Pipelines ===== -->
      <el-tab-pane label="Pipelines" name="pipelines">
        <div class="fp-body">
          <!-- Left: pipeline list -->
          <div class="fp-sidebar">
            <div class="sidebar-header">
              <span class="sidebar-title">Pipelines</span>
              <el-button size="small" type="primary" @click="newPipeline">+ New</el-button>
            </div>
            <div class="pipeline-list">
              <div
                v-for="p in pipelines"
                :key="p.id"
                class="pipeline-item"
                :class="{ active: selectedPipelineId === p.id }"
                @click="selectPipeline(p.id)"
              >
                <span class="pipeline-name">{{ p.name }}</span>
                <el-button size="small" type="danger" text @click.stop="confirmDeletePipeline(p.id)">✕</el-button>
              </div>
              <div v-if="!pipelines.length" class="list-empty">No pipelines yet.</div>
            </div>
          </div>

          <!-- Right: editor -->
          <div class="fp-editor" v-if="selectedPipelineId">
            <!-- Pipeline name + save + toolbar -->
            <div class="editor-topbar">
              <el-input v-model="pipelineName" size="small" placeholder="Pipeline name" style="width:180px" />
              <el-button size="small" type="primary" @click="savePipeline" :loading="saving">Save</el-button>
              <div class="topbar-divider" />
              <el-button
                v-for="t in nodeTypes" :key="t.type"
                size="small"
                @click="addNode(t.type)"
                :style="{ background: NODE_COLORS[t.type]?.bg, color:'#fff', borderColor: NODE_COLORS[t.type]?.border, fontSize:'12px' }"
              >+ {{ t.label }}</el-button>
              <div class="topbar-divider" />
              <el-button size="small" type="success" @click="showRun = true">▶ Run</el-button>
            </div>

            <!-- Vue Flow canvas + node panel side by side -->
            <div class="fp-canvas-area">
              <VueFlow
                v-model:nodes="vfNodes"
                v-model:edges="vfEdges"
                :default-viewport="{ zoom: 1 }"
                fit-view-on-init
                class="fp-flow"
                @node-click="onNodeClick"
                @pane-click="onPaneClick"
                @connect="onConnect"
                @edges-change="onEdgesChange"
                @nodes-change="onNodesChange"
              >
                <Background pattern-color="#e4e7ed" gap="20" />
                <Controls />
                <template #node-custom="nodeProps">
                  <CustomNode v-bind="nodeProps" :selected="nodeProps.id === selectedNodeId" />
                </template>
              </VueFlow>

              <!-- Node editor panel (right side) -->
              <transition name="slide">
                <div class="node-panel" v-if="selectedNode">
                  <div class="panel-header">
                    <div class="panel-type-badge" :style="{ background: NODE_COLORS[selectedNode.data.nodeType]?.bg }">{{ selectedNode.data.nodeType }}</div>
                    <el-button size="small" type="danger" text @click="deleteSelectedNode">Delete</el-button>
                  </div>
                  <!-- rename_ext -->
                  <template v-if="selectedNode.data.nodeType === 'rename_ext'">
                    <el-form size="small" label-position="top">
                      <el-form-item label="New extension">
                        <el-input v-model="selectedNode.data.params.new_ext" placeholder="zip" @input="syncNodeLabel" />
                      </el-form-item>
                    </el-form>
                  </template>
                  <!-- strip_cjk -->
                  <template v-else-if="selectedNode.data.nodeType === 'strip_cjk'">
                    <p class="panel-hint">Strips CJK characters appended after the file extension. No parameters needed.</p>
                  </template>
                  <!-- extract -->
                  <template v-else-if="selectedNode.data.nodeType === 'extract'">
                    <el-form size="small" label-position="top">
                      <el-form-item label="Tool">
                        <el-select v-model="selectedNode.data.params.tool_id" placeholder="Select tool" style="width:100%" @change="syncNodeLabel">
                          <el-option v-for="t in tools" :key="t.id" :label="t.name" :value="t.id" />
                        </el-select>
                      </el-form-item>
                      <el-form-item label="Password required">
                        <el-switch v-model="selectedNode.data.params.password_required" />
                      </el-form-item>
                      <el-form-item label="Password" v-if="selectedNode.data.params.password_required">
                        <el-input v-model="selectedNode.data.params.password" type="password" show-password />
                      </el-form-item>
                    </el-form>
                  </template>
                  <!-- condition -->
                  <template v-else-if="selectedNode.data.nodeType === 'condition'">
                    <p class="panel-hint">Connect edges from this node to branch targets. Label each edge with a keyword or <code>default</code> for fallback.</p>
                  </template>
                  <!-- start / end -->
                  <template v-else>
                    <p class="panel-hint">No parameters.</p>
                  </template>
                </div>
              </transition>
            </div>
          </div>
          <div class="fp-editor fp-editor-empty" v-else>
            Select or create a pipeline.
          </div>
        </div>
      </el-tab-pane>

      <!-- ===== Tab 2: Toolbox ===== -->
      <el-tab-pane label="Toolbox" name="toolbox">
        <div style="padding:16px">
          <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px">
            <span style="font-weight:600;font-size:15px">Extraction Tools</span>
            <el-button size="small" type="primary" @click="showAddTool = true">+ Add Tool</el-button>
          </div>
          <el-table :data="tools" size="small" stripe style="max-width:900px">
            <el-table-column prop="name" label="Name" width="140" />
            <el-table-column prop="exe_path" label="Exe Path" show-overflow-tooltip />
            <el-table-column prop="args_template" label="Args Template" show-overflow-tooltip />
            <el-table-column label="Actions" width="120">
              <template #default="{ row }">
                <el-button size="small" text @click="editTool(row)">Edit</el-button>
                <el-button size="small" text type="danger" @click="confirmDeleteTool(row.id)">Del</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div style="margin-top:12px;font-size:12px;color:#909399">
            Args template tokens: <code>{archive}</code> = archive file path, <code>{dest}</code> = output directory, <code>{password}</code> = password.
          </div>
        </div>
      </el-tab-pane>

    </el-tabs>

    <!-- Run dialog -->
    <el-dialog v-model="showRun" title="Run Pipeline" width="520px">
      <el-form label-position="top" size="small">
        <el-form-item label="Folder path (scan first-level files)">
          <el-input v-model="runFolderPath" placeholder="/path/to/folder" clearable />
        </el-form-item>
      </el-form>
      <div v-if="runResults">
        <el-table :data="runResults" size="small" stripe style="margin-top:12px" max-height="300">
          <el-table-column prop="file" label="File" show-overflow-tooltip />
          <el-table-column label="Steps" show-overflow-tooltip>
            <template #default="{ row }">{{ row.steps_taken?.join(' → ') }}</template>
          </el-table-column>
          <el-table-column prop="status" label="Status" width="80">
            <template #default="{ row }">
              <el-tag :type="row.status === 'done' ? 'success' : 'danger'" size="small">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="error" label="Error" show-overflow-tooltip />
        </el-table>
      </div>
      <template #footer>
        <el-button @click="showRun = false">Close</el-button>
        <el-button type="primary" @click="executePipeline" :loading="running">Execute</el-button>
      </template>
    </el-dialog>

    <!-- Add/Edit Tool dialog -->
    <el-dialog v-model="showAddTool" :title="editingTool ? 'Edit Tool' : 'Add Tool'" width="500px">
      <el-form :model="toolForm" label-position="top" size="small">
        <el-form-item label="Name"><el-input v-model="toolForm.name" /></el-form-item>
        <el-form-item label="Exe Path"><el-input v-model="toolForm.exe_path" placeholder='C:\Program Files\WinRAR\Rar.exe' /></el-form-item>
        <el-form-item label="Args Template"><el-input v-model="toolForm.args_template" placeholder='x "{archive}" "{dest}" -p{password} -y' /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddTool = false">Cancel</el-button>
        <el-button type="primary" @click="saveTool">Save</el-button>
      </template>
    </el-dialog>

    <!-- Edge label dialog (condition branches) -->
    <el-dialog v-model="showEdgeLabel" title="Edge label" width="380px">
      <el-form size="small" label-position="top">
        <el-form-item label="Keyword (or 'default' for fallback)">
          <el-input v-model="pendingEdgeLabel" placeholder="default" @keyup.enter="confirmEdge" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="cancelEdge">Cancel</el-button>
        <el-button type="primary" @click="confirmEdge">OK</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script lang="ts" setup>
import { ref, reactive, computed, onMounted, watch, defineComponent, h } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  VueFlow,
  useVueFlow,
  type Node,
  type Edge,
  type NodeMouseEvent,
  type Connection,
  type EdgeChange,
  type NodeChange,
  Position,
  Handle,
  applyNodeChanges,
  applyEdgeChanges,
} from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import { v4 as uuidv4 } from 'uuid'
import type { Tool, Pipeline } from '../service/FilePipelineService'
import {
  getTools, addTool, updateTool, deleteTool,
  getPipelines, getPipeline, addPipeline, updatePipeline, deletePipeline,
  runPipeline,
} from '../service/FilePipelineService'

// ---- node colors ----

const NODE_COLORS: Record<string, { bg: string; border: string; text: string }> = {
  start:      { bg: '#22c55e', border: '#16a34a', text: '#fff' },
  end:        { bg: '#ef4444', border: '#dc2626', text: '#fff' },
  rename_ext: { bg: '#3b82f6', border: '#2563eb', text: '#fff' },
  strip_cjk:  { bg: '#a855f7', border: '#9333ea', text: '#fff' },
  extract:    { bg: '#f97316', border: '#ea580c', text: '#fff' },
  condition:  { bg: '#64748b', border: '#475569', text: '#fff' },
}

const nodeTypes = [
  { type: 'rename_ext', label: 'rename_ext' },
  { type: 'strip_cjk',  label: 'strip_cjk'  },
  { type: 'extract',    label: 'extract'     },
  { type: 'condition',  label: 'condition'   },
  { type: 'end',        label: 'end'         },
]

// ---- custom node component ----

const CustomNode = defineComponent({
  name: 'CustomNode',
  props: {
    id: String,
    type: String,
    data: Object,
    selected: Boolean,
  },
  setup(props) {
    const colors = computed(() => NODE_COLORS[props.data?.nodeType || 'start'] || NODE_COLORS.start)
    const label = computed(() => props.data?.label || props.data?.nodeType || '')
    const showTarget = computed(() => props.data?.nodeType !== 'start')
    const showSource = computed(() => props.data?.nodeType !== 'end')
    return () => h('div', {
      style: {
        background: colors.value.bg,
        border: `2px solid ${props.selected ? '#1d1d1f' : colors.value.border}`,
        borderRadius: '8px',
        padding: '8px 16px',
        color: colors.value.text,
        fontWeight: '600',
        fontSize: '13px',
        minWidth: '90px',
        textAlign: 'center',
        boxShadow: props.selected ? '0 0 0 3px rgba(0,0,0,0.15)' : '0 1px 4px rgba(0,0,0,0.12)',
        cursor: 'pointer',
        userSelect: 'none',
      }
    }, [
      showTarget.value && h(Handle, { type: 'target', position: Position.Left }),
      h('span', label.value),
      showSource.value && h(Handle, { type: 'source', position: Position.Right }),
    ])
  },
})

// ---- state ----

const activeTab = ref('pipelines')
const pipelines = ref<Pipeline[]>([])
const tools = ref<Tool[]>([])
const selectedPipelineId = ref<number | null>(null)
const pipelineName = ref('')
const saving = ref(false)

// Vue Flow nodes/edges
const vfNodes = ref<Node[]>([])
const vfEdges = ref<Edge[]>([])

// selected node (from vfNodes)
const selectedNodeId = ref<string | null>(null)
const selectedNode = computed<Node | null>(() =>
  vfNodes.value.find(n => n.id === selectedNodeId.value) ?? null
)

// run
const showRun = ref(false)
const runFolderPath = ref('')
const runResults = ref<any[] | null>(null)
const running = ref(false)

// toolbox
const showAddTool = ref(false)
const editingTool = ref<Tool | null>(null)
const toolForm = reactive({ name: '', exe_path: '', args_template: '' })

// edge label dialog
const showEdgeLabel = ref(false)
const pendingEdgeLabel = ref('default')
let pendingEdgeConnection: Connection | null = null

// ---- helpers ----

function nodeLabel(type: string, params: any): string {
  if (type === 'rename_ext') return `rename → .${params?.new_ext || '?'}`
  return type
}

function defaultParams(type: string): any {
  if (type === 'rename_ext') return { new_ext: '' }
  if (type === 'extract')    return { tool_id: null, password: '', password_required: false }
  return {}
}

function toVfNode(n: any, index = 0): Node {
  const params = n.params || {}
  return {
    id: n.id,
    type: 'custom',
    position: { x: n.x ?? 100 + index * 160, y: n.y ?? 200 },
    data: { nodeType: n.type, label: nodeLabel(n.type, params), params },
  }
}

function toVfEdge(e: any): Edge {
  return {
    id: e.id,
    source: e.from,
    target: e.to,
    label: e.label || '',
    type: 'smoothstep',
    animated: false,
    style: { stroke: '#94a3b8', strokeWidth: 2 },
    labelStyle: { fontSize: '11px', fill: '#64748b' },
    labelBgStyle: { fill: '#f8fafc', fillOpacity: 0.9 },
  }
}

// ---- lifecycle ----

onMounted(async () => {
  await Promise.all([loadPipelines(), loadTools()])
})

async function loadPipelines() {
  pipelines.value = await getPipelines()
}

async function loadTools() {
  tools.value = await getTools()
}

// ---- pipeline actions ----

async function newPipeline() {
  const name = `Pipeline ${pipelines.value.length + 1}`
  const startNode = { id: uuidv4(), type: 'start', params: {}, x: 100, y: 200 }
  const graph = { nodes: [startNode], edges: [] }
  const id = await addPipeline(name, graph) as any
  await loadPipelines()
  selectPipeline(id)
}

async function selectPipeline(id: number) {
  selectedPipelineId.value = id
  selectedNodeId.value = null
  const p = await getPipeline(id)
  pipelineName.value = p.name
  const graph = p.steps ? JSON.parse(p.steps) : { nodes: [], edges: [] }
  vfNodes.value = (graph.nodes || []).map((n: any, i: number) => toVfNode(n, i))
  vfEdges.value = (graph.edges || []).map((e: any) => toVfEdge(e))
}

async function confirmDeletePipeline(id: number) {
  await ElMessageBox.confirm('Delete this pipeline?', 'Confirm', { type: 'warning' })
  await deletePipeline(id)
  if (selectedPipelineId.value === id) {
    selectedPipelineId.value = null
    vfNodes.value = []
    vfEdges.value = []
  }
  await loadPipelines()
}

async function savePipeline() {
  if (!selectedPipelineId.value) return
  saving.value = true
  try {
    const nodes = vfNodes.value.map(n => ({
      id: n.id,
      type: n.data.nodeType,
      params: n.data.params,
      x: n.position.x,
      y: n.position.y,
    }))
    const edges = vfEdges.value.map(e => ({
      id: e.id,
      from: e.source,
      to: e.target,
      label: e.label || '',
    }))
    await updatePipeline(selectedPipelineId.value, pipelineName.value, { nodes, edges })
    await loadPipelines()
    ElMessage.success('Saved')
  } finally {
    saving.value = false
  }
}

// ---- node actions ----

function addNode(type: string) {
  const node: Node = {
    id: uuidv4(),
    type: 'custom',
    position: { x: 200 + Math.random() * 200, y: 150 + Math.random() * 150 },
    data: { nodeType: type, label: nodeLabel(type, {}), params: defaultParams(type) },
  }
  vfNodes.value = [...vfNodes.value, node]
}

function deleteSelectedNode() {
  if (!selectedNodeId.value) return
  const id = selectedNodeId.value
  vfNodes.value = vfNodes.value.filter(n => n.id !== id)
  vfEdges.value = vfEdges.value.filter(e => e.source !== id && e.target !== id)
  selectedNodeId.value = null
}

function syncNodeLabel() {
  if (!selectedNode.value) return
  const n = selectedNode.value
  const newLabel = nodeLabel(n.data.nodeType, n.data.params)
  vfNodes.value = vfNodes.value.map(node =>
    node.id === n.id ? { ...node, data: { ...node.data, label: newLabel } } : node
  )
}

// ---- Vue Flow events ----

function onNodeClick(event: NodeMouseEvent) {
  selectedNodeId.value = event.node.id
}

function onPaneClick() {
  selectedNodeId.value = null
}

function onConnect(connection: Connection) {
  const fromNode = vfNodes.value.find(n => n.id === connection.source)
  if (fromNode?.data?.nodeType === 'condition') {
    pendingEdgeConnection = connection
    pendingEdgeLabel.value = 'default'
    showEdgeLabel.value = true
  } else {
    commitEdge(connection, '')
  }
}

function commitEdge(conn: Connection, label: string) {
  const edge: Edge = {
    id: uuidv4(),
    source: conn.source!,
    target: conn.target!,
    label,
    type: 'smoothstep',
    style: { stroke: '#94a3b8', strokeWidth: 2 },
    labelStyle: { fontSize: '11px', fill: '#64748b' },
    labelBgStyle: { fill: '#f8fafc', fillOpacity: 0.9 },
  }
  vfEdges.value = [...vfEdges.value, edge]
}

function confirmEdge() {
  showEdgeLabel.value = false
  if (pendingEdgeConnection) {
    commitEdge(pendingEdgeConnection, pendingEdgeLabel.value || 'default')
    pendingEdgeConnection = null
  }
}

function cancelEdge() {
  showEdgeLabel.value = false
  pendingEdgeConnection = null
}

function onEdgesChange(changes: EdgeChange[]) {
  vfEdges.value = applyEdgeChanges(changes, vfEdges.value)
}

function onNodesChange(changes: NodeChange[]) {
  vfNodes.value = applyNodeChanges(changes, vfNodes.value)
}

// ---- run ----

async function executePipeline() {
  if (!selectedPipelineId.value) return
  running.value = true
  runResults.value = null
  try {
    runResults.value = await runPipeline(selectedPipelineId.value, runFolderPath.value) as any
  } finally {
    running.value = false
  }
}

// ---- toolbox ----

function editTool(t: Tool) {
  editingTool.value = t
  Object.assign(toolForm, { name: t.name, exe_path: t.exe_path, args_template: t.args_template })
  showAddTool.value = true
}

async function saveTool() {
  if (editingTool.value) {
    await updateTool(editingTool.value.id, toolForm)
  } else {
    await addTool(toolForm)
  }
  showAddTool.value = false
  editingTool.value = null
  Object.assign(toolForm, { name: '', exe_path: '', args_template: '' })
  await loadTools()
}

async function confirmDeleteTool(id: number) {
  await ElMessageBox.confirm('Delete this tool?', 'Confirm', { type: 'warning' })
  await deleteTool(id)
  await loadTools()
}

watch(showAddTool, (v) => {
  if (!v) {
    editingTool.value = null
    Object.assign(toolForm, { name: '', exe_path: '', args_template: '' })
  }
})
</script>

<style scoped>
.fp-root { min-height: 100vh; padding: 24px; box-sizing: border-box; }
.fp-header { display: flex; align-items: center; gap: 16px; margin-bottom: 16px; }
.fp-title { margin: 0; font-size: 22px; font-weight: 600; }

.fp-body { display: flex; gap: 0; height: calc(100vh - 160px); }

.fp-sidebar { width: 220px; flex-shrink: 0; border-right: 1px solid #e4e7ed; padding-right: 12px; display: flex; flex-direction: column; }
.sidebar-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.sidebar-title { font-weight: 600; font-size: 14px; }
.pipeline-list { flex: 1; overflow-y: auto; }
.pipeline-item { display: flex; align-items: center; justify-content: space-between; padding: 8px 10px; border-radius: 8px; cursor: pointer; margin-bottom: 2px; }
.pipeline-item:hover { background: #f5f7fa; }
.pipeline-item.active { background: #ecf5ff; }
.pipeline-name { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.list-empty { color: #909399; font-size: 13px; padding: 16px 0; text-align: center; }

.fp-editor { flex: 1; min-width: 0; padding-left: 16px; display: flex; flex-direction: column; gap: 10px; }
.fp-editor-empty { display: flex; align-items: center; justify-content: center; color: #909399; }

.editor-topbar { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.topbar-divider { width: 1px; height: 20px; background: #dcdfe6; margin: 0 2px; }

.fp-canvas-area { flex: 1; min-height: 0; display: flex; gap: 0; border: 1px solid #dcdfe6; border-radius: 10px; overflow: hidden; }

.fp-flow { flex: 1; min-width: 0; }

/* Vue Flow overrides */
:deep(.vue-flow__controls) { box-shadow: 0 2px 8px rgba(0,0,0,0.1); border-radius: 8px; }
:deep(.vue-flow__controls-button) { border: 1px solid #e4e7ed; border-radius: 4px; }

/* Node panel */
.node-panel {
  width: 260px;
  flex-shrink: 0;
  border-left: 1px solid #e4e7ed;
  background: #fff;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow-y: auto;
}
.panel-header { display: flex; align-items: center; justify-content: space-between; }
.panel-type-badge {
  display: inline-block;
  padding: 3px 10px;
  border-radius: 12px;
  color: #fff;
  font-size: 12px;
  font-weight: 600;
}
.panel-hint { font-size: 12px; color: #909399; line-height: 1.6; margin: 0; }

.slide-enter-active, .slide-leave-active { transition: width 0.2s ease, opacity 0.2s ease; }
.slide-enter-from, .slide-leave-to { width: 0; opacity: 0; }
</style>
