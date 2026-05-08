/**
 * PhotoClassifier E2E Tests - Core Functionality
 *
 * These tests verify the core functionality of PhotoClassifier including:
 * - Group creation
 * - Mark all normal
 * - Category assignment in default group
 * - File movement verification
 */

describe('PhotoClassifier - Core Functionality Tests', () => {
  before(() => {
    // Clean up any existing test data before starting
    cy.cleanupTest()
  })

  after(() => {
    // Clean up test data after all tests
    cy.cleanupTest()
  })

  beforeEach(() => {
    // Check backend health before each test
    cy.checkBackendHealth()
  })

  /**
   * Test Case 1: Verify group creation functionality
   * - Create 5 images
   * - Successfully create 3 groups
   */
  it('should create 3 groups from 5 images', () => {
    const testName = 'test_case_1_groups'

    // Setup: Create test directory and images
    cy.setupTest(testName, 5).then((setup) => {
      cy.log(`Test directory: ${setup.testDir}`)

      // Load test images into PhotoClassifier
      cy.loadTestImages(setup.testDir)

      // Navigate to default group
      cy.goToDefaultGroup()

      // Wait for images to load
      cy.get('.pc-default-group-view').should('be.visible')

      // Create first group with first image (Press Q)
      cy.pressKey('KeyQ')
      cy.wait(500)

      // Navigate to second image and add to a new group
      cy.goToNextImage()
      cy.pressKey('KeyQ')
      cy.wait(500)

      // Navigate to third image and add to a new group
      cy.goToNextImage()
      cy.pressKey('KeyQ')
      cy.wait(500)

      // Open group drawer to verify 3 groups were created
      cy.contains('button', '显示Group').click()
      cy.get('.group-card').should('have.length', 3)

      // Cleanup this specific test
      cy.cleanupTest(testName)
    })
  })

  /**
   * Test Case 2: Verify mark all normal functionality
   * - Create 5 images
   * - Execute mark all normal
   * - Submit
   * - Verify all images moved to normal folder
   */
  it('should mark all images as normal and move them to normal folder', () => {
    const testName = 'test_case_2_mark_all_normal'

    cy.setupTest(testName, 5).then((setup) => {
      const testDir = setup.testDir
      cy.log(`Test directory: ${testDir}`)

      // Load test images into PhotoClassifier
      cy.loadTestImages(testDir)

      // Navigate to default group
      cy.goToDefaultGroup()
      cy.get('.pc-default-group-view').should('be.visible')

      // Mark all as normal
      cy.markAllNormal()
      cy.contains('All files marked as Normal').should('be.visible')

      // Apply changes
      cy.applyChanges()

      // Wait for file operations to complete
      cy.wait(2000)

      // Verify file distribution
      cy.verifyDistribution(testDir).should((distribution) => {
        expect(distribution.normal).to.equal(5)
        expect(distribution.best).to.equal(0)
        expect(distribution.better).to.equal(0)
        expect(distribution.remaining).to.equal(0)
      })

      // Cleanup
      cy.cleanupTest(testName)
    })
  })

  /**
   * Test Case 3: Verify category assignment with immediate Enter
   * - Create 5 images
   * - Mark all normal
   * - Mark image 1 as best
   * - Navigate to image 2
   * - Mark image 2 as better
   * - Press Enter on image 2 (immediate submit)
   * - Verify: 1 best, 1 better, 3 normal
   */
  it('should correctly assign categories when submitting immediately after marking', () => {
    const testName = 'test_case_3_immediate_submit'

    cy.setupTest(testName, 5).then((setup) => {
      const testDir = setup.testDir
      cy.log(`Test directory: ${testDir}`)

      // Load test images into PhotoClassifier
      cy.loadTestImages(testDir)

      // Navigate to default group
      cy.goToDefaultGroup()
      cy.get('.pc-default-group-view').should('be.visible')

      // Mark all as normal
      cy.markAllNormal()

      // Mark first image as best (KeyZ)
      cy.markAs('best')
      cy.wait(300)

      // Navigate to second image
      cy.goToNextImage()

      // Mark second image as better (KeyX)
      cy.markAs('better')
      cy.wait(300)

      // Immediately press Enter to submit
      cy.pressKey('Enter')

      // Wait for file operations to complete
      cy.wait(2000)

      // Verify file distribution
      cy.verifyDistribution(testDir).should((distribution) => {
        expect(distribution.best).to.equal(1, 'Should have 1 file in best folder')
        expect(distribution.better).to.equal(1, 'Should have 1 file in better folder')
        expect(distribution.normal).to.equal(3, 'Should have 3 files in normal folder')
        expect(distribution.remaining).to.equal(0, 'Should have no files remaining in root')
      })

      // Cleanup
      cy.cleanupTest(testName)
    })
  })

  /**
   * Test Case 4: Verify category assignment after navigation
   * - Create 5 images
   * - Mark all normal
   * - Mark image 1 as best
   * - Navigate to image 2
   * - Mark image 2 as better
   * - Navigate to last image (image 5)
   * - Press Enter to submit
   * - Verify: 1 best, 1 better, 3 normal
   */
  it('should correctly assign categories when submitting after navigation', () => {
    const testName = 'test_case_4_submit_after_navigation'

    cy.setupTest(testName, 5).then((setup) => {
      const testDir = setup.testDir
      cy.log(`Test directory: ${testDir}`)

      // Load test images into PhotoClassifier
      cy.loadTestImages(testDir)

      // Navigate to default group
      cy.goToDefaultGroup()
      cy.get('.pc-default-group-view').should('be.visible')

      // Mark all as normal
      cy.markAllNormal()

      // Mark first image as best
      cy.markAs('best')
      cy.wait(300)

      // Navigate to second image
      cy.goToNextImage()

      // Mark second image as better
      cy.markAs('better')
      cy.wait(300)

      // Navigate to the last image (image 5)
      // We're at image 2, need to go right 3 times
      cy.goToNextImage() // image 3
      cy.goToNextImage() // image 4
      cy.goToNextImage() // image 5

      // Now press Enter to submit
      cy.pressKey('Enter')

      // Wait for file operations to complete
      cy.wait(2000)

      // Verify file distribution
      cy.verifyDistribution(testDir).should((distribution) => {
        expect(distribution.best).to.equal(1, 'Should have 1 file in best folder')
        expect(distribution.better).to.equal(1, 'Should have 1 file in better folder')
        expect(distribution.normal).to.equal(3, 'Should have 3 files in normal folder')
        expect(distribution.remaining).to.equal(0, 'Should have no files remaining in root')
      })

      // Cleanup
      cy.cleanupTest(testName)
    })
  })
})
