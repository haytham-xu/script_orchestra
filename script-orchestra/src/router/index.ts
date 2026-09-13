import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

// Always-present routes (infrastructure, not tools)
const BASE_ROUTES: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'dashboard',
    component: () => import('@/dashboard/views/OrchestraView.vue'),
  },
]

// Tool routes grouped by tool key.
// Each tool key matches the kebab-case key used in backend/enabled_tools.json.
const TOOL_ROUTES: Record<string, RouteRecordRaw[]> = {
  'manga-classifier': [
    { path: '/manga-classifier', name: 'manga-classifier', component: () => import('@/manga_classifier/views/MangaClassifierView.vue') },
    { path: '/manga-classifier/settings', name: 'manga-classifier-settings', component: () => import('@/manga_classifier/views/SettingsView.vue') },
  ],
  'photo-classifier': [
    { path: '/photo-classifier', name: 'photo-classifier', component: () => import('@/photo_classifier/views/PCDashboardView.vue') },
    { path: '/photo-classifier/batch-select', name: 'photo-classifier-batch-select', component: () => import('@/photo_classifier/views/PCBatchSelectView.vue') },
    { path: '/photo-classifier/default-group', name: 'photo-classifier-default', component: () => import('@/photo_classifier/views/PCDefaultGroupView.vue') },
    {
      path: '/photo-classifier/group/:groupId', name: 'photo-classifier-group',
      component: () => import('@/photo_classifier/views/PCGroupView.vue'),
      props: (route) => ({ groupId: Number(route.params.groupId) }),
    },
    {
      path: '/photo-classifier/group/:groupId/batch', name: 'photo-classifier-group-batch',
      component: () => import('@/photo_classifier/views/PCGroupBatchView.vue'),
      props: (route) => ({ groupId: Number(route.params.groupId) }),
    },
  ],
  'manga-viewer': [
    { path: '/manga-viewer', name: 'manga-viewer', component: () => import('@/manga_viwer/views/MangaViewerView.vue') },
    { path: '/manga-viewer/random', name: 'manga-viewer-random', component: () => import('@/manga_viwer/views/RandomView.vue') },
    { path: '/manga-viewer/settings', name: 'manga-viewer-settings', component: () => import('@/manga_viwer/views/SettingsView.vue') },
    { path: '/manga-viewer/batch', name: 'manga-viewer-batch', component: () => import('@/manga_viwer/views/MangaViewerHubView.vue') },
    { path: '/manga-viewer/batch/edit', name: 'manga-viewer-batch-edit', component: () => import('@/manga_viwer/views/BatchOperationView.vue') },
    { path: '/manga-viewer/import', name: 'manga-viewer-import', component: () => import('@/manga_viwer/views/MangaImportView.vue') },
    { path: '/manga-viewer/read-queue', name: 'manga-viewer-read-queue', component: () => import('@/manga_viwer/views/ReadQueueView.vue') },
    { path: '/manga-viewer/snooze-queue', name: 'manga-viewer-snooze-queue', component: () => import('@/manga_viwer/views/SnoozeQueueView.vue') },
    { path: '/manga-viewer/series-grouper', name: 'manga-viewer-series-grouper', component: () => import('@/manga_viwer/views/SeriesGrouperView.vue') },
    { path: '/manga-viewer/series-grouper/settings', name: 'manga-viewer-series-grouper-settings', component: () => import('@/manga_viwer/views/SeriesGrouperSettingsView.vue') },
  ],
  'roadmap': [
    { path: '/roadmap', name: 'roadmap', component: () => import('@/roadmap/views/RoadmapView.vue') },
  ],
  'pdf-converter': [
    { path: '/pdf-converter', name: 'pdf-converter', component: () => import('@/pdf_converter/views/PdfConverterView.vue') },
  ],
  'unzip': [
    { path: '/unzip', name: 'unzip', component: () => import('@/unzip/views/UnzipView.vue') },
  ],
  'duplicate-finder': [
    { path: '/duplicate-finder', name: 'duplicate-finder', component: () => import('@/duplicate_finder/views/DuplicateFinderView.vue') },
  ],
  'video-duplicate-finder': [
    { path: '/video-duplicate-finder', name: 'video-duplicate-finder', component: () => import('@/video-duplicate-finder/views/VideoDuplicateFinderView.vue') },
  ],
  'clipboard-share': [
    { path: '/clipboard-share', name: 'clipboard-share', component: () => import('@/clipboard_share/views/ClipboardShareView.vue') },
  ],
  'caffeinate': [
    { path: '/caffeinate', name: 'caffeinate', component: () => import('@/caffeinate/views/CaffeinateView.vue') },
  ],
  'browser-agent': [
    { path: '/browser-agent', name: 'browser-agent', component: () => import('@/browser_agent/views/BrowserAgentHubView.vue') },
    { path: '/browser-agent/tabs', name: 'browser-agent-tabs', component: () => import('@/browser_agent/views/TabsView.vue') },
    { path: '/browser-agent/tab-dedup', name: 'browser-agent-tab-dedup', component: () => import('@/browser_agent/views/TabDedupView.vue') },
    { path: '/browser-agent/download-ssmh', name: 'browser-agent-download-ssmh', component: () => import('@/browser_agent/views/DownloadSSMHView.vue') },
    { path: '/browser-agent/download-jm', name: 'browser-agent-download-jm', component: () => import('@/browser_agent/views/DownloadJMView.vue') },
  ],
  'memory-curve': [
    { path: '/memory-curve', name: 'memory-curve', component: () => import('@/memory_curve/views/MemoryCurveView.vue') },
  ],
  'knowledge-vault': [
    { path: '/knowledge-vault', name: 'knowledge-vault', component: () => import('@/knowledge_vault/views/KnowledgeVaultView.vue') },
  ],
  'translator': [
    { path: '/translator', name: 'translator', component: () => import('@/translator/views/TranslatorView.vue') },
  ],
  'claude-bridge': [
    { path: '/claude-bridge', name: 'claude-bridge', component: () => import('@/claude_bridge/views/ChatView.vue') },
    { path: '/claude-bridge/terminal', name: 'claude-bridge-terminal', component: () => import('@/claude_bridge/views/TerminalView.vue') },
  ],
  'assistant': [
    { path: '/assistant', name: 'assistant', component: () => import('@/assistant/views/AssistantView.vue') },
  ],
  'file-git': [
    { path: '/file-git', name: 'file-git', component: () => import('@/file_git/views/FileGitReposView.vue') },
    { path: '/file-git/settings', name: 'file-git-settings', component: () => import('@/file_git/views/FileGitSettingsView.vue') },
    { path: '/file-git/:id', name: 'file-git-detail', component: () => import('@/file_git/views/FileGitRepoDetailView.vue') },
    { path: '/file-git/:id/settings', name: 'file-git-repo-settings', component: () => import('@/file_git/views/FileGitRepoSettingsView.vue') },
    { path: '/file-git/:id/manual', name: 'file-git-repo-manual', component: () => import('@/file_git/views/FileGitRepoManualView.vue') },
    { path: '/file-git/:id/sync-filter', name: 'file-git-repo-sync-filter', component: () => import('@/file_git/views/FileGitRepoSyncFilterView.vue') },
  ],
  'proxy-forward': [
    { path: '/proxy-forward', name: 'proxy-forward', component: () => import('@/proxy_forward/views/ProxyForwardView.vue') },
  ],
  'relay-proxy': [
    { path: '/relay-proxy', name: 'relay-proxy', component: () => import('@/relay_proxy/views/RelayProxyView.vue') },
  ],
  'clean-keyword': [
    { path: '/clean-keyword', name: 'clean-keyword', component: () => import('@/clean_keyword/views/CleanKeywordView.vue') },
  ],
  'loans-calc': [
    { path: '/loans-calc', name: 'loans-calc', component: () => import('@/loans_calc/views/LoansCalcView.vue') },
  ],
  'compress-image': [
    { path: '/compress-image', name: 'compress-image', component: () => import('@/compress_image/views/CompressImageView.vue') },
  ],
  'dedup-folder': [
    { path: '/dedup-folder', name: 'dedup-folder', component: () => import('@/dedup_folder/views/DedupFolderView.vue') },
  ],
  'file-pipeline': [
    { path: '/file-pipeline', name: 'file-pipeline', component: () => import('@/file_pipeline/views/FilePipelineView.vue') },
  ],
  'file-tracker': [
    { path: '/file-tracker', name: 'file-tracker', component: () => import('@/file_tracker/views/FileTrackerView.vue') },
    { path: '/file-tracker/settings', name: 'file-tracker-settings', component: () => import('@/file_tracker/views/FileTrackerSettingsView.vue') },
  ],
  'apprentice': [
    { path: '/apprentice', name: 'apprentice', component: () => import('@/apprentice/views/ApprenticeView.vue') },
  ],
}

/**
 * Create the app router.
 * @param enabled - Set of enabled tool keys. Empty set = all disabled.
 */
export function createToolRouter(enabled: Set<string>) {
  const routes: RouteRecordRaw[] = [...BASE_ROUTES]
  for (const [key, toolRoutes] of Object.entries(TOOL_ROUTES)) {
    if (enabled.has(key)) {
      routes.push(...toolRoutes)
    }
  }
  return createRouter({
    history: createWebHistory(import.meta.env.BASE_URL),
    routes,
  })
}

// All known tool keys — exported for dashboard use
export const ALL_TOOL_KEYS = Object.keys(TOOL_ROUTES)
