import { createRouter, createWebHistory } from 'vue-router'
import DashboardView from '@/dashboard/views/OrchestraView.vue'
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
import MangaImportView from '@/manga_viwer/views/MangaImportView.vue'
import RoadmapView from '@/roadmap/views/RoadmapView.vue'
import PdfConverterView from '@/pdf_converter/views/PdfConverterView.vue'
import UnzipView from '@/unzip/views/UnzipView.vue'
import ClipboardShareView from '@/clipboard_share/views/ClipboardShareView.vue'
import CaffeinateView from '@/caffeinate/views/CaffeinateView.vue'
import BrowserAgentView from '@/browser_agent/views/BrowserAgentView.vue'
import BrowserAgentSettingsView from '@/browser_agent/views/SettingsView.vue'
import BrowserAgentHubView from '@/browser_agent/views/BrowserAgentHubView.vue'
import TabsView from '@/browser_agent/views/TabsView.vue'
import TabDedupView from '@/browser_agent/views/TabDedupView.vue'
import DownloadSSMHView from '@/browser_agent/views/DownloadSSMHView.vue'
import DownloadJMView from '@/browser_agent/views/DownloadJMView.vue'
import CaptchaTrainerView from '@/browser_agent/views/CaptchaTrainerView.vue'
import MemoryCurveView from '@/memory_curve/views/MemoryCurveView.vue'
import KnowledgeVaultView from '@/knowledge_vault/views/KnowledgeVaultView.vue'
import TranslatorView from '@/translator/views/TranslatorView.vue'
import ClaudeBridgeView from '@/claude_bridge/views/ChatView.vue'
import ClaudeBridgeTerminalView from '@/claude_bridge/views/TerminalView.vue'
import AssistantView from '@/assistant/views/AssistantView.vue'
import FileGitReposView from '@/file_git/views/FileGitReposView.vue'
import FileGitRepoDetailView from '@/file_git/views/FileGitRepoDetailView.vue'
import FileGitRepoSettingsView from '@/file_git/views/FileGitRepoSettingsView.vue'
import FileGitSettingsView from '@/file_git/views/FileGitSettingsView.vue'
import ProxyForwardView from '@/proxy_forward/views/ProxyForwardView.vue'
import RelayProxyView from '@/relay_proxy/views/RelayProxyView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'dashboard',
      component: DashboardView,
    },
    {
      path: '/manga-classifier',
      name: 'manga-classifier',
      component: MangaClassifierView,
    },
    {
      path: '/manga-classifier/settings',
      name: 'manga-classifier-settings',
      component: MangaClassifierSettingsView,
    },
    {
      path: '/photo-classifier',
      name: 'photo-classifier',
      component: PCDashboardView,
    },
    {
      path: '/photo-classifier/batch-select',
      name: 'photo-classifier-batch-select',
      component: PCBatchSelectView
    },
    {
      path: '/photo-classifier/default-group',
      name: 'photo-classifier-default',
      component: PCDefaultGroupView
    },
    {
      path: '/photo-classifier/group/:groupId',
      name: 'photo-classifier-group',
      component: PCGroupView,
      props: (route) => ({ groupId: Number(route.params.groupId) }),
    },
    {
      path: '/photo-classifier/group/:groupId/batch',
      name: 'photo-classifier-group-batch',
      component: PCGroupBatchView,
      props: (route) => ({ groupId: Number(route.params.groupId) }),
    },
    {
      path: '/manga-viewer',
      name: 'manga-viewer',
      component: MangaViewerView
    },
    {
      // DEPRECATED: standalone Random page — hidden from the UI (entry button
      // commented out). Route kept so the page still works if reached directly.
      path: '/manga-viewer/random',
      name: 'manga-viewer-random',
      component: MangaViewerRandomView
    },
    {
      path: '/manga-viewer/settings',
      name: 'manga-viewer-settings',
      component: MangaViewerSettingsView
    },
    {
      path: '/manga-viewer/batch',
      name: 'manga-viewer-batch',
      component: MangaViewerBatchView
    },
    {
      // DEPRECATED: Import page — hidden from the UI (entry button commented
      // out). Route kept so the page still works if reached directly.
      path: '/manga-viewer/import',
      name: 'manga-viewer-import',
      component: MangaImportView
    },
    {
      path: '/roadmap',
      name: 'roadmap',
      component: RoadmapView
    },
    {
      path: '/pdf-converter',
      name: 'pdf-converter',
      component: PdfConverterView
    },
    {
      path: '/unzip',
      name: 'unzip',
      component: UnzipView
    },
    {
      path: '/duplicate-finder',
      name: 'duplicate-finder',
      component: DuplicateFinderView
    },
    {
      path: '/video-duplicate-finder',
      name: 'video-duplicate-finder',
      component: VideoDuplicateFinderView
    },
    {
      path: '/clipboard-share',
      name: 'clipboard-share',
      component: ClipboardShareView
    },
    {
      path: '/caffeinate',
      name: 'caffeinate',
      component: CaffeinateView
    },
    {
      path: '/browser-agent/settings',
      name: 'browser-agent-settings',
      component: BrowserAgentSettingsView
    },
    {
      path: '/browser-agent/tabs',
      name: 'browser-agent-tabs',
      component: TabsView
    },
    {
      path: '/browser-agent/tab-dedup',
      name: 'browser-agent-tab-dedup',
      component: TabDedupView
    },
    {
      path: '/browser-agent/download-ssmh',
      name: 'browser-agent-download-ssmh',
      component: DownloadSSMHView
    },
    {
      path: '/browser-agent/download-jm',
      name: 'browser-agent-download-jm',
      component: DownloadJMView
    },
    {
      path: '/browser-agent/captcha-trainer',
      name: 'browser-agent-captcha-trainer',
      component: CaptchaTrainerView
    },
    {
      path: '/browser-agent/downloads',
      name: 'browser-agent-downloads',
      component: BrowserAgentView
    },
    {
      path: '/browser-agent',
      name: 'browser-agent',
      component: BrowserAgentHubView
    },
    {
      path: '/memory-curve',
      name: 'memory-curve',
      component: MemoryCurveView
    },
    {
      path: '/knowledge-vault',
      name: 'knowledge-vault',
      component: KnowledgeVaultView
    },
    {
      path: '/translator',
      name: 'translator',
      component: TranslatorView
    },
    {
      path: '/claude-bridge',
      name: 'claude-bridge',
      component: ClaudeBridgeView
    },
    {
      path: '/claude-bridge/terminal',
      name: 'claude-bridge-terminal',
      component: ClaudeBridgeTerminalView
    },
    {
      path: '/assistant',
      name: 'assistant',
      component: AssistantView
    },
    {
      path: '/proxy-forward',
      name: 'proxy-forward',
      component: ProxyForwardView
    },
    {
      path: '/relay-proxy',
      name: 'relay-proxy',
      component: RelayProxyView
    },
    {
      path: '/file-git',
      name: 'file-git',
      component: FileGitReposView
    },
    {
      path: '/file-git/settings',
      name: 'file-git-settings',
      component: FileGitSettingsView
    },
    {
      path: '/file-git/:id',
      name: 'file-git-detail',
      component: FileGitRepoDetailView
    },
    {
      path: '/file-git/:id/settings',
      name: 'file-git-repo-settings',
      component: FileGitRepoSettingsView
    },
  ],
})

export default router
