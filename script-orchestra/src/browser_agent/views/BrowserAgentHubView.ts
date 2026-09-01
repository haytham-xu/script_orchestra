import { defineComponent, computed } from 'vue'
import { useRouter } from 'vue-router'

// One entry per tool exposed under /browser-agent/*. Icons are inline SVG,
// following the same convention as the top-level dashboard so both feel
// visually consistent.
interface Tool {
  key: string
  name: string
  path: string
  icon: string
}

const TOOLS: Tool[] = [
  {
    key: 'tabs',
    name: 'All Tabs',
    path: '/browser-agent/tabs',
    icon: `
      <svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
        <rect x="4" y="4" width="56" height="56" rx="14" fill="#2563eb"/>
        <rect x="10" y="18" width="44" height="6" rx="2" fill="#fff"/>
        <rect x="10" y="29" width="44" height="6" rx="2" fill="#bfdbfe"/>
        <rect x="10" y="40" width="44" height="6" rx="2" fill="#93c5fd"/>
      </svg>`,
  },
  {
    key: 'tab-dedup',
    name: 'Tab Dedup',
    path: '/browser-agent/tab-dedup',
    icon: `
      <svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
        <rect x="4" y="4" width="56" height="56" rx="14" fill="#0891b2"/>
        <rect x="10" y="16" width="30" height="20" rx="3" fill="#fff"/>
        <rect x="20" y="26" width="30" height="20" rx="3" fill="#a5f3fc"/>
        <path d="M43 40l6 6M49 40l-6 6" stroke="#0e7490" stroke-width="3" stroke-linecap="round"/>
      </svg>`,
  },
  {
    key: 'download-ssmh',
    name: 'Download SSMH',
    path: '/browser-agent/download-ssmh',
    icon: `
      <svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
        <rect x="4" y="4" width="56" height="56" rx="14" fill="#7c3aed"/>
        <rect x="14" y="14" width="24" height="6" rx="1" fill="#fff"/>
        <rect x="14" y="24" width="24" height="6" rx="1" fill="#c4b5fd"/>
        <path d="M44 18v14M38 26l6 6 6-6" stroke="#fff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
        <rect x="14" y="42" width="36" height="6" rx="2" fill="#ddd6fe"/>
      </svg>`,
  },
  {
    key: 'download-jm',
    name: 'Download JM',
    path: '/browser-agent/download-jm',
    icon: `
      <svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
        <rect x="4" y="4" width="56" height="56" rx="14" fill="#db2777"/>
        <circle cx="32" cy="26" r="8" fill="none" stroke="#fff" stroke-width="3"/>
        <path d="M32 20v6M32 26h4" stroke="#fff" stroke-width="2.5" stroke-linecap="round"/>
        <path d="M20 44v14M32 40v18M44 44v14" stroke="#fff" stroke-width="3" stroke-linecap="round"/>
        <rect x="12" y="52" width="40" height="6" rx="2" fill="#fbcfe8"/>
      </svg>`,
  },
  {
    key: 'captcha-trainer',
    name: 'Captcha Trainer',
    path: '/browser-agent/captcha-trainer',
    icon: `
      <svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
        <rect x="4" y="4" width="56" height="56" rx="14" fill="#f97316"/>
        <text x="18" y="28" fill="#fff" font-family="monospace" font-size="16" font-weight="bold">7+2</text>
        <path d="M12 36h40" stroke="#fed7aa" stroke-width="2"/>
        <path d="M22 44l6 6 14-14" stroke="#fff" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
      </svg>`,
  },
  {
    key: 'downloads',
    name: 'Download Queue',
    path: '/browser-agent/downloads',
    icon: `
      <svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
        <rect x="4" y="4" width="56" height="56" rx="14" fill="#0284c7"/>
        <path d="M32 14v24" stroke="#fff" stroke-width="4" stroke-linecap="round"/>
        <path d="M22 30l10 10 10-10" stroke="#fff" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
        <rect x="14" y="44" width="36" height="6" rx="2" fill="#bae6fd"/>
      </svg>`,
  },
  {
    key: 'settings',
    name: 'Settings',
    path: '/browser-agent/settings',
    icon: `
      <svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
        <rect x="4" y="4" width="56" height="56" rx="14" fill="#64748b"/>
        <circle cx="32" cy="32" r="8" fill="none" stroke="#fff" stroke-width="4"/>
        <g stroke="#fff" stroke-width="4" stroke-linecap="round">
          <path d="M32 12v6"/><path d="M32 46v6"/>
          <path d="M12 32h6"/><path d="M46 32h6"/>
          <path d="M18 18l4 4"/><path d="M42 42l4 4"/>
          <path d="M46 18l-4 4"/><path d="M22 42l-4 4"/>
        </g>
      </svg>`,
  },
]

export default defineComponent({
  name: 'BrowserAgentHubView',
  setup() {
    const router = useRouter()
    const tools = computed(() => TOOLS)
    function goTo(path: string) { router.push(path) }
    return { tools, goTo }
  }
})
