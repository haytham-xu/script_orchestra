/**
 * PhotoClassifier E2E Tests - Group Batch Operations
 *
 * This test suite covers group batch page operations:
 * - Batch removing files from groups
 * - Canceling remove operations
 * - Shift range selection
 * - Infinite scroll
 * - Edge cases (no selection)
 */

describe('PhotoClassifier - Group Batch Operations', () => {
  const TEST_DATA_ROOT = '/Users/I353667/Documents/code/github/script_orchestra/backend/cypress_test_data/photo_classifier'

  before(() => {
    cy.enableTestMode('photo_classifier', {
      rootPath: TEST_DATA_ROOT
    })
    cy.cleanupTest()
  })

  after(() => {
    // Config restore and cleanup are handled in 99-cleanup.cy.ts
  })

  beforeEach(() => {
    cy.checkBackendHealth()

    // Reset store to ensure test isolation
    // This prevents state pollution from previous tests
    cy.resetPhotoClassifierStore()
  })

  /**
   * Case 29: Batch remove from group
   */
  it('should remove selected files from group', () => {
    const testName = 'test_group_batch_remove'

    cy.setupTest({
      testName: testName,
      images: 6,
      videos: 0,
      prefix: 'img'
    }).then((setup) => {
      const testDir = setup.testDir

      cy.loadTestMedia(testDir)
      cy.goToDefaultGroup()

      cy.get('.main-image').should('be.visible')
      cy.wait(500)

      // Add all 6 files to group 0
      cy.pressKey('KeyQ')  // File 1 -> group 0, Q auto-advances to file 2
      cy.wait(300)
      for (let i = 0; i < 5; i++) {
        cy.pressKey('KeyW')  // W auto-advances to next file
        cy.wait(300)
      }

      // Navigate to group batch mode
      cy.visit('/photo-classifier/group/0/batch')
      cy.wait(2000) // Further increase wait time for batch page load

      // Wait for grid to be visible
      cy.get('.image-grid', { timeout: 15000 }).should('be.visible')

      // Should have 6 files
      cy.get('.image-card', { timeout: 15000 }).should('have.length', 6)

      // Select files at indices 0, 2, 4 (files 1, 3, 5)
      cy.selectImageByIndex(0)
      cy.selectImageByIndex(2)
      cy.selectImageByIndex(4)
      cy.verifySelectionCount(3)

      // Remove selected
      cy.clickRemoveSelected()
      cy.wait(300)

      // Confirm dialog
      cy.confirmDialog()
      cy.wait(500)

      // Should now have 3 files remaining
      cy.get('.image-card', { timeout: 10000 }).should('have.length', 3)

      // Verify by going to group view
      cy.visit('/photo-classifier/group/0')
      cy.wait(1000) // Wait for store initialization
      cy.get('.header-progress', { timeout: 10000 }).should('contain', '1 / 3')

      cy.log('✅ Case 29 completed')
    })
  })

  /**
   * Case 30: Cancel remove operation
   */
  it('should cancel remove operation when user clicks cancel', () => {
    const testName = 'test_group_batch_cancel'

    cy.setupTest({
      testName: testName,
      images: 4,
      videos: 0,
      prefix: 'img'
    }).then((setup) => {
      const testDir = setup.testDir

      cy.loadTestMedia(testDir)
      cy.goToDefaultGroup()

      cy.get('.main-image').should('be.visible')
      cy.wait(500)

      // Add all files to group 0
      cy.pressKey('KeyQ')  // File 1 -> group 0, Q auto-advances to file 2
      cy.wait(300)
      for (let i = 0; i < 3; i++) {
        cy.pressKey('KeyW')  // W auto-advances to next file
        cy.wait(300)
      }

      // Go to batch mode
      cy.visit('/photo-classifier/group/0/batch')
      cy.wait(2000) // Increase wait for batch page load

      // Select 2 files
      cy.selectImageByIndex(0)
      cy.selectImageByIndex(1)
      cy.verifySelectionCount(2)

      // Try to remove
      cy.clickRemoveSelected()
      cy.wait(300)

      // Cancel dialog
      cy.cancelDialog()
      cy.wait(300)

      // Should still have 4 files
      cy.get('.image-card', { timeout: 10000 }).should('have.length', 4)

      // Selection should be maintained
      cy.verifySelectionCount(2)

      cy.log('✅ Case 30 completed')
    })
  })

  /**
   * Case 31: Shift range selection in group batch
   */
  it('should select range with shift in group batch', () => {
    const testName = 'test_group_batch_shift'

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

      // Add all files to group 0
      cy.pressKey('KeyQ')  // File 1 -> group 0, Q auto-advances to file 2
      cy.wait(300)
      for (let i = 0; i < 9; i++) {
        cy.pressKey('KeyW')  // W auto-advances to next file
        cy.wait(300)
      }

      // Go to batch mode
      cy.visit('/photo-classifier/group/0/batch')
      cy.wait(2000) // Increase wait for batch page load

      // Shift select range from 2 to 6 (5 files)
      cy.shiftSelectImageRange(2, 6)
      cy.verifySelectionCount(5)

      cy.log('✅ Case 31 completed')
    })
  })

  /**
   * Case 32: Infinite scroll in group batch
   */
  it('should load more files on scroll in group batch', () => {
    const testName = 'test_group_batch_scroll'

    cy.setupTest({
      testName: testName,
      images: 150,
      videos: 0,
      prefix: 'img'
    }).then((setup) => {
      const testDir = setup.testDir

      cy.loadTestMedia(testDir)
      cy.goToDefaultGroup()

      cy.get('.main-image').should('be.visible')
      cy.wait(500)

      // Add all files to group 0 (this will take a while)
      // For testing purposes, we'll use the API directly or batch select
      cy.visit('/photo-classifier')
      cy.clickBatchSelectButton()
      cy.wait(500)

      // Select all and create group
      cy.get('.image-card').first().click()
      cy.get('.image-card').eq(99).click({ shiftKey: true })
      cy.wait(300)
      cy.clickCreateNewGroup()
      cy.wait(1000)

      // Add remaining files
      cy.get('.image-card').first().click()
      cy.get('.image-card').eq(49).click({ shiftKey: true })
      cy.wait(300)
      cy.clickAddToExistingGroup()
      cy.wait(500) // Wait for drawer to open
      cy.get('.el-drawer', { timeout: 5000 }).should('be.visible')
      cy.wait(300) // Wait for group cards in drawer to render
      cy.get('.el-drawer .group-card', { timeout: 10000 }).should('exist')
      cy.get('.el-drawer .group-card').first().within(() => {
        cy.contains('button', 'Add').click()
      })
      cy.wait(1000)

      // Go to group batch
      cy.visit('/photo-classifier/group/0/batch')
      cy.wait(2000) // Increase wait for batch page load

      // Initially should show 100 files
      cy.get('.image-card', { timeout: 15000 }).should('have.length', 100)

      // Scroll to bottom
      cy.get('.image-grid').scrollTo('bottom')
      cy.wait(1000)

      // Should load more
      cy.get('.image-card', { timeout: 15000 }).should('have.length.gt', 100)

      cy.log('✅ Case 32 completed')
    })
  })

  /**
   * Case 33: No selection warning in group batch
   */
  it('should show warning when removing without selection', () => {
    const testName = 'test_group_batch_no_selection'

    cy.setupTest({
      testName: testName,
      images: 4,
      videos: 0,
      prefix: 'img'
    }).then((setup) => {
      const testDir = setup.testDir

      cy.loadTestMedia(testDir)
      cy.goToDefaultGroup()

      cy.get('.main-image').should('be.visible')
      cy.wait(500)

      // Add all files to group 0
      cy.pressKey('KeyQ')  // File 1 -> group 0, Q auto-advances to file 2
      cy.wait(300)
      for (let i = 0; i < 3; i++) {
        cy.pressKey('KeyW')  // W auto-advances to next file
        cy.wait(300)
      }

      // Go to batch mode
      cy.visit('/photo-classifier/group/0/batch')
      cy.wait(2000) // Increase wait for batch page load

      // Try to remove without selecting anything - button should be disabled
      cy.contains('button', '移除选中').should('be.disabled')

      cy.log('✅ Case 33 completed')
    })
  })
})
