<template>
  <div class="assistant-view">
    <!-- Sidebar: conversation list -->
    <aside class="sidebar">
      <div class="sidebar-header">
        <el-button @click="goBack" size="small" plain circle>
          <el-icon><ArrowLeft /></el-icon>
        </el-button>
        <h2 class="app-title">Assistant</h2>
        <el-button
          size="small"
          plain
          circle
          @click="openSearch"
          title="Search all conversations"
        >
          <el-icon><Search /></el-icon>
        </el-button>
        <el-button
          type="primary"
          size="small"
          @click="handleNewConversation"
          :loading="isCreating"
        >
          <el-icon><Plus /></el-icon>
          New
        </el-button>
      </div>

      <!-- Search panel: overlays the conversation list while open -->
      <div v-if="searchOpen" class="search-panel">
        <div class="search-input-row">
          <el-input
            id="assistant-search-input"
            v-model="searchQuery"
            placeholder="Search all conversations…"
            clearable
            @input="onSearchInput"
            @keydown.esc="closeSearch"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
          <el-button size="small" text @click="closeSearch">Close</el-button>
        </div>
        <div v-if="isSearching" class="search-loading">
          <el-icon class="is-loading"><Loading /></el-icon>
          Searching…
        </div>
        <div v-else-if="searchQuery && !searchHits.length" class="search-empty">
          No matches.
        </div>
        <div v-else class="search-hits">
          <div
            v-for="hit in searchHits"
            :key="hit.message_id"
            class="search-hit"
            @click="openHit(hit)"
          >
            <div class="search-hit-head">
              <span class="search-hit-title">{{ hit.conversation_title }}</span>
              <el-tag size="small" effect="plain"
                      :type="hit.role === 'user' ? '' : 'info'">
                {{ hit.role }}
              </el-tag>
            </div>
            <div class="search-hit-snippet" v-html="hit.snippet" />
            <div class="search-hit-meta">
              {{ formatDate(hit.created_at) }}
              <span v-if="hit.model"> · {{ prettyModel(hit.model) }}</span>
            </div>
          </div>
        </div>
      </div>

      <div class="sidebar-list">
        <template v-for="group in groupedConversations" :key="group.key">
          <div v-if="group.items.length" class="conv-group-header">
            {{ group.label }} · {{ group.items.length }}
          </div>
          <div
            v-for="conv in group.items"
            :key="conv.id"
            class="conv-item"
            :class="{ active: conv.id === activeConvId, archived: conv.archived }"
            @click="selectConversation(conv.id)"
          >
            <div class="conv-title" :title="conv.title">
              <span v-if="conv.pinned" class="conv-pin-mark" title="pinned">📌</span>
              {{ conv.title }}
            </div>
            <div class="conv-meta">
              <el-tag size="small" :type="aliasTagType(conv.model_alias)" effect="plain">
                {{ conv.model_alias }}
              </el-tag>
              <span class="conv-time">{{ formatDate(conv.updated_at) }}</span>
            </div>
            <div class="conv-actions" @click.stop>
              <el-dropdown trigger="click" @command="(cmd) => handleConvCommand(cmd, conv)">
                <el-icon class="conv-more"><MoreFilled /></el-icon>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="rename">Rename</el-dropdown-item>
                    <el-dropdown-item command="export">Export to Markdown</el-dropdown-item>
                    <el-dropdown-item :command="conv.pinned ? 'unpin' : 'pin'" divided>
                      {{ conv.pinned ? 'Unpin' : 'Pin' }}
                    </el-dropdown-item>
                    <el-dropdown-item :command="conv.archived ? 'unarchive' : 'archive'">
                      {{ conv.archived ? 'Unarchive' : 'Archive' }}
                    </el-dropdown-item>
                    <el-dropdown-item command="delete" divided>Delete</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </div>
        </template>

        <el-empty
          v-if="conversations.length === 0 && !isLoadingList"
          description="No conversations yet"
          :image-size="80"
        />
      </div>

      <!-- Stats footer -->
      <div class="sidebar-footer" v-if="usageStats">
        <div class="stats-summary" @click="statsOpen = !statsOpen">
          <span class="stats-label">Usage</span>
          <span class="stats-figures">
            <span :title="`Input tokens today`">
              ↓ {{ formatTokens(usageStats.today.input) }}
            </span>
            <span :title="`Output tokens today`">
              ↑ {{ formatTokens(usageStats.today.output) }}
            </span>
            <span class="stats-caret">{{ statsOpen ? '▾' : '▸' }}</span>
          </span>
        </div>
        <div v-if="statsOpen" class="stats-detail">
          <div class="stats-row">
            <span class="stats-key">Today</span>
            <span class="stats-val">
              ↓ {{ formatTokens(usageStats.today.input) }} ·
              ↑ {{ formatTokens(usageStats.today.output) }}
            </span>
          </div>
          <div class="stats-row">
            <span class="stats-key">7 days</span>
            <span class="stats-val">
              ↓ {{ formatTokens(usageStats.last_7_days.input) }} ·
              ↑ {{ formatTokens(usageStats.last_7_days.output) }}
            </span>
          </div>
          <div class="stats-row">
            <span class="stats-key">All time</span>
            <span class="stats-val">
              ↓ {{ formatTokens(usageStats.overall.input) }} ·
              ↑ {{ formatTokens(usageStats.overall.output) }}
            </span>
          </div>
          <el-divider class="stats-divider" />
          <div
            v-for="m in usageStats.by_model"
            :key="m.model"
            class="stats-row"
          >
            <span class="stats-key" :title="m.model">
              {{ prettyModel(m.model) }}
            </span>
            <span class="stats-val">
              ↓ {{ formatTokens(m.input) }} ·
              ↑ {{ formatTokens(m.output) }}
              <span class="stats-msg-count">({{ m.message_count }})</span>
            </span>
          </div>
          <div v-if="!usageStats.by_model.length" class="stats-empty">
            No usage recorded yet.
          </div>
        </div>
      </div>
    </aside>

    <!-- Main: chat area -->
    <main class="chat-area">
      <template v-if="activeConv">
        <div class="chat-header">
          <h3 class="chat-title" @click="startRenameActive">{{ activeConv.title }}</h3>
          <el-tag
            v-if="activeConv.kb_enabled && lastKbHits.length"
            size="small"
            type="success"
            effect="plain"
            style="margin-left:8px"
            :title="lastKbHits.map(h => `${h.source_name}/${h.relpath} · ${h.score}`).join('\n')"
          >
            KB: {{ lastKbHits.length }} chunk(s)
          </el-tag>
          <div class="chat-header-right">
            <el-tooltip
              :content="wakeIsListening
                ? `Listening for &quot;${wakeKeyword}&quot; — click to stop`
                : 'Enable wake-word listening'"
              placement="bottom"
            >
              <el-button
                :type="wakeIsListening ? 'success' : ''"
                size="small"
                plain
                circle
                :loading="wakeBusy"
                @click="handleToggleWake"
              >
                <el-icon><Headset /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              :content="activeConv.kb_enabled ? 'Knowledge base: on' : 'Knowledge base: off'"
              placement="bottom"
            >
              <el-button
                :type="activeConv.kb_enabled ? 'primary' : ''"
                size="small"
                plain
                circle
                :disabled="kbSources.length === 0"
                @click="toggleKbForConversation(!activeConv.kb_enabled)"
                :title="kbSources.length === 0 ? 'Add a KB source first (Settings)' : ''"
              >
                <el-icon>
                  <FolderOpened v-if="activeConv.kb_enabled" />
                  <Folder v-else />
                </el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              :content="autoTTS ? 'Auto TTS: on (click to disable)' : 'Auto TTS: off (click to enable)'"
              placement="bottom"
            >
              <el-button
                :type="autoTTS ? 'primary' : ''"
                size="small"
                plain
                circle
                @click="toggleAutoTTS"
              >
                <el-icon>
                  <BellFilled v-if="autoTTS" />
                  <Bell v-else />
                </el-icon>
              </el-button>
            </el-tooltip>
            <el-button
              v-if="player.isBusy.value"
              size="small"
              plain
              circle
              @click="player.stop"
              title="Stop speaking"
            >
              <el-icon><VideoPause /></el-icon>
            </el-button>
            <span class="model-label">Model:</span>
            <el-select
              v-model="activeAlias"
              size="small"
              style="width: 110px"
              @change="handleAliasChange"
            >
              <el-option
                v-for="alias in aliases"
                :key="alias"
                :label="alias"
                :value="alias"
              />
            </el-select>
            <el-button
              size="small"
              plain
              circle
              @click="openSettings"
              title="Conversation settings"
            >
              <el-icon><Setting /></el-icon>
            </el-button>
          </div>
        </div>

        <div class="messages" ref="messagesRef">
          <div
            v-for="msg in messages"
            :key="msg.id"
            class="msg-row"
            :class="[`role-${msg.role}`, { 'msg-highlight': msg.id === highlightedMessageId }]"
            :data-msg-id="msg.id"
          >
            <div class="msg-bubble">
              <div class="msg-meta" v-if="msg.role === 'assistant'">
                <el-tag size="small" type="info" effect="plain">
                  {{ prettyModel(msg.model) }}
                </el-tag>
                <el-tag
                  v-if="msg.complexity"
                  size="small"
                  :type="complexityTagType(msg.complexity)"
                  effect="plain"
                >
                  {{ msg.complexity }}
                </el-tag>
                <span v-if="msg.output_tokens != null" class="msg-tokens">
                  {{ msg.input_tokens }}→{{ msg.output_tokens }} tokens
                </span>
                <div class="msg-actions">
                  <el-button
                    v-if="msg.content && msg.id > 0 && msg.id === lastAssistantId"
                    class="msg-action-btn"
                    size="small"
                    text
                    circle
                    :loading="isSending"
                    @click="regenerateLastReply"
                    title="Regenerate this reply"
                  >
                    <el-icon><RefreshRight /></el-icon>
                  </el-button>
                  <el-button
                    v-if="msg.content && msg.id > 0"
                    class="msg-action-btn"
                    size="small"
                    text
                    circle
                    :loading="isForking"
                    @click="forkFromMessage(msg, 'up-to')"
                    title="Continue from here in a new conversation"
                  >
                    <el-icon><Share /></el-icon>
                  </el-button>
                  <el-button
                    v-if="msg.content && msg.id > 0"
                    class="msg-action-btn"
                    size="small"
                    text
                    circle
                    @click="speakMessage(msg)"
                    title="Speak this message"
                  >
                    <el-icon><Bell /></el-icon>
                  </el-button>
                </div>
              </div>
              <div
                v-if="msg.role === 'assistant'"
                class="msg-body markdown"
                v-html="renderMarkdown(msg.content)"
              />
              <div v-else class="msg-body user">
                <div
                  v-if="msg.attachments && msg.attachments.length"
                  class="msg-attachments"
                >
                  <div
                    v-for="att in msg.attachments"
                    :key="att.id"
                    class="msg-att"
                  >
                    <img
                      v-if="att.kind === 'image'"
                      :src="attachmentPreviewUrl(att)"
                      :alt="att.filename"
                      class="msg-att-img"
                    />
                    <div v-else class="msg-att-file">
                      <el-icon><Document /></el-icon>
                      <span class="msg-att-name">{{ att.filename }}</span>
                      <span class="msg-att-size">{{ formatSize(att.byte_size) }}</span>
                    </div>
                  </div>
                </div>
                <div v-if="msg.content" class="msg-user-text">{{ msg.content }}</div>
                <div v-if="msg.id > 0" class="msg-actions user-actions">
                  <el-button
                    class="msg-action-btn"
                    size="small"
                    text
                    circle
                    @click="editMessage(msg)"
                    title="Edit this message and regenerate"
                  >
                    <el-icon><EditPen /></el-icon>
                  </el-button>
                  <el-button
                    class="msg-action-btn"
                    size="small"
                    text
                    circle
                    :loading="isForking"
                    @click="forkFromMessage(msg, 'before')"
                    title="Ask this question again in a new conversation"
                  >
                    <el-icon><RefreshRight /></el-icon>
                  </el-button>
                </div>
              </div>
            </div>
          </div>

          <div v-if="isSending && !messages.some(m => m.id < 0 && m.role === 'assistant')" class="msg-row role-assistant">
            <div class="msg-bubble">
              <div class="msg-meta">
                <el-tag size="small" type="warning" effect="plain">thinking…</el-tag>
              </div>
              <div class="msg-body markdown">
                <el-icon class="is-loading"><Loading /></el-icon>
              </div>
            </div>
          </div>
        </div>

        <div class="composer">
          <div
            v-if="pendingAttachments.length || isUploading"
            class="pending-attachments"
          >
            <div
              v-for="att in pendingAttachments"
              :key="att.id"
              class="pending-att"
            >
              <img
                v-if="att.kind === 'image'"
                :src="attachmentPreviewUrl(att)"
                :alt="att.filename"
                class="pending-att-img"
              />
              <div v-else class="pending-att-file">
                <el-icon><Document /></el-icon>
              </div>
              <div class="pending-att-meta">
                <span class="pending-att-name" :title="att.filename">
                  {{ att.filename }}
                </span>
                <span class="pending-att-size">
                  {{ formatSize(att.byte_size) }}
                </span>
              </div>
              <el-button
                class="pending-att-remove"
                size="small"
                text
                circle
                @click="removePendingAttachment(att.id)"
                title="Remove"
              >
                <el-icon><Close /></el-icon>
              </el-button>
            </div>
            <div v-if="isUploading" class="pending-att pending-att-uploading">
              <el-icon class="is-loading"><Loading /></el-icon>
              <span>Uploading…</span>
            </div>
          </div>

          <input
            ref="fileInputRef"
            type="file"
            multiple
            style="display:none"
            accept="image/*,application/pdf,text/*"
            @change="handleFilesChosen"
          />

          <el-input
            v-model="draft"
            type="textarea"
            :rows="3"
            :autosize="{ minRows: 2, maxRows: 8 }"
            placeholder="Type your message… (Cmd/Ctrl+Enter to send)"
            @keydown.ctrl.enter="handleSend"
            @keydown.meta.enter="handleSend"
            :disabled="isSending"
          />
          <div class="composer-actions">
            <div class="composer-left">
              <el-button
                circle
                @click="openFilePicker"
                :disabled="isSending || isUploading"
                :loading="isUploading"
                title="Attach file (image, PDF, text)"
              >
                <el-icon><Paperclip /></el-icon>
              </el-button>
              <el-button
                v-if="recorder.isSupported.value"
                :type="recorder.isRecording.value ? 'danger' : ''"
                :loading="isTranscribing"
                circle
                @mousedown="handleMicDown"
                @mouseup="handleMicUp"
                @mouseleave="handleMicLeave"
                @touchstart.prevent="handleMicDown"
                @touchend.prevent="handleMicUp"
                :title="recorder.isRecording.value ? 'Release to transcribe' : 'Hold to record'"
              >
                <el-icon>
                  <Microphone v-if="!recorder.isRecording.value" />
                  <Mute v-else />
                </el-icon>
              </el-button>
              <span v-if="recorder.isRecording.value" class="rec-status">
                Recording… release to send
              </span>
              <span v-else-if="isTranscribing" class="rec-status">
                Transcribing…
              </span>
              <span v-else class="composer-hint">
                Cmd/Ctrl+Enter to send · Hold mic to speak
              </span>
            </div>
            <el-button
              type="primary"
              @click="handleSend"
              :loading="isSending"
              :disabled="!draft.trim() && pendingAttachments.length === 0"
            >
              <el-icon><Position /></el-icon>
              Send
            </el-button>
          </div>
        </div>
      </template>

      <el-empty
        v-else
        description="Pick or create a conversation to start"
      >
        <el-button type="primary" @click="handleNewConversation">New Conversation</el-button>
      </el-empty>
    </main>

    <!-- Settings drawer -->
    <el-drawer
      v-model="settingsOpen"
      title="Conversation settings"
      direction="rtl"
      size="480px"
    >
      <div class="settings-form" v-if="settingsDraft">
        <el-form label-position="top">
          <el-form-item label="Title">
            <el-input v-model="settingsDraft.title" placeholder="Conversation title" />
          </el-form-item>
          <el-form-item label="Model routing">
            <el-select v-model="settingsDraft.model_alias" style="width: 100%">
              <el-option
                v-for="alias in aliases"
                :key="alias"
                :label="alias"
                :value="alias"
              />
            </el-select>
            <div class="settings-hint">
              <b>auto</b> lets Claude pick model per prompt based on complexity.
              Pin a specific tier to skip that classification step.
            </div>
          </el-form-item>
          <el-form-item label="System prompt">
            <el-input
              v-model="settingsDraft.system_prompt"
              type="textarea"
              :autosize="{ minRows: 8, maxRows: 20 }"
              placeholder="Instructions that shape how the assistant behaves in this conversation."
            />
            <div class="settings-hint">
              Applies to all future turns in this conversation. Existing
              messages are not resent — the change takes effect on your next
              send.
            </div>
          </el-form-item>
        </el-form>

        <el-divider content-position="left">Voice engines</el-divider>
        <div v-if="voiceDraft && voiceConfig" class="voice-section">
          <el-form label-position="top">
            <el-form-item label="Whisper model (ASR)">
              <el-select v-model="voiceDraft.whisper_model" style="width: 100%">
                <el-option
                  v-for="(desc, tag) in voiceConfig.whisper_models"
                  :key="tag"
                  :value="tag"
                >
                  <div style="display:flex;flex-direction:column;line-height:1.3;padding:2px 0;">
                    <span style="font-weight:600;">{{ tag }}</span>
                    <span style="color:#909399;font-size:11px;">{{ desc }}</span>
                  </div>
                </el-option>
              </el-select>
              <div class="settings-hint">
                Switching model unloads the current one on next transcription
                (5–10 s reload). See docs/voice-engines.md for the trade-offs.
              </div>
            </el-form-item>
            <el-form-item label="TTS engine">
              <el-select v-model="voiceDraft.tts_engine" style="width: 100%">
                <el-option
                  v-for="(desc, name) in voiceConfig.tts_engines"
                  :key="name"
                  :value="name"
                >
                  <div style="display:flex;flex-direction:column;line-height:1.3;padding:2px 0;">
                    <span style="font-weight:600;">{{ name }}</span>
                    <span style="color:#909399;font-size:11px;">{{ desc }}</span>
                  </div>
                </el-option>
              </el-select>
              <div class="settings-hint">
                <b>say</b> is zero-config and reliable; <b>kokoro</b> is more
                natural but must be installed separately.
              </div>
            </el-form-item>
          </el-form>
        </div>
        <div v-else class="settings-hint">
          Voice endpoints unavailable — start the backend to enable ASR / TTS.
        </div>

        <el-divider content-position="left">Wake word</el-divider>
        <div class="wake-section">
          <div class="settings-hint" style="margin-bottom:8px">
            When enabled, the backend listens on the system microphone.
            Say the wake word, then talk — your speech is transcribed and
            dropped into the composer for review.
          </div>
          <el-form label-position="top">
            <el-form-item label="Keyword">
              <el-select
                v-model="wakeKeyword"
                style="width: 100%"
                :disabled="wakeIsListening"
              >
                <el-option
                  v-for="k in (wakeStatus?.keywords_available || ['hey_jarvis'])"
                  :key="k"
                  :label="k"
                  :value="k"
                />
              </el-select>
              <div class="settings-hint">
                Changing the keyword requires stopping and restarting the
                listener.
              </div>
            </el-form-item>
          </el-form>
        </div>

        <el-divider content-position="left">Knowledge base</el-divider>
        <div class="kb-section">
          <div class="settings-hint" style="margin-bottom:8px">
            Point at a local folder — Markdown, text, PDF, and common code
            files inside will be indexed and used as context when a conversation
            has the folder icon enabled.
          </div>

          <div class="kb-add-row">
            <el-input
              v-model="kbNewName"
              placeholder="Name (optional)"
              size="small"
              style="width: 30%"
            />
            <el-input
              v-model="kbNewPath"
              placeholder="/absolute/path/to/folder"
              size="small"
              style="flex:1"
            />
            <el-button size="small" type="primary" @click="handleAddKbSource">
              <el-icon><Plus /></el-icon>
              Add
            </el-button>
          </div>

          <div v-if="kbSources.length === 0" class="settings-hint">
            No knowledge sources yet.
          </div>

          <div v-else class="kb-list">
            <div
              v-for="src in kbSources"
              :key="src.id"
              class="kb-item"
              :class="{ 'kb-disabled': !src.enabled }"
            >
              <div class="kb-item-info">
                <div class="kb-item-title">
                  <el-switch
                    :model-value="!!src.enabled"
                    @change="() => toggleKbSource(src)"
                    size="small"
                  />
                  <span class="kb-item-name">{{ src.name }}</span>
                </div>
                <div class="kb-item-path" :title="src.path">{{ src.path }}</div>
                <div class="kb-item-meta">
                  {{ src.file_count }} file(s) · {{ src.chunk_count }} chunk(s)
                  <span v-if="src.last_scanned_at">
                    · scanned {{ formatDate(src.last_scanned_at) }}
                  </span>
                  <span v-else class="kb-item-warning">
                    · never scanned — click Refresh
                  </span>
                </div>
              </div>
              <div class="kb-item-actions">
                <el-button
                  size="small"
                  plain
                  :loading="kbRefreshingIds.has(src.id)"
                  @click="handleRefreshKb(src)"
                >
                  <el-icon><RefreshRight /></el-icon>
                  Refresh
                </el-button>
                <el-button
                  size="small"
                  plain
                  type="danger"
                  @click="handleDeleteKb(src)"
                >
                  <el-icon><Close /></el-icon>
                </el-button>
              </div>
            </div>
          </div>
        </div>
      </div>
      <template #footer>
        <div class="settings-footer">
          <el-button @click="resetSystemPrompt" plain>Reset to default</el-button>
          <div class="settings-footer-right">
            <el-button @click="settingsOpen = false">Cancel</el-button>
            <el-button
              type="primary"
              :loading="isSavingSettings"
              @click="saveSettings"
            >
              Save
            </el-button>
          </div>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script lang="ts" setup>
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ArrowLeft,
  Plus,
  Position,
  Loading,
  MoreFilled,
  Setting,
  Microphone,
  Mute,
  VideoPause,
  Bell,
  BellFilled,
  Paperclip,
  Close,
  Document,
  Search,
  Share,
  RefreshRight,
  Folder,
  FolderOpened,
  EditPen,
  Headset,
} from '@element-plus/icons-vue'
import { marked } from 'marked'
import {
  listConversations,
  createConversation,
  getConversation,
  updateConversation,
  deleteConversation,
  listMessages,
  streamChat,
  getModels,
  transcribeAudio,
  getVoiceConfig,
  updateVoiceConfig,
  uploadAttachment,
  attachmentRawUrl,
  getUsageStats,
  downloadExport,
  searchMessages,
  forkConversation,
  listKbSources,
  createKbSource,
  updateKbSource,
  deleteKbSource,
  refreshKbSource,
  editUserMessage,
  streamRegenerate,
  getWakeStatus,
  startWake,
  stopWake,
  type Conversation,
  type ConversationSummary,
  type Message,
  type ModelAlias,
  type VoiceConfig,
  type WhisperModel,
  type TTSEngine,
  type Attachment,
  type AttachmentSummary,
  type UsageStats,
  type SearchHit,
  type ForkMode,
  type KbSource,
  type KbHit,
  type WakeStatus,
} from '../service/api'
import { useRecorder } from '../service/recorder'
import { usePlayer } from '../service/player'
import { getWakeWebSocketService, type WakeEvent } from '../service/wake'

marked.setOptions({ gfm: true, breaks: true })

const router = useRouter()

const conversations = ref<ConversationSummary[]>([])
const activeConvId = ref<string | null>(null)
const activeConv = ref<Conversation | null>(null)
const activeAlias = ref<ModelAlias>('auto')
const messages = ref<Message[]>([])
const draft = ref('')
const aliases = ref<ModelAlias[]>(['auto', 'haiku', 'sonnet', 'opus'])
const isLoadingList = ref(false)
const isCreating = ref(false)
const isSending = ref(false)
const messagesRef = ref<HTMLElement | null>(null)

// Settings drawer
const settingsOpen = ref(false)
const isSavingSettings = ref(false)
const DEFAULT_SYSTEM_PROMPT = (
  'You are a helpful, concise assistant. '
  + 'Answer in the same language the user writes in. '
  + 'When code is involved, use fenced code blocks with language tags.'
)
const settingsDraft = ref<{
  title: string
  system_prompt: string
  model_alias: ModelAlias
} | null>(null)

// Voice: recorder + transcription state
const recorder = useRecorder()
const isTranscribing = ref(false)

// Voice: TTS playback state
const player = usePlayer()
const TTS_STORAGE_KEY = 'assistant.autoTTS'
const autoTTS = ref<boolean>(
  typeof localStorage !== 'undefined'
    ? localStorage.getItem(TTS_STORAGE_KEY) === '1'
    : false
)
watch(autoTTS, (v) => {
  try { localStorage.setItem(TTS_STORAGE_KEY, v ? '1' : '0') } catch { /* noop */ }
  if (!v) player.stop()
})

// Voice config (drawer + engine info)
const voiceConfig = ref<VoiceConfig | null>(null)
const voiceDraft = ref<{ whisper_model: WhisperModel; tts_engine: TTSEngine } | null>(null)
const isSavingVoice = ref(false)

// Attachments pending on the composer, uploaded but not yet sent.
const fileInputRef = ref<HTMLInputElement | null>(null)
const pendingAttachments = ref<Attachment[]>([])
const isUploading = ref(false)

// Usage stats (refreshed after each message)
const usageStats = ref<UsageStats | null>(null)
const statsOpen = ref(false)

// Search
const searchOpen = ref(false)
const searchQuery = ref('')
const searchHits = ref<SearchHit[]>([])
const isSearching = ref(false)
let searchDebounceTimer: number | null = null
const highlightedMessageId = ref<number | null>(null)

// Knowledge Base
const kbSources = ref<KbSource[]>([])
const kbNewPath = ref('')
const kbNewName = ref('')
const kbRefreshingIds = ref<Set<string>>(new Set())
const lastKbHits = ref<KbHit[]>([])   // hits used for the most recent reply

// Wake word
const wakeStatus = ref<WakeStatus | null>(null)
const wakeIsListening = ref(false)
const wakeBusy = ref(false)   // recording / transcribing right after a wake
const wakeKeyword = ref<string>('hey_jarvis')
const wakeWs = getWakeWebSocketService()

function goBack() {
  router.push('/')
}

function formatDate(iso: string) {
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

function aliasTagType(alias: string): 'primary' | 'success' | 'warning' | 'danger' | 'info' {
  switch (alias) {
    case 'auto': return 'primary'
    case 'haiku': return 'success'
    case 'sonnet': return 'warning'
    case 'opus': return 'danger'
    default: return 'info'
  }
}

function complexityTagType(c: string | null | undefined): 'success' | 'warning' | 'danger' | 'info' {
  switch (c) {
    case 'simple': return 'success'
    case 'medium': return 'warning'
    case 'hard': return 'danger'
    default: return 'info'
  }
}

function prettyModel(m: string | null): string {
  if (!m) return '-'
  if (m.includes('haiku')) return 'Haiku 4.5'
  if (m.includes('sonnet')) return 'Sonnet 4.5'
  if (m.includes('opus')) return 'Opus 4.7'
  return m
}

function renderMarkdown(text: string): string {
  return marked.parse(text) as string
}

async function scrollToBottom() {
  await nextTick()
  const el = messagesRef.value
  if (el) el.scrollTop = el.scrollHeight
}

async function refreshList() {
  isLoadingList.value = true
  try {
    conversations.value = await listConversations()
  } catch (err: any) {
    ElMessage.error(err.message || 'Failed to load conversations')
  } finally {
    isLoadingList.value = false
  }
}

async function refreshStats() {
  try {
    usageStats.value = await getUsageStats()
  } catch (err) {
    // stats endpoint failure shouldn't be user-visible
    console.error('[assistant] refreshStats failed', err)
  }
}

// ── Search ────────────────────────────────────────────
function openSearch() {
  searchOpen.value = true
  setTimeout(() => {
    const el = document.getElementById('assistant-search-input')
    ;(el as HTMLInputElement | null)?.focus()
  }, 50)
}

function closeSearch() {
  searchOpen.value = false
  searchQuery.value = ''
  searchHits.value = []
}

function onSearchInput() {
  if (searchDebounceTimer !== null) {
    clearTimeout(searchDebounceTimer)
  }
  const q = searchQuery.value.trim()
  if (!q) {
    searchHits.value = []
    isSearching.value = false
    return
  }
  isSearching.value = true
  searchDebounceTimer = window.setTimeout(async () => {
    try {
      const resp = await searchMessages(q, 30)
      // Guard against stale responses landing after a newer query.
      if (searchQuery.value.trim() === q) {
        searchHits.value = resp.hits
      }
    } catch (err: any) {
      ElMessage.error(err.message || 'Search failed')
    } finally {
      isSearching.value = false
    }
  }, 250)
}

async function openHit(hit: SearchHit) {
  await selectConversation(hit.conversation_id)
  highlightedMessageId.value = hit.message_id
  closeSearch()
  // Scroll the target message into view after messages render.
  setTimeout(() => {
    const el = document.querySelector(
      `[data-msg-id="${hit.message_id}"]`
    ) as HTMLElement | null
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }, 100)
  // Fade the highlight out after a few seconds.
  setTimeout(() => {
    if (highlightedMessageId.value === hit.message_id) {
      highlightedMessageId.value = null
    }
  }, 4000)
}

// ── Fork ──────────────────────────────────────────────
const isForking = ref(false)

async function forkFromMessage(msg: Message, mode: ForkMode) {
  if (!activeConvId.value) return
  isForking.value = true
  try {
    const newConv = await forkConversation(
      activeConvId.value,
      msg.id,
      mode,
    )
    await refreshList()
    await selectConversation(newConv.id)
    const label = mode === 'up-to'
      ? 'Continued in new conversation'
      : 'New conversation ready — send a new question'
    ElMessage.success(label)
  } catch (err: any) {
    ElMessage.error(err.message || 'Fork failed')
  } finally {
    isForking.value = false
  }
}

// ── Edit user message + regenerate ────────────────────────
// ── Edit user message + regenerate ────────────────────────
const lastAssistantId = computed(() => {
  for (let i = messages.value.length - 1; i >= 0; i--) {
    const m = messages.value[i]
    if (m.role === 'assistant' && m.id > 0) return m.id
  }
  return null
})

// Sidebar grouping: pinned → active → archived. The list itself is
// already sorted server-side by (pinned DESC, archived ASC, updated_at DESC).
const groupedConversations = computed(() => {
  const pinned: ConversationSummary[] = []
  const active: ConversationSummary[] = []
  const archived: ConversationSummary[] = []
  for (const c of conversations.value) {
    if (c.archived) archived.push(c)
    else if (c.pinned) pinned.push(c)
    else active.push(c)
  }
  return [
    { key: 'pinned', label: 'Pinned', items: pinned },
    { key: 'active', label: 'Conversations', items: active },
    { key: 'archived', label: 'Archived', items: archived },
  ]
})

async function regenerateLastReply() {
  if (!activeConvId.value || isSending.value) return
  const convId = activeConvId.value

  const streamingAssistant: Message = {
    id: -Date.now() - 1,
    conversation_id: convId,
    role: 'assistant',
    content: '',
    model: null,
    complexity: null,
    input_tokens: null,
    output_tokens: null,
    created_at: new Date().toISOString(),
  }
  // Drop the previous assistant reply from the UI immediately so users
  // see the regeneration happening in its place.
  const dropped = messages.value.filter(m => m.id !== lastAssistantId.value)
  messages.value = [...dropped, streamingAssistant]
  scrollToBottom()

  isSending.value = true
  try {
    await streamRegenerate(convId, (evt) => {
      if (evt.type === 'start') {
        streamingAssistant.model = evt.model
        streamingAssistant.complexity = evt.complexity
        lastKbHits.value = evt.kb_hits || []
      } else if (evt.type === 'delta') {
        streamingAssistant.content += evt.text
        scrollToBottom()
      } else if (evt.type === 'done') {
        streamingAssistant.id = evt.message.id
        streamingAssistant.content = evt.message.content
        streamingAssistant.input_tokens = evt.input_tokens
        streamingAssistant.output_tokens = evt.output_tokens
        streamingAssistant.created_at = evt.message.created_at
        if (autoTTS.value) {
          player.speak(evt.message.content).catch(() => {})
        }
      } else if (evt.type === 'error') {
        throw new Error(evt.message)
      }
    })
    messages.value = await listMessages(convId)
    scrollToBottom()
    refreshStats()
    ElMessage.success('Regenerated')
  } catch (err: any) {
    // Keep partial content if any, resync from DB.
    try {
      messages.value = await listMessages(convId)
    } catch { /* ignore */ }
    ElMessage.error(err.message || 'Regeneration failed')
  } finally {
    isSending.value = false
  }
}

async function editMessage(msg: Message) {
  if (msg.role !== 'user' || !activeConvId.value || msg.id <= 0) return
  const convId = activeConvId.value
  try {
    const { value } = await ElMessageBox.prompt(
      'Edit message',
      'Editing this message will delete all subsequent replies and regenerate.',
      {
        inputValue: msg.content,
        inputType: 'textarea',
        confirmButtonText: 'Save & regenerate',
        cancelButtonText: 'Cancel',
      },
    )
    const newContent = (value || '').trim()
    if (!newContent || newContent === msg.content) return

    await editUserMessage(convId, msg.id, newContent)
    messages.value = await listMessages(convId)
    scrollToBottom()

    // Regenerate assistant reply.
    const streamingAssistant: Message = {
      id: -Date.now() - 1,
      conversation_id: convId,
      role: 'assistant',
      content: '',
      model: null,
      complexity: null,
      input_tokens: null,
      output_tokens: null,
      created_at: new Date().toISOString(),
    }
    messages.value.push(streamingAssistant)
    isSending.value = true
    try {
      await streamRegenerate(convId, (evt) => {
        if (evt.type === 'start') {
          streamingAssistant.model = evt.model
          streamingAssistant.complexity = evt.complexity
          lastKbHits.value = evt.kb_hits || []
        } else if (evt.type === 'delta') {
          streamingAssistant.content += evt.text
          scrollToBottom()
        } else if (evt.type === 'done') {
          streamingAssistant.id = evt.message.id
          streamingAssistant.content = evt.message.content
          streamingAssistant.input_tokens = evt.input_tokens
          streamingAssistant.output_tokens = evt.output_tokens
          streamingAssistant.created_at = evt.message.created_at
          if (autoTTS.value) {
            player.speak(evt.message.content).catch(() => {})
          }
        } else if (evt.type === 'error') {
          throw new Error(evt.message)
        }
      })
      messages.value = await listMessages(convId)
      scrollToBottom()
      refreshStats()
      ElMessage.success('Regenerated with edited message')
    } catch (err: any) {
      messages.value = messages.value.filter(m => m.id !== streamingAssistant.id)
      ElMessage.error(err.message || 'Regeneration failed')
    } finally {
      isSending.value = false
    }
  } catch (err: any) {
    if (err !== 'cancel') {
      ElMessage.error(err.message || 'Edit failed')
    }
  }
}

// ── Knowledge Base ─────────────────────────────────────
async function refreshKbSources() {
  try {
    kbSources.value = await listKbSources()
  } catch (err: any) {
    ElMessage.error(err.message || 'Failed to load KB sources')
  }
}

async function handleAddKbSource() {
  const path = kbNewPath.value.trim()
  if (!path) {
    ElMessage.warning('Enter a folder path')
    return
  }
  try {
    await createKbSource(kbNewName.value.trim(), path)
    kbNewPath.value = ''
    kbNewName.value = ''
    await refreshKbSources()
    ElMessage.success('Source added — click Refresh to index it')
  } catch (err: any) {
    ElMessage.error(err.message || 'Failed to add source')
  }
}

async function handleRefreshKb(src: KbSource) {
  kbRefreshingIds.value.add(src.id)
  try {
    const result = await refreshKbSource(src.id)
    await refreshKbSources()
    ElMessage.success(
      `Indexed: +${result.added} new, ${result.changed} changed, `
      + `${result.unchanged} unchanged, ${result.deleted} removed`,
    )
  } catch (err: any) {
    ElMessage.error(err.message || 'Refresh failed')
  } finally {
    kbRefreshingIds.value.delete(src.id)
  }
}

async function handleDeleteKb(src: KbSource) {
  try {
    await ElMessageBox.confirm(
      `Delete knowledge source "${src.name}"? Indexed chunks will be removed too.`,
      'Warning',
      { confirmButtonText: 'Delete', cancelButtonText: 'Cancel', type: 'warning' },
    )
    await deleteKbSource(src.id)
    await refreshKbSources()
    ElMessage.success('Source deleted')
  } catch (err: any) {
    if (err !== 'cancel') {
      ElMessage.error(err.message || 'Delete failed')
    }
  }
}

async function toggleKbSource(src: KbSource) {
  try {
    await updateKbSource(src.id, { enabled: !src.enabled })
    await refreshKbSources()
  } catch (err: any) {
    ElMessage.error(err.message || 'Toggle failed')
  }
}

async function toggleKbForConversation(val: boolean) {
  if (!activeConv.value) return
  try {
    const updated = await updateConversation(activeConv.value.id, {
      kb_enabled: val,
    })
    activeConv.value = updated
    await refreshList()
    ElMessage.success(val
      ? 'Knowledge base enabled for this conversation'
      : 'Knowledge base disabled')
  } catch (err: any) {
    ElMessage.error(err.message || 'Update failed')
  }
}

// ── Wake word ────────────────────────────────────────
async function refreshWakeStatus() {
  try {
    wakeStatus.value = await getWakeStatus()
    wakeIsListening.value = !!wakeStatus.value.running
    wakeKeyword.value = wakeStatus.value.keyword || wakeKeyword.value
  } catch (err) {
    console.error('[assistant] wake status failed', err)
  }
}

async function handleToggleWake() {
  if (wakeBusy.value) return
  try {
    if (wakeIsListening.value) {
      await stopWake()
      wakeIsListening.value = false
      ElMessage.info('Stopped listening')
    } else {
      const st = await startWake({ keyword: wakeKeyword.value })
      wakeIsListening.value = st.running
      ElMessage.success(`Listening for "${st.keyword}" — say it to speak`)
    }
  } catch (err: any) {
    ElMessage.error(err.message || 'Wake toggle failed')
  }
}

function handleWakeEvent(evt: WakeEvent) {
  if (evt.type === 'wake') {
    wakeBusy.value = true
    ElMessage({
      message: `Wake word detected (${evt.keyword} · ${evt.score})`,
      type: 'success',
      duration: 1500,
    })
  } else if (evt.type === 'transcribing') {
    // Keep the "busy" flag; the transcript event will follow.
  } else if (evt.type === 'transcript') {
    wakeBusy.value = false
    const text = (evt.text || '').trim()
    if (!text) {
      ElMessage.info('Nothing recognized')
      return
    }
    // Append to composer so the user can review before sending.
    draft.value = draft.value
      ? `${draft.value.trimEnd()} ${text}`
      : text
    ElMessage.success('Transcribed — review and send')
  } else if (evt.type === 'cancelled') {
    wakeBusy.value = false
    ElMessage.info(`Cancelled: ${evt.reason}`)
  } else if (evt.type === 'error') {
    wakeBusy.value = false
    wakeIsListening.value = false
    ElMessage.error(`Wake error: ${evt.message}`)
  } else if (evt.type === 'status') {
    wakeIsListening.value = !!evt.running
  }
}

function formatTokens(n: number): string {
  if (n < 1000) return String(n)
  if (n < 1000000) return `${(n / 1000).toFixed(1)}k`
  return `${(n / 1000000).toFixed(2)}M`
}

async function loadConversation(id: string) {
  const [conv, msgs] = await Promise.all([
    getConversation(id),
    listMessages(id),
  ])
  activeConv.value = conv
  activeAlias.value = conv.model_alias
  messages.value = msgs
  scrollToBottom()
}

async function selectConversation(id: string) {
  if (activeConvId.value === id) return
  activeConvId.value = id
  try {
    await loadConversation(id)
  } catch (err: any) {
    ElMessage.error(err.message || 'Failed to load conversation')
  }
}

async function handleNewConversation() {
  isCreating.value = true
  try {
    const conv = await createConversation({ title: 'New chat', model_alias: 'auto' })
    await refreshList()
    activeConvId.value = conv.id
    await loadConversation(conv.id)
  } catch (err: any) {
    ElMessage.error(err.message || 'Failed to create conversation')
  } finally {
    isCreating.value = false
  }
}

async function handleAliasChange(newAlias: ModelAlias) {
  if (!activeConv.value) return
  try {
    const updated = await updateConversation(activeConv.value.id, { model_alias: newAlias })
    activeConv.value = updated
    const item = conversations.value.find(c => c.id === updated.id)
    if (item) item.model_alias = updated.model_alias
  } catch (err: any) {
    ElMessage.error(err.message || 'Failed to update model')
  }
}

async function startRenameActive() {
  if (!activeConv.value) return
  try {
    const { value } = await ElMessageBox.prompt('Rename conversation', 'Rename', {
      inputValue: activeConv.value.title,
      confirmButtonText: 'Save',
      cancelButtonText: 'Cancel',
    })
    if (value && value.trim()) {
      const updated = await updateConversation(activeConv.value.id, { title: value.trim() })
      activeConv.value = updated
      await refreshList()
    }
  } catch {
    // cancelled
  }
}

async function handleConvCommand(cmd: string, conv: ConversationSummary) {
  if (cmd === 'rename') {
    try {
      const { value } = await ElMessageBox.prompt('Rename conversation', 'Rename', {
        inputValue: conv.title,
        confirmButtonText: 'Save',
        cancelButtonText: 'Cancel',
      })
      if (value && value.trim()) {
        await updateConversation(conv.id, { title: value.trim() })
        await refreshList()
        if (activeConvId.value === conv.id) {
          await loadConversation(conv.id)
        }
      }
    } catch {
      // cancelled
    }
  } else if (cmd === 'export') {
    try {
      await downloadExport(conv.id, conv.title)
      ElMessage.success('Exported')
    } catch (err: any) {
      ElMessage.error(err.message || 'Export failed')
    }
  } else if (cmd === 'pin' || cmd === 'unpin') {
    try {
      await updateConversation(conv.id, { pinned: cmd === 'pin' })
      await refreshList()
    } catch (err: any) {
      ElMessage.error(err.message || 'Update failed')
    }
  } else if (cmd === 'archive' || cmd === 'unarchive') {
    try {
      await updateConversation(conv.id, { archived: cmd === 'archive' })
      await refreshList()
    } catch (err: any) {
      ElMessage.error(err.message || 'Update failed')
    }
  } else if (cmd === 'delete') {
    try {
      await ElMessageBox.confirm(
        `Delete conversation "${conv.title}"?`,
        'Warning',
        { confirmButtonText: 'Delete', cancelButtonText: 'Cancel', type: 'warning' },
      )
      await deleteConversation(conv.id)
      if (activeConvId.value === conv.id) {
        activeConvId.value = null
        activeConv.value = null
        messages.value = []
      }
      await refreshList()
      ElMessage.success('Conversation deleted')
    } catch {
      // cancelled
    }
  }
}

async function handleSend() {
  const text = draft.value.trim()
  const attachmentIds = pendingAttachments.value.map(a => a.id)
  if (!text && attachmentIds.length === 0) return
  if (!activeConvId.value || isSending.value) return
  const convId = activeConvId.value
  const snapshotAttachments = pendingAttachments.value.map(a => ({
    id: a.id,
    kind: a.kind,
    mime_type: a.mime_type,
    filename: a.filename,
    byte_size: a.byte_size,
  } as AttachmentSummary))

  // Optimistic user message
  const optimisticUser: Message = {
    id: -Date.now(),
    conversation_id: convId,
    role: 'user',
    content: text || `[${attachmentIds.length} attachment(s)]`,
    model: null,
    complexity: null,
    input_tokens: null,
    output_tokens: null,
    created_at: new Date().toISOString(),
    attachments: snapshotAttachments,
  }
  messages.value.push(optimisticUser)

  // Streaming assistant placeholder — content grows as tokens arrive.
  const streamingAssistant: Message = {
    id: -Date.now() - 1,
    conversation_id: convId,
    role: 'assistant',
    content: '',
    model: null,
    complexity: null,
    input_tokens: null,
    output_tokens: null,
    created_at: new Date().toISOString(),
  }
  messages.value.push(streamingAssistant)

  draft.value = ''
  pendingAttachments.value = []
  scrollToBottom()

  isSending.value = true
  try {
    await streamChat(convId, text, (evt) => {
      if (evt.type === 'start') {
        streamingAssistant.model = evt.model
        streamingAssistant.complexity = evt.complexity
        lastKbHits.value = evt.kb_hits || []
      } else if (evt.type === 'delta') {
        streamingAssistant.content += evt.text
        scrollToBottom()
      } else if (evt.type === 'done') {
        // Replace placeholders with authoritative rows from DB payload.
        streamingAssistant.id = evt.message.id
        streamingAssistant.content = evt.message.content
        streamingAssistant.model = evt.model
        streamingAssistant.complexity = evt.complexity
        streamingAssistant.input_tokens = evt.input_tokens
        streamingAssistant.output_tokens = evt.output_tokens
        streamingAssistant.created_at = evt.message.created_at
        if (autoTTS.value) {
          // Fire and forget — don't block sending on TTS success.
          player.speak(evt.message.content).catch((err) => {
            console.error('[assistant] auto-TTS failed', err)
          })
        }
      } else if (evt.type === 'error') {
        // Preserve any partial content — the backend also persisted it,
        // so refreshing messages will bring us the authoritative row.
        ElMessage.error(evt.message || 'Streaming failed')
        return
      }
    }, { attachmentIds })

    // Refresh from DB so both user + assistant rows carry real IDs / timestamps.
    messages.value = await listMessages(convId)
    scrollToBottom()
    await refreshList()
    refreshStats()  // fire-and-forget
  } catch (err: any) {
    // If we already streamed content, keep it visible — sync from DB.
    if (streamingAssistant.content) {
      try {
        messages.value = await listMessages(convId)
        scrollToBottom()
      } catch { /* ignore */ }
      ElMessage.error(err.message || 'Streaming interrupted — partial reply kept')
    } else {
      // No content produced: roll back the placeholders and let the user retry.
      messages.value = messages.value.filter(
        m => m.id !== optimisticUser.id && m.id !== streamingAssistant.id,
      )
      pendingAttachments.value = snapshotAttachments.map(a =>
        pendingAttachments.value.find(p => p.id === a.id)
          ?? (a as Attachment)
      ) as Attachment[]
      ElMessage.error(err.message || 'Failed to send message')
    }
  } finally {
    isSending.value = false
  }
}

function openSettings() {
  if (!activeConv.value) return
  settingsDraft.value = {
    title: activeConv.value.title,
    system_prompt: activeConv.value.system_prompt,
    model_alias: activeConv.value.model_alias,
  }
  if (voiceConfig.value) {
    voiceDraft.value = {
      whisper_model: voiceConfig.value.whisper_model,
      tts_engine: voiceConfig.value.tts_engine,
    }
  }
  settingsOpen.value = true
}

function resetSystemPrompt() {
  if (settingsDraft.value) {
    settingsDraft.value.system_prompt = DEFAULT_SYSTEM_PROMPT
  }
}

async function saveSettings() {
  if (!activeConv.value || !settingsDraft.value) return
  const payload = {
    title: settingsDraft.value.title.trim() || 'New chat',
    system_prompt: settingsDraft.value.system_prompt,
    model_alias: settingsDraft.value.model_alias,
  }
  isSavingSettings.value = true
  try {
    const updated = await updateConversation(activeConv.value.id, payload)
    activeConv.value = updated
    activeAlias.value = updated.model_alias
    await refreshList()

    // Persist voice draft if it changed
    if (voiceDraft.value && voiceConfig.value) {
      const changed = (
        voiceDraft.value.whisper_model !== voiceConfig.value.whisper_model
        || voiceDraft.value.tts_engine !== voiceConfig.value.tts_engine
      )
      if (changed) {
        isSavingVoice.value = true
        try {
          voiceConfig.value = await updateVoiceConfig(voiceDraft.value)
        } finally {
          isSavingVoice.value = false
        }
      }
    }

    settingsOpen.value = false
    ElMessage.success('Settings saved')
  } catch (err: any) {
    ElMessage.error(err.message || 'Failed to save settings')
  } finally {
    isSavingSettings.value = false
  }
}

// ── Voice recording (press-and-hold) ──────────────────
async function handleMicDown() {
  if (isSending.value || isTranscribing.value) return
  try {
    await recorder.start()
  } catch (err: any) {
    ElMessage.error(err.message || 'Cannot access microphone')
  }
}

async function handleMicUp() {
  if (!recorder.isRecording.value) return
  isTranscribing.value = true
  try {
    const blob = await recorder.stop()
    if (!blob || blob.size < 500) {
      ElMessage.info('Clip too short — try holding a bit longer')
      return
    }
    // Filename hint helps ffmpeg pick a demuxer server-side.
    const filename = blob.type.includes('mp4') ? 'clip.mp4'
      : blob.type.includes('ogg') ? 'clip.ogg' : 'clip.webm'
    const result = await transcribeAudio(blob, filename)
    if (!result.text.trim()) {
      ElMessage.warning('Nothing recognized in that clip')
      return
    }
    // Append transcription to composer so the user can review / edit
    // before sending.
    draft.value = draft.value
      ? `${draft.value.trimEnd()} ${result.text.trim()}`
      : result.text.trim()
    ElMessage.success(`Transcribed (${result.language}, ${result.whisper_model})`)
  } catch (err: any) {
    ElMessage.error(err.message || 'Transcription failed')
  } finally {
    isTranscribing.value = false
  }
}

function handleMicLeave() {
  // If the pointer slides off the button mid-hold, cancel instead of send.
  if (recorder.isRecording.value) {
    recorder.cancel()
    ElMessage.info('Recording cancelled')
  }
}

// ── Voice playback ────────────────────────────────────

async function speakMessage(msg: Message) {
  try {
    await player.speak(msg.content)
  } catch (err: any) {
    ElMessage.error(err.message || 'TTS failed')
  }
}

function toggleAutoTTS() {
  autoTTS.value = !autoTTS.value
}

// ── Attachments ───────────────────────────────────────
function openFilePicker() {
  fileInputRef.value?.click()
}

async function handleFilesChosen(evt: Event) {
  const target = evt.target as HTMLInputElement
  const files = Array.from(target.files || [])
  target.value = ''  // reset so choosing the same file again re-fires
  if (!files.length || !activeConvId.value) return

  const MAX_ATTS = 8
  const remaining = MAX_ATTS - pendingAttachments.value.length
  if (remaining <= 0) {
    ElMessage.warning(`Max ${MAX_ATTS} attachments per message`)
    return
  }
  const toUpload = files.slice(0, remaining)
  if (toUpload.length < files.length) {
    ElMessage.warning(`Only the first ${remaining} file(s) will be attached`)
  }

  isUploading.value = true
  try {
    for (const f of toUpload) {
      let att: Attachment | null = null
      try {
        att = await uploadAttachment(activeConvId.value, f)
      } catch (err: any) {
        // One automatic retry — most upload failures are transient.
        try {
          await new Promise(r => setTimeout(r, 500))
          att = await uploadAttachment(activeConvId.value, f)
        } catch (err2: any) {
          ElMessage.error(`${f.name}: ${err2.message || err.message || 'upload failed'}`)
        }
      }
      if (att) pendingAttachments.value.push(att)
    }
  } finally {
    isUploading.value = false
  }
}

function removePendingAttachment(id: string) {
  pendingAttachments.value = pendingAttachments.value.filter(a => a.id !== id)
}

function attachmentPreviewUrl(att: AttachmentSummary): string {
  return attachmentRawUrl(att.id)
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

onMounted(async () => {
  try {
    const info = await getModels()
    aliases.value = info.aliases
  } catch {
    // fall back to defaults
  }
  try {
    voiceConfig.value = await getVoiceConfig()
  } catch {
    // voice endpoints unavailable — mic button will simply do nothing on hover
  }
  refreshKbSources()  // fire-and-forget
  refreshWakeStatus()
  wakeWs.connect()
  wakeWs.onEvent(handleWakeEvent)
  await refreshList()
  refreshStats()
})

watch(activeConvId, (id) => {
  if (id === null) {
    activeConv.value = null
    messages.value = []
  }
})

onUnmounted(() => {
  wakeWs.offEvent()
  wakeWs.disconnect()
})
</script>

<style scoped>
.assistant-view {
  display: flex;
  height: calc(100vh - 0px);
  background: #f7f8fa;
}

/* ── Sidebar ─────────────────────────────────── */
.sidebar {
  width: 280px;
  min-width: 280px;
  border-right: 1px solid #e4e7ed;
  background: #ffffff;
  display: flex;
  flex-direction: column;
}

.sidebar-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  border-bottom: 1px solid #e4e7ed;
}

.app-title {
  flex: 1;
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.sidebar-list {
  flex: 1;
  overflow-y: auto;
  padding: 6px;
}

.conv-group-header {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.6px;
  color: #909399;
  padding: 8px 12px 4px 12px;
}

.conv-pin-mark {
  margin-right: 4px;
}

.conv-item.archived {
  opacity: 0.55;
}

.conv-item {
  position: relative;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  margin-bottom: 4px;
  transition: background 0.15s;
}

.conv-item:hover {
  background: #f0f2f5;
}

.conv-item.active {
  background: #eef4ff;
}

.conv-title {
  font-size: 13px;
  font-weight: 500;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding-right: 24px;
}

.conv-meta {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-top: 6px;
  font-size: 11px;
  color: #909399;
}

.conv-time {
  font-size: 11px;
  color: #909399;
}

.conv-actions {
  position: absolute;
  right: 8px;
  top: 10px;
  opacity: 0;
  transition: opacity 0.15s;
}

.conv-item:hover .conv-actions {
  opacity: 1;
}

.conv-more {
  cursor: pointer;
  color: #909399;
}

/* Sidebar footer + stats */
.sidebar-footer {
  border-top: 1px solid #e4e7ed;
  background: #fafbfc;
  padding: 8px 12px;
  font-size: 12px;
  color: #606266;
}

/* ── Search panel ────────────────────────────── */
.search-panel {
  position: absolute;
  inset: 52px 0 0 0;   /* below header */
  background: #ffffff;
  border-right: 1px solid #e4e7ed;
  display: flex;
  flex-direction: column;
  z-index: 10;
}

.search-input-row {
  display: flex;
  gap: 6px;
  padding: 8px 12px;
  border-bottom: 1px solid #f0f2f5;
}

.search-loading,
.search-empty {
  padding: 20px;
  text-align: center;
  color: #909399;
  font-size: 13px;
}

.search-hits {
  flex: 1;
  overflow-y: auto;
  padding: 4px 0;
}

.search-hit {
  padding: 10px 14px;
  border-bottom: 1px solid #f5f7fa;
  cursor: pointer;
}

.search-hit:hover {
  background: #f5f9ff;
}

.search-hit-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
  gap: 8px;
}

.search-hit-title {
  font-size: 12px;
  font-weight: 600;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.search-hit-snippet {
  font-size: 12px;
  color: #606266;
  line-height: 1.5;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
}

.search-hit-snippet :deep(mark) {
  background: #fff3cd;
  color: #664d03;
  padding: 0 2px;
  border-radius: 2px;
}

.search-hit-meta {
  margin-top: 4px;
  font-size: 11px;
  color: #909399;
}

/* Sidebar needs to be positioning context for the overlay panel. */
.sidebar {
  position: relative;
}

/* Highlight animation on search jump */
.msg-highlight .msg-bubble {
  box-shadow: 0 0 0 3px #ffe58f;
  transition: box-shadow 1.2s ease;
}

.stats-summary {
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  user-select: none;
  padding: 4px 0;
}

.stats-label {
  font-weight: 600;
  color: #303133;
}

.stats-figures {
  display: flex;
  gap: 10px;
  align-items: center;
  color: #606266;
  font-variant-numeric: tabular-nums;
}

.stats-caret {
  color: #909399;
  font-size: 10px;
}

.stats-detail {
  padding-top: 6px;
}

.stats-row {
  display: flex;
  justify-content: space-between;
  padding: 3px 0;
  font-variant-numeric: tabular-nums;
}

.stats-key {
  color: #909399;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100px;
}

.stats-val {
  color: #303133;
}

.stats-msg-count {
  color: #909399;
  margin-left: 4px;
}

.stats-divider {
  margin: 6px 0;
}

.stats-empty {
  color: #909399;
  padding: 4px 0;
}

/* ── Chat area ───────────────────────────────── */
.chat-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 24px;
  border-bottom: 1px solid #e4e7ed;
  background: #ffffff;
}

.chat-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
}

.chat-title:hover {
  color: #409eff;
}

.chat-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.model-label {
  font-size: 12px;
  color: #909399;
}

.messages {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px;
}

.msg-row {
  display: flex;
  margin-bottom: 16px;
}

.msg-row.role-user {
  justify-content: flex-end;
}

.msg-bubble {
  max-width: 780px;
  padding: 12px 16px;
  border-radius: 12px;
  background: #ffffff;
  border: 1px solid #e4e7ed;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
}

.msg-row.role-user .msg-bubble {
  background: #ecf5ff;
  border-color: #b3d8ff;
}

.msg-meta {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-bottom: 8px;
  font-size: 11px;
  color: #909399;
}

.msg-tokens {
  color: #909399;
  font-size: 11px;
}

.msg-speak {
  margin-left: auto;
  color: #909399;
}

.msg-speak:hover {
  color: #409eff;
}

.msg-actions {
  margin-left: auto;
  display: flex;
  gap: 2px;
  opacity: 0.6;
  transition: opacity 0.15s;
}
.msg-row:hover .msg-actions {
  opacity: 1;
}
.msg-action-btn {
  color: #909399;
  padding: 0 6px !important;
  min-height: 24px !important;
  height: 24px !important;
}
.msg-action-btn:hover {
  color: #409eff;
}
.user-actions {
  justify-content: flex-end;
  margin-top: 6px;
}
.role-user .msg-action-btn {
  color: #79bbff;
}
.role-user .msg-action-btn:hover {
  color: #1677ff;
}

.msg-body {
  font-size: 14px;
  line-height: 1.6;
  color: #303133;
  word-wrap: break-word;
}

.msg-body.user {
  white-space: pre-wrap;
}

.msg-user-text {
  margin-top: 6px;
}

.msg-attachments {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 4px;
}

.msg-att {
  border-radius: 6px;
  overflow: hidden;
  background: #fff;
  border: 1px solid #d9ecff;
}

.msg-att-img {
  display: block;
  max-width: 240px;
  max-height: 240px;
  object-fit: cover;
}

.msg-att-file {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  font-size: 12px;
  color: #606266;
}

.msg-att-name {
  font-weight: 500;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.msg-att-size {
  color: #909399;
}

/* Composer pending-attachment chips */
.pending-attachments {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}

.pending-att {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  background: #f4f4f5;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  max-width: 260px;
}

.pending-att-uploading {
  color: #909399;
  font-size: 12px;
}

.pending-att-img {
  width: 40px;
  height: 40px;
  object-fit: cover;
  border-radius: 4px;
  flex-shrink: 0;
}

.pending-att-file {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #ecf5ff;
  border-radius: 4px;
  color: #409eff;
  flex-shrink: 0;
}

.pending-att-meta {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1;
}

.pending-att-name {
  font-size: 12px;
  font-weight: 500;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pending-att-size {
  font-size: 11px;
  color: #909399;
}

.pending-att-remove {
  color: #909399;
}
.pending-att-remove:hover {
  color: #f56c6c;
}

/* Markdown rendering styles */
.msg-body.markdown :deep(p) {
  margin: 0 0 8px 0;
}
.msg-body.markdown :deep(p:last-child) { margin-bottom: 0; }
.msg-body.markdown :deep(pre) {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12.5px;
  line-height: 1.5;
}
.msg-body.markdown :deep(code) {
  background: #f4f4f5;
  color: #c7254e;
  padding: 1px 5px;
  border-radius: 3px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12.5px;
}
.msg-body.markdown :deep(pre code) {
  background: transparent;
  color: inherit;
  padding: 0;
  border-radius: 0;
}
.msg-body.markdown :deep(ul),
.msg-body.markdown :deep(ol) {
  margin: 4px 0 8px 20px;
  padding: 0;
}
.msg-body.markdown :deep(h1),
.msg-body.markdown :deep(h2),
.msg-body.markdown :deep(h3) {
  margin: 12px 0 6px 0;
  font-weight: 600;
}
.msg-body.markdown :deep(h1) { font-size: 18px; }
.msg-body.markdown :deep(h2) { font-size: 16px; }
.msg-body.markdown :deep(h3) { font-size: 14px; }
.msg-body.markdown :deep(blockquote) {
  margin: 4px 0;
  padding: 6px 12px;
  border-left: 3px solid #dcdfe6;
  background: #fafafa;
  color: #606266;
}
.msg-body.markdown :deep(table) {
  border-collapse: collapse;
  margin: 8px 0;
}
.msg-body.markdown :deep(th),
.msg-body.markdown :deep(td) {
  border: 1px solid #e4e7ed;
  padding: 4px 8px;
  font-size: 13px;
}
.msg-body.markdown :deep(th) {
  background: #f4f4f5;
}

/* ── Composer ────────────────────────────────── */
.composer {
  border-top: 1px solid #e4e7ed;
  padding: 12px 24px;
  background: #ffffff;
}

.composer-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 8px;
}

.composer-hint {
  font-size: 12px;
  color: #909399;
}

.composer-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.rec-status {
  font-size: 12px;
  color: #f56c6c;
  font-weight: 500;
}

/* ── Settings drawer ─────────────────────────── */
.settings-form {
  padding: 0 4px;
}

.voice-section {
  padding: 8px 4px 0 4px;
}

.wake-section {
  padding: 8px 4px 0 4px;
}

/* ── Knowledge Base section ─────────────────── */
.kb-section {
  padding: 8px 4px 0 4px;
}

.kb-add-row {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-bottom: 12px;
}

.kb-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.kb-item {
  padding: 10px 12px;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.kb-item.kb-disabled {
  opacity: 0.6;
}

.kb-item-info {
  flex: 1;
  min-width: 0;
}

.kb-item-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.kb-item-name {
  font-weight: 600;
  color: #303133;
}

.kb-item-path {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
  color: #909399;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-top: 4px;
}

.kb-item-meta {
  font-size: 11px;
  color: #909399;
  margin-top: 4px;
}

.kb-item-warning {
  color: #e6a23c;
}

.kb-item-actions {
  display: flex;
  gap: 6px;
  align-items: center;
  flex-shrink: 0;
}

.settings-hint {
  margin-top: 6px;
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
}

.settings-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.settings-footer-right {
  display: flex;
  gap: 8px;
}
</style>
