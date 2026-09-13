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
            <!-- Pipeline name + save -->
            <div class="editor-topbar">
              <el-input v-model="pipelineName" size="small" placeholder="Pipeline name" style="width:200px" />
              <el-button size="small" type="primary" @click="savePipeline" :loading="saving">Save</el-button>
              <span style="flex:1" />
              <!-- Node type buttons -->
              <el-button-group size="small">
                <el-button v-for="t in nodeTypes" :key="t.type" @click="addNode(t.type)" :style="{ background: TYPE_COLOR[t.type].bg, color:'#fff', borderColor: TYPE_COLOR[t.type].border }">
                  + {{ t.label }}
                </el-button>
              </el-button-group>
              <el-button size="small" :type="connectMode ? 'warning' : 'default'" @click="toggleConnectMode" style="margin-left:12px">↔ {{ connectMode ? 'Cancel Connect' : 'Connect' }}</el-button>
              <el-button size="small" type="success" @click="showRun = true" style="margin-left:12px">▶ Run</el-button>
            </div>

            <!-- Canvas -->
            <div ref="graphEl" class="fp-canvas"></div>

            <!-- Node editor panel -->
            <div class="node-editor" v-if="selectedNode">
              <div class="node-editor-title">
                Edit: <b>{{ selectedNode.type }}</b>
                <el-button size="small" type="danger" text @click="deleteSelectedNode" style="margin-left:8px">Delete node</el-button>
              </div>
              <!-- rename_ext -->
              <template v-if="selectedNode.type === 'rename_ext'">
                <el-form size="small" label-width="120px">
                  <el-form-item label="New extension">
                    <el-input v-model="selectedNode.params.new_ext" placeholder="zip" @change="updateNodeLabel" />
                  </el-form-item>
                </el-form>
              </template>
              <!-- strip_cjk -->
              <template v-if="selectedNode.type === 'strip_cjk'">
                <div style="color:#909399;font-size:13px">Strips CJK characters appended after the file extension. No parameters needed.</div>
              </template>
              <!-- extract -->
              <template v-if="selectedNode.type === 'extract'">
                <el-form size="small" label-width="140px">
                  <el-form-item label="Tool">
                    <el-select v-model="selectedNode.params.tool_id" placeholder="Select tool" @change="updateNodeLabel">
                      <el-option v-for="t in tools" :key="t.id" :label="t.name" :value="t.id" />
                    </el-select>
                  </el-form-item>
                  <el-form-item label="Password required">
                    <el-switch v-model="selectedNode.params.password_required" />
                  </el-form-item>
                  <el-form-item label="Password" v-if="selectedNode.params.password_required">
                    <el-input v-model="selectedNode.params.password" placeholder="optional" />
                  </el-form-item>
                </el-form>
              </template>
              <!-- condition -->
              <template v-if="selectedNode.type === 'condition'">
                <div style="font-size:13px;color:#606266;margin-bottom:8px">
                  Branches: match filename contains keyword. Add one edge per keyword from this node; label the edge with the keyword. Use <code>default</code> for fallback.
                </div>
                <div style="font-size:12px;color:#909399">Connect edges from this node to targets using the canvas. Label each edge with a keyword or "default".</div>
              </template>
              <!-- start / end -->
              <template v-if="selectedNode.type === 'start' || selectedNode.type === 'end'">
                <div style="color:#909399;font-size:13px">No parameters.</div>
              </template>
            </div>
            <div class="node-editor node-editor-empty" v-else>
              Click a node to edit its parameters. Drag between nodes to connect them.<br/>
              When connecting from a condition node, enter the branch keyword as the edge label.
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
            Args template tokens: <code>{archive}</code> = archive file path, <code>{dest}</code> = output directory, <code>{password}</code> = password (omitted if not required).
          </div>
        </div>
      </el-tab-pane>

    </el-tabs>

    <!-- Run dialog -->
    <el-dialog v-model="showRun" title="Run Pipeline" width="500px">
      <el-form label-position="top" size="small">
        <el-form-item label="Folder path (scan first-level files)">
          <el-input v-model="runFolderPath" placeholder="C:\Users\...\folder" clearable />
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

    <!-- Edge label dialog -->
    <el-dialog v-model="showEdgeLabel" title="Edge label (branch keyword)" width="380px">
      <el-form size="small" label-position="top">
        <el-form-item label="Keyword (or 'default' for fallback)">
          <el-input v-model="pendingEdgeLabel" placeholder="default" />
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
import { ref, reactive, onMounted, nextTick, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Network, DataSet } from 'vis-network/standalone'
import { v4 as uuidv4 } from 'uuid'
import type { Tool, Pipeline } from '../service/FilePipelineService'
import {
  getTools, addTool, updateTool, deleteTool,
  getPipelines, getPipeline, addPipeline, updatePipeline, deletePipeline,
  runPipeline,
} from '../service/FilePipelineService'

// ---- constants ----

const TYPE_COLOR: Record<string, { bg: string; border: string }> = {
  start:      { bg: '#34c759', border: '#248a3d' },
  end:        { bg: '#ff3b30', border: '#c0392b' },
  rename_ext: { bg: '#0a84ff', border: '#0060c7' },
  strip_cjk:  { bg: '#bf5af2', border: '#8944ab' },
  extract:    { bg: '#ff9f0a', border: '#b97200' },
  condition:  { bg: '#636366', border: '#3a3a3c' },
}

const nodeTypes = [
  { type: 'rename_ext', label: 'rename_ext' },
  { type: 'strip_cjk',  label: 'strip_cjk'  },
  { type: 'extract',    label: 'extract'     },
  { type: 'condition',  label: 'condition'   },
  { type: 'end',        label: 'end'         },
]

function defaultParams(type: string): any {
  if (type === 'rename_ext') return { new_ext: '' }
  if (type === 'extract')    return { tool_id: null, password: '', password_required: false }
  return {}
}

function nodeLabel(type: string, params: any): string {
  if (type === 'rename_ext') return `rename → .${params.new_ext || '?'}`
  if (type === 'extract')    return `extract`
  return type
}

// ---- state ----

const activeTab = ref('pipelines')
const pipelines = ref<Pipeline[]>([])
const tools = ref<Tool[]>([])
const selectedPipelineId = ref<number | null>(null)
const pipelineName = ref('')
const saving = ref(false)

// vis-network
const graphEl = ref<HTMLElement | null>(null)
let network: Network | null = null
let visNodes: DataSet<any>
let visEdges: DataSet<any>

// local graph model
interface NodeModel { id: string; type: string; params: any; x?: number; y?: number }
interface EdgeModel { id: string; from: string; to: string; label: string }
const graphNodes = ref<NodeModel[]>([])
const graphEdges = ref<EdgeModel[]>([])

const selectedNode = ref<NodeModel | null>(null)
const connectMode = ref(false)

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
let pendingEdgeCallback: ((label: string | null) => void) | null = null

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

// ---- pipeline list actions ----

async function newPipeline() {
  const name = `Pipeline ${pipelines.value.length + 1}`
  const startNode: NodeModel = { id: uuidv4(), type: 'start', params: {}, x: 100, y: 200 }
  const graph = { nodes: [startNode], edges: [] }
  const id = await addPipeline(name, graph)
  await loadPipelines()
  selectPipeline(id)
}

async function selectPipeline(id: number) {
  selectedPipelineId.value = id
  const p = await getPipeline(id)
  pipelineName.value = p.name
  const graph = p.steps ? JSON.parse(p.steps) : { nodes: [], edges: [] }
  graphNodes.value = graph.nodes || []
  graphEdges.value = graph.edges || []
  selectedNode.value = null
  await nextTick()
  initNetwork()
}

async function confirmDeletePipeline(id: number) {
  await ElMessageBox.confirm('Delete this pipeline?', 'Confirm', { type: 'warning' })
  await deletePipeline(id)
  if (selectedPipelineId.value === id) {
    selectedPipelineId.value = null
    network = null
  }
  await loadPipelines()
}

async function savePipeline() {
  if (!selectedPipelineId.value) return
  saving.value = true
  try {
    const positions = network ? network.getPositions() : {}
    const nodes = graphNodes.value.map(n => {
      const pos = positions[n.id]
      return { ...n, x: pos?.x ?? n.x, y: pos?.y ?? n.y }
    })
    const graph = { nodes, edges: graphEdges.value }
    await updatePipeline(selectedPipelineId.value, pipelineName.value, graph)
    await loadPipelines()
    ElMessage.success('Saved')
  } finally {
    saving.value = false
  }
}

// ---- vis-network ----

function toVisNode(n: NodeModel) {
  const c = TYPE_COLOR[n.type] || { bg: '#8e8e93', border: '#636366' }
  return {
    id: n.id,
    label: nodeLabel(n.type, n.params),
    color: { background: c.bg, border: c.border, highlight: { background: c.bg, border: '#1d1d1f' } },
    font: { color: '#fff', size: 13, bold: true },
    shape: 'box',
    borderWidth: 2,
    x: n.x,
    y: n.y,
  }
}

function toVisEdge(e: EdgeModel) {
  return {
    id: e.id,
    from: e.from,
    to: e.to,
    label: e.label || '',
    font: { size: 11, color: '#606266', strokeWidth: 0 },
    color: { color: '#c7c7cc', highlight: '#0a84ff' },
    arrows: { to: { enabled: true, scaleFactor: 0.6 } },
    smooth: { enabled: true, type: 'curvedCW', roundness: 0.2 },
  }
}

function initNetwork() {
  if (!graphEl.value) return

  visNodes = new DataSet(graphNodes.value.map(toVisNode))
  visEdges = new DataSet(graphEdges.value.map(toVisEdge))

  const options = {
    physics: { enabled: false },
    interaction: { hover: true },
    manipulation: {
      enabled: false,
      addNode: false,
      addEdge: (edgeData: any, callback: Function) => {
        askEdgeLabel(edgeData.from, (label) => {
          connectMode.value = false
          if (label === null) { callback(null); return }
          const newEdge: EdgeModel = { id: uuidv4(), from: edgeData.from, to: edgeData.to, label }
          graphEdges.value.push(newEdge)
          edgeData.id = newEdge.id
          edgeData.label = label
          callback(edgeData)
        })
      },
    },
    edges: { smooth: { enabled: true, type: 'curvedCW', roundness: 0.2 } },
  }

  if (network) {
    network.destroy()
  }
  network = new Network(graphEl.value, { nodes: visNodes, edges: visEdges }, options as any)

  network.on('click', (params: any) => {
    const nodeId = params.nodes?.[0]
    if (nodeId) {
      selectedNode.value = graphNodes.value.find(n => n.id === nodeId) || null
    } else {
      selectedNode.value = null
    }
  })
}

// ---- node actions ----

function addNode(type: string) {
  const node: NodeModel = {
    id: uuidv4(),
    type,
    params: defaultParams(type),
    x: 200 + Math.random() * 200,
    y: 200 + Math.random() * 150,
  }
  graphNodes.value.push(node)
  if (visNodes) visNodes.add(toVisNode(node))
}

function deleteSelectedNode() {
  if (!selectedNode.value) return
  const id = selectedNode.value.id
  const edgesToRemove = graphEdges.value.filter(e => e.from === id || e.to === id).map(e => e.id)
  graphNodes.value = graphNodes.value.filter(n => n.id !== id)
  graphEdges.value = graphEdges.value.filter(e => e.from !== id && e.to !== id)
  if (visNodes) visNodes.remove(id)
  if (visEdges) visEdges.remove(edgesToRemove)
  selectedNode.value = null
}

function updateNodeLabel() {
  if (!selectedNode.value || !visNodes) return
  visNodes.update({ id: selectedNode.value.id, label: nodeLabel(selectedNode.value.type, selectedNode.value.params) })
}

function toggleConnectMode() {
  if (!network) return
  if (connectMode.value) {
    network.disableEditMode()
    connectMode.value = false
  } else {
    network.addEdgeMode()
    connectMode.value = true
  }
}

// ---- edge label dialog ----

function askEdgeLabel(fromNodeId: string, cb: (label: string | null) => void) {
  const fromNode = graphNodes.value.find(n => n.id === fromNodeId)
  if (fromNode?.type !== 'condition') {
    cb('')
    return
  }
  pendingEdgeLabel.value = 'default'
  pendingEdgeCallback = cb
  showEdgeLabel.value = true
}

function confirmEdge() {
  showEdgeLabel.value = false
  pendingEdgeCallback?.(pendingEdgeLabel.value || 'default')
  pendingEdgeCallback = null
}

function cancelEdge() {
  showEdgeLabel.value = false
  pendingEdgeCallback?.(null)
  pendingEdgeCallback = null
}

// ---- run ----

async function executePipeline() {
  if (!selectedPipelineId.value) return
  running.value = true
  runResults.value = null
  try {
    runResults.value = await runPipeline(selectedPipelineId.value, runFolderPath.value)
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

.fp-sidebar { width: 240px; flex-shrink: 0; border-right: 1px solid #e4e7ed; padding-right: 12px; display: flex; flex-direction: column; }
.sidebar-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.sidebar-title { font-weight: 600; font-size: 14px; }
.pipeline-list { flex: 1; overflow-y: auto; }
.pipeline-item { display: flex; align-items: center; justify-content: space-between; padding: 8px 10px; border-radius: 8px; cursor: pointer; margin-bottom: 2px; }
.pipeline-item:hover { background: #f5f7fa; }
.pipeline-item.active { background: #ecf5ff; }
.pipeline-name { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.list-empty { color: #909399; font-size: 13px; padding: 16px 0; text-align: center; }

.fp-editor { flex: 1; min-width: 0; padding-left: 16px; display: flex; flex-direction: column; gap: 0; }
.fp-editor-empty { display: flex; align-items: center; justify-content: center; color: #909399; }

.editor-topbar { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }

.fp-canvas { flex: 1; min-height: 300px; border: 1px solid #dcdfe6; border-radius: 8px; background: #fafafa; }

.node-editor { border-top: 1px solid #e4e7ed; padding: 12px; min-height: 80px; background: #fff; }
.node-editor-title { font-weight: 600; font-size: 13px; margin-bottom: 10px; display: flex; align-items: center; }
.node-editor-empty { color: #909399; font-size: 13px; display: flex; align-items: center; }
</style>
