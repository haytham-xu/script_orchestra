import { createRouter, createWebHistory } from 'vue-router'
// import HomeView from '../views/HomeView.vue'
import DashboardView from '@/dashboard/views/OrchestraView.vue'
import MangaClassifierView from '@/manga_classifier/views/MangaClassifierView.vue'
import PhotoClassifierView from '@/photo_classifier/views/DashboardView.vue'

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
      component: PhotoClassifierView,
    },
  ],
})

export default router
