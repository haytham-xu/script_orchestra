import { defineComponent, ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getCards, getDue, createCard, updateCard, deleteCard, reviewCard,
  getSettings, updateSettings,
} from '../service/MemoryCurveService'
import type { MemoryCard, MemoryCurveSettings, Rating } from '../service/Model'

export default defineComponent({
  name: 'MemoryCurveView',
  setup() {
    const activeTab = ref<'review' | 'manage'>('review')
    const settings = ref<MemoryCurveSettings>({ card_mode: 'qa', daily_new_limit: 20 })
    const isQa = computed(() => settings.value.card_mode === 'qa')

    // ---- review ----
    const dueCards = ref<MemoryCard[]>([])
    const reviewIndex = ref(0)
    const answerShown = ref(false)
    const currentCard = computed(() => dueCards.value[reviewIndex.value] || null)
    const reviewDone = computed(() => dueCards.value.length > 0 && reviewIndex.value >= dueCards.value.length)

    async function loadDue() {
      dueCards.value = await getDue()
      reviewIndex.value = 0
      answerShown.value = false
    }

    function showAnswer() { answerShown.value = true }

    async function rate(rating: Rating) {
      const card = currentCard.value
      if (!card) return
      try {
        await reviewCard(card.id, rating)
        reviewIndex.value += 1
        answerShown.value = false
      } catch (e: any) {
        ElMessage.error(e.message || 'Review failed')
      }
    }

    // ---- manage ----
    const cards = ref<MemoryCard[]>([])
    const editing = ref<MemoryCard | null>(null)
    const draft = ref<{ front: string; back: string; deck: string }>({ front: '', back: '', deck: '' })
    const showEditor = ref(false)

    async function loadCards() { cards.value = await getCards() }

    function openNew() {
      editing.value = null
      draft.value = { front: '', back: '', deck: '' }
      showEditor.value = true
    }
    function openEdit(c: MemoryCard) {
      editing.value = c
      draft.value = { front: c.front, back: c.back, deck: c.deck }
      showEditor.value = true
    }
    async function saveDraft() {
      if (!draft.value.front.trim()) { ElMessage.warning('Content is required'); return }
      try {
        if (editing.value) {
          await updateCard(editing.value.id, draft.value)
        } else {
          await createCard(draft.value.front, draft.value.back, draft.value.deck)
        }
        showEditor.value = false
        await loadCards()
      } catch (e: any) {
        ElMessage.error(e.message || 'Save failed')
      }
    }
    async function removeCard(c: MemoryCard) {
      try {
        await ElMessageBox.confirm(`Delete this card?`, 'Confirm', { type: 'warning' })
        await deleteCard(c.id)
        await loadCards()
      } catch { /* cancelled */ }
    }

    // ---- settings ----
    async function toggleMode(mode: 'qa' | 'single') {
      try {
        settings.value = await updateSettings({ card_mode: mode })
        ElMessage.success(`Card mode: ${mode}`)
      } catch (e: any) {
        ElMessage.error(e.message || 'Failed to update mode')
      }
    }

    onMounted(async () => {
      try { settings.value = await getSettings() } catch { /* defaults */ }
      await loadDue()
      await loadCards()
    })

    return {
      activeTab, settings, isQa,
      dueCards, reviewIndex, answerShown, currentCard, reviewDone,
      loadDue, showAnswer, rate,
      cards, showEditor, editing, draft, openNew, openEdit, saveDraft, removeCard, loadCards,
      toggleMode,
    }
  },
})
