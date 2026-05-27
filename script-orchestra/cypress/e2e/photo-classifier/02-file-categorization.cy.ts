/**
 * PhotoClassifier E2E Tests - File Categorization
 *
 * This test suite verifies:
 * 1. Mark all files as normal and apply
 * 2. Mark individual files with different categories
 * 3. Verify files are moved to correct category folders
 *
 * These tests validate the core file categorization and moving functionality.
 */

describe('PhotoClassifier - File Categorization', () => {
  const TEST_DATA_ROOT = '/Users/I353667/Documents/code/github/script_orchestra/backend/cypress_test_data/photo_classifier'

  before(() => {
    // Enable test mode (saves snapshot and sets test config)
    cy.enableTestMode('photo_classifier', {
      rootPath: TEST_DATA_ROOT
    })

    // Clean up any existing test data before starting
    cy.cleanupTest()
  })

  after(() => {
    // Restore config and cleanup test data after this file completes
    cy.disableTestMode('photo_classifier')
    cy.cleanupTest()
  })

  beforeEach(() => {
    // Check backend health before each test
    cy.checkBackendHealth()

    // Reset store to ensure test isolation
    // This prevents state pollution from previous tests
    cy.resetPhotoClassifierStore()
  })

  /**
   * Test Case 1: Mark all files as normal and apply
   * - Create 4 images
   * - Go to default group
   * - Mark all as normal
   * - Apply changes
   * - Verify all 4 images moved to normal folder
   */
  it('should mark all files as normal and apply', () => {
    const testName = 'test_mark_all_normal'

    cy.setupTest({
      testName: testName,
      images: 4,
      videos: 0,
      prefix: 'img'
    }).then((setup) => {
      const testDir = setup.testDir

      cy.log(`📂 Test directory: ${testDir}`)
      cy.log(`📸 Created ${setup.imagePaths.length} images`)

      // Load test media
      cy.loadTestMedia(testDir)

      // Navigate to default group
      cy.goToDefaultGroup()

      // Wait for image to be visible
      cy.get('.main-image').should('be.visible')
      cy.wait(500) // Extra wait for Vue reactivity

      // Mark all as normal
      cy.markAllNormal()
      cy.log('✅ Marked all files as normal')

      // Apply changes
      cy.pressKey('Enter')
      cy.log('✅ Applied changes')

      // Don't wait - verifyFileDistribution will retry until files are ready

      // Verify file distribution with retries
      cy.verifyFileDistribution({
        testDir: testDir,
        expected: {
          normal: 4,
          best: 0,
          better: 0,
          del: 0,
          remaining: 0
        },
        maxRetries: 15,
        retryDelay: 1000
      })

      cy.log('✅ Test case 1 completed successfully')
    })
  })

  /**
   * Test Case 2: Mark files with different categories (apply at 3rd image)
   * - Create 4 images
   * - Go to default group
   * - Mark all as normal
   * - Mark 2nd image as best
   * - Mark 3rd image as better
   * - Apply at 3rd image position
   * - Verify: images 1,4 in normal, 2 in best, 3 in better
   */
  it('should mark files with different categories and apply at 3rd position', () => {
    const testName = 'test_mixed_categories_pos3'

    cy.setupTest({
      testName: testName,
      images: 4,
      videos: 0,
      prefix: 'img'
    }).then((setup) => {
      const testDir = setup.testDir

      cy.log(`📂 Test directory: ${testDir}`)
      cy.log(`📸 Created ${setup.imagePaths.length} images`)

      // Load test media
      cy.loadTestMedia(testDir)

      // Navigate to default group
      cy.goToDefaultGroup()

      // Wait for image to be visible
      cy.get('.main-image').should('be.visible')
      cy.wait(500) // Extra wait for Vue reactivity

      // Mark all as normal first
      cy.markAllNormal()
      cy.log('✅ Marked all files as normal')

      // Now we're at image 1, go to image 2 and mark as best
      cy.goToNextImage() // Now at image 2
      cy.markAs('best')
      cy.log('✅ Marked image 2 as best')

      // Go to image 3 and mark as better
      cy.goToNextImage() // Now at image 3
      cy.markAs('better')
      cy.log('✅ Marked image 3 as better')

      // Apply at current position (image 3)
      cy.pressKey('Enter')
      cy.log('✅ Applied changes at image 3')

      // Don't wait - verifyFileDistribution will retry

      // Verify file distribution
      cy.verifyFileDistribution({
        testDir: testDir,
        expected: {
          normal: 2,  // Images 1 and 4
          best: 1,    // Image 2
          better: 1,  // Image 3
          del: 0,
          remaining: 0
        },
        maxRetries: 15,  // Simple file move (4 files)
        retryDelay: 1000
      })

      cy.log('✅ Test case 2 completed successfully')
    })
  })

  /**
   * Test Case 3: Mark files with different categories (apply at 4th image)
   * - Create 4 images
   * - Go to default group
   * - Mark all as normal
   * - Mark 2nd image as best
   * - Mark 3rd image as better
   * - Navigate to 4th image
   * - Apply at 4th image position
   * - Verify: images 1,4 in normal, 2 in best, 3 in better
   */
  it('should mark files with different categories and apply at 4th position', () => {
    const testName = 'test_mixed_categories_pos4'

    cy.setupTest({
      testName: testName,
      images: 4,
      videos: 0,
      prefix: 'img'
    }).then((setup) => {
      const testDir = setup.testDir

      cy.log(`📂 Test directory: ${testDir}`)
      cy.log(`📸 Created ${setup.imagePaths.length} images`)

      // Load test media
      cy.loadTestMedia(testDir)

      // Navigate to default group
      cy.goToDefaultGroup()

      // Wait for image to be visible
      cy.get('.main-image').should('be.visible')
      cy.wait(500) // Extra wait for Vue reactivity

      // Mark all as normal first
      cy.markAllNormal()
      cy.log('✅ Marked all files as normal')

      // Now we're at image 1, go to image 2 and mark as best
      cy.goToNextImage() // Now at image 2
      cy.markAs('best')
      cy.log('✅ Marked image 2 as best')

      // Go to image 3 and mark as better
      cy.goToNextImage() // Now at image 3
      cy.markAs('better')
      cy.log('✅ Marked image 3 as better')

      // Go to image 4 (don't change its category, should remain normal)
      cy.goToNextImage() // Now at image 4
      cy.log('✅ Navigated to image 4')

      // Apply at current position (image 4)
      cy.pressKey('Enter')
      cy.log('✅ Applied changes at image 4')

      // Don't wait - verifyFileDistribution will retry

      // Verify file distribution
      cy.verifyFileDistribution({
        testDir: testDir,
        expected: {
          normal: 2,  // Images 1 and 4
          best: 1,    // Image 2
          better: 1,  // Image 3
          del: 0,
          remaining: 0
        },
        maxRetries: 15,  // Simple file move (4 files)
        retryDelay: 1000
      })

      cy.log('✅ Test case 3 completed successfully')
    })
  })
})
