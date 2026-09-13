<template>
  <div class="ap-root">
    <div class="ap-header">
      <el-button type="default" size="small" @click="$router.push('/')">← Back</el-button>
      <h2 class="ap-title">Apprentice</h2>
      <el-tag v-if="runningTaskId" type="warning" size="small">Running task #{{ runningTaskId }}</el-tag>
    </div>

    <el-tabs v-model="activeTab" class="ap-tabs">
      <!-- ── Tab 1: Tasks ─────────────────────────────── -->
      <el-tab-pane label="Tasks" name="tasks">
        <div class="ap-tasks-layout">
          <!-- Left: task list -->
          <div class="ap-task-list">
            <div class="ap-task-list-header">
              <span class="ap-section-title">Tasks</span>
              <el-button type="primary" size="small" @click="showNewTaskDialog = true">+ New</el-button>
            </div>
            <div
              v-for="task in tasks"
              :key="task.id"
              class="ap-task-item"
              :class="{ active: selectedTaskId === task.id }"
              @click="selectTask(task.id)"
            >
              <div class="ap-task-item-title">{{ task.title }}</div>
              <div class="ap-task-item-meta">
                <el-tag :type="statusType(task.status)" size="small">{{ task.status }}</el-tag>
                <span class="ap-task-item-date">{{ formatDate(task.created_at) }}</span>
              </div>
            </div>
            <div v-if="tasks.length === 0" class="ap-empty">No tasks yet.</div>
          </div>

          <!-- Right: task detail -->
          <div class="ap-task-detail" v-if="selectedTask">
            <div class="ap-task-detail-header">
              <div>
                <h3 class="ap-task-title">{{ selectedTask.title }}</h3>
                <div class="ap-task-repo">{{ selectedTask.repo_path }}</div>
              </div>
              <div class="ap-task-actions">
                <el-button
                  v-if="selectedTask.status === 'pending'"
                  type="success" size="small"
                  @click="startTask(selectedTask.id)"
                >▶ Start</el-button>
                <el-button
                  v-if="selectedTask.status === 'running'"
                  type="danger" size="small"
                  @click="stopTask(selectedTask.id)"
                >■ Stop</el-button>
              </div>
            </div>

            <!-- Checkpoint banner -->
            <div v-if="pendingCheckpoint" class="ap-checkpoint-banner">
              <div class="ap-checkpoint-icon">⏸</div>
              <div class="ap-checkpoint-content">
                <div class="ap-checkpoint-label">Commander is waiting for your review</div>
                <div class="ap-checkpoint-msg">{{ pendingCheckpoint }}</div>
              </div>
              <div class="ap-checkpoint-actions">
                <el-button size="small" type="success" @click="approveCheckpoint">Approve</el-button>
                <el-button size="small" @click="rejectCheckpoint">Reject</el-button>
              </div>
            </div>

            <!-- Main area: log + human channel -->
            <div class="ap-task-body">
              <!-- Log stream -->
              <div class="ap-log" ref="logEl">
                <div v-for="(entry, i) in logEntries" :key="i" class="ap-log-entry" :class="`ap-log-${entry.type}`">
                  <template v-if="entry.type === 'commander_text'">
                    <span class="ap-log-prefix">Commander</span>
                    <span class="ap-log-text">{{ entry.text }}</span>
                  </template>
                  <template v-else-if="entry.type === 'commander_tool_use'">
                    <el-tag size="small" type="info">{{ entry.tool_name }}</el-tag>
                    <span class="ap-log-text ap-log-dim">{{ entry.input_preview }}</span>
                  </template>
                  <template v-else-if="entry.type === 'soldier_start'">
                    <span class="ap-log-prefix ap-soldier">⚡ Soldier #{{ entry.seq }}</span>
                    <span class="ap-log-text">{{ entry.prompt_preview }}...</span>
                  </template>
                  <template v-else-if="entry.type === 'soldier_done'">
                    <span class="ap-log-prefix ap-soldier">✓ Soldier #{{ entry.seq }}</span>
                    <el-tag :type="entry.status === 'done' ? 'success' : 'danger'" size="small">{{ entry.status }}</el-tag>
                  </template>
                  <template v-else-if="entry.type === 'memory_written'">
                    <span class="ap-log-prefix ap-memory">📝 Memory written</span>
                    <span class="ap-log-text ap-log-dim">{{ entry.preview }}</span>
                  </template>
                  <template v-else-if="entry.type === 'done'">
                    <span class="ap-log-prefix" :class="entry.status === 'completed' ? 'ap-done' : 'ap-failed'">
                      {{ entry.status === 'completed' ? '✅ Done' : '❌ Failed' }}
                    </span>
                    <span v-if="entry.reason" class="ap-log-text ap-log-dim">{{ entry.reason }}</span>
                  </template>
                  <template v-else-if="entry.type === 'system'">
                    <span class="ap-log-system">{{ entry.content }}</span>
                  </template>
                </div>
                <div v-if="logEntries.length === 0" class="ap-empty">No events yet.</div>
              </div>

              <!-- Human channel -->
              <div class="ap-human-channel">
                <div class="ap-channel-header">Human Channel</div>
                <div class="ap-channel-msgs" ref="channelEl">
                  <div
                    v-for="msg in channelMessages"
                    :key="msg.id"
                    class="ap-channel-msg"
                    :class="msg.direction === 'user_to_cmd' ? 'ap-msg-user' : 'ap-msg-cmd'"
                  >
                    <div class="ap-msg-author">{{ msg.direction === 'user_to_cmd' ? 'You' : 'Commander' }}</div>
                    <div class="ap-msg-body">{{ msg.content }}</div>
                    <div class="ap-msg-time">{{ formatDate(msg.created_at) }}</div>
                  </div>
                  <div v-if="channelMessages.length === 0" class="ap-empty ap-channel-empty">No messages yet.</div>
                </div>
                <div class="ap-channel-input">
                  <el-input
                    v-model="channelInput"
                    placeholder="Send a message to Commander..."
                    size="small"
                    @keyup.enter="sendChannelMessage"
                  />
                  <el-button size="small" type="primary" @click="sendChannelMessage">Send</el-button>
                </div>
              </div>
            </div>

            <!-- Post-completion feedback -->
            <div v-if="selectedTask.status === 'done' && !feedbackSubmitted" class="ap-feedback">
              <span class="ap-feedback-label">Rate this task:</span>
              <el-rate v-model="feedbackScore" :max="5" />
              <el-input
                v-model="feedbackNote"
                placeholder="Optional note..."
                size="small"
                style="flex:1"
              />
              <el-button size="small" type="primary" @click="submitFeedback">Submit</el-button>
            </div>
          </div>
          <div class="ap-task-detail ap-task-empty" v-else>
            <span>Select a task to view details.</span>
          </div>
        </div>
      </el-tab-pane>

      <!-- ── Tab 2: Memory ───────────────────────────── -->
      <el-tab-pane label="Memory" name="memory">
        <div class="ap-memory-layout">
          <div class="ap-memory-section">
            <div class="ap-memory-section-header">
              <span class="ap-section-title">Long-term Memory</span>
              <el-button size="small" type="primary" @click="distill" :loading="distilling">
                Distill Now
              </el-button>
            </div>
            <div class="ap-long-memory">
              <pre v-if="longMemory">{{ longMemory }}</pre>
              <div v-else class="ap-empty">No long-term memory yet. Complete some tasks and distill.</div>
            </div>
          </div>

          <div class="ap-memory-section">
            <div class="ap-memory-section-header">
              <span class="ap-section-title">Short-term Memory (recent tasks)</span>
            </div>
            <el-table :data="shortMemory" size="small" style="width:100%">
              <el-table-column prop="task_id" label="Task" width="70" />
              <el-table-column prop="created_at" label="Date" width="180" :formatter="(r) => formatDate(r.created_at)" />
              <el-table-column prop="user_score" label="Score" width="70" />
              <el-table-column label="Distilled" width="90">
                <template #default="{ row }">
                  <el-tag :type="row.distilled ? 'success' : 'info'" size="small">
                    {{ row.distilled ? 'Yes' : 'No' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="raw_log" label="Narrative" show-overflow-tooltip />
            </el-table>
            <div v-if="shortMemory.length === 0" class="ap-empty">No short-term memories yet.</div>
          </div>
        </div>
      </el-tab-pane>

      <!-- ── Tab 3: Boundaries & Settings ──────────── -->
      <el-tab-pane label="Boundaries & Settings" name="settings">
        <div class="ap-settings-layout">
          <!-- Red lines -->
          <div class="ap-settings-section">
            <div class="ap-settings-section-header">
              <span class="ap-section-title">Red Lines</span>
            </div>
            <div class="ap-redlines">
              <div v-for="line in redLines" :key="line.id" class="ap-redline-item">
                <span class="ap-redline-rule">{{ line.rule }}</span>
                <el-button size="small" type="danger" plain @click="deleteRedLine(line.id)">Delete</el-button>
              </div>
              <div v-if="redLines.length === 0" class="ap-empty">No red lines yet.</div>
              <div class="ap-redline-add">
                <el-input v-model="newRedLine" placeholder="New rule..." size="small" style="flex:1" />
                <el-button size="small" type="primary" @click="addRedLine">Add</el-button>
              </div>
            </div>
          </div>

          <!-- Settings form -->
          <div class="ap-settings-section">
            <div class="ap-settings-section-header">
              <span class="ap-section-title">Settings</span>
              <el-button size="small" type="primary" @click="saveSettings" :loading="savingSettings">Save</el-button>
            </div>
            <el-form v-if="settingsForm" label-width="200px" size="small" class="ap-settings-form">
              <el-form-item label="Commander model">
                <el-input v-model="settingsForm.commander_model" />
              </el-form-item>
              <el-form-item label="Soldier model">
                <el-input v-model="settingsForm.soldier_model" />
              </el-form-item>
              <el-form-item label="Commander max turns">
                <el-input-number v-model="settingsForm.commander_max_turns" :min="1" :max="200" />
              </el-form-item>
              <el-form-item label="Max cost USD (0=off)">
                <el-input-number v-model="settingsForm.max_cost_usd" :min="0" :precision="2" :step="1" />
              </el-form-item>
              <el-form-item label="Distillation threshold">
                <el-input-number v-model="settingsForm.distillation_threshold" :min="1" :max="100" />
              </el-form-item>
              <el-form-item label="Distillation model">
                <el-input v-model="settingsForm.distillation_model" />
              </el-form-item>
              <el-divider />
              <el-form-item label="GitHub token">
                <el-input v-model="settingsForm.github_token" type="password" show-password />
              </el-form-item>
              <el-form-item label="Jenkins URL">
                <el-input v-model="settingsForm.jenkins_url" />
              </el-form-item>
              <el-form-item label="Jenkins user">
                <el-input v-model="settingsForm.jenkins_user" />
              </el-form-item>
              <el-form-item label="Jenkins token">
                <el-input v-model="settingsForm.jenkins_token" type="password" show-password />
              </el-form-item>
            </el-form>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- New task dialog -->
    <el-dialog v-model="showNewTaskDialog" title="New Task" width="560px">
      <el-form label-width="120px" size="small">
        <el-form-item label="Title">
          <el-input v-model="newTask.title" placeholder="Short label" />
        </el-form-item>
        <el-form-item label="Description">
          <el-input
            v-model="newTask.description"
            type="textarea"
            :rows="5"
            placeholder="Describe what you want the agent to do..."
          />
        </el-form-item>
        <el-form-item label="Repo path">
          <el-input v-model="newTask.repo_path" placeholder="/path/to/your/repo" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showNewTaskDialog = false">Cancel</el-button>
        <el-button type="primary" @click="createAndStartTask">Create & Start</el-button>
        <el-button @click="createTask">Create only</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script lang="ts" setup>
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { ApprenticeService } from '../service/ApprenticeService'
import { BACKEND_BASE_URL } from '@/basic/Constants'
import type { Task, MemoryShortEntry, HumanMessage, RedLine, ApprenticeSettings, SseEvent } from '../service/Model'

// ── State ────────────────────────────────────────────────────
const activeTab = ref('tasks')
const tasks = ref<Task[]>([])
const selectedTaskId = ref<number | null>(null)
const selectedTask = computed(() => tasks.value.find(t => t.id === selectedTaskId.value) ?? null)

const logEntries = ref<SseEvent[]>([])
const channelMessages = ref<HumanMessage[]>([])
const channelInput = ref('')
const pendingCheckpoint = ref<string | null>(null)

const longMemory = ref('')
const shortMemory = ref<MemoryShortEntry[]>([])
const distilling = ref(false)

const redLines = ref<RedLine[]>([])
const newRedLine = ref('')
const settingsForm = ref<ApprenticeSettings | null>(null)
const savingSettings = ref(false)

const showNewTaskDialog = ref(false)
const newTask = ref({ title: '', description: '', repo_path: '' })

const feedbackScore = ref(0)
const feedbackNote = ref('')
const feedbackSubmitted = ref(false)

const logEl = ref<HTMLElement | null>(null)
const channelEl = ref<HTMLElement | null>(null)

let sseSource: EventSource | null = null
let channelPollTimer: ReturnType<typeof setInterval> | null = null

// ── Computed ─────────────────────────────────────────────────
const runningTaskId = computed(() =>
  tasks.value.find(t => t.status === 'running')?.id ?? null
)

// ── Helpers ──────────────────────────────────────────────────
function statusType(status: string) {
  const map: Record<string, string> = {
    pending: 'info', running: 'warning', done: 'success', failed: 'danger', stopped: ''
  }
  return map[status] ?? 'info'
}

function formatDate(iso: string) {
  if (!iso) return ''
  return new Date(iso).toLocaleString()
}

// ── Data loading ─────────────────────────────────────────────
async function loadTasks() {
  const res = await ApprenticeService.listTasks()
  if (res) tasks.value = res.tasks
}

async function loadMemory() {
  const [longRes, shortRes] = await Promise.all([
    ApprenticeService.getLongMemory(),
    ApprenticeService.listShortMemory(),
  ])
  if (longRes) longMemory.value = longRes.content
  if (shortRes) shortMemory.value = shortRes.entries
}

async function loadRedLines() {
  const res = await ApprenticeService.listRedLines()
  if (res) redLines.value = res.red_lines
}

async function loadSettings() {
  const res = await ApprenticeService.getSettings()
  if (res) settingsForm.value = { ...res }
}

async function loadChannelMessages(taskId: number) {
  const res = await ApprenticeService.listMessages(taskId)
  if (res) channelMessages.value = res.messages
  await nextTick()
  scrollChannel()
}

function scrollLog() {
  if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight
}

function scrollChannel() {
  if (channelEl.value) channelEl.value.scrollTop = channelEl.value.scrollHeight
}

// ── Task selection ────────────────────────────────────────────
async function selectTask(id: number) {
  if (selectedTaskId.value === id) return
  closeSse()
  stopChannelPoll()
  selectedTaskId.value = id
  logEntries.value = []
  channelMessages.value = []
  pendingCheckpoint.value = null
  feedbackSubmitted.value = false
  feedbackScore.value = 0
  feedbackNote.value = ''

  const task = tasks.value.find(t => t.id === id)
  if (task && task.status === 'running') {
    openSse(id)
    startChannelPoll(id)
  }
  await loadChannelMessages(id)
}

// ── SSE ───────────────────────────────────────────────────────
function openSse(taskId: number) {
  closeSse()
  sseSource = new EventSource(`${BACKEND_BASE_URL}/apprentice/tasks/${taskId}/events`)
  sseSource.onmessage = (e) => {
    try {
      const event: SseEvent = JSON.parse(e.data)
      handleSseEvent(event)
    } catch {}
  }
  sseSource.onerror = () => {
    closeSse()
  }
}

function closeSse() {
  if (sseSource) {
    sseSource.close()
    sseSource = null
  }
}

function handleSseEvent(event: SseEvent) {
  const type = event.event || ''
  if (type === 'heartbeat') return

  logEntries.value.push({ ...event, type })
  nextTick(scrollLog)

  if (type === 'checkpoint') {
    pendingCheckpoint.value = event.content || ''
  }
  if (type === 'done' || type === 'run_finished') {
    closeSse()
    stopChannelPoll()
    loadTasks()
  }
}

// ── Channel polling ───────────────────────────────────────────
function startChannelPoll(taskId: number) {
  stopChannelPoll()
  channelPollTimer = setInterval(() => loadChannelMessages(taskId), 3000)
}

function stopChannelPoll() {
  if (channelPollTimer) {
    clearInterval(channelPollTimer)
    channelPollTimer = null
  }
}

// ── Task actions ──────────────────────────────────────────────
async function createTask() {
  const { title, description, repo_path } = newTask.value
  if (!title.trim() || !description.trim() || !repo_path.trim()) {
    ElMessage.warning('All fields are required')
    return
  }
  await ApprenticeService.createTask({ title, description, repo_path })
  showNewTaskDialog.value = false
  newTask.value = { title: '', description: '', repo_path: '' }
  await loadTasks()
}

async function createAndStartTask() {
  const { title, description, repo_path } = newTask.value
  if (!title.trim() || !description.trim() || !repo_path.trim()) {
    ElMessage.warning('All fields are required')
    return
  }
  const task = await ApprenticeService.createTask({ title, description, repo_path })
  showNewTaskDialog.value = false
  newTask.value = { title: '', description: '', repo_path: '' }
  await loadTasks()
  if (task) {
    await selectTask(task.id)
    await startTask(task.id)
  }
}

async function startTask(id: number) {
  await ApprenticeService.startTask(id)
  await loadTasks()
  openSse(id)
  startChannelPoll(id)
}

async function stopTask(id: number) {
  await ApprenticeService.stopTask(id)
  closeSse()
  stopChannelPoll()
  await loadTasks()
}

// ── Human channel ─────────────────────────────────────────────
async function sendChannelMessage() {
  const content = channelInput.value.trim()
  if (!content || !selectedTaskId.value) return
  await ApprenticeService.sendMessage(selectedTaskId.value, content)
  channelInput.value = ''
  await loadChannelMessages(selectedTaskId.value)
}

async function approveCheckpoint() {
  if (!selectedTaskId.value) return
  await ApprenticeService.sendMessage(selectedTaskId.value, 'Approved. Please continue.')
  pendingCheckpoint.value = null
}

async function rejectCheckpoint() {
  if (!selectedTaskId.value) return
  await ApprenticeService.sendMessage(selectedTaskId.value, 'Rejected. Please rethink your approach.')
  pendingCheckpoint.value = null
}

// ── Feedback ──────────────────────────────────────────────────
async function submitFeedback() {
  if (!selectedTask.value) return
  const entry = shortMemory.value.find(e => e.task_id === selectedTask.value!.id)
  if (!entry) { ElMessage.info('No memory entry found for this task yet'); return }
  await ApprenticeService.submitFeedback(entry.id, feedbackScore.value || null, feedbackNote.value)
  feedbackSubmitted.value = true
  ElMessage.success('Feedback submitted')
  await loadMemory()
}

// ── Memory ────────────────────────────────────────────────────
async function distill() {
  distilling.value = true
  try {
    await ApprenticeService.distill()
    await loadMemory()
    ElMessage.success('Distillation complete')
  } catch {
    ElMessage.error('Distillation failed')
  } finally {
    distilling.value = false
  }
}

// ── Red lines ─────────────────────────────────────────────────
async function addRedLine() {
  const rule = newRedLine.value.trim()
  if (!rule) return
  await ApprenticeService.addRedLine(rule)
  newRedLine.value = ''
  await loadRedLines()
}

async function deleteRedLine(id: number) {
  await ApprenticeService.deleteRedLine(id)
  await loadRedLines()
}

// ── Settings ──────────────────────────────────────────────────
async function saveSettings() {
  if (!settingsForm.value) return
  savingSettings.value = true
  try {
    await ApprenticeService.saveSettings(settingsForm.value)
    ElMessage.success('Settings saved')
  } finally {
    savingSettings.value = false
  }
}

// ── Tab watch (lazy load) ─────────────────────────────────────
watch(activeTab, async (tab) => {
  if (tab === 'memory') await loadMemory()
  if (tab === 'settings') { await loadRedLines(); await loadSettings() }
})

// ── Mount ─────────────────────────────────────────────────────
onMounted(async () => {
  await loadTasks()
})
</script>

<style scoped>
.ap-root { display: flex; flex-direction: column; height: 100vh; padding: 20px; box-sizing: border-box; }
.ap-header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.ap-title { margin: 0; font-size: 20px; font-weight: 600; }
.ap-tabs { flex: 1; display: flex; flex-direction: column; }
.ap-tabs :deep(.el-tabs__content) { flex: 1; overflow: hidden; }
.ap-tabs :deep(.el-tab-pane) { height: 100%; }

/* Tasks tab */
.ap-tasks-layout { display: flex; gap: 16px; height: calc(100vh - 140px); }
.ap-task-list { width: 260px; flex-shrink: 0; border: 1px solid #e4e7ed; border-radius: 8px; overflow-y: auto; background: #fafafa; }
.ap-task-list-header { display: flex; align-items: center; justify-content: space-between; padding: 10px 12px; border-bottom: 1px solid #e4e7ed; }
.ap-section-title { font-weight: 600; font-size: 13px; }
.ap-task-item { padding: 10px 12px; cursor: pointer; border-bottom: 1px solid #f0f0f0; transition: background 0.1s; }
.ap-task-item:hover { background: #f0f7ff; }
.ap-task-item.active { background: #ecf5ff; }
.ap-task-item-title { font-size: 13px; font-weight: 500; margin-bottom: 4px; }
.ap-task-item-meta { display: flex; align-items: center; gap: 8px; }
.ap-task-item-date { font-size: 11px; color: #999; }

.ap-task-detail { flex: 1; display: flex; flex-direction: column; gap: 12px; overflow: hidden; }
.ap-task-detail-header { display: flex; justify-content: space-between; align-items: flex-start; }
.ap-task-title { margin: 0 0 4px; font-size: 15px; font-weight: 600; }
.ap-task-repo { font-size: 12px; color: #909399; }
.ap-task-actions { display: flex; gap: 8px; }
.ap-task-empty { align-items: center; justify-content: center; color: #c0c4cc; }

.ap-checkpoint-banner { display: flex; align-items: center; gap: 12px; padding: 10px 14px; background: #fef9ec; border: 1px solid #f5dfa0; border-radius: 8px; }
.ap-checkpoint-icon { font-size: 22px; }
.ap-checkpoint-content { flex: 1; }
.ap-checkpoint-label { font-size: 12px; font-weight: 600; color: #e6a23c; }
.ap-checkpoint-msg { font-size: 13px; margin-top: 2px; }
.ap-checkpoint-actions { display: flex; gap: 8px; }

.ap-task-body { flex: 1; display: flex; gap: 12px; overflow: hidden; min-height: 0; }
.ap-log { flex: 1; border: 1px solid #e4e7ed; border-radius: 8px; overflow-y: auto; padding: 10px; background: #1e1e1e; font-family: monospace; font-size: 12px; }
.ap-log-entry { margin-bottom: 6px; display: flex; align-items: flex-start; gap: 8px; flex-wrap: wrap; }
.ap-log-prefix { color: #7ec8e3; font-weight: 600; white-space: nowrap; }
.ap-log-text { color: #d4d4d4; }
.ap-log-dim { color: #808080; }
.ap-log-system { color: #6a9955; }
.ap-soldier { color: #ce9178; }
.ap-memory { color: #dcdcaa; }
.ap-done { color: #4ec9b0; }
.ap-failed { color: #f44747; }

.ap-human-channel { width: 280px; display: flex; flex-direction: column; border: 1px solid #e4e7ed; border-radius: 8px; overflow: hidden; }
.ap-channel-header { padding: 8px 12px; background: #f5f7fa; font-size: 12px; font-weight: 600; border-bottom: 1px solid #e4e7ed; }
.ap-channel-msgs { flex: 1; overflow-y: auto; padding: 8px; display: flex; flex-direction: column; gap: 8px; }
.ap-channel-empty { text-align: center; padding: 20px 0; }
.ap-channel-msg { max-width: 100%; }
.ap-msg-user { align-self: flex-end; text-align: right; }
.ap-msg-cmd { align-self: flex-start; }
.ap-msg-author { font-size: 10px; color: #909399; margin-bottom: 2px; }
.ap-msg-body { font-size: 12px; padding: 6px 10px; border-radius: 8px; background: #ecf5ff; display: inline-block; max-width: 220px; word-break: break-word; }
.ap-msg-cmd .ap-msg-body { background: #f0f9eb; }
.ap-msg-time { font-size: 10px; color: #c0c4cc; margin-top: 2px; }
.ap-channel-input { display: flex; gap: 6px; padding: 8px; border-top: 1px solid #e4e7ed; }

.ap-feedback { display: flex; align-items: center; gap: 10px; padding: 10px; background: #f5f7fa; border-radius: 8px; }
.ap-feedback-label { font-size: 13px; white-space: nowrap; }

/* Memory tab */
.ap-memory-layout { display: flex; flex-direction: column; gap: 20px; height: calc(100vh - 140px); overflow-y: auto; }
.ap-memory-section { border: 1px solid #e4e7ed; border-radius: 8px; overflow: hidden; }
.ap-memory-section-header { display: flex; align-items: center; justify-content: space-between; padding: 10px 14px; background: #f5f7fa; border-bottom: 1px solid #e4e7ed; }
.ap-long-memory { padding: 14px; min-height: 120px; }
.ap-long-memory pre { margin: 0; white-space: pre-wrap; font-size: 13px; line-height: 1.6; font-family: inherit; }

/* Settings tab */
.ap-settings-layout { display: flex; flex-direction: column; gap: 20px; height: calc(100vh - 140px); overflow-y: auto; }
.ap-settings-section { border: 1px solid #e4e7ed; border-radius: 8px; overflow: hidden; }
.ap-settings-section-header { display: flex; align-items: center; justify-content: space-between; padding: 10px 14px; background: #f5f7fa; border-bottom: 1px solid #e4e7ed; }
.ap-settings-form { padding: 16px; }
.ap-redlines { padding: 12px; display: flex; flex-direction: column; gap: 8px; }
.ap-redline-item { display: flex; align-items: center; justify-content: space-between; padding: 6px 10px; background: #fff5f5; border: 1px solid #ffd0d0; border-radius: 6px; }
.ap-redline-rule { font-size: 13px; }
.ap-redline-add { display: flex; gap: 8px; margin-top: 4px; }
.ap-empty { color: #c0c4cc; font-size: 13px; padding: 8px 0; }
</style>
