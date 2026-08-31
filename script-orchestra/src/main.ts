
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
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
  if (window.caches?.keys) {
    caches.keys().then((keys) => keys.forEach((k) => caches.delete(k))).catch(() => { /* ignore */ })
  }
}

const app = createApp(App)
app.use(createPinia())
app.use(router)

app.use(ElementPlus, {
  message: {
    offset: 20,
    duration: 1500,
    customClass: 'message-bottom'
  }
})
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.mount('#app')
