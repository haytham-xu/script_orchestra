
import { defineComponent, ref, onMounted, onBeforeUnmount, computed, watch, reactive, nextTick, toRefs } from 'vue'
import { useMangaIndexStore } from '@/manga_viwer/service/Store'
import type { FolderModel } from '../service/Model'
import { ElInput, ElTag, ElSwitch, ElRadio, ElRadioGroup, ElLoading } from 'element-plus'

export default defineComponent({
  name: 'MangaViewerView',
  components: { ElInput, ElTag, ElSwitch, ElRadio, ElRadioGroup },
  setup() {
    //  Basic
    // -------------------------------------------------------------------------------------------------------
    const store = useMangaIndexStore()
    const { hotTags } = toRefs(store)

    // Lazy load on scroll
    // -------------------------------------------------------------------------------------------------------
    const pageSize = 10
    const currentPage = ref(1)
    const loadingToken = ref(0)
    function onScroll() {
      const nearBottom = window.innerHeight + window.scrollY >= document.body.offsetHeight - 300
      if (nearBottom && canLoadMore.value) {
        currentPage.value++
        fetchFilesForCurrentPage()
      }
    }

    // Search with Hot Tags
    // -------------------------------------------------------------------------------------------------------
    const searchTokens = ref<string[]>([])
    const searchInput = ref('')
    const showUninitializedOnly = ref(false)
    const sizeSortEnabled = ref(false)
    const nameSortEnabled = ref(true)
    const classifierModeEnabled = ref(true)

    function addSearchToken() {
      const v = searchInput.value.trim()
      if (!v) return
      if (!searchTokens.value.includes(v)) searchTokens.value.push(v)
      store.recordHotTag(v)
      searchInput.value = ''
    }
    function removeSearchToken(idx: number) {
      searchTokens.value.splice(idx, 1)
    }
    function addHotTag(tag: string) {
      store.recordHotTag(tag)
      if (!searchTokens.value.includes(tag)) searchTokens.value.push(tag)
    }

    const folders = computed(() => Object.values(store.mangaIndex.folders))

    const filteredFolders = computed(() => {
      const tokens = searchTokens.value.map(t => t.trim().toLowerCase()).filter(Boolean)
      let base = folders.value
      if (tokens.length) {
        base = base.filter(f => {
          const pool: string[] = [
            f.name,
            f.tags.category_main,
            f.tags.category_sub,
            String(f.tags.mosaic ?? '')
          ].concat(f.tags.auth, f.tags.name, f.tags.custom, f.tags.others).map(s => s?.toLowerCase())
          return tokens.every(tok => pool.some(p => p && p.includes(tok)))
        })
      }
      if (showUninitializedOnly.value) {
        base = base.filter(f => !f.initialized)
      }
      if (nameSortEnabled.value) {
        base = [...base].sort((a, b) => a.name.localeCompare(b.name))
      } else if (sizeSortEnabled.value) {
        base = [...base].sort((a, b) => b.size - a.size)
      }
      return base
    })

    watch(searchTokens, () => {
      currentPage.value = 1
      fetchFilesForCurrentPage()
    })
    watch(sizeSortEnabled, () => {
      currentPage.value = 1
      fetchFilesForCurrentPage()
    })
    watch(nameSortEnabled, () => {
      currentPage.value = 1
      fetchFilesForCurrentPage()
    })
    // Lazy Load Files
    // -------------------------------------------------------------------------------------------------------
    const pagedFolders = computed(() =>
      filteredFolders.value.slice(0, currentPage.value * pageSize)
    )

    const canLoadMore = computed(() =>
      pagedFolders.value.length < filteredFolders.value.length
    )

    async function fetchFilesForCurrentPage() {
      const token = ++loadingToken.value
      for (const f of pagedFolders.value) {
        if (loadingToken.value !== token) return
        if (!f.files || f.files.length === 0) {
          await store.fetchFolderFiles(f)
        }
      }
    }

    watch(filteredFolders, () => {
      currentPage.value = 1
      fetchFilesForCurrentPage()
    })

    // Preivew Imag/Video
    // -------------------------------------------------------------------------------------------------------
    function previewImages(f: FolderModel): string[] {
      const exts = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp']
      const list: string[] = (f.files || []).filter((p: string) => {
        const e = p.split('.').pop()?.toLowerCase() || ''
        return exts.includes(e)
      })
      return list.slice(0, 3)
    }

    const dialogVisible = ref(false)
    const dialogFolder = ref<FolderModel | null>(null)
    const dialogFiles = computed(() => dialogFolder.value?.files || [])

    function openModal(f: FolderModel) {
      dialogFolder.value = f
      dialogVisible.value = true
      if (!f.files || f.files.length === 0) {
        store.fetchFolderFiles(f)
      }
    }
    function closeModal() {
      dialogVisible.value = false
      dialogFolder.value = null
    }

    function isImage(p: string) { return /\.(jpe?g|png|gif|webp|bmp|tiff)$/i.test(p) }
    function isVideo(p: string) { return /\.(mp4|webm|mov|mkv|avi|flv)$/i.test(p) }

    // Code for Update
    // -------------------------------------------------------------------------------------------------------

    const activeInput = ref<InstanceType<typeof ElInput> | null>(null)

    function setActiveInput(el: InstanceType<typeof ElInput> | null) {
      activeInput.value = el
      if (!el) return
      nextTick(() => {
        if (typeof el.focus === 'function') {
          el.focus()
          return
        }
        const root: HTMLElement | null = (el as unknown as { $el?: HTMLElement }).$el || null
        const raw: HTMLInputElement | null = root?.querySelector('input') || null
        raw?.focus()
      })
    }

    const editingNameFlag = ref<string | null>(null)
    const editValue = reactive({name: ''})
    function startNameEdit(f: FolderModel) {
      editingNameFlag.value = f.id
      editValue.name = f.name
    }

    async function commitNameAndRadioEdit(field: 'name' | 'category_main' | 'category_sub' | 'mosaic', f: FolderModel) {
      if (field === 'name') {
        editingNameFlag.value = null
        if (f.name !== editValue.name) {
          f.name = editValue.name.trim()
          f.initialized = true
          store.addChangeId(f.id)
        }
        return
      }
      f.initialized = true
      store.addChangeId(f.id)
      if (field === 'category_main' || field === 'category_sub') {
        store.addMoveId(f.id)
      }
    }

    // Update -Tags
    // -------------------------------------------------------------------------------------------------------
    const tagInputVisible = reactive<Record<string, Record<string, boolean>>>({})
    const tagInputValues = reactive<Record<string, Record<string, string>>>({})
    const tagInputRefs = reactive<Record<string, Record<string, InstanceType<typeof ElInput> | null>>>({})

    function ensureTagState(folderId: string, group: string) {
      if (!tagInputVisible[folderId]) tagInputVisible[folderId] = {}
      if (!tagInputValues[folderId]) tagInputValues[folderId] = {}
      if (!tagInputRefs[folderId]) tagInputRefs[folderId] = {}
      if (tagInputValues[folderId][group] === undefined) tagInputValues[folderId][group] = ''
    }

    function isTagInputVisible(f: FolderModel, group: 'auth' | 'name' | 'custom' | 'others'): boolean {
      return !!tagInputVisible[f.id]?.[group]
    }

    function setTagInputRef(folderId: string, group: string) {
      return (el: InstanceType<typeof ElInput> | null) => {
        ensureTagState(folderId, group)
        tagInputRefs[folderId][group] = el
        if (el) {
          nextTick(() => {
            if (typeof el.focus === 'function') el.focus()
            else {
              const raw: HTMLInputElement | null = (el as any).$el?.querySelector('input') || null
              raw?.focus()
            }
          })
        }
      }
    }

    function parseAuthName(raw: string): { auth: string; name: string } {
      const s = (raw || '').trim()
      const m = s.match(/^(\[(?<b>[^\]]+)\]|\((?<p>[^)]+)\))(?<rest>.*)$/)
      if (!m) {
        const nm = s.match(/^([^[(]+)/)
        return { auth: '', name: (nm ? nm[1] : s).trim() }
      }
      const auth = (m.groups?.b || m.groups?.p || '').trim()
      const rest = (m.groups?.rest || '')
      const nm = rest.match(/^([^[(]+)/)
      const name = (nm ? nm[1] : '').trim()
      return { auth, name }
    }

    function showTagInput(f: FolderModel, group: 'auth' | 'name' | 'custom' | 'others') {
      ensureTagState(f.id, group)
      tagInputVisible[f.id][group] = true
      const { auth, name } = parseAuthName(f.name)
      if (group === 'auth') {
        tagInputValues[f.id].auth = auth
      }
      if (group === 'name') {
        tagInputValues[f.id].name = name
      }
    }

    async function handleTagInputConfirm(f: FolderModel, group: 'auth' | 'name' | 'custom' | 'others') {
      ensureTagState(f.id, group)
      const v = tagInputValues[f.id][group].trim()
      tagInputVisible[f.id][group] = false
      if (!v) {
        tagInputValues[f.id][group] = ''
        return
      }
      if (!f.tags[group].includes(v)) {
        f.tags[group].push(v)
        f.initialized = true
        store.addChangeId(f.id)
      }
      tagInputValues[f.id][group] = ''
    }

    async function removeTag(f: FolderModel, group: 'auth' | 'name' | 'custom' | 'others', index: number) {
      f.tags[group].splice(index, 1)
      store.addChangeId(f.id)
    }


    // Appying
    // -------------------------------------------------------------------------------------------------------
    async function applyChanges() {
      const loading = ElLoading.service({ lock: true, text: 'Applying...', background: 'rgba(0,0,0,0.4)' })
      await store.applyChanges(classifierModeEnabled.value)
      loading.close()
    }

    // Life Cycle
    // -------------------------------------------------------------------------------------------------------
    onMounted(async () => {
      await store.loadIndex()
      fetchFilesForCurrentPage()
      window.addEventListener('scroll', onScroll)
    })
    onBeforeUnmount(() => {
      window.removeEventListener('scroll', onScroll)
    })

    return {
      // Search with Hot Tags
      searchTokens,
      searchInput,
      hotTags,
      addSearchToken,
      removeSearchToken,
      addHotTag,
      // Update - Basic
      startEdit: startNameEdit,
      commitEdit: commitNameAndRadioEdit,
      editingNameFlag,
      editValue,
      setActiveInput,
      // Update — Tag
      isTagInputVisible,
      showTagInput,
      handleTagInputConfirm,
      setTagInputRef,
      removeTag,
      tagInputValues,
      // unknown
      pagedFolders,
      canLoadMore,
      previewImages,
      openModal,
      closeModal,
      dialogVisible,
      dialogFolder,
      dialogFiles,
      isImage,
      isVideo,
      // Switch Initialized
      showUninitializedOnly,
      sizeSortEnabled,
      nameSortEnabled,
      classifierModeEnabled,
      // Applying
      applyChanges,
    }
  }
})
