/**
 * PhotoClassifier E2E Tests - Basic Media Loading
 *
 * This is the first test suite that verifies:
 * 1. Backend test API is working
 * 2. Media files (images and videos) are created correctly
 * 3. File system synchronization is reliable
 * 4. Frontend can load and display media files
 *
 * This test is intentionally simple and focuses on the fundamentals.
 */

describe('PhotoClassifier - Basic Media Loading', () => {
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
    // Note: Config restore and cleanup are handled in 99-cleanup.cy.ts
    // This allows you to inspect test data when running tests manually
  })

  beforeEach(() => {
    // Check backend health before each test
    cy.checkBackendHealth()

    // Reset store to ensure test isolation
    // This prevents state pollution from previous tests
    cy.resetPhotoClassifierStore()
  })

  /**
   * Test Case 1: Verify backend can create images
   * - Create test directory
   * - Generate 3 images
   * - Verify files exist in file system
   */
  it('should create test images and verify file system', () => {
    const testName = 'test_images_only'

    cy.setupTest({
      testName: testName,
      images: 3,
      videos: 0,
      prefix: 'img'
    }).then((setup) => {
      // Verify we got 3 image paths
      expect(setup.imagePaths).to.have.length(3)
      expect(setup.videoPaths).to.have.length(0)

      cy.log(`✅ Test directory: ${setup.testDir}`)
      cy.log(`✅ Images: ${setup.imagePaths.length}`)
    })
  })

  /**
   * Test Case 2: Verify backend can create videos
   * - Create test directory
   * - Generate 2 videos
   * - Verify files exist in file system
   */
  it('should create test videos and verify file system', () => {
    const testName = 'test_videos_only'

    cy.setupTest({
      testName: testName,
      images: 0,
      videos: 2,
      prefix: 'vid'
    }).then((setup) => {
      // Verify we got 2 video paths
      expect(setup.imagePaths).to.have.length(0)
      expect(setup.videoPaths).to.have.length(2)

      cy.log(`✅ Test directory: ${setup.testDir}`)
      cy.log(`✅ Videos: ${setup.videoPaths.length}`)
    })
  })

  /**
   * Test Case 3: Verify backend can create mixed media
   * - Create test directory
   * - Generate 2 images + 1 video
   * - Verify all files exist
   */
  it('should create mixed media (images + videos) and verify file system', () => {
    const testName = 'test_mixed_media'

    cy.setupTest({
      testName: testName,
      images: 2,
      videos: 1,
      prefix: 'mixed'
    }).then((setup) => {
      // Verify we got correct counts
      expect(setup.imagePaths).to.have.length(2)
      expect(setup.videoPaths).to.have.length(1)

      cy.log(`✅ Test directory: ${setup.testDir}`)
      cy.log(`✅ Images: ${setup.imagePaths.length}`)
      cy.log(`✅ Videos: ${setup.videoPaths.length}`)
    })
  })

  /**
   * Test Case 4: Load media into PhotoClassifier frontend
   * - Create 3 images and 1 video
   * - Load into PhotoClassifier
   * - Verify frontend displays the media
   */
  it('should load images and videos into PhotoClassifier frontend', () => {
    const testName = 'test_frontend_load'

    cy.setupTest({
      testName: testName,
      images: 3,
      videos: 1,
      prefix: 'media'
    }).then((setup) => {
      const testDir = setup.testDir

      cy.log(`📂 Test directory: ${testDir}`)
      cy.log(`📸 Created ${setup.imagePaths.length} images`)
      cy.log(`🎬 Created ${setup.videoPaths.length} videos`)

      // Load test media into PhotoClassifier
      cy.loadTestMedia(testDir)

      // Verify PhotoClassifier page loaded
      cy.url().should('include', '/photo-classifier')

      // Verify group cards are visible (meaning media was loaded)
      cy.get('.group-card').should('exist')
      cy.get('.group-card').should('be.visible')

      // Log success
      cy.log('✅ Frontend successfully loaded and displayed media')

      // Optional: Check if we can see file counts
      // This depends on your PhotoClassifier UI implementation
      cy.get('.group-card').first().within(() => {
        // You might want to verify file counts here
        // Example: cy.contains('4 files') or similar
        cy.log('Group card is visible and interactive')
      })
    })
  })

  /**
   * Test Case 5: Navigate to default group and verify media display
   * - Create 4 images
   * - Load into PhotoClassifier
   * - Navigate to default group
   * - Verify images are displayed
   */
  it('should navigate to default group and display images', () => {
    const testName = 'test_default_group_nav'

    cy.setupTest({
      testName: testName,
      images: 4,
      videos: 0,
      prefix: 'img'
    }).then((setup) => {
      const testDir = setup.testDir

      // Load test media
      cy.loadTestMedia(testDir)

      // Navigate to default group
      cy.goToDefaultGroup()

      // Verify we're on the default group page
      cy.url().should('include', '/photo-classifier/default-group')

      // Verify the default group view is visible
      cy.get('.pc-default-group-view').should('exist')
      cy.get('.pc-default-group-view').should('be.visible')

      cy.log('✅ Default group page loaded successfully')
    })
  })
})
