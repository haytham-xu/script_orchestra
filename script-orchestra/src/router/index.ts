import { createRouter, createWebHistory } from 'vue-router'
// import HomeView from '../views/HomeView.vue'
import DashboardView from '@/dashboard/views/OrchestraView.vue'
import MangaClassifierView from '@/manga_classifier/views/MangaClassifierView.vue'
import PCDashboardView from '@/photo_classifier/views/PCDashboardView.vue'
import PCDefaultGroupView from '@/photo_classifier/views/PCDefaultGroupView.vue'
import PCGroupView from '@/photo_classifier/views/PCGroupView.vue'

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
      path: '/photo-classifier/default-group',
      name: 'photo-classifier-default',
      component: PCDefaultGroupView
    },
    {
      path: '/photo-classifier/group/:groupId',
      name: 'photo-classifier-group',
      component: PCGroupView,
      props: true,
    }
  ],
})

export default router
