/**
 * Knowledge Vault — View-Matrix E2E tests
 *
 * Canonical test dataset (10 fragments):
 *
 *   Fragment                    | group_id    | archived
 *   ----------------------------|-------------|--------
 *   Example-Top Group           | / (root=1)  | false
 *   Example-L1-1                | l1-1        | false
 *   Example-L1-2                | l1-2        | false
 *   Example-L2-1                | l2-1        | false
 *   Example-ungroup             | null        | false
 *   Archive-Example-Top Group   | / (root=1)  | true
 *   Archive-Example-L1-1        | l1-1        | true
 *   Archive-Example-L1-2        | l1-2        | true
 *   Archive-Example-L2-1        | l2-1        | true
 *   Archive-Example-ungroup     | null        | true
 *
 * Visibility matrix (8 view combinations):
 *
 *   Fragment                  | A=off Normal /  | A=off All | A=off Ungrouped | A=on Normal /  | A=on All | A=on Ungrouped | A=off Normal <group> | A=on Normal <group>
 *   --------------------------|-----------------|-----------|-----------------|----------------|----------|----------------|----------------------|--------------------
 *   Example-Top Group         | SHOW            | SHOW      | HIDE            | HIDE           | HIDE     | HIDE           | show at /            | HIDE
 *   Example-L1-1              | HIDE            | SHOW      | HIDE            | HIDE           | HIDE     | HIDE           | show in l1-1         | HIDE
 *   Example-L1-2              | HIDE            | SHOW      | HIDE            | HIDE           | HIDE     | HIDE           | show in l1-2         | HIDE
 *   Example-L2-1              | HIDE            | SHOW      | HIDE            | HIDE           | HIDE     | HIDE           | show in l2-1         | HIDE
 *   Example-ungroup           | HIDE            | SHOW      | SHOW            | HIDE           | HIDE     | HIDE           | HIDE in all groups   | HIDE
 *   Archive-Example-Top Group | HIDE            | HIDE      | HIDE            | SHOW           | SHOW     | HIDE           | HIDE                 | show at /
 *   Archive-Example-L1-1      | HIDE            | HIDE      | HIDE            | HIDE           | SHOW     | HIDE           | HIDE                 | show in l1-1
 *   Archive-Example-L1-2      | HIDE            | HIDE      | HIDE            | HIDE           | SHOW     | HIDE           | HIDE                 | show in l1-2
 *   Archive-Example-L2-1      | HIDE            | HIDE      | HIDE            | HIDE           | SHOW     | HIDE           | HIDE                 | show in l2-1
 *   Archive-Example-ungroup   | HIDE            | HIDE      | HIDE            | HIDE           | SHOW     | SHOW           | HIDE                 | HIDE in all groups
 *
 * Rules summarised:
 *   - Archive toggle is orthogonal to view mode — it determines which dataset is loaded.
 *   - Normal at /: shows group-folder cards + fragments with group_id = root (1).
 *   - Normal in <group>: shows sub-group cards + fragments belonging to that group.
 *   - All: shows every fragment in the current archive-state dataset.
 *   - Ungrouped: shows only fragments with group_id = null in the current archive-state dataset.
 *   - Fragments with group_id = null are NEVER shown in Normal view (any level).
 */

const BASE = 'http://localhost:5001'
const PAGE  = '/knowledge-vault/capture'

// ─── helpers ────────────────────────────────────────────────────────────────

function seedFixtures() {
  cy.task('kvSeedFixtures')
}

function clearFixtures() {
  cy.task('kvClearFixtures')
}

function visitCapture() {
  cy.visit(PAGE)
  cy.get('.kv-main', { timeout: 10000 }).should('be.visible')
  cy.wait(300)
}

function setArchive(on: boolean) {
  cy.get('button:has-text("Archive")').then($btn => {
    const isActive = $btn.hasClass('kv-btn-active') || $btn.css('color').includes('255, 159')
    if (on !== isActive) cy.wrap($btn).click()
  })
  cy.wait(300)
}

function clickViewMode(mode: 'Normal' | 'All' | 'Ungrouped') {
  cy.get(`button.kv-seg-btn:contains("${mode}")`).click()
  cy.wait(200)
}

function navigateToGroup(name: string) {
  // Click the group card in the main area
  cy.contains('.kv-group-card .kv-gc-name', name).click()
  cy.wait(300)
}

function navigateToRoot() {
  // Click "All" in sidebar or breadcrumb
  cy.get('.sg-root').click()
  cy.wait(300)
}

function shouldShow(header: string) {
  cy.get('.kv-list').contains('.kv-row-title', header).should('exist')
}

function shouldHide(header: string) {
  cy.get('.kv-list').contains('.kv-row-title', header).should('not.exist')
}

// ─── suite ──────────────────────────────────────────────────────────────────

describe('Knowledge Vault — view-matrix', () => {
  before(() => {
    seedFixtures()
  })

  after(() => {
    clearFixtures()
  })

  beforeEach(() => {
    visitCapture()
  })

  // ── Column 1: Archive=off, Normal, at root "/" ────────────────────────────
  describe('Archive=off | Normal | root /', () => {
    beforeEach(() => {
      setArchive(false)
      clickViewMode('Normal')
      navigateToRoot()
    })

    it('shows Example-Top Group (group_id=root)', () => shouldShow('Example-Top Group'))
    it('hides Example-L1-1 (belongs to l1-1, not root)', () => shouldHide('Example-L1-1'))
    it('hides Example-L1-2', () => shouldHide('Example-L1-2'))
    it('hides Example-L2-1', () => shouldHide('Example-L2-1'))
    it('hides Example-ungroup (group_id=null, never in Normal)', () => shouldHide('Example-ungroup'))
    it('hides all Archive-* fragments', () => {
      shouldHide('Archive-Example-Top Group')
      shouldHide('Archive-Example-L1-1')
      shouldHide('Archive-Example-L1-2')
      shouldHide('Archive-Example-L2-1')
      shouldHide('Archive-Example-ungroup')
    })
  })

  // ── Column 2: Archive=off, All ────────────────────────────────────────────
  describe('Archive=off | All', () => {
    beforeEach(() => {
      setArchive(false)
      clickViewMode('All')
    })

    it('shows all 5 non-archived fixtures', () => {
      shouldShow('Example-Top Group')
      shouldShow('Example-L1-1')
      shouldShow('Example-L1-2')
      shouldShow('Example-L2-1')
      shouldShow('Example-ungroup')
    })
    it('hides all archived fixtures', () => {
      shouldHide('Archive-Example-Top Group')
      shouldHide('Archive-Example-L1-1')
      shouldHide('Archive-Example-L1-2')
      shouldHide('Archive-Example-L2-1')
      shouldHide('Archive-Example-ungroup')
    })
  })

  // ── Column 3: Archive=off, Ungrouped ─────────────────────────────────────
  describe('Archive=off | Ungrouped', () => {
    beforeEach(() => {
      setArchive(false)
      clickViewMode('Ungrouped')
    })

    it('shows Example-ungroup (group_id=null, not archived)', () => shouldShow('Example-ungroup'))
    it('hides grouped non-archived fragments', () => {
      shouldHide('Example-Top Group')
      shouldHide('Example-L1-1')
      shouldHide('Example-L1-2')
      shouldHide('Example-L2-1')
    })
    it('hides all archived fixtures', () => {
      shouldHide('Archive-Example-Top Group')
      shouldHide('Archive-Example-L1-1')
      shouldHide('Archive-Example-L1-2')
      shouldHide('Archive-Example-L2-1')
      shouldHide('Archive-Example-ungroup')
    })
  })

  // ── Column 4: Archive=on, Normal, at root "/" ─────────────────────────────
  describe('Archive=on | Normal | root /', () => {
    beforeEach(() => {
      setArchive(true)
      clickViewMode('Normal')
      navigateToRoot()
    })

    it('shows Archive-Example-Top Group (group_id=root, archived)', () => {
      shouldShow('Archive-Example-Top Group')
    })
    it('hides non-archived fragments', () => {
      shouldHide('Example-Top Group')
      shouldHide('Example-L1-1')
      shouldHide('Example-L1-2')
      shouldHide('Example-L2-1')
      shouldHide('Example-ungroup')
    })
    it('hides archive fragments in named groups', () => {
      shouldHide('Archive-Example-L1-1')
      shouldHide('Archive-Example-L1-2')
      shouldHide('Archive-Example-L2-1')
    })
    it('hides Archive-Example-ungroup (group_id=null, never in Normal)', () => {
      shouldHide('Archive-Example-ungroup')
    })
  })

  // ── Column 5: Archive=on, All ─────────────────────────────────────────────
  describe('Archive=on | All', () => {
    beforeEach(() => {
      setArchive(true)
      clickViewMode('All')
    })

    it('shows all 5 archived fixtures', () => {
      shouldShow('Archive-Example-Top Group')
      shouldShow('Archive-Example-L1-1')
      shouldShow('Archive-Example-L1-2')
      shouldShow('Archive-Example-L2-1')
      shouldShow('Archive-Example-ungroup')
    })
    it('hides all non-archived fixtures', () => {
      shouldHide('Example-Top Group')
      shouldHide('Example-L1-1')
      shouldHide('Example-L1-2')
      shouldHide('Example-L2-1')
      shouldHide('Example-ungroup')
    })
  })

  // ── Column 6: Archive=on, Ungrouped ──────────────────────────────────────
  describe('Archive=on | Ungrouped', () => {
    beforeEach(() => {
      setArchive(true)
      clickViewMode('Ungrouped')
    })

    it('shows Archive-Example-ungroup (group_id=null, archived)', () => {
      shouldShow('Archive-Example-ungroup')
    })
    it('hides grouped archived fragments', () => {
      shouldHide('Archive-Example-Top Group')
      shouldHide('Archive-Example-L1-1')
      shouldHide('Archive-Example-L1-2')
      shouldHide('Archive-Example-L2-1')
    })
    it('hides all non-archived fixtures', () => {
      shouldHide('Example-Top Group')
      shouldHide('Example-L1-1')
      shouldHide('Example-L1-2')
      shouldHide('Example-L2-1')
      shouldHide('Example-ungroup')
    })
  })

  // ── Column 7: Archive=off, Normal, inside named groups ────────────────────
  describe('Archive=off | Normal | inside named groups', () => {
    beforeEach(() => {
      setArchive(false)
      clickViewMode('Normal')
    })

    it('shows Example-L1-1 when navigated into l1-1', () => {
      navigateToGroup('l1-1')
      shouldShow('Example-L1-1')
      shouldHide('Archive-Example-L1-1')
    })

    it('shows Example-L1-2 when navigated into l1-2', () => {
      navigateToGroup('l1-1')
      navigateToGroup('l1-2')
      shouldShow('Example-L1-2')
      shouldHide('Archive-Example-L1-2')
    })

    it('shows Example-L2-1 when navigated into l2-1', () => {
      navigateToGroup('l2-1')
      shouldShow('Example-L2-1')
      shouldHide('Archive-Example-L2-1')
    })

    it('shows Example-Top Group at root level in Normal view', () => {
      navigateToRoot()
      shouldShow('Example-Top Group')
    })

    it('Example-ungroup is hidden in every group including root', () => {
      // root
      navigateToRoot()
      shouldHide('Example-ungroup')
      // named group
      navigateToGroup('l1-1')
      shouldHide('Example-ungroup')
    })
  })

  // ── Column 8: Archive=on, Normal, inside named groups ─────────────────────
  describe('Archive=on | Normal | inside named groups', () => {
    beforeEach(() => {
      setArchive(true)
      clickViewMode('Normal')
    })

    it('shows Archive-Example-L1-1 when navigated into l1-1', () => {
      navigateToGroup('l1-1')
      shouldShow('Archive-Example-L1-1')
      shouldHide('Example-L1-1')
    })

    it('shows Archive-Example-L1-2 when navigated into l1-2', () => {
      navigateToGroup('l1-1')
      navigateToGroup('l1-2')
      shouldShow('Archive-Example-L1-2')
      shouldHide('Example-L1-2')
    })

    it('shows Archive-Example-L2-1 when navigated into l2-1', () => {
      navigateToGroup('l2-1')
      shouldShow('Archive-Example-L2-1')
      shouldHide('Example-L2-1')
    })

    it('shows Archive-Example-Top Group at root level', () => {
      navigateToRoot()
      shouldShow('Archive-Example-Top Group')
    })

    it('Archive-Example-ungroup is hidden in every group including root', () => {
      navigateToRoot()
      shouldHide('Archive-Example-ungroup')
      navigateToGroup('l1-1')
      shouldHide('Archive-Example-ungroup')
    })
  })
})
