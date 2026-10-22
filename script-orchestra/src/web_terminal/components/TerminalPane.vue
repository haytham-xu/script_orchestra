<template>
  <div ref="containerEl" class="terminal-pane" />
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { Terminal, type ITheme } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'
import type { WebTerminalWsService } from '../service/WebTerminalWsService'
import type { WtEvent } from '../service/Model'

interface Props {
  windowId: string
  wsService: WebTerminalWsService
  initialScrollback?: string
  theme?: Partial<ITheme>
  fontSize?: number
}

const props = withDefaults(defineProps<Props>(), {
  initialScrollback: '',
  fontSize: 13,
})

const emit = defineEmits<{ ready: [cols: number, rows: number] }>()

const containerEl = ref<HTMLElement | null>(null)

let term: Terminal | null = null
let fit: FitAddon | null = null
let ro: ResizeObserver | null = null

function buildTerm(): Terminal {
  return new Terminal({
    cursorBlink: true,
    fontSize: props.fontSize,
    fontFamily: 'Menlo, Monaco, "Courier New", monospace',
    theme: {
      background: '#1e1e1e',
      foreground: '#d4d4d4',
      cursor: '#d4d4d4',
      selectionBackground: '#264f78',
      ...props.theme,
    },
    scrollback: 5000,
    allowProposedApi: true,
  })
}

function sendResize() {
  if (term && props.windowId) {
    props.wsService.sendResize(props.windowId, term.cols, term.rows)
  }
}

function onWtEvent(e: WtEvent) {
  if (e.window_id !== props.windowId) return
  if (e.event === 'wt_output' && e.data != null) {
    term?.write(e.data)
  } else if (e.event === 'wt_exit') {
    term?.write('\r\n\x1b[90m[process exited — press Enter to restart]\x1b[0m\r\n')
  }
}

function mount() {
  if (!containerEl.value) return
  term?.dispose()

  term = buildTerm()
  fit = new FitAddon()
  term.loadAddon(fit)
  term.open(containerEl.value)

  if (props.initialScrollback) {
    term.write(props.initialScrollback)
  }

  term.onData((d) => {
    props.wsService.sendInput(props.windowId, d)
  })

  // Wait two animation frames: first lets the browser paint the container at
  // its real size, second ensures FitAddon reads stable dimensions.
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      fit?.fit()
      sendResize()
      emit('ready', term?.cols ?? 80, term?.rows ?? 24)
      term?.focus()

      // Track future resize events (window resize, split pane, etc.)
      if (containerEl.value) {
        ro = new ResizeObserver(() => {
          fit?.fit()
          sendResize()
        })
        ro.observe(containerEl.value)
      }
    })
  })
}

onMounted(() => {
  props.wsService.onEvent(onWtEvent)
  mount()
})

onBeforeUnmount(() => {
  props.wsService.offEvent(onWtEvent)
  ro?.disconnect()
  term?.dispose()
  term = null
})

defineExpose({ focus: () => term?.focus() })
</script>

<style scoped>
.terminal-pane {
  width: 100%;
  height: 100%;
  min-height: 0;
  background: #1e1e1e;
  padding: 4px 6px;
  box-sizing: border-box;
  overflow: hidden;
}
</style>
