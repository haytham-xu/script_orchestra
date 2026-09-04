<template>
  <div class="fg-repos">
    <header class="fg-topbar">
      <div class="fg-topbar-left">
        <el-button @click="$router.push('/')" circle size="small"><el-icon><ArrowLeft /></el-icon></el-button>
        <h1>File-Git</h1>
        <p class="fg-sub">Repositories for git-style cloud backup</p>
      </div>
      <div class="fg-topbar-right">
        <el-button :icon="Setting" @click="goToSettings">Settings</el-button>
        <el-button :icon="FolderOpened" @click="openImportDialog">Import</el-button>
        <el-button :icon="Plus" type="primary" @click="openAddDialog">Add Repository</el-button>
      </div>
    </header>

    <main class="fg-content" v-loading="isLoading">
      <div v-if="!hasRepos && !isLoading" class="fg-empty">
        <el-empty description="No repositories yet">
          <el-button type="primary" @click="openAddDialog">Add Your First Repository</el-button>
        </el-empty>
      </div>

      <div v-else class="fg-grid">
        <el-card
          v-for="repo in repos"
          :key="repo.id"
          class="fg-repo-card"
          shadow="hover"
          @click="goToRepo(repo.id)">
          <div class="fg-repo-head">
            <div class="fg-repo-name">
              <el-icon><FolderOpened /></el-icon>
              <span>{{ repo.name }}</span>
            </div>
            <div class="fg-repo-actions" @click.stop>
              <el-button :icon="FolderOpened" circle size="small"
                         @click="openFolder(repo.id)" title="Open folder" />
              <el-button :icon="Delete" circle size="small" type="danger"
                         @click="openDeleteDialog(repo)" title="Delete" />
            </div>
          </div>

          <dl class="fg-repo-meta">
            <dt>Path</dt>
            <dd class="mono">{{ repo.local_path }}</dd>

            <dt>Mode</dt>
            <dd>
              <el-tag :type="repo.mode === 'ENCRYPTED' ? 'success' : 'info'" size="small">
                {{ repo.mode || 'unknown' }}
              </el-tag>
            </dd>

            <dt>Status</dt>
            <dd>
              <el-tag
                :type="statusColor(repo.status)"
                size="small">
                {{ repo.status || 'unknown' }}
              </el-tag>
            </dd>

            <dt>Updated</dt>
            <dd class="mono">{{ formatTime(repo.last_updated) }}</dd>
          </dl>
        </el-card>
      </div>
    </main>

    <!-- Add dialog -->
    <el-dialog v-model="showAddDialog" title="Add Repository" width="480">
      <el-form label-position="top">
        <el-form-item label="Local path (absolute)">
          <el-input v-model="newRepoPath" placeholder="/absolute/path/to/folder" />
        </el-form-item>
        <el-form-item label="Mode (cannot be changed later)">
          <el-radio-group v-model="newRepoMode">
            <el-radio-button label="ORIGINAL">ORIGINAL (plaintext)</el-radio-button>
            <el-radio-button label="ENCRYPTED">ENCRYPTED (AES-256-GCM)</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <p class="fg-hint">
          Password and remote path are configured after creation in the
          repo detail page.
        </p>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">Cancel</el-button>
        <el-button type="primary" @click="addRepo">Create</el-button>
      </template>
    </el-dialog>

    <!-- Import dialog -->
    <el-dialog v-model="showImportDialog" title="Import Existing Repository" width="480">
      <el-form label-position="top">
        <el-form-item label="Local path (must contain .fgit/)">
          <el-input v-model="importRepoPath" placeholder="/absolute/path/to/folder" />
        </el-form-item>
        <p class="fg-hint">Mode is read from the existing .fgit/config.json.</p>
      </el-form>
      <template #footer>
        <el-button @click="showImportDialog = false">Cancel</el-button>
        <el-button type="primary" @click="importRepo">Import</el-button>
      </template>
    </el-dialog>

    <!-- Delete dialog -->
    <el-dialog v-model="showDeleteDialog" title="Delete Repository" width="480">
      <p>
        This removes the repo from the registry AND deletes its
        <code>.fgit/</code> folder. Files in the working tree are NOT touched.
      </p>
      <p>Type <b>{{ deleteRepoName }}</b> to confirm:</p>
      <el-input v-model="deleteConfirmInput" placeholder="repository name" />
      <template #footer>
        <el-button @click="showDeleteDialog = false">Cancel</el-button>
        <el-button
          type="danger"
          :disabled="deleteConfirmInput !== deleteRepoName"
          @click="confirmDelete">
          Delete
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script lang="ts" setup>
import { useFileGitReposView } from './FileGitReposView'
import { FolderOpened, Setting, Plus, Delete } from '@element-plus/icons-vue'

const {
  repos, hasRepos, isLoading,
  showAddDialog, showImportDialog, showDeleteDialog,
  newRepoPath, newRepoMode, importRepoPath, deleteRepoName, deleteConfirmInput,
  openAddDialog, addRepo, openImportDialog, importRepo,
  openDeleteDialog, confirmDelete, openFolder, goToRepo, goToSettings,
} = useFileGitReposView()

function statusColor(status: string) {
  if (status === 'ready') return 'success'
  if (status === 'syncing') return 'warning'
  if (status === 'locked') return 'warning'
  return 'danger'
}

function formatTime(iso: string) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}
</script>

<style scoped>
.fg-repos {
  min-height: 100vh;
  background: #f5f5f7;
  color: #1d1d1f;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
}

.fg-topbar {
  position: sticky;
  top: 0;
  z-index: 10;
  background: rgba(245, 245, 247, 0.85);
  backdrop-filter: saturate(180%) blur(20px);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  padding: 16px 24px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}

.fg-topbar-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.fg-topbar-left h1 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}

.fg-sub {
  margin: 2px 0 0;
  font-size: 12px;
  color: #86868b;
}

.fg-topbar-right {
  display: flex;
  gap: 8px;
}

.fg-content {
  max-width: 1100px;
  margin: 0 auto;
  padding: 24px;
}

.fg-empty {
  padding: 60px 20px;
  display: flex;
  justify-content: center;
}

.fg-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}

.fg-repo-card {
  border-radius: 12px;
  cursor: pointer;
  transition: transform 0.12s;
}
.fg-repo-card:hover {
  transform: translateY(-1px);
}

.fg-repo-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.fg-repo-name {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  font-size: 15px;
}
.fg-repo-actions {
  display: flex;
  gap: 4px;
}

.fg-repo-meta {
  display: grid;
  grid-template-columns: 60px 1fr;
  row-gap: 4px;
  column-gap: 8px;
  margin: 0;
  font-size: 12px;
}
.fg-repo-meta dt {
  color: #86868b;
}
.fg-repo-meta dd {
  margin: 0;
  color: #1d1d1f;
}
.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  word-break: break-all;
}

.fg-hint {
  font-size: 12px;
  color: #86868b;
  margin: 8px 0 0;
}
</style>
