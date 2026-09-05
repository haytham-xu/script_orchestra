import { defineComponent, ref, computed, onMounted, watch, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  closeTabs,
  groupTabsByDomain,
  mergeTabs,
  tabArchiveCreateLabel,
  tabArchiveDeleteRecord,
  tabArchiveHealthCheckCancel,
  tabArchiveHealthCheckStart,
  tabArchiveHealthCheckStatus,
  tabArchiveListLabels,
  tabArchiveRestore,
  tabArchiveSafePreview,
  tabArchiveSafeRun,
  tabArchiveSelected,
  tabArchiveSetRecordLabels,
  tabArchiveSnapshot,
  tabArchiveUpdateRecord,
  tabArchiveReplaceUrl,
} from '@/browser_agent/service/BrowserAgentService'
import type {
  HeatLevel,
  TabArchiveLabel,
  TabArchiveHealthCheckJob,
  TabArchiveSortBy,
  TabArchiveSortOrder,
  TabArchiveLiveCard,
  TabArchiveRecord,
  TabArchiveRestoreResultRow,
  TabArchiveSafePreview,
  TabArchiveReplaceUrlPreviewRow,
} from '@/browser_agent/service/Model'

type Pane = 'live' | 'archive'
type RestoreDestination = 'new_window' | 'current_window'

type EternalFilter = 'all' | 'eternal' | 'not_eternal'
type HealthFilter = 'all' | 'healthy' | 'unknown' | 'unavailable'
type HeatFilter = 'all' | HeatLevel

const TAB_ARCHIVE_LOG_PREFIX = '[tab-archive-ui]'

function uiDebug(event: string, payload?: unknown) {
  if (!import.meta.env.DEV) {
    return
  }
  if (payload === undefined) {
    console.debug(`${TAB_ARCHIVE_LOG_PREFIX} ${event}`)
    return
  }
  console.debug(`${TAB_ARCHIVE_LOG_PREFIX} ${event}`, payload)
}

function uiWarn(event: string, payload?: unknown) {
  if (!import.meta.env.DEV) {
    return
  }
  if (payload === undefined) {
    console.warn(`${TAB_ARCHIVE_LOG_PREFIX} ${event}`)
    return
  }
  console.warn(`${TAB_ARCHIVE_LOG_PREFIX} ${event}`, payload)
}

function uiError(event: string, payload?: unknown) {
  if (!import.meta.env.DEV) {
    return
  }
  if (payload === undefined) {
    console.error(`${TAB_ARCHIVE_LOG_PREFIX} ${event}`)
    return
  }
  console.error(`${TAB_ARCHIVE_LOG_PREFIX} ${event}`, payload)
}

function errorMessage(error: unknown, fallback: string): string {
  const e = error as { response?: { data?: { error?: string } }; message?: string }
  return e?.response?.data?.error || e?.message || fallback
}

function uniqueNumbers(values: number[]): number[] {
  return Array.from(new Set(values.filter(v => Number.isInteger(v) && v > 0)))
}

function restoreFailureReason(error: string): string {
  const text = (error || '').toLowerCase()
  if (text.includes('extension_outdated') || text.includes('unknown command type')) return 'extension-outdated'
  if (text.includes('record_not_found')) return 'record-not-found'
  if (text.includes('focus_failed')) return 'focus-failed'
  if (text.includes('open_failed')) return 'open-failed'
  if (text.includes('missing_result')) return 'missing-extension-result'
  return 'other'
}

function buildRestoreFailureSummary(rows: TabArchiveRestoreResultRow[]): {
  headline: string
  details: string
} {
  const failed = rows.filter(row => !row.ok)
  if (failed.length === 0) {
    return {
      headline: '',
      details: '',
    }
  }

  const reasonCounts = new Map<string, number>()
  failed.forEach(row => {
    const reason = restoreFailureReason(row.error)
    reasonCounts.set(reason, (reasonCounts.get(reason) || 0) + 1)
  })

  const reasonLine = Array.from(reasonCounts.entries())
    .sort((a, b) => b[1] - a[1])
    .map(([reason, count]) => `${reason}=${count}`)
    .join(', ')

  const exampleLines = failed.slice(0, 5).map(row => {
    const name = (row.title || '').trim() || row.url || `record#${row.record_id}`
    return `- ${name}: ${row.error || 'unknown_error'}`
  })

  const details = [
    `Failure reasons: ${reasonLine}`,
    '',
    'Examples:',
    ...exampleLines,
  ].join('\n')

  return {
    headline: reasonLine,
    details,
  }
}

export default defineComponent({
  name: 'TabsView',
  setup() {
    const router = useRouter()

    const loading = ref(false)
    const busy = ref(false)
    const activePane = ref<Pane>('live')
    const search = ref('')

    const liveRows = ref<TabArchiveLiveCard[]>([])
    const archiveRows = ref<TabArchiveRecord[]>([])
    const extensionAvailable = ref(true)
    const liveError = ref('')

    const selectedLiveTabIds = ref<Set<number>>(new Set())
    const selectedArchiveIds = ref<Set<number>>(new Set())
    const archiveCache = ref<Record<number, TabArchiveRecord>>({})

    const labels = ref<TabArchiveLabel[]>([])

    const restoreDestination = ref<RestoreDestination>('new_window')
    const safeIncludePinned = ref(false)

    const archiveDomainFilter = ref('')
    const archiveSortBy = ref<TabArchiveSortBy>('heat')
    const archiveSortOrder = ref<TabArchiveSortOrder>('desc')
    const semanticEnabled = ref(false)
    const semanticAvailable = ref(false)
    const semanticError = ref('')
    const semanticModel = ref('')
    const semanticTopK = ref(0)
    const archiveEternalFilter = ref<EternalFilter>('all')
    const archiveHealthFilter = ref<HealthFilter>('all')
    const archiveHeatFilter = ref<HeatFilter>('all')
    const archiveLabelFilter = ref<string[]>([])

    const safePreviewVisible = ref(false)
    const safePreview = ref<TabArchiveSafePreview | null>(null)

    const editVisible = ref(false)
    const editingRecordId = ref<number | null>(null)
    const editTitle = ref('')
    const editComment = ref('')
    const editEternal = ref(false)
    const editLabelIds = ref<number[]>([])

    const healthJob = ref<TabArchiveHealthCheckJob | null>(null)
    const healthScopeLabel = ref('')

    // --- Live keyword select ---
    const liveKeywordSelect = ref('')

    // --- Archive replace URL ---
    const replaceUrlVisible = ref(false)
    const replaceUrlFind = ref('')
    const replaceUrlReplace = ref('')
    const replaceUrlPreviewRows = ref<TabArchiveReplaceUrlPreviewRow[]>([])
    const replaceUrlPreviewed = ref(false)

    let searchTimer: number | undefined
    let healthPollTimer: number | undefined

    const labelNameById = computed<Record<number, string>>(() => {
      const out: Record<number, string> = {}
      labels.value.forEach(label => {
        out[label.id] = label.name
      })
      return out
    })

    const labelIdByName = computed<Record<string, number>>(() => {
      const out: Record<string, number> = {}
      labels.value.forEach(label => {
        out[label.name] = label.id
      })
      return out
    })

    const visibleArchiveRows = computed(() => {
      return archiveRows.value.filter(record => {
        const domainNeedle = archiveDomainFilter.value.trim().toLowerCase()
        if (domainNeedle && !(record.domain || '').toLowerCase().includes(domainNeedle)) {
          return false
        }

        if (archiveEternalFilter.value === 'eternal' && !record.eternal) {
          return false
        }
        if (archiveEternalFilter.value === 'not_eternal' && record.eternal) {
          return false
        }

        if (archiveHealthFilter.value !== 'all') {
          if (archiveHealthFilter.value === 'healthy' && record.health_status !== 'healthy') {
            return false
          }
          if (
            archiveHealthFilter.value === 'unknown'
            && !['unknown', 'unchecked'].includes(record.health_status)
          ) {
            return false
          }
          if (archiveHealthFilter.value === 'unavailable' && record.health_status !== 'unavailable') {
            return false
          }
        }

        if (archiveHeatFilter.value !== 'all' && record.heat_level !== archiveHeatFilter.value) {
          return false
        }

        if (archiveLabelFilter.value.length > 0) {
          const names = new Set(record.labels || [])
          if (!archiveLabelFilter.value.every(labelName => names.has(labelName))) {
            return false
          }
        }

        return true
      })
    })

    const selectedArchiveRecords = computed(() => {
      const result: TabArchiveRecord[] = []
      selectedArchiveIds.value.forEach(id => {
        const cached = archiveCache.value[id]
        if (cached) {
          result.push(cached)
        }
      })
      return result.sort((a, b) => (a.title || '').localeCompare(b.title || ''))
    })

    const allVisibleLiveSelected = computed(() => {
      const rows = liveRows.value
      if (rows.length === 0) {
        return false
      }
      return rows.every(row => selectedLiveTabIds.value.has(row.tab_id))
    })

    const someVisibleLiveSelected = computed(() => {
      if (allVisibleLiveSelected.value) {
        return false
      }
      return liveRows.value.some(row => selectedLiveTabIds.value.has(row.tab_id))
    })

    const allVisibleArchiveSelected = computed(() => {
      const rows = visibleArchiveRows.value
      if (rows.length === 0) {
        return false
      }
      return rows.every(row => selectedArchiveIds.value.has(row.id))
    })

    const someVisibleArchiveSelected = computed(() => {
      if (allVisibleArchiveSelected.value) {
        return false
      }
      return visibleArchiveRows.value.some(row => selectedArchiveIds.value.has(row.id))
    })

    const heatTagType = (heat: HeatLevel): 'danger' | 'warning' | 'success' | 'info' => {
      if (heat === 'high') return 'danger'
      if (heat === 'medium') return 'warning'
      if (heat === 'low') return 'success'
      return 'info'
    }

    const healthJobRunning = computed(() => {
      const status = healthJob.value?.status
      return status === 'queued' || status === 'running' || status === 'cancelling'
    })

    async function loadLabels() {
      labels.value = await tabArchiveListLabels()
    }

    async function loadSnapshot() {
      loading.value = true
      uiDebug('snapshot.start', {
        queryLen: search.value.trim().length,
        sortBy: archiveSortBy.value,
        sortOrder: archiveSortOrder.value,
        semantic: semanticEnabled.value,
      })
      try {
        const data = await tabArchiveSnapshot({
          q: search.value.trim(),
          scope: 'all',
          include_live_urls: true,
          sort_by: archiveSortBy.value,
          sort_order: archiveSortOrder.value,
          semantic: semanticEnabled.value,
        })

        extensionAvailable.value = data.extension_available
        liveError.value = data.live_error || ''
        liveRows.value = data.live || []
        archiveRows.value = data.archive || []
        semanticAvailable.value = !!data.search?.semantic_available
        semanticError.value = data.search?.semantic_error || ''
        semanticModel.value = data.search?.semantic_model || ''
        semanticTopK.value = Number(data.search?.semantic_top_k || 0)

        const cache = { ...archiveCache.value }
        archiveRows.value.forEach(row => {
          cache[row.id] = row
        })
        archiveCache.value = cache

        // Live selections should only keep currently existing tabs.
        const existingLiveIds = new Set(liveRows.value.map(row => row.tab_id))
        const nextLiveSelected = new Set<number>()
        selectedLiveTabIds.value.forEach(id => {
          if (existingLiveIds.has(id)) {
            nextLiveSelected.add(id)
          }
        })
        selectedLiveTabIds.value = nextLiveSelected
        uiDebug('snapshot.done', {
          live: liveRows.value.length,
          archive: archiveRows.value.length,
          extensionAvailable: extensionAvailable.value,
          semanticAvailable: semanticAvailable.value,
        })
      } catch (error) {
        uiError('snapshot.failed', error)
        ElMessage.error(errorMessage(error, 'Failed to load tab snapshot'))
      } finally {
        loading.value = false
      }
    }

    function scheduleSearchReload() {
      if (searchTimer !== undefined) {
        window.clearTimeout(searchTimer)
      }
      searchTimer = window.setTimeout(() => {
        void loadSnapshot()
      }, 250)
    }

    function toggleLiveSelection(tabId: number) {
      const next = new Set(selectedLiveTabIds.value)
      if (next.has(tabId)) next.delete(tabId)
      else next.add(tabId)
      selectedLiveTabIds.value = next
    }

    function toggleVisibleLiveSelection() {
      const next = new Set(selectedLiveTabIds.value)
      if (allVisibleLiveSelected.value) {
        liveRows.value.forEach(row => next.delete(row.tab_id))
      } else {
        liveRows.value.forEach(row => next.add(row.tab_id))
      }
      selectedLiveTabIds.value = next
    }

    function toggleArchiveSelection(recordId: number) {
      const next = new Set(selectedArchiveIds.value)
      if (next.has(recordId)) next.delete(recordId)
      else next.add(recordId)
      selectedArchiveIds.value = next
    }

    function toggleVisibleArchiveSelection() {
      const next = new Set(selectedArchiveIds.value)
      if (allVisibleArchiveSelected.value) {
        visibleArchiveRows.value.forEach(row => next.delete(row.id))
      } else {
        visibleArchiveRows.value.forEach(row => next.add(row.id))
      }
      selectedArchiveIds.value = next
    }

    function removeFromArchiveBasket(recordId: number) {
      const next = new Set(selectedArchiveIds.value)
      next.delete(recordId)
      selectedArchiveIds.value = next
    }

    function clearArchiveBasket() {
      selectedArchiveIds.value = new Set()
    }

    async function archiveSelectedLive() {
      const ids = uniqueNumbers(Array.from(selectedLiveTabIds.value))
      if (ids.length === 0) {
        ElMessage.info('No live tabs selected')
        return
      }
      uiDebug('archiveSelected.start', { count: ids.length })

      try {
        await ElMessageBox.confirm(
          `Archive and close ${ids.length} selected tab(s)?`,
          'Confirm archive',
          {
            type: 'warning',
            confirmButtonText: 'Archive selected',
            cancelButtonText: 'Cancel',
          },
        )
      } catch {
        return
      }

      busy.value = true
      try {
        const result = await tabArchiveSelected(ids)
        uiDebug('archiveSelected.done', {
          requested: result.requested,
          closed: result.closed_count,
          failed: result.failed_count,
        })
        if (result.failed_count > 0) {
          uiWarn('archiveSelected.partial', {
            failed: result.failed_count,
            failures: result.failures?.slice(0, 5) || [],
          })
          ElMessage.warning(
            `Archived ${result.closed_count}/${result.requested}. ${result.failed_count} failed.`,
          )
        } else {
          ElMessage.success(`Archived ${result.closed_count} tab(s)`)
        }
        selectedLiveTabIds.value = new Set()
        await loadSnapshot()
      } catch (error) {
        uiError('archiveSelected.failed', error)
        ElMessage.error(errorMessage(error, 'Archive selected failed'))
      } finally {
        busy.value = false
      }
    }

    async function previewSafeArchive() {
      busy.value = true
      try {
        safePreview.value = await tabArchiveSafePreview(safeIncludePinned.value)
        safePreviewVisible.value = true
      } catch (error) {
        ElMessage.error(errorMessage(error, 'Failed to load safe archive preview'))
      } finally {
        busy.value = false
      }
    }

    async function runSafeArchive() {
      try {
        await ElMessageBox.confirm(
          'Archive all previewed candidates and close their tabs?',
          'Run safe archive',
          {
            type: 'warning',
            confirmButtonText: 'Run now',
            cancelButtonText: 'Cancel',
          },
        )
      } catch {
        return
      }

      busy.value = true
      try {
        const result = await tabArchiveSafeRun(safeIncludePinned.value)
        uiDebug('safeArchive.done', {
          requested: result.requested,
          closed: result.closed_count,
          failed: result.failed_count,
          excluded: result.excluded_count,
        })
        safePreviewVisible.value = false
        safePreview.value = null

        if (result.failed_count > 0) {
          ElMessage.warning(
            `Safe archive closed ${result.closed_count}/${result.requested}. ${result.failed_count} failed.`,
          )
        } else {
          ElMessage.success(`Safe archive closed ${result.closed_count} tab(s)`)
        }

        selectedLiveTabIds.value = new Set()
        await loadSnapshot()
      } catch (error) {
        uiError('safeArchive.failed', error)
        ElMessage.error(errorMessage(error, 'Safe archive failed'))
      } finally {
        busy.value = false
      }
    }

    async function restoreSelectedArchive() {
      const ids = uniqueNumbers(Array.from(selectedArchiveIds.value))
      if (ids.length === 0) {
        ElMessage.info('No archived records selected')
        return
      }
      uiDebug('restore.start', {
        count: ids.length,
        destination: restoreDestination.value,
      })

      busy.value = true
      try {
        const result = await tabArchiveRestore(ids, restoreDestination.value)
        uiDebug('restore.done', {
          requested: result.requested,
          opened: result.opened_count,
          alreadyLive: result.already_live_count,
          failed: result.failed_count,
        })

        const failedIds = new Set(
          result.results
            .filter(row => !row.ok)
            .map(row => row.record_id),
        )

        if (failedIds.size === 0) {
          selectedArchiveIds.value = new Set()
          ElMessage.success(`Restore completed: ${result.opened_count} opened, ${result.already_live_count} already live`)
        } else {
          selectedArchiveIds.value = new Set(Array.from(failedIds))
          const summary = buildRestoreFailureSummary(result.results)
          const headline = summary.headline ? ` (${summary.headline})` : ''
          uiWarn('restore.partial', {
            failedIds: Array.from(failedIds),
            reasonSummary: summary.headline,
            sampleFailures: result.results.filter(row => !row.ok).slice(0, 5),
          })
          ElMessage.warning(`Restore partial: ${result.failed_count} failed, kept in basket${headline}`)
          if (summary.details) {
            await ElMessageBox.alert(summary.details, 'Restore failure details', {
              type: 'warning',
              confirmButtonText: 'OK',
            })
          }
        }

        await loadSnapshot()
      } catch (error) {
        uiError('restore.failed', error)
        ElMessage.error(errorMessage(error, 'Restore failed'))
      } finally {
        busy.value = false
      }
    }

    function stopHealthPoll() {
      if (healthPollTimer !== undefined) {
        window.clearTimeout(healthPollTimer)
        healthPollTimer = undefined
      }
    }

    function scheduleHealthPoll(jobId: string) {
      stopHealthPoll()
      healthPollTimer = window.setTimeout(async () => {
        try {
          const statusRes = await tabArchiveHealthCheckStatus(jobId)
          if (!statusRes.exists || !statusRes.job) {
            stopHealthPoll()
            return
          }

          healthJob.value = statusRes.job
          const status = statusRes.job.status
          uiDebug('health.poll', {
            jobId,
            status,
            processed: statusRes.job.processed,
            total: statusRes.job.total,
          })
          if (status === 'queued' || status === 'running' || status === 'cancelling') {
            scheduleHealthPoll(jobId)
            return
          }

          if (status === 'completed') {
            ElMessage.success(
              `Health check completed (${healthScopeLabel.value || 'archive'}): ${statusRes.job.processed}/${statusRes.job.total}`,
            )
            await loadSnapshot()
          } else if (status === 'cancelled') {
            ElMessage.info('Health check cancelled')
            await loadSnapshot()
          } else if (status === 'failed') {
            ElMessage.error(statusRes.job.last_error || 'Health check failed')
          }
          stopHealthPoll()
        } catch (error) {
          uiError('health.poll.failed', { jobId, error })
          ElMessage.error(errorMessage(error, 'Health check polling failed'))
          stopHealthPoll()
        }
      }, 900)
    }

    async function startHealthCheck(recordIds: number[], scopeLabel: string) {
      if (healthJobRunning.value) {
        ElMessage.info('A health-check job is already running')
        return
      }
      if (recordIds.length === 0) {
        ElMessage.info('No archived records to check')
        return
      }
      uiDebug('health.start', {
        scope: scopeLabel,
        count: recordIds.length,
      })

      busy.value = true
      try {
        const startRes = await tabArchiveHealthCheckStart({
          record_ids: recordIds,
          batch_size: 20,
        })
        healthJob.value = startRes.job
        healthScopeLabel.value = scopeLabel
        uiDebug('health.started', {
          jobId: startRes.job.job_id,
          total: startRes.job.total,
        })
        ElMessage.success(`Health check started for ${recordIds.length} item(s)`)
        scheduleHealthPoll(startRes.job.job_id)
      } catch (error) {
        uiError('health.start.failed', error)
        ElMessage.error(errorMessage(error, 'Failed to start health check'))
      } finally {
        busy.value = false
      }
    }

    async function checkArchiveHealthSelected() {
      const ids = uniqueNumbers(Array.from(selectedArchiveIds.value))
      await startHealthCheck(ids, 'selected')
    }

    async function checkArchiveHealthVisible() {
      const ids = uniqueNumbers(visibleArchiveRows.value.map(row => row.id)).slice(0, 200)
      await startHealthCheck(ids, 'visible')
    }

    async function cancelArchiveHealthCheck() {
      const jobId = healthJob.value?.job_id
      if (!jobId) {
        return
      }
      uiDebug('health.cancel.requested', { jobId })
      try {
        const res = await tabArchiveHealthCheckCancel(jobId)
        if (res.job) {
          healthJob.value = res.job
        }
        uiDebug('health.cancel.accepted', {
          jobId,
          status: res.job?.status,
        })
        scheduleHealthPoll(jobId)
      } catch (error) {
        uiError('health.cancel.failed', { jobId, error })
        ElMessage.error(errorMessage(error, 'Failed to cancel health check'))
      }
    }

    async function closeSingleLive(tabId: number) {
      busy.value = true
      try {
        const result = await closeTabs([tabId])
        if ((result.closed || 0) > 0) {
          ElMessage.success('Tab closed')
        } else {
          ElMessage.warning('Close request returned no closed tabs')
        }
        await loadSnapshot()
      } catch (error) {
        ElMessage.error(errorMessage(error, 'Failed to close tab'))
      } finally {
        busy.value = false
      }
    }

    async function closeSelectedLiveOnly() {
      const ids = uniqueNumbers(Array.from(selectedLiveTabIds.value))
      if (ids.length === 0) {
        ElMessage.info('No live tabs selected')
        return
      }

      try {
        await ElMessageBox.confirm(`Close ${ids.length} selected live tab(s)?`, 'Confirm', {
          type: 'warning',
          confirmButtonText: 'Close selected',
          cancelButtonText: 'Cancel',
        })
      } catch {
        return
      }

      busy.value = true
      try {
        const result = await closeTabs(ids)
        const failed = result.failed?.length || 0
        if (failed > 0) {
          ElMessage.warning(`Closed ${result.closed}; ${failed} failed`)
        } else {
          ElMessage.success(`Closed ${result.closed} tab(s)`)
        }
        selectedLiveTabIds.value = new Set()
        await loadSnapshot()
      } catch (error) {
        ElMessage.error(errorMessage(error, 'Failed to close selected tabs'))
      } finally {
        busy.value = false
      }
    }

    async function mergeAll() {
      busy.value = true
      try {
        const result = await mergeTabs()
        ElMessage.success(`Merged ${result.moved} tab(s) into one window`)
        await loadSnapshot()
      } catch (error) {
        ElMessage.error(errorMessage(error, 'Failed to merge windows'))
      } finally {
        busy.value = false
      }
    }

    async function groupByDomain() {
      busy.value = true
      try {
        const result = await groupTabsByDomain()
        ElMessage.success(`Grouped ${result.grouped} tab(s) by domain`)
        await loadSnapshot()
      } catch (error) {
        ElMessage.error(errorMessage(error, 'Failed to group tabs'))
      } finally {
        busy.value = false
      }
    }

    function startEditRecord(record: TabArchiveRecord) {
      editingRecordId.value = record.id
      editTitle.value = record.title || ''
      editComment.value = record.comment || ''
      editEternal.value = !!record.eternal
      editLabelIds.value = uniqueNumbers((record.labels || []).map(name => labelIdByName.value[name] || 0))
      editVisible.value = true
    }

    async function createLabelInEditor() {
      const promptResult = await ElMessageBox.prompt('Label name', 'Create Label', {
        inputPlaceholder: 'e.g. reference, learning, work',
      }).catch(() => null)

      const value = promptResult?.value?.trim()
      if (!value) {
        return
      }

      busy.value = true
      try {
        const label = await tabArchiveCreateLabel(value)
        labels.value = [...labels.value, label].sort((a, b) => a.name.localeCompare(b.name))
        editLabelIds.value = uniqueNumbers([...editLabelIds.value, label.id])
      } catch (error) {
        ElMessage.error(errorMessage(error, 'Failed to create label'))
      } finally {
        busy.value = false
      }
    }

    async function saveRecordEdit() {
      const id = editingRecordId.value
      if (!id) {
        return
      }

      busy.value = true
      try {
        let record = await tabArchiveUpdateRecord(id, {
          title: editTitle.value,
          comment: editComment.value,
          eternal: editEternal.value,
        })
        record = await tabArchiveSetRecordLabels(id, uniqueNumbers(editLabelIds.value))

        const cache = { ...archiveCache.value }
        cache[id] = record
        archiveCache.value = cache

        editVisible.value = false
        ElMessage.success('Record updated')
        await loadSnapshot()
      } catch (error) {
        ElMessage.error(errorMessage(error, 'Failed to update record'))
      } finally {
        busy.value = false
      }
    }

    async function deleteRecord(record: TabArchiveRecord) {
      try {
        await ElMessageBox.confirm(
          `Delete archived record "${record.title || record.domain || record.url}"?`,
          'Delete record',
          {
            type: 'warning',
            confirmButtonText: 'Delete',
            cancelButtonText: 'Cancel',
          },
        )
      } catch {
        return
      }

      busy.value = true
      try {
        await tabArchiveDeleteRecord(record.id)
        const selected = new Set(selectedArchiveIds.value)
        selected.delete(record.id)
        selectedArchiveIds.value = selected

        const cache = { ...archiveCache.value }
        delete cache[record.id]
        archiveCache.value = cache

        ElMessage.success('Record deleted')
        await loadSnapshot()
      } catch (error) {
        ElMessage.error(errorMessage(error, 'Failed to delete record'))
      } finally {
        busy.value = false
      }
    }

    function hideFavicon(event: Event) {
      const img = event.target as HTMLImageElement | null
      if (img) {
        img.style.display = 'none'
      }
    }

    // --- Live: select by keyword ---

    function selectLiveByKeyword() {
      const kw = liveKeywordSelect.value.trim().toLowerCase()
      if (!kw) {
        ElMessage.info('Enter a keyword first')
        return
      }
      const next = new Set(selectedLiveTabIds.value)
      let added = 0
      liveRows.value.forEach(row => {
        const matches =
          (row.title || '').toLowerCase().includes(kw) ||
          (row.url || '').toLowerCase().includes(kw) ||
          (row.domain || '').toLowerCase().includes(kw)
        if (matches && !next.has(row.tab_id)) {
          next.add(row.tab_id)
          added++
        }
      })
      selectedLiveTabIds.value = next
      ElMessage.success(`Added ${added} tab(s) to selection`)
    }

    // --- Archive: replace URL ---

    function openReplaceUrlDialog() {
      replaceUrlFind.value = ''
      replaceUrlReplace.value = ''
      replaceUrlPreviewRows.value = []
      replaceUrlPreviewed.value = false
      replaceUrlVisible.value = true
    }

    async function previewReplaceUrl() {
      if (!replaceUrlFind.value.trim()) {
        ElMessage.warning('Find text must not be empty')
        return
      }
      busy.value = true
      try {
        const scopeIds = selectedArchiveIds.value.size > 0
          ? uniqueNumbers(Array.from(selectedArchiveIds.value))
          : undefined
        const result = await tabArchiveReplaceUrl({
          find: replaceUrlFind.value,
          replace: replaceUrlReplace.value,
          record_ids: scopeIds,
          preview: true,
        })
        replaceUrlPreviewRows.value = result.preview || []
        replaceUrlPreviewed.value = true
        if (replaceUrlPreviewRows.value.length === 0) {
          ElMessage.info('No records match the find text')
        }
      } catch (error) {
        ElMessage.error(errorMessage(error, 'Preview failed'))
      } finally {
        busy.value = false
      }
    }

    async function applyReplaceUrl() {
      if (!replaceUrlFind.value.trim()) {
        ElMessage.warning('Find text must not be empty')
        return
      }
      const count = replaceUrlPreviewRows.value.length
      if (count === 0) {
        ElMessage.info('Nothing to replace')
        return
      }
      try {
        await ElMessageBox.confirm(
          `Replace URL in ${count} record(s)?`,
          'Confirm replace',
          {
            type: 'warning',
            confirmButtonText: 'Replace',
            cancelButtonText: 'Cancel',
          },
        )
      } catch {
        return
      }

      busy.value = true
      try {
        const scopeIds = selectedArchiveIds.value.size > 0
          ? uniqueNumbers(Array.from(selectedArchiveIds.value))
          : undefined
        const result = await tabArchiveReplaceUrl({
          find: replaceUrlFind.value,
          replace: replaceUrlReplace.value,
          record_ids: scopeIds,
          preview: false,
        })
        ElMessage.success(`Replaced URL in ${result.updated} record(s)`)
        replaceUrlVisible.value = false
        await loadSnapshot()
      } catch (error) {
        ElMessage.error(errorMessage(error, 'Replace failed'))
      } finally {
        busy.value = false
      }
    }

    function formatTime(text: string | null): string {
      if (!text) {
        return '-'
      }
      return text
    }

    watch(search, () => {
      scheduleSearchReload()
    })

    watch(semanticEnabled, enabled => {
      if (enabled && archiveSortBy.value === 'heat') {
        archiveSortBy.value = 'relevance'
      }
    })

    watch([archiveSortBy, archiveSortOrder, semanticEnabled], () => {
      void loadSnapshot()
    })

    onMounted(async () => {
      await Promise.all([loadLabels(), loadSnapshot()])
      try {
        const status = await tabArchiveHealthCheckStatus()
        if (status.exists && status.job) {
          healthJob.value = status.job
          if (status.job.status === 'queued' || status.job.status === 'running' || status.job.status === 'cancelling') {
            healthScopeLabel.value = 'resume'
            scheduleHealthPoll(status.job.job_id)
          }
        }
      } catch {
        // Ignore status bootstrapping failures; manual actions still work.
      }
    })

    onUnmounted(() => {
      if (searchTimer !== undefined) {
        window.clearTimeout(searchTimer)
      }
      stopHealthPoll()
    })

    return {
      activePane,
      loading,
      busy,
      search,
      extensionAvailable,
      liveError,
      liveRows,
      archiveRows,
      labels,

      selectedLiveTabIds,
      selectedArchiveIds,
      selectedArchiveRecords,
      allVisibleLiveSelected,
      someVisibleLiveSelected,
      allVisibleArchiveSelected,
      someVisibleArchiveSelected,

      restoreDestination,
      safeIncludePinned,
      safePreviewVisible,
      safePreview,

      archiveDomainFilter,
      archiveSortBy,
      archiveSortOrder,
      semanticEnabled,
      semanticAvailable,
      semanticError,
      semanticModel,
      semanticTopK,
      healthJob,
      healthScopeLabel,
      healthJobRunning,
      archiveEternalFilter,
      archiveHealthFilter,
      archiveHeatFilter,
      archiveLabelFilter,
      visibleArchiveRows,

      editVisible,
      editTitle,
      editComment,
      editEternal,
      editLabelIds,

      labelNameById,

      loadSnapshot,
      toggleLiveSelection,
      toggleVisibleLiveSelection,
      toggleArchiveSelection,
      toggleVisibleArchiveSelection,
      removeFromArchiveBasket,
      clearArchiveBasket,
      archiveSelectedLive,
      previewSafeArchive,
      runSafeArchive,
      restoreSelectedArchive,
      checkArchiveHealthSelected,
      checkArchiveHealthVisible,
      cancelArchiveHealthCheck,
      closeSingleLive,
      closeSelectedLiveOnly,
      mergeAll,
      groupByDomain,
      startEditRecord,
      createLabelInEditor,
      saveRecordEdit,
      deleteRecord,
      hideFavicon,
      heatTagType,
      formatTime,
      goBack: () => router.push('/browser-agent'),

      liveKeywordSelect,
      selectLiveByKeyword,

      replaceUrlVisible,
      replaceUrlFind,
      replaceUrlReplace,
      replaceUrlPreviewRows,
      replaceUrlPreviewed,
      openReplaceUrlDialog,
      previewReplaceUrl,
      applyReplaceUrl,
    }
  },
})
