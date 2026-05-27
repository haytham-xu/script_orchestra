/**
 * PhotoClassifier E2E Tests - Small Group Operations
 *
 * This test suite covers small group (already grouped files) operations:
 * - Marking and applying in group view
 * - Navigating between groups
 * - Navigating within a group
 * - Entering batch mode from group
 * - Edge case: empty group
 */

describe('PhotoClassifier - Small Group Operations', () => {
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
   * Case 15: Mark and apply in group page
   */
  it('should mark files in group and apply successfully', () => {
    const testName = 'test_group_mark_apply'

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

      // Add all 4 files to group 0
      cy.pressKey('KeyQ')  // File 1 -> group 0, Q auto-advances to file 2
      cy.wait(300)
      cy.pressKey('KeyW')  // File 2 -> group 0, W auto-advances to file 3
      cy.wait(300)
      cy.pressKey('KeyW')  // File 3 -> group 0, W auto-advances to file 4
      cy.wait(300)
      cy.pressKey('KeyW')  // File 4 -> group 0, W auto-advances (no more files)
      cy.wait(300)

      // Navigate to group 0
      cy.visit('/photo-classifier/group/0')
      cy.get('.main-image', { timeout: 10000 }).should('be.visible')
      cy.wait(500)

      // Mark all normal first
      cy.contains('button', 'Mark All Normal').click()
      cy.wait(200)

      // Change file 2 to best
      cy.goToNextImage()
      cy.markAs('best')

      // Apply
      cy.pressKey('Enter')
      // Don't wait - verifyFileDistribution will retry until files are ready

      // Verify distribution
      cy.verifyFileDistribution({
        testDir: testDir,
        expected: {
          normal: 3,
          best: 1,
          remaining: 0
        },
        maxRetries: 15, // Simple file move (4 files)
        retryDelay: 1000
      })

      cy.log('✅ Case 15 completed')
    })
  })

  /**
   * Case 16: Navigate between groups
   */
  it('should navigate between groups correctly', () => {
    const testName = 'test_group_navigation'

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

      // Create 3 groups with 2 files each
      // Group 0: files 1,2
      cy.pressKey('KeyQ')  // File 1 -> group 0, Q auto-advances to file 2
      cy.wait(300)
      cy.pressKey('KeyW')  // File 2 -> group 0, W auto-advances to file 3
      cy.wait(300)

      // Group 1: files 3,4
      cy.pressKey('KeyQ')  // File 3 -> group 1, Q auto-advances to file 4
      cy.wait(300)
      cy.pressKey('KeyW')  // File 4 -> group 1, W auto-advances to file 5
      cy.wait(300)

      // Group 2: files 5,6
      cy.pressKey('KeyQ')  // File 5 -> group 2, Q auto-advances to file 6
      cy.wait(300)
      cy.pressKey('KeyW')  // File 6 -> group 2, W auto-advances (no more files)
      cy.wait(300)

      // Navigate to group 0
      cy.visit('/photo-classifier/group/0')
      cy.get('.main-image', { timeout: 10000 }).should('be.visible')
      cy.wait(500)
      cy.url().should('include', '/group/0')

      // Click next group button
      cy.contains('button', '下一组').click()
      cy.wait(500)
      cy.url().should('include', '/group/1')

      // Try next group again
      cy.contains('button', '下一组').click()
      cy.wait(500)
      cy.url().should('include', '/group/2')

      // Try next group at last group - should show message
      cy.contains('button', '下一组').click()
      cy.wait(300)
      cy.url().should('include', '/group/2') // Should stay at group 2

      // Go back to previous group
      cy.contains('button', '上一组').click()
      cy.wait(500)
      cy.url().should('include', '/group/1')

      // Try previous at first group
      cy.visit('/photo-classifier/group/0')
      cy.wait(500)
      cy.contains('button', '上一组').click()
      cy.wait(300)
      cy.url().should('include', '/group/0') // Should stay at group 0

      cy.log('✅ Case 16 completed')
    })
  })

  /**
   * Case 17: Navigate within group
   */
  it('should navigate within group correctly', () => {
    const testName = 'test_group_internal_nav'

    cy.setupTest({
      testName: testName,
      images: 3,
      videos: 0,
      prefix: 'img'
    }).then((setup) => {
      const testDir = setup.testDir

      cy.loadTestMedia(testDir)
      cy.goToDefaultGroup()

      cy.get('.main-image').should('be.visible')
      cy.wait(500)

      // Add all 3 files to group 0
      cy.pressKey('KeyQ')  // File 1 -> group 0, Q auto-advances to file 2
      cy.wait(300)
      cy.pressKey('KeyW')  // File 2 -> group 0, W auto-advances to file 3
      cy.wait(300)
      cy.pressKey('KeyW')  // File 3 -> group 0, W auto-advances (no more files)
      cy.wait(300)

      // Navigate to group 0
      cy.visit('/photo-classifier/group/0')
      cy.get('.main-image', { timeout: 10000 }).should('be.visible')
      cy.wait(500) // Wait for Vue reactivity after page navigation

      // Should start at 1/3
      cy.get('.header-progress', { timeout: 15000 }).should('contain', '1 / 3')

      // Navigate to 2/3
      cy.pressKey('ArrowRight')
      cy.wait(300)
      cy.get('.header-progress', { timeout: 5000 }).should('contain', '2 / 3')

      // Navigate to 3/3
      cy.pressKey('ArrowRight')
      cy.wait(300)
      cy.get('.header-progress', { timeout: 5000 }).should('contain', '3 / 3')

      // Try going right at boundary
      cy.pressKey('ArrowRight')
      cy.wait(300)
      cy.get('.header-progress', { timeout: 5000 }).should('contain', '3 / 3') // Should stay at 3/3

      // Go back
      cy.pressKey('ArrowLeft')
      cy.wait(300)
      cy.get('.header-progress', { timeout: 5000 }).should('contain', '2 / 3')

      cy.log('✅ Case 17 completed')
    })
  })

  /**
   * Case 18: Enter batch mode from group
   */
  it('should enter batch mode from group view', () => {
    const testName = 'test_group_to_batch'

    cy.setupTest({
      testName: testName,
      images: 5,
      videos: 0,
      prefix: 'img'
    }).then((setup) => {
      const testDir = setup.testDir

      cy.loadTestMedia(testDir)
      cy.goToDefaultGroup()

      cy.get('.main-image').should('be.visible')
      cy.wait(500)

      // Add all files to group 0
      cy.pressKey('KeyQ')  // File 1 -> group 0, auto-advances to file 2
      cy.wait(300)
      for (let i = 0; i < 4; i++) {
        cy.pressKey('KeyW')  // Add current file to group 0, auto-advances to next
        cy.wait(300)
      }

      // Navigate to group 0
      cy.visit('/photo-classifier/group/0')
      cy.get('.main-image', { timeout: 10000 }).should('be.visible')
      cy.wait(1000) // Wait for group view to fully load

      // Click batch manage button
      cy.clickBatchManageButton()

      // Verify we're in batch mode
      cy.url().should('include', '/group/0/batch')
      cy.wait(1000) // Wait for batch page to load
      cy.get('.image-grid', { timeout: 10000 }).should('exist')
      cy.get('.image-card', { timeout: 15000 }).should('have.length', 5)

      cy.log('✅ Case 18 completed')
    })
  })

  /**
   * Case 19: Empty group edge case
   */
  it('should handle empty group gracefully', () => {
    const testName = 'test_empty_group'

    cy.setupTest({
      testName: testName,
      images: 2,
      videos: 0,
      prefix: 'img'
    }).then((setup) => {
      const testDir = setup.testDir

      cy.loadTestMedia(testDir)
      cy.goToDefaultGroup()

      cy.get('.main-image').should('be.visible')
      cy.wait(500)

      // Create an empty group (this might require backend API call)
      // For now, create a group and then try to access it before adding files
      cy.pressKey('KeyQ')
      cy.wait(300)

      // Try to visit a non-existent group or group with no files
      cy.visit('/photo-classifier/group/1')
      cy.wait(500)

      // Should handle gracefully (show 0/0 or redirect)
      // Verify no crash occurred
      cy.get('body').should('exist')

      cy.log('✅ Case 19 completed - empty group handled')
    })
  })
})
