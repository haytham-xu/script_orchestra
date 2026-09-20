import { createRouter, createWebHistory } from 'vue-router'
import { BACKEND_BASE_URL, ENABLED_TOOLS_ENDPOINT } from '@/basic/Constants'

import OrchestraView from '@/dashboard/views/OrchestraView.vue'
import MangaClassifierView from '@/manga_classifier/views/MangaClassifierView.vue'
import MangaClassifierSettingsView from '@/manga_classifier/views/SettingsView.vue'
import PCDashboardView from '@/photo_classifier/views/PCDashboardView.vue'
import PCDefaultGroupView from '@/photo_classifier/views/PCDefaultGroupView.vue'
import PCGroupView from '@/photo_classifier/views/PCGroupView.vue'
import PCBatchSelectView from '@/photo_classifier/views/PCBatchSelectView.vue'
import PCGroupBatchView from '@/photo_classifier/views/PCGroupBatchView.vue'
import DuplicateFinderView from '@/duplicate_finder/views/DuplicateFinderView.vue'
import VideoDuplicateFinderView from '@/video-duplicate-finder/views/VideoDuplicateFinderView.vue'
import MangaViewerView from '@/manga_viwer/views/MangaViewerView.vue'
import MangaViewerRandomView from '@/manga_viwer/views/RandomView.vue'
import MangaViewerSettingsView from '@/manga_viwer/views/SettingsView.vue'
import MangaViewerBatchView from '@/manga_viwer/views/BatchOperationView.vue'
import MangaViewerHubView from '@/manga_viwer/views/MangaViewerHubView.vue'
import MangaImportView from '@/manga_viwer/views/MangaImportView.vue'
import ReadQueueView from '@/manga_viwer/views/ReadQueueView.vue'
import SnoozeQueueView from '@/manga_viwer/views/SnoozeQueueView.vue'
import SeriesGrouperView from '@/manga_viwer/views/SeriesGrouperView.vue'
import SeriesGrouperSettingsView from '@/manga_viwer/views/SeriesGrouperSettingsView.vue'
import RoadmapView from '@/roadmap/views/RoadmapView.vue'
import PdfConverterView from '@/pdf_converter/views/PdfConverterView.vue'
import UnzipView from '@/unzip/views/UnzipView.vue'
import ClipboardShareView from '@/clipboard_share/views/ClipboardShareView.vue'
import CaffeinateView from '@/caffeinate/views/CaffeinateView.vue'
import BrowserAgentHubView from '@/browser_agent/views/BrowserAgentHubView.vue'
import TabsView from '@/browser_agent/views/TabsView.vue'
import TabDedupView from '@/browser_agent/views/TabDedupView.vue'
import DownloadSSMHView from '@/browser_agent/views/DownloadSSMHView.vue'
import DownloadJMView from '@/browser_agent/views/DownloadJMView.vue'
import MemoryCurveView from '@/memory_curve/views/MemoryCurveView.vue'
import KnowledgeVaultView from '@/knowledge_vault/views/KnowledgeVaultView.vue'
import TranslatorView from '@/translator/views/TranslatorView.vue'
import ClaudeBridgeChatView from '@/claude_bridge/views/ChatView.vue'
import ClaudeBridgeTerminalView from '@/claude_bridge/views/TerminalView.vue'
import AssistantView from '@/assistant/views/AssistantView.vue'
import FileGitReposView from '@/file_git/views/FileGitReposView.vue'
import FileGitSettingsView from '@/file_git/views/FileGitSettingsView.vue'
import FileGitRepoDetailView from '@/file_git/views/FileGitRepoDetailView.vue'
import FileGitRepoSettingsView from '@/file_git/views/FileGitRepoSettingsView.vue'
import FileGitRepoManualView from '@/file_git/views/FileGitRepoManualView.vue'
import FileGitRepoSyncFilterView from '@/file_git/views/FileGitRepoSyncFilterView.vue'
import ProxyForwardView from '@/proxy_forward/views/ProxyForwardView.vue'
import RelayProxyView from '@/relay_proxy/views/RelayProxyView.vue'
import CleanKeywordView from '@/clean_keyword/views/CleanKeywordView.vue'
import LoansCalcView from '@/loans_calc/views/LoansCalcView.vue'
import CompressImageView from '@/compress_image/views/CompressImageView.vue'
import DedupFolderView from '@/dedup_folder/views/DedupFolderView.vue'
import FilePipelineView from '@/file_pipeline/views/FilePipelineView.vue'
import FileTrackerView from '@/file_tracker/views/FileTrackerView.vue'
import FileTrackerSettingsView from '@/file_tracker/views/FileTrackerSettingsView.vue'
import ApprenticeView from '@/apprentice/views/ApprenticeView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', name: 'dashboard', component: OrchestraView },

    { path: '/manga-classifier', name: 'manga-classifier', component: MangaClassifierView },
    { path: '/manga-classifier/settings', name: 'manga-classifier-settings', component: MangaClassifierSettingsView },

    { path: '/photo-classifier', name: 'photo-classifier', component: PCDashboardView },
    { path: '/photo-classifier/batch-select', name: 'photo-classifier-batch-select', component: PCBatchSelectView },
    { path: '/photo-classifier/default-group', name: 'photo-classifier-default', component: PCDefaultGroupView },
    {
      path: '/photo-classifier/group/:groupId', name: 'photo-classifier-group',
      component: PCGroupView,
      props: (route) => ({ groupId: Number(route.params.groupId) }),
    },
    {
      path: '/photo-classifier/group/:groupId/batch', name: 'photo-classifier-group-batch',
      component: PCGroupBatchView,
      props: (route) => ({ groupId: Number(route.params.groupId) }),
    },

    { path: '/manga-viewer', name: 'manga-viewer', component: MangaViewerView },
    { path: '/manga-viewer/random', name: 'manga-viewer-random', component: MangaViewerRandomView },
    { path: '/manga-viewer/settings', name: 'manga-viewer-settings', component: MangaViewerSettingsView },
    { path: '/manga-viewer/batch', name: 'manga-viewer-batch', component: MangaViewerHubView },
    { path: '/manga-viewer/batch/edit', name: 'manga-viewer-batch-edit', component: MangaViewerBatchView },
    { path: '/manga-viewer/import', name: 'manga-viewer-import', component: MangaImportView },
    { path: '/manga-viewer/read-queue', name: 'manga-viewer-read-queue', component: ReadQueueView },
    { path: '/manga-viewer/snooze-queue', name: 'manga-viewer-snooze-queue', component: SnoozeQueueView },
    { path: '/manga-viewer/series-grouper', name: 'manga-viewer-series-grouper', component: SeriesGrouperView },
    { path: '/manga-viewer/series-grouper/settings', name: 'manga-viewer-series-grouper-settings', component: SeriesGrouperSettingsView },

    { path: '/roadmap', name: 'roadmap', component: RoadmapView },
    { path: '/pdf-converter', name: 'pdf-converter', component: PdfConverterView },
    { path: '/unzip', name: 'unzip', component: UnzipView },
    { path: '/duplicate-finder', name: 'duplicate-finder', component: DuplicateFinderView },
    { path: '/video-duplicate-finder', name: 'video-duplicate-finder', component: VideoDuplicateFinderView },
    { path: '/clipboard-share', name: 'clipboard-share', component: ClipboardShareView },
    { path: '/caffeinate', name: 'caffeinate', component: CaffeinateView },

    { path: '/browser-agent', name: 'browser-agent', component: BrowserAgentHubView },
    { path: '/browser-agent/tabs', name: 'browser-agent-tabs', component: TabsView },
    { path: '/browser-agent/tab-dedup', name: 'browser-agent-tab-dedup', component: TabDedupView },
    { path: '/browser-agent/download-ssmh', name: 'browser-agent-download-ssmh', component: DownloadSSMHView },
    { path: '/browser-agent/download-jm', name: 'browser-agent-download-jm', component: DownloadJMView },

    { path: '/memory-curve', name: 'memory-curve', component: MemoryCurveView },
    { path: '/knowledge-vault', name: 'knowledge-vault', component: KnowledgeVaultView },
    { path: '/translator', name: 'translator', component: TranslatorView },
    { path: '/claude-bridge', name: 'claude-bridge', component: ClaudeBridgeChatView },
    { path: '/claude-bridge/terminal', name: 'claude-bridge-terminal', component: ClaudeBridgeTerminalView },
    { path: '/assistant', name: 'assistant', component: AssistantView },

    { path: '/file-git', name: 'file-git', component: FileGitReposView },
    { path: '/file-git/settings', name: 'file-git-settings', component: FileGitSettingsView },
    { path: '/file-git/:id', name: 'file-git-detail', component: FileGitRepoDetailView },
    { path: '/file-git/:id/settings', name: 'file-git-repo-settings', component: FileGitRepoSettingsView },
    { path: '/file-git/:id/manual', name: 'file-git-repo-manual', component: FileGitRepoManualView },
    { path: '/file-git/:id/sync-filter', name: 'file-git-repo-sync-filter', component: FileGitRepoSyncFilterView },

    { path: '/proxy-forward', name: 'proxy-forward', component: ProxyForwardView },
    { path: '/relay-proxy', name: 'relay-proxy', component: RelayProxyView },
    { path: '/clean-keyword', name: 'clean-keyword', component: CleanKeywordView },
    { path: '/loans-calc', name: 'loans-calc', component: LoansCalcView },
    { path: '/compress-image', name: 'compress-image', component: CompressImageView },
    { path: '/dedup-folder', name: 'dedup-folder', component: DedupFolderView },
    { path: '/file-pipeline', name: 'file-pipeline', component: FilePipelineView },
    { path: '/file-tracker', name: 'file-tracker', component: FileTrackerView },
    { path: '/file-tracker/settings', name: 'file-tracker-settings', component: FileTrackerSettingsView },
    { path: '/apprentice', name: 'apprentice', component: ApprenticeView },
  ],
})

export default router

// All known tool keys — used by dashboard and the nav guard below.
export const ALL_TOOL_KEYS = [
  'manga-classifier', 'photo-classifier', 'manga-viewer', 'roadmap', 'pdf-converter',
  'unzip', 'duplicate-finder', 'video-duplicate-finder', 'clipboard-share', 'caffeinate',
  'browser-agent', 'memory-curve', 'knowledge-vault', 'translator', 'claude-bridge',
  'assistant', 'file-git', 'proxy-forward', 'relay-proxy', 'clean-keyword',
  'loans-calc', 'compress-image', 'dedup-folder', 'file-pipeline', 'file-tracker',
  'apprentice',
]

// Navigation guard: redirect to dashboard when navigating to a disabled tool,
// preventing the view from mounting and hitting 404 backend endpoints.
// The enabled set is fetched once at first navigation and cached for the session.
let _enabledCache: Set<string> | null = null
let _enabledPending: Promise<Set<string>> | null = null

function fetchEnabledOnce(): Promise<Set<string>> {
  if (_enabledCache) return Promise.resolve(_enabledCache)
  if (_enabledPending) return _enabledPending
  _enabledPending = fetch(`${BACKEND_BASE_URL}${ENABLED_TOOLS_ENDPOINT}`)
    .then(r => r.json())
    .then(d => { _enabledCache = new Set<string>(Array.isArray(d.enabled) ? d.enabled : []); return _enabledCache })
    .catch(() => { _enabledCache = new Set(); return _enabledCache })
  return _enabledPending
}

const _allToolKeySet = new Set(ALL_TOOL_KEYS)

router.beforeEach(async (to) => {
  if (to.path === '/') return true
  const segment = to.path.replace(/^\//, '').split('/')[0]
  if (!_allToolKeySet.has(segment)) return true
  const enabled = await fetchEnabledOnce()
  if (!enabled.has(segment)) return '/'
  return true
})
