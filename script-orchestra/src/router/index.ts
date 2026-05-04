import { createRouter, createWebHistory } from 'vue-router'
import DashboardView from '@/dashboard/views/OrchestraView.vue'
import MangaClassifierView from '@/manga_classifier/views/MangaClassifierView.vue'
import PCDashboardView from '@/photo_classifier/views/PCDashboardView.vue'
import PCDefaultGroupView from '@/photo_classifier/views/PCDefaultGroupView.vue'
import PCGroupView from '@/photo_classifier/views/PCGroupView.vue'
import PCBatchSelectView from '@/photo_classifier/views/PCBatchSelectView.vue'
import PCGroupBatchView from '@/photo_classifier/views/PCGroupBatchView.vue'
import MangaViewerView from '@/manga_viwer/views/MangaViewerView.vue'
import RoadmapView from '@/roadmap/views/RoadmapView.vue'
import PdfConverterView from '@/pdf_converter/views/PdfConverterView.vue'
import UnzipView from '@/unzip/views/UnzipView.vue'
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
      props: true,
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
