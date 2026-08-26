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
import AssistantView from '@/assistant/views/AssistantView.vue'
import FileGitReposView from '@/file_git/views/FileGitReposView.vue'
import FileGitRepoDetailView from '@/file_git/views/FileGitRepoDetailView.vue'
import FileGitSettingsView from '@/file_git/views/FileGitSettingsView.vue'

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
      path: '/browser-agent',
      name: 'browser-agent',
      component: BrowserAgentView
    },
    {
      path: '/assistant',
      name: 'assistant',
      component: AssistantView
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
  ],
})

export default router
