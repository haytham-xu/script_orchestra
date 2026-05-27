/**
 * PhotoClassifier E2E Tests - Batch Select Operations
 *
 * This test suite covers batch select page operations:
 * - Single selection and deselection
 * - Shift range selection
 * - Creating new groups (batch)
 * - Adding to existing groups (batch)
 * - Filter toggling
 * - Clear selection
 * - Edge cases and validation
 * - Infinite scroll
 */

describe('PhotoClassifier - Batch Select Operations', () => {
  const TEST_DATA_ROOT = '/Users/I353667/Documents/code/github/script_orchestra/backend/cypress_test_data/photo_classifier'

  before(() => {
    // Enable test mode (saves snapshot and sets test config)
    cy.enableTestMode('photo_classifier', {
      rootPath: TEST_DATA_ROOT
    })
    cy.cleanupTest()
  })

  after(() => {
    // Restore config and cleanup test data after this file completes
    cy.disableTestMode('photo_classifier')
    cy.cleanupTest()
  })

  beforeEach(() => {
    cy.checkBackendHealth()

    // Reset store to ensure test isolation
    // This prevents state pollution from previous tests
    cy.resetPhotoClassifierStore()
  })

  /**
   * Case 20: Single selection and deselection
   */
  it('should select and deselect files individually', () => {
    const testName = 'test_single_selection'

    cy.setupTest({
      testName: testName,
      images: 6,
      videos: 0,
      prefix: 'img'
    }).then((setup) => {
      const testDir = setup.testDir

      cy.loadTestMedia(testDir)

      // Navigate to batch select
      cy.clickBatchSelectButton()
      cy.wait(500)

      // Select file 1
      cy.selectImageByIndex(0)
      cy.verifySelectionCount(1)

      // Select file 3
      cy.selectImageByIndex(2)
      cy.verifySelectionCount(2)

      // Deselect file 1
      cy.selectImageByIndex(0)
      cy.verifySelectionCount(1)

      cy.log('✅ Case 20 completed')
    })
  })

  /**
   * Case 21: Shift range selection
   */
  it('should select range of files with Shift', () => {
    const testName = 'test_shift_selection'

    cy.setupTest({
      testName: testName,
      images: 10,
      videos: 0,
      prefix: 'img'
    }).then((setup) => {
      const testDir = setup.testDir

      cy.loadTestMedia(testDir)
      cy.clickBatchSelectButton()
      cy.wait(500)

      // Select range from index 1 to 5 (files 2-6, total 5 files)
      cy.shiftSelectImageRange(1, 5)
      cy.verifySelectionCount(5)

      cy.log('✅ Case 21 completed')
    })
  })

  /**
   * Case 22: Create new group (batch)
   */
  it('should create new group with selected files', () => {
    const testName = 'test_batch_create_group'

    cy.setupTest({
      testName: testName,
      images: 8,
      videos: 0,
      prefix: 'img'
    }).then((setup) => {
      const testDir = setup.testDir

      cy.loadTestMedia(testDir)
      cy.clickBatchSelectButton()
      cy.wait(500)

      // Select files 1, 3, 5 (indices 0, 2, 4)
      cy.selectImageByIndex(0)
      cy.selectImageByIndex(2)
      cy.selectImageByIndex(4)
      cy.verifySelectionCount(3)

      // Create new group
      cy.clickCreateNewGroup()
      cy.wait(500)

      // Verify success message appeared
      // Verify selection was cleared
      cy.verifySelectionCount(0)

      // Go back to dashboard and verify group was created
      // Dashboard shows: 1 default group card (5 remaining files) + 1 custom group card = 2 total
      cy.visit('/photo-classifier')
      cy.get('.group-card', { timeout: 10000 }).should('have.length', 2)

      cy.log('✅ Case 22 completed')
    })
  })

  /**
   * Case 23: Add to existing group (batch)
   */
  it('should add selected files to existing group', () => {
    const testName = 'test_batch_add_to_group'

    cy.setupTest({
      testName: testName,
      images: 8,
      videos: 0,
      prefix: 'img'
    }).then((setup) => {
      const testDir = setup.testDir

      cy.loadTestMedia(testDir)
      cy.goToDefaultGroup()

      cy.get('.main-image').should('be.visible')
      cy.wait(500)

      // Create group 0 with first 2 files
      cy.pressKey('KeyQ')  // File 1 -> group 0, Q auto-advances to file 2
      cy.wait(300)
      cy.pressKey('KeyW')  // File 2 -> group 0, W auto-advances to file 3
      cy.wait(300)

      // Go back and enter batch select
      cy.visit('/photo-classifier')
      cy.clickBatchSelectButton()
      cy.wait(500)

      // Select files 3, 4, 5 (indices 2, 3, 4)
      cy.selectImageByIndex(2)
      cy.selectImageByIndex(3)
      cy.selectImageByIndex(4)
      cy.verifySelectionCount(3)

      // Add to existing group
      cy.clickAddToExistingGroup()
      cy.wait(500) // Increase wait for drawer to open

      // Select group 0 from drawer
      cy.get('.el-drawer', { timeout: 5000 }).should('be.visible')
      cy.wait(300) // Wait for group items in drawer to render
      cy.get('.el-drawer .group-item', { timeout: 10000 }).should('exist')
      cy.get('.el-drawer .group-item').eq(0).click()
      cy.wait(500)

      // Verify drawer closed and selection cleared
      cy.verifySelectionCount(0)

      // Verify group 0 now has 5 files
      cy.visit('/photo-classifier/group/0')
      cy.wait(1000) // Wait for store initialization
      cy.get('.header-progress', { timeout: 10000 }).should('contain', '1 / 5')

      cy.log('✅ Case 23 completed')
    })
  })

  /**
   * Case 24: Toggle "only ungrouped" filter
   */
  it('should filter ungrouped files correctly', () => {
    const testName = 'test_batch_filter'

    cy.setupTest({
      testName: testName,
      images: 10,
      videos: 0,
      prefix: 'img'
    }).then((setup) => {
      const testDir = setup.testDir

      cy.loadTestMedia(testDir)
      cy.goToDefaultGroup()

      cy.get('.main-image').should('be.visible')
      cy.wait(500)

      // Add first 3 files to group 0
      cy.pressKey('KeyQ')  // File 1 -> group 0, Q auto-advances to file 2
      cy.wait(300)
      cy.pressKey('KeyW')  // File 2 -> group 0, W auto-advances to file 3
      cy.wait(300)
      cy.pressKey('KeyW')  // File 3 -> group 0, W auto-advances to file 4
      cy.wait(300)

      // Go to batch select
      cy.visit('/photo-classifier')
      cy.clickBatchSelectButton()
      cy.wait(500)

      // Should show all 10 files initially
      cy.get('.image-card').should('have.length', 10)

      // Toggle filter to show only ungrouped
      cy.toggleUnidentifiedFilter()
      cy.wait(500)

      // Should show only 7 ungrouped files
      cy.get('.image-card').should('have.length', 7)

      // Select 2 files
      cy.selectImageByIndex(0)
      cy.selectImageByIndex(1)
      cy.verifySelectionCount(2)

      // Toggle filter back - selection should be cleared
      cy.toggleUnidentifiedFilter()
      cy.wait(500)
      cy.verifySelectionCount(0)

      cy.log('✅ Case 24 completed')
    })
  })

  /**
   * Case 25: Clear selection
   */
  it('should clear selection when button clicked', () => {
    const testName = 'test_clear_selection'

    cy.setupTest({
      testName: testName,
      images: 6,
      videos: 0,
      prefix: 'img'
    }).then((setup) => {
      const testDir = setup.testDir

      cy.loadTestMedia(testDir)
      cy.clickBatchSelectButton()
      cy.wait(500)

      // Select 3 files
      cy.selectImageByIndex(0)
      cy.selectImageByIndex(1)
      cy.selectImageByIndex(2)
      cy.verifySelectionCount(3)

      // Clear selection
      cy.clickClearSelection()
      cy.verifySelectionCount(0)

      cy.log('✅ Case 25 completed')
    })
  })

  /**
   * Case 26: No selection warning
   */
  it('should show warning when no files selected', () => {
    const testName = 'test_no_selection_warning'

    cy.setupTest({
      testName: testName,
      images: 4,
      videos: 0,
      prefix: 'img'
    }).then((setup) => {
      const testDir = setup.testDir

      cy.loadTestMedia(testDir)
      cy.clickBatchSelectButton()
      cy.wait(500)

      // Try to create group without selection - button should be disabled
      // Verify button is disabled
      cy.contains('button', '创建新分组').should('be.disabled')

      // Try to add to existing group - button should be disabled
      cy.contains('button', '添加到分组').should('be.disabled')

      cy.log('✅ Case 26 completed')
    })
  })

  /**
   * Case 27: Select all files
   */
  it('should select all files with shift range', () => {
    const testName = 'test_select_all'

    cy.setupTest({
      testName: testName,
      images: 5,
      videos: 0,
      prefix: 'img'
    }).then((setup) => {
      const testDir = setup.testDir

      cy.loadTestMedia(testDir)
      cy.clickBatchSelectButton()
      cy.wait(500)

      // Select all by shift-clicking first and last
      cy.shiftSelectImageRange(0, 4)
      cy.verifySelectionCount(5)

      // Create group with all files
      cy.clickCreateNewGroup()
      cy.wait(1500) // Further increase wait time for group creation and Vue updates

      // Verify dashboard shows: 1 default group + 1 custom group = 2 total
      // Note: defaultGroup.files still contains all 5 files (fileStatus=IN_GROUP)
      cy.visit('/photo-classifier')
      cy.wait(1000) // Wait for Vue to recalculate group cards
      cy.get('.group-card', { timeout: 10000 }).should('have.length', 2)

      cy.log('✅ Case 27 completed')
    })
  })

  /**
   * Case 28: Infinite scroll loading
   */
  it('should load more files on scroll', () => {
    const testName = 'test_infinite_scroll'

    cy.setupTest({
      testName: testName,
      images: 150,
      videos: 0,
      prefix: 'img'
    }).then((setup) => {
      const testDir = setup.testDir

      cy.loadTestMedia(testDir)
      cy.clickBatchSelectButton()
      cy.wait(500)

      // Initially should load 100 files (pageSize)
      cy.get('.image-card').should('have.length', 100)

      // Scroll to bottom
      cy.get('.image-grid').scrollTo('bottom')
      cy.wait(1000) // Wait for more to load

      // Should have loaded more (up to 150 total)
      cy.get('.image-card').should('have.length', 150)

      cy.log('✅ Case 28 completed')
    })
  })
})
