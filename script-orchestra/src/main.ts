
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import { createToolRouter } from './router'
import { BACKEND_BASE_URL, ENABLED_TOOLS_ENDPOINT } from './basic/Constants'
import '@/assets/main.css'

import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

// Virtual Scroller for large lists
import 'vue-virtual-scroller/dist/vue-virtual-scroller.css'

// One-time cleanup: the app used to ship a PWA service worker (vite-plugin-pwa),
// which aggressively cached the app shell and caused stale pages that survived
// hard refresh (and could affect other localhost sites). PWA is now removed;
// proactively unregister any leftover service worker and drop its caches so
// clients that visited the PWA build recover without manual DevTools steps.
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.getRegistrations().then((regs) => {
    regs.forEach((r) => r.unregister())
  }).catch(() => { /* ignore */ })
  if ('caches' in window && typeof caches.keys === 'function') {
    caches.keys().then((keys) => keys.forEach((k) => caches.delete(k))).catch(() => { /* ignore */ })
  }
}

async function bootstrap() {
  let enabled: Set<string> = new Set()
  try {
    const res = await fetch(`${BACKEND_BASE_URL}${ENABLED_TOOLS_ENDPOINT}`)
    const data = await res.json()
    if (Array.isArray(data.enabled)) {
      enabled = new Set(data.enabled)
    }
  } catch {
    // Backend unreachable on load — no tools enabled (default: all disabled)
  }

  const app = createApp(App)
  app.use(createPinia())
  app.use(createToolRouter(enabled))

  app.use(ElementPlus, {
    message: {
      offset: 20,
      duration: 1500
    }
  })
  for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
    app.component(key, component)
  }

  app.mount('#app')
}

bootstrap()
