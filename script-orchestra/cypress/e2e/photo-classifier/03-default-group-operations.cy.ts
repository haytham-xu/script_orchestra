/**
 * PhotoClassifier E2E Tests - Default Group Operations
 *
 * This test suite covers advanced default group operations:
 * - Marking files with different categories (del, best, better, normal)
 * - Creating and managing groups (Q, W keys)
 * - Using group drawer
 * - Filter toggling
 * - Edge cases (empty list, single file, navigation boundaries, direct URL access)
 */

describe('PhotoClassifier - Default Group Operations', () => {
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
   * Case 6: Mark files as del
   */
  it('should mark files as del and verify deletion', () => {
    const testName = 'test_mark_del'

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

      // Mark pattern: 1=normal, 2=del, 3=normal, 4=del
      cy.markAs('normal')
      cy.goToNextImage()
      cy.markAs('del')
      cy.goToNextImage()
      cy.markAs('normal')
      cy.goToNextImage()
      cy.markAs('del')

      cy.pressKey('Enter')
      // Don't wait - verifyFileDistribution will retry

      cy.verifyFileDistribution({
        testDir: testDir,
        expected: {
          normal: 2,
          del: 2,
          best: 0,
          better: 0,
          remaining: 0
        },
        maxRetries: 20,
        retryDelay: 1000
      })

      cy.log('✅ Case 6 completed')
    })
  })

  /**
   * Case 7: Create new groups with Q key
   */
  it('should create new groups using Q key', () => {
    const testName = 'test_create_groups'

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

      // Create group 0 with file 1
      cy.pressKey('KeyQ')  // Q auto-advances to file 2
      cy.wait(300)

      // Navigate to file 3 and create group 1
      cy.goToNextImage()  // Now at file 3
      cy.pressKey('KeyQ')  // Q auto-advances to file 4
      cy.wait(300)

      // Verify groups created (check success messages or group count)
      // Note: We can't directly verify Vue store from Cypress,
      // but we can verify by going back to dashboard and checking group cards
      // Dashboard shows: 1 default group card + 2 custom group cards = 3 total
      cy.visit('/photo-classifier')
      cy.get('.group-card', { timeout: 10000 }).should('have.length', 3)

      cy.log('✅ Case 7 completed - 2 groups created')
    })
  })

  /**
   * Case 8: Add to existing group with W key
   */
  it('should add files to existing group using W key', () => {
    const testName = 'test_add_to_group'

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

      // Create group 0 with file 1
      cy.pressKey('KeyQ')  // Q auto-advances to file 2
      cy.wait(300)

      // Add file 2 to group 0
      cy.pressKey('KeyW')  // W auto-advances to file 3
      cy.wait(300)

      // Create group 1 with file 3
      cy.pressKey('KeyQ')  // Q auto-advances to file 4
      cy.wait(300)

      // Add file 4 to group 1
      cy.pressKey('KeyW')  // W auto-advances (no more files)
      cy.wait(300)

      // Verify by going to dashboard
      // Dashboard shows: 1 default group + 2 custom groups = 3 total
      // Note: defaultGroup.files always contains all files (full set), even if they're grouped
      cy.visit('/photo-classifier')
      cy.wait(500) // Wait for Vue to update after all operations
      cy.get('.group-card', { timeout: 10000 }).should('have.length', 3)

      // Verify group 0 has 2 files (first custom group card is at index 1, after default group)
      cy.get('.group-card').eq(1).click()
      cy.url().should('include', '/group/0')
      cy.verifyIndexDisplay('1 / 2')

      cy.log('✅ Case 8 completed')
    })
  })

  /**
   * Case 9: Use group drawer to add files
   */
  it('should use group drawer to add files to groups', () => {
    const testName = 'test_group_drawer'

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

      // Create 2 groups first
      cy.pressKey('KeyQ')  // Group 0, Q auto-advances to file 2
      cy.wait(300)
      cy.pressKey('KeyQ')  // Group 1, Q auto-advances to file 3
      cy.wait(300)

      // Open group drawer
      cy.openGroupDrawer()

      // Navigate to file 3 and add to group 0
      cy.goToNextImage()
      cy.clickGroupCardAdd(0)
      cy.wait(300)

      // Navigate to file 4 and add to group 1
      cy.goToNextImage()
      cy.clickGroupCardAdd(1)
      cy.wait(300)

      // Verify by checking dashboard
      // Dashboard shows: 1 default group card + 2 custom group cards = 3 total
      cy.visit('/photo-classifier')
      cy.get('.group-card').should('have.length', 3)

      cy.log('✅ Case 9 completed')
    })
  })

  /**
   * Case 10: Toggle unidentified filter
   */
  it('should filter unidentified files correctly', () => {
    const testName = 'test_filter_unidentified'

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

      // Add files 1,2,3 to groups
      cy.pressKey('KeyQ')  // File 1 -> group 0, Q auto-advances to file 2
      cy.wait(300)
      cy.pressKey('KeyW')  // File 2 -> group 0, W auto-advances to file 3
      cy.wait(300)
      cy.pressKey('KeyW')  // File 3 -> group 0, W auto-advances to file 4
      cy.wait(300)

      // Before filtering, we're at file 4 (index 4/6)
      // After adding files 1,2,3 to group, we auto-advanced to file 4
      cy.verifyIndexDisplay('4 / 6')

      // Toggle unidentified filter - should keep showing file 4 (first ungrouped file)
      cy.toggleUnidentifiedFilter()
      cy.wait(500)

      // Should show only 3 ungrouped files (4, 5, 6), file 4 is now at position 1
      cy.verifyIndexDisplay('1 / 3')

      cy.log('✅ Case 10 completed')
    })
  })

  /**
   * Case 11: Empty file list boundary
   */
  it('should handle empty file list gracefully', () => {
    const testName = 'test_empty_list'

    cy.setupTest({
      testName: testName,
      images: 0,
      videos: 0,
      prefix: 'img'
    }).then((setup) => {
      const testDir = setup.testDir

      cy.loadTestMedia(testDir)

      // With 0 files, default group card won't be shown (v-if condition)
      // So go directly to default group URL, no need to check dashboard
      cy.visit('/photo-classifier/default-group')

      cy.wait(500)

      // Verify 0/0 display
      cy.verifyIndexDisplay('0 / 0')

      // Verify mark all normal doesn't crash
      cy.markAllNormal()
      cy.wait(200)

      // Verify no errors
      cy.log('✅ Case 11 completed - handled empty list')
    })
  })

  /**
   * Case 12: Single file boundary
   */
  it('should handle single file correctly', () => {
    const testName = 'test_single_file'

    cy.setupTest({
      testName: testName,
      images: 1,
      videos: 0,
      prefix: 'img'
    }).then((setup) => {
      const testDir = setup.testDir

      cy.loadTestMedia(testDir)
      cy.goToDefaultGroup()

      cy.get('.main-image').should('be.visible')
      cy.wait(500)

      cy.verifyIndexDisplay('1 / 1')

      // Mark as best and apply
      cy.markAs('best')
      cy.pressKey('Enter')
      // Don't wait - verifyFileDistribution will retry

      cy.verifyFileDistribution({
        testDir: testDir,
        expected: {
          best: 1,
          remaining: 0
        },
        maxRetries: 15,
        retryDelay: 1000
      })

      cy.log('✅ Case 12 completed')
    })
  })

  /**
   * Case 13: Navigation boundaries
   */
  it('should respect navigation boundaries', () => {
    const testName = 'test_navigation_boundary'

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

      // Should start at 1/3
      cy.verifyIndexDisplay('1 / 3')

      // Press left 10 times - should stay at 1/3
      for (let i = 0; i < 10; i++) {
        cy.pressKey('ArrowLeft')
        cy.wait(50)
      }
      cy.verifyIndexDisplay('1 / 3')

      // Go to last file
      cy.pressKey('ArrowRight')
      cy.pressKey('ArrowRight')
      cy.verifyIndexDisplay('3 / 3')

      // Press right 10 times - should stay at 3/3
      for (let i = 0; i < 10; i++) {
        cy.pressKey('ArrowRight')
        cy.wait(50)
      }
      cy.verifyIndexDisplay('3 / 3')

      cy.log('✅ Case 13 completed')
    })
  })

  /**
   * Case 14: Direct URL access / page refresh
   */
  it('should handle direct URL access correctly', () => {
    const testName = 'test_direct_url_access'

    cy.setupTest({
      testName: testName,
      images: 4,
      videos: 0,
      prefix: 'img'
    }).then((setup) => {
      const testDir = setup.testDir

      // Set up test media but don't navigate through UI
      cy.loadTestMedia(testDir)

      // Directly visit default group URL
      cy.visit('/photo-classifier/default-group')

      cy.get('.main-image', { timeout: 10000 }).should('be.visible')
      cy.wait(500)

      // Should show 4 files (not 0/0)
      cy.verifyIndexDisplay('1 / 4')

      // Verify files are loaded and can be navigated
      cy.pressKey('ArrowRight')
      cy.verifyIndexDisplay('2 / 4')

      cy.log('✅ Case 14 completed - direct URL access works')
    })
  })
})
