/**
 * PhotoClassifier E2E Tests - Settings Page
 *
 * This test suite covers settings page operations:
 * - Changing root path and reloading
 * - Switching root path clears working state
 */

describe('PhotoClassifier - Settings Page', () => {
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
   * Case 1: Change root path and reload
   */
  it('should change root path and reload successfully', () => {
    const testNameA = 'test_path_a'

    cy.setupTest({
      testName: testNameA,
      images: 4,
      videos: 0,
      prefix: 'img'
    }).then((setupA) => {
      const testDirA = setupA.testDir

      // Visit photo classifier
      cy.visit('/photo-classifier')
      cy.wait(500)

      // Open settings drawer
      cy.get('[data-testid="settings-button"], .el-icon').first().click()
      cy.wait(300)
      cy.get('.el-drawer').should('be.visible')

      // Change root path to test directory A
      cy.get('.el-drawer').within(() => {
        cy.get('textarea').clear().type(testDirA)
        cy.contains('button', 'Save and Reload').click()
      })

      // Wait for page reload (might take a moment)
      cy.wait(2000)

      // Should be back on dashboard
      cy.url().should('include', '/photo-classifier')

      // Open settings again to verify current path
      cy.get('.el-icon').first().click()
      cy.wait(300)
      cy.get('.el-drawer').within(() => {
        cy.get('.current-path .path').should('contain', testDirA)
      })

      // Close drawer
      cy.get('.el-drawer__close-btn').click()
      cy.wait(300)

      // Verify we can see the 4 images
      cy.get('.group-card').should('exist')

      cy.log('✅ Case 1 completed')
    })
  })

  /**
   * Case 2: Switching root path clears working state
   */
  it('should clear working state when switching directories', () => {
    const testNameA = 'test_switch_a'
    const testNameB = 'test_switch_b'

    // Setup directory A with 4 images
    cy.setupTest({
      testName: testNameA,
      images: 4,
      videos: 0,
      prefix: 'img'
    }).then((setupA) => {
      const testDirA = setupA.testDir

      // Setup directory B with 3 images
      cy.setupTest({
        testName: testNameB,
        images: 3,
        videos: 0,
        prefix: 'img'
      }).then((setupB) => {
        const testDirB = setupB.testDir

        // Load directory A and create some groups/marks
        cy.request('PUT', 'http://localhost:5001/photo-classifier/settings', {
          rootPath: testDirA
        })
        cy.wait(500)

        cy.visit('/photo-classifier')
        cy.wait(500)

        cy.goToDefaultGroup()
        cy.get('.main-image').should('be.visible')
        cy.wait(500)

        // Create a group and mark a file
        cy.pressKey('KeyQ') // Create group
        cy.wait(300)
        cy.goToNextImage()
        cy.markAs('best') // Mark file
        cy.wait(300)

        // Switch to directory B via settings
        cy.visit('/photo-classifier')
        cy.get('.el-icon').first().click()
        cy.wait(300)
        cy.get('.el-drawer').within(() => {
          cy.get('textarea').clear().type(testDirB)
          cy.contains('button', 'Save and Reload').click()
        })
        cy.wait(2000)

        // Verify directory B has NO groups from directory A
        cy.visit('/photo-classifier')
        cy.wait(500)
        // Should see default group card only (no custom groups)
        cy.get('.group-card').should('have.length', 1)

        // Switch back to directory A
        cy.get('.el-icon').first().click()
        cy.wait(300)
        cy.get('.el-drawer').within(() => {
          cy.get('textarea').clear().type(testDirA)
          cy.contains('button', 'Save and Reload').click()
        })
        cy.wait(2000)

        // Verify groups/marks are cleared (fresh start)
        cy.visit('/photo-classifier')
        cy.wait(500)
        cy.get('.group-card').should('have.length', 1) // Only default group

        cy.goToDefaultGroup()
        cy.get('.main-image').should('be.visible')
        cy.wait(500)

        // Check if marks were cleared (file should have no category)
        cy.get('.header-right, .header-tags').should('not.contain', 'best')

        cy.log('✅ Case 2 completed - working state cleared on path switch')
      })
    })
  })
})
