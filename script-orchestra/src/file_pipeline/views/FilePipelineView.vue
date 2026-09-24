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

          <!-- Right: editor with inner tabs -->
          <div class="fp-editor" v-if="selectedPipelineId">
            <!-- Shared top bar: name / save / run -->
            <div class="editor-topbar-main">
              <el-input v-model="pipelineName" size="small" placeholder="Pipeline name" style="width:180px" />
              <el-button size="small" type="primary" @click="savePipeline" :loading="saving">Save</el-button>
              <div class="topbar-divider" />
              <el-button size="small" type="success" @click="startRun" :loading="running">▶ Run</el-button>
            </div>

            <!-- Inner tabs: Graph / Settings / Progress -->
            <el-tabs v-model="editorTab" class="editor-inner-tabs">

              <!-- Graph tab -->
              <el-tab-pane label="Graph" name="graph">
                <div class="node-toolbar">
                  <el-button
                    v-for="t in nodeTypes" :key="t.type"
                    size="small"
                    @click="addNode(t.type)"
                    :style="{ background: NODE_COLORS[t.type]?.bg, color:'#fff', borderColor: NODE_COLORS[t.type]?.border, fontSize:'12px' }"
                  >+ {{ t.label }}</el-button>
                </div>
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
                          <el-form-item label="Use password list">
                            <el-switch v-model="selectedNode.data.params.use_password_list" />
                            <span style="font-size:11px;color:#909399;margin-left:8px">Try vault passwords if first fails</span>
                          </el-form-item>
                        </el-form>
                      </template>
                      <!-- condition -->
                      <template v-else-if="selectedNode.data.nodeType === 'condition'">
                        <p class="panel-hint">Connect edges from this node to branch targets. Label each edge with a keyword or <code>default</code> for fallback.</p>
                      </template>
                      <!-- mkdir_and_move -->
                      <template v-else-if="selectedNode.data.nodeType === 'mkdir_and_move'">
                        <p class="panel-hint">Creates a folder named after the file (without extension) in the same directory, then moves the file into it. No parameters needed.</p>
                      </template>
                      <!-- is_file_or_dir -->
                      <template v-else-if="selectedNode.data.nodeType === 'is_file_or_dir'">
                        <p class="panel-hint">Branches based on whether the current path is a file or directory. Label outgoing edges <code>file</code> or <code>dir</code>.</p>
                      </template>
                      <!-- enter_folder -->
                      <template v-else-if="selectedNode.data.nodeType === 'enter_folder'">
                        <p class="panel-hint">Enters a directory and checks its first-level files. Label outgoing edges: <code>single</code> (exactly 1 file → cur_file becomes that file), <code>many</code> (&gt;1 files), <code>empty</code> (no files).</p>
                      </template>
                      <!-- move_to -->
                      <template v-else-if="selectedNode.data.nodeType === 'move_to'">
                        <el-form size="small" label-position="top">
                          <el-form-item label="Output path">
                            <el-input v-model="selectedNode.data.params.output_path" placeholder="D:\output" @input="syncNodeLabel" />
                          </el-form-item>
                        </el-form>
                      </template>
                      <!-- record_size -->
                      <template v-else-if="selectedNode.data.nodeType === 'record_size'">
                        <el-form size="small" label-position="top">
                          <el-form-item label="Key (x0 / x1 / x2 ...)">
                            <el-input v-model="selectedNode.data.params.key" placeholder="x0" @input="syncNodeLabel" />
                          </el-form-item>
                        </el-form>
                        <p class="panel-hint">Records cur_file path &amp; size into execution context under the given key. Use x0 before first extract, x1 after, x2 after second.</p>
                      </template>
                      <!-- size_cleanup -->
                      <template v-else-if="selectedNode.data.nodeType === 'size_cleanup'">
                        <el-form size="small" label-position="top">
                          <el-form-item label="Threshold (0.0 – 1.0)">
                            <el-input-number v-model="selectedNode.data.params.threshold" :min="0.01" :max="1" :step="0.05" :precision="2" style="width:100%" />
                          </el-form-item>
                        </el-form>
                        <p class="panel-hint">Compares x0/x1/x2 sizes. If all within threshold %, deletes the archive (x0) and moves x1 to <code>delete_path</code> run-var. Requires a <code>delete_path</code> setting.</p>
                      </template>
                      <!-- find_part1 -->
                      <template v-else-if="selectedNode.data.nodeType === 'find_part1'">
                        <p class="panel-hint">Finds the first part of a split archive inside the current folder. Looks for <code>*.001</code> or <code>*.part01.rar</code> patterns. No parameters needed.</p>
                      </template>
                      <!-- strip_suffix -->
                      <template v-else-if="selectedNode.data.nodeType === 'strip_suffix'">
                        <el-form size="small" label-position="top">
                          <el-form-item label="Suffix to strip">
                            <el-input v-model="selectedNode.data.params.suffix" placeholder=".to-delete" @input="syncNodeLabel" />
                          </el-form-item>
                        </el-form>
                        <p class="panel-hint">Strips the suffix from cur_file's name if present, then renames. No-op if the file doesn't end with that suffix.</p>
                      </template>
                      <!-- start / end -->
                      <template v-else>
                        <p class="panel-hint">No parameters.</p>
                      </template>
                    </div>
                  </transition>
                </div>
              </el-tab-pane>

              <!-- Settings tab -->
              <el-tab-pane label="Settings" name="settings">
                <div class="settings-panel">
                  <el-form label-position="top" size="small" style="max-width:480px">
                    <el-form-item label="Folder path (source)">
                      <el-input v-model="configFolderPath" placeholder="E:\to_process" clearable />
                    </el-form-item>
                    <el-form-item label="Output path (move_to destination)">
                      <el-input v-model="configOutputPath" placeholder="E:\output" clearable />
                    </el-form-item>
                    <el-form-item label="Delete path (size_cleanup moves x1 here)">
                      <el-input v-model="configDeletePath" placeholder="E:\review" clearable />
                    </el-form-item>
                  </el-form>
                  <el-button type="primary" size="small" @click="saveConfig" :loading="configSaving">Save defaults</el-button>
                  <p class="panel-hint" style="margin-top:12px">These values are pre-loaded each time you click ▶ Run. Output path overrides any value set on the move_to node.</p>
                </div>
              </el-tab-pane>

              <!-- Progress tab -->
              <el-tab-pane label="Progress" name="progress">
                <div class="progress-panel">
                  <div class="progress-header">
                    <el-tag :type="progressPhase === 'done' ? 'success' : progressPhase === 'error' ? 'danger' : progressPhase === 'running' ? 'warning' : 'info'" size="small">
                      {{ progressPhase || 'idle' }}
                    </el-tag>
                    <span v-if="progressTotal > 0" style="font-size:13px;margin-left:10px">
                      {{ progressDone }} / {{ progressTotal }} files
                    </span>
                    <el-progress
                      v-if="progressTotal > 0"
                      :percentage="Math.round((progressDone / progressTotal) * 100)"
                      :status="progressPhase === 'done' ? 'success' : progressPhase === 'error' ? 'exception' : undefined"
                      style="flex:1;margin-left:16px;margin-right:0"
                    />
                  </div>

                  <div class="log-container" ref="logContainerRef">
                    <div
                      v-for="entry in progressLog"
                      :key="entry.id"
                      :class="['log-entry', 'log-' + entry.phase]"
                    >
                      <span class="log-time">{{ entry.time }}</span>
                      <span class="log-msg" v-html="entry.msg" />
                    </div>
                    <div v-if="!progressLog.length" class="list-empty">No runs yet. Click ▶ Run to start.</div>
                  </div>
                </div>
              </el-tab-pane>

            </el-tabs>
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

      <!-- ===== Tab 3: Passwords ===== -->
      <el-tab-pane label="Passwords" name="passwords">
        <div style="padding:16px">
          <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px">
            <span style="font-weight:600;font-size:15px">Password Vault</span>
            <el-button size="small" type="primary" @click="showPasswordDialog = true">+ Add Password</el-button>
          </div>
          <el-table :data="passwords" size="small" stripe style="max-width:700px">
            <el-table-column prop="value" label="Password" width="200">
              <template #default="{ row }">
                <span style="font-family:monospace">{{ '*'.repeat(Math.min(row.value.length, 12)) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="note" label="Note" show-overflow-tooltip />
            <el-table-column label="Order" width="100">
              <template #default="{ $index }">
                <el-button size="small" text @click="movePassword($index, -1)" :disabled="$index === 0">▲</el-button>
                <el-button size="small" text @click="movePassword($index, 1)" :disabled="$index === passwords.length - 1">▼</el-button>
              </template>
            </el-table-column>
            <el-table-column label="Actions" width="120">
              <template #default="{ row }">
                <el-button size="small" text @click="editPasswordRow(row)">Edit</el-button>
                <el-button size="small" text type="danger" @click="confirmDeletePassword(row.id)">Del</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div style="margin-top:12px;font-size:12px;color:#909399">
            Passwords are tried in order when "Use password list" is enabled on an extract node. First success wins.
          </div>
        </div>
      </el-tab-pane>

    </el-tabs>

    <!-- Add/Edit Password dialog -->
    <el-dialog v-model="showPasswordDialog" :title="editingPassword ? 'Edit Password' : 'Add Password'" width="420px">
      <el-form :model="passwordForm" label-position="top" size="small">
        <el-form-item label="Password"><el-input v-model="passwordForm.value" type="password" show-password /></el-form-item>
        <el-form-item label="Note (optional)"><el-input v-model="passwordForm.note" placeholder="e.g. for MHZX series" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showPasswordDialog = false">Cancel</el-button>
        <el-button type="primary" @click="savePassword">Save</el-button>
      </template>
    </el-dialog>

    <!-- Add/Edit Tool dialog -->
    <el-dialog v-model="showAddTool" :title="editingTool ? 'Edit Tool' : 'Add Tool'" width="500px">
      <el-form :model="toolForm" label-position="top" size="small">
        <el-form-item label="Name"><el-input v-model="toolForm.name" /></el-form-item>
        <el-form-item label="Exe Path"><el-input v-model="toolForm.exe_path" placeholder='C:\Program Files\WinRAR\WinRAR.exe' /></el-form-item>
        <el-form-item label="Args Template"><el-input v-model="toolForm.args_template" placeholder='x "{archive}" "{dest}" -p{password} -y' /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddTool = false">Cancel</el-button>
        <el-button type="primary" @click="saveTool">Save</el-button>
      </template>
    </el-dialog>

    <!-- Edge label dialog (condition / is_file_or_dir / enter_folder branches) -->
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
import { ref, reactive, computed, onMounted, onUnmounted, watch, nextTick, defineComponent, h } from 'vue'
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
import { io } from 'socket.io-client'
import { v4 as uuidv4 } from 'uuid'
import { BACKEND_BASE_URL } from '@/basic/Constants'
import type { Tool, Pipeline, Password, ProgressEvent } from '../service/FilePipelineService'
import {
  getTools, addTool, updateTool, deleteTool,
  getPipelines, getPipeline, addPipeline, updatePipeline, deletePipeline,
  getPipelineConfig, savePipelineConfig,
  runPipeline,
  getPasswords, addPassword, updatePassword, deletePassword, reorderPasswords,
} from '../service/FilePipelineService'

// ---- node colors ----

const NODE_COLORS: Record<string, { bg: string; border: string; text: string }> = {
  start:           { bg: '#22c55e', border: '#16a34a', text: '#fff' },
  end:             { bg: '#ef4444', border: '#dc2626', text: '#fff' },
  rename_ext:      { bg: '#3b82f6', border: '#2563eb', text: '#fff' },
  strip_cjk:       { bg: '#a855f7', border: '#9333ea', text: '#fff' },
  extract:         { bg: '#f97316', border: '#ea580c', text: '#fff' },
  condition:       { bg: '#64748b', border: '#475569', text: '#fff' },
  mkdir_and_move:  { bg: '#0ea5e9', border: '#0284c7', text: '#fff' },
  is_file_or_dir:  { bg: '#06b6d4', border: '#0891b2', text: '#fff' },
  enter_folder:    { bg: '#8b5cf6', border: '#7c3aed', text: '#fff' },
  move_to:         { bg: '#eab308', border: '#ca8a04', text: '#fff' },
  record_size:     { bg: '#14b8a6', border: '#0d9488', text: '#fff' },
  size_cleanup:    { bg: '#f43f5e', border: '#e11d48', text: '#fff' },
  find_part1:      { bg: '#84cc16', border: '#65a30d', text: '#fff' },
  strip_suffix:    { bg: '#fb923c', border: '#ea580c', text: '#fff' },
}

const nodeTypes = [
  { type: 'rename_ext',     label: 'rename_ext'     },
  { type: 'strip_cjk',      label: 'strip_cjk'      },
  { type: 'extract',        label: 'extract'         },
  { type: 'condition',      label: 'condition'       },
  { type: 'mkdir_and_move', label: 'mkdir_and_move'  },
  { type: 'is_file_or_dir', label: 'is_file_or_dir'  },
  { type: 'enter_folder',   label: 'enter_folder'    },
  { type: 'move_to',        label: 'move_to'         },
  { type: 'record_size',    label: 'record_size'     },
  { type: 'size_cleanup',   label: 'size_cleanup'    },
  { type: 'find_part1',     label: 'find_part1'      },
  { type: 'strip_suffix',   label: 'strip_suffix'    },
  { type: 'end',            label: 'end'             },
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
        padding: '6px 16px 8px',
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
      h('div', { style: { lineHeight: '1.3' } }, label.value),
      h('div', {
        style: {
          fontSize: '10px',
          fontWeight: '400',
          opacity: '0.75',
          marginTop: '2px',
          fontFamily: 'monospace',
          letterSpacing: '0.02em',
        }
      }, props.id),
      showSource.value && h(Handle, { type: 'source', position: Position.Right }),
    ])
  },
})

// ---- state ----

const activeTab = ref('pipelines')
const editorTab = ref('graph')
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

// settings
const configFolderPath = ref('')
const configOutputPath = ref('')
const configDeletePath = ref('')
const configSaving = ref(false)

// progress
const running = ref(false)
const progressPhase = ref('')
const progressTotal = ref(0)
const progressDone = ref(0)
const progressLog = ref<{id: string, phase: string, msg: string, time: string}[]>([])
const activeRunId = ref('')
const logContainerRef = ref<HTMLElement | null>(null)

// toolbox
const showAddTool = ref(false)
const editingTool = ref<Tool | null>(null)
const toolForm = reactive({ name: '', exe_path: '', args_template: '' })

// edge label dialog
const showEdgeLabel = ref(false)
const pendingEdgeLabel = ref('default')
let pendingEdgeConnection: Connection | null = null

// passwords
const passwords = ref<Password[]>([])
const showPasswordDialog = ref(false)
const editingPassword = ref<Password | null>(null)
const passwordForm = reactive({ value: '', note: '' })

// ---- socket.io ----

const socket = io(BACKEND_BASE_URL, { transports: ['websocket', 'polling'] })

function handleProgress(data: any) {
  if (data.run_id !== activeRunId.value) return

  const time = new Date().toLocaleTimeString('en-GB', { hour12: false })
  const addLog = (phase: string, msg: string) => {
    progressLog.value = [...progressLog.value, { id: uuidv4(), phase, msg, time }]
    nextTick(() => {
      if (logContainerRef.value) logContainerRef.value.scrollTop = logContainerRef.value.scrollHeight
    })
  }

  switch (data.phase) {
    case 'start':
      progressTotal.value = data.total_files
      addLog('start', `Pipeline started &mdash; <b>${data.total_files}</b> item(s) to process`)
      break
    case 'file_start':
      progressDone.value = data.file_index
      addLog('file_start', `<b>File ${data.file_index + 1}/${data.total_files}:</b> ${data.file}`)
      break
    case 'step':
      addLog('step', `&nbsp;&nbsp;&nbsp;&#8627; step ${data.step_num}: <code>${data.node_type}</code>`)
      break
    case 'step_branch':
      addLog('step_branch', `&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<b>${data.node_type}</b> &rarr; branch: <code>${data.branch}</code>`)
      break
    case 'file_done': {
      progressDone.value = data.file_index + 1
      const allDone = data.results?.every((r: any) => r.status === 'done')
      const err = data.results?.find((r: any) => r.error)?.error
      if (allDone) {
        addLog('file_done_ok', `&nbsp;&nbsp;&nbsp;<span class="ok">&#10003; Done</span>`)
      } else {
        addLog('file_done_err', `&nbsp;&nbsp;&nbsp;<span class="err">&#10007; Error: ${err || 'unknown'}</span>`)
      }
      break
    }
    case 'size_cleanup': {
      const fmt = (n: number) => n ? (n / 1024).toFixed(1) + ' KB' : '?'
      const x0 = fmt(data.x0_size), x1 = fmt(data.x1_size), x2 = fmt(data.x2_size)
      if (data.cleaned) {
        addLog('size_cleanup_yes', `&nbsp;&nbsp;&nbsp;<span class="cleanup-yes">&#9986; size_cleanup triggered</span> x0=${x0} x1=${x1} x2=${x2} — archive deleted, x1 moved to delete_path`)
      } else {
        addLog('size_cleanup_no', `&nbsp;&nbsp;&nbsp;<span class="cleanup-no">&#9711; size_cleanup skipped</span> x0=${x0} x1=${x1} x2=${x2}`)
      }
      break
    }
    case 'done':
      progressPhase.value = 'done'
      running.value = false
      addLog('done', `<b>All done</b>`)
      break
    case 'error':
      progressPhase.value = 'error'
      running.value = false
      addLog('error', `<span class="err">Pipeline error: ${data.error || ''}</span>`)
      break
  }
}

// ---- helpers ----

function nodeLabel(type: string, params: any): string {
  if (type === 'rename_ext') return `rename → .${params?.new_ext || '?'}`
  if (type === 'move_to')    return `move → ${params?.output_path || '?'}`
  return type
}

function defaultParams(type: string): any {
  if (type === 'rename_ext') return { new_ext: '' }
  if (type === 'extract')    return { tool_id: null, password: '', password_required: false, use_password_list: false }
  if (type === 'move_to')    return { output_path: '' }
  if (type === 'record_size') return { key: 'x0' }
  if (type === 'size_cleanup') return { threshold: 0.2 }
  if (type === 'strip_suffix') return { suffix: '.to-delete' }
  if (type === 'find_part1') return {}
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
  socket.on('fp_progress', handleProgress)
  await Promise.all([loadPipelines(), loadTools(), loadPasswords()])
})

onUnmounted(() => {
  socket.off('fp_progress', handleProgress)
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
  await loadConfig(id)
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

// ---- settings ----

async function loadConfig(pipelineId: number) {
  const cfg = await getPipelineConfig(pipelineId)
  configFolderPath.value = cfg.folder_path || ''
  configOutputPath.value = cfg.output_path || ''
  configDeletePath.value = cfg.delete_path || ''
}

async function saveConfig() {
  if (!selectedPipelineId.value) return
  configSaving.value = true
  try {
    await savePipelineConfig(selectedPipelineId.value, {
      folder_path: configFolderPath.value,
      output_path: configOutputPath.value,
      delete_path: configDeletePath.value,
    })
    ElMessage.success('Settings saved')
  } finally {
    configSaving.value = false
  }
}

// ---- run ----

async function startRun() {
  if (!selectedPipelineId.value) return
  if (!configFolderPath.value.trim()) {
    editorTab.value = 'settings'
    ElMessage.warning('Set a folder path in Settings before running')
    return
  }
  running.value = true
  progressPhase.value = 'running'
  progressLog.value = []
  progressDone.value = 0
  progressTotal.value = 0
  editorTab.value = 'progress'
  try {
    const runVars: Record<string, string> = {}
    if (configOutputPath.value.trim()) runVars.output_path = configOutputPath.value.trim()
    if (configDeletePath.value.trim()) runVars.delete_path = configDeletePath.value.trim()
    const runId = await runPipeline(selectedPipelineId.value, configFolderPath.value.trim(), runVars)
    activeRunId.value = runId
  } catch (e: any) {
    progressPhase.value = 'error'
    running.value = false
    ElMessage.error(e?.message || 'Run failed')
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
  const labeledTypes = ['condition', 'is_file_or_dir', 'enter_folder']
  if (labeledTypes.includes(fromNode?.data?.nodeType)) {
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

// ---- passwords ----

async function loadPasswords() {
  passwords.value = await getPasswords()
}

function editPasswordRow(p: Password) {
  editingPassword.value = p
  Object.assign(passwordForm, { value: p.value, note: p.note })
  showPasswordDialog.value = true
}

async function savePassword() {
  if (editingPassword.value) {
    await updatePassword(editingPassword.value.id, passwordForm.value, passwordForm.note)
  } else {
    await addPassword(passwordForm.value, passwordForm.note)
  }
  showPasswordDialog.value = false
  editingPassword.value = null
  Object.assign(passwordForm, { value: '', note: '' })
  await loadPasswords()
}

async function confirmDeletePassword(id: number) {
  await ElMessageBox.confirm('Delete this password?', 'Confirm', { type: 'warning' })
  await deletePassword(id)
  await loadPasswords()
}

async function movePassword(index: number, dir: -1 | 1) {
  const arr = [...passwords.value]
  const swapIdx = index + dir
  if (swapIdx < 0 || swapIdx >= arr.length) return
  ;[arr[index], arr[swapIdx]] = [arr[swapIdx], arr[index]]
  await reorderPasswords(arr.map(p => p.id))
  await loadPasswords()
}

watch(showPasswordDialog, (v) => {
  if (!v) {
    editingPassword.value = null
    Object.assign(passwordForm, { value: '', note: '' })
  }
})

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

.fp-editor { flex: 1; min-width: 0; padding-left: 16px; display: flex; flex-direction: column; gap: 8px; }
.fp-editor-empty { display: flex; align-items: center; justify-content: center; color: #909399; }

.editor-topbar-main { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.topbar-divider { width: 1px; height: 20px; background: #dcdfe6; margin: 0 2px; }

.editor-inner-tabs { flex: 1; min-height: 0; display: flex; flex-direction: column; }
:deep(.editor-inner-tabs .el-tabs__content) { flex: 1; min-height: 0; overflow: hidden; }
:deep(.editor-inner-tabs .el-tab-pane) { height: 100%; display: flex; flex-direction: column; }

.node-toolbar { display: flex; flex-wrap: wrap; gap: 4px; padding: 4px 0 8px; }

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

/* Settings tab */
.settings-panel { padding: 16px 0; }

/* Progress tab */
.progress-panel { padding: 8px 0; flex: 1; display: flex; flex-direction: column; gap: 8px; overflow: hidden; }
.progress-header { display: flex; align-items: center; gap: 8px; }

.log-container {
  flex: 1;
  overflow-y: auto;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 10px 14px;
  font-family: monospace;
  font-size: 12.5px;
  line-height: 1.8;
  background: #fafafa;
}
.log-entry { display: flex; gap: 10px; }
.log-time { color: #b0b8c1; flex-shrink: 0; }
.log-msg { word-break: break-all; }
.log-entry.log-file_start .log-msg { color: #1a56db; }
.log-entry.log-step .log-msg { color: #374151; }
.log-entry.log-step_branch .log-msg { color: #7c3aed; }
.log-entry.log-file_done_ok .log-msg .ok { color: #16a34a; font-weight: 600; }
.log-entry.log-file_done_err .log-msg .err, .log-entry.log-error .log-msg .err { color: #dc2626; font-weight: 600; }
.log-entry.log-done .log-msg { color: #16a34a; font-weight: 700; }

.log-entry.log-size_cleanup_yes .log-msg .cleanup-yes { color: #f43f5e; font-weight: 600; }
.log-entry.log-size_cleanup_no .log-msg .cleanup-no { color: #14b8a6; }

.slide-enter-active, .slide-leave-active { transition: width 0.2s ease, opacity 0.2s ease; }
.slide-enter-from, .slide-leave-to { width: 0; opacity: 0; }
</style>
