/// <reference types="cypress" />

// ***********************************************
// This example commands.ts shows you how to
// create various custom commands and overwrite
// existing commands.
//
// For more comprehensive examples of custom
// commands please read more here:
// https://on.cypress.io/custom-commands
// ***********************************************

declare global {
  namespace Cypress {
    interface Chainable {
      /**
       * Enable test mode for a tool (saves snapshot and sets test config)
       * @example cy.enableTestMode('photo_classifier', { rootPath: '/test/path' })
       */
      enableTestMode(tool: string, testConfig: object): Chainable<void>

      /**
       * Disable test mode for a tool (restores original config)
       * @example cy.disableTestMode('photo_classifier')
       */
      disableTestMode(tool: string): Chainable<void>

      /**
       * Custom command to check if backend is ready
       * @example cy.checkBackendHealth()
       */
      checkBackendHealth(): Chainable<void>

      /**
       * Setup test environment with test directory and media files
       * Creates directory, generates media, and verifies file system sync
       * @example cy.setupTest({ testName: 'test1', images: 3, videos: 2 })
       */
      setupTest(options: {
        testName: string
        images?: number
        videos?: number
        prefix?: string
      }): Chainable<{ testDir: string; imagePaths: string[]; videoPaths: string[] }>

      /**
       * Wait for files to exist in file system
       * Useful after creating files to ensure FS has synced
       * @example cy.waitForFiles(['/path/to/file1.jpg', '/path/to/file2.mp4'])
       */
      waitForFiles(filePaths: string[], timeout?: number): Chainable<void>

      /**
       * Load test media into PhotoClassifier by scanning directory
       * @example cy.loadTestMedia(testDir)
       */
      loadTestMedia(testDir: string): Chainable<void>

      /**
       * Reset PhotoClassifier store to clean state
       * Clears all groups, marks, and resets store to initial state
       * @example cy.resetPhotoClassifierStore()
       */
      resetPhotoClassifierStore(): Chainable<void>

      /**
       * Cleanup test data
       * @example cy.cleanupTest('test_case_1')
       */
      cleanupTest(testName?: string): Chainable<void>

      /**
       * Verify file distribution in test directory
       * @example cy.verifyDistribution(testDir).should('deep.equal', { best: 1, better: 1, normal: 3 })
       */
      verifyDistribution(testDir: string): Chainable<any>

      /**
       * Navigate to next image using arrow key
       * @example cy.goToNextImage()
       */
      goToNextImage(): Chainable<void>

      /**
       * Navigate to previous image using arrow key
       * @example cy.goToPrevImage()
       */
      goToPrevImage(): Chainable<void>

      /**
       * Mark current image with category using keyboard
       * @example cy.markAs('best')
       */
      markAs(category: 'best' | 'better' | 'normal' | 'del'): Chainable<void>
    }
  }
}

// Custom command implementations

// Configuration Management Commands

Cypress.Commands.add('enableTestMode', (tool: string, testConfig: object) => {
  cy.log(`🔧 Enabling test mode for ${tool}`)

  // 1. Save current config snapshot
  return cy.task('saveConfigSnapshot', tool).then(() => {
    cy.log(`✅ Config snapshot saved for ${tool}`)

    // 2. Set test config
    return cy.task('setTestConfig', { tool, testConfig }).then(() => {
      cy.log(`✅ Test config applied for ${tool}`)
      return null
    })
  })
})

Cypress.Commands.add('disableTestMode', (tool: string) => {
  cy.log(`🔄 Disabling test mode for ${tool}`)

  // Restore original config from snapshot
  return cy.task('restoreConfig', tool).then(() => {
    cy.log(`✅ Config restored for ${tool}`)
    return null
  })
})

Cypress.Commands.add('checkBackendHealth', () => {
  cy.task('checkBackendHealth').then((result: any) => {
    cy.log(`✅ Backend health: ${result.message}`)
  })
})

Cypress.Commands.add('goToPhotoClassifier', () => {
  cy.visit('/photo-classifier')
  cy.url().should('include', '/photo-classifier')
})

Cypress.Commands.add('goToDefaultGroup', () => {
  cy.visit('/photo-classifier/default-group')
  cy.url().should('include', '/photo-classifier/default-group')
  // Wait for Vue app to load
  cy.get('#app', { timeout: 10000 }).should('exist')
  // Wait for the default group view to be visible
  cy.get('.pc-default-group-view', { timeout: 10000 }).should('exist')
})

Cypress.Commands.add('pressKey', (keyCode: string) => {
  cy.get('body').trigger('keydown', { code: keyCode, bubbles: true })
})

Cypress.Commands.add('markAllNormal', () => {
  cy.contains('button', 'Mark All Normal').click()
})

Cypress.Commands.add('applyChanges', () => {
  cy.contains('button', 'Apply').click()
})

// Test data management commands

Cypress.Commands.add('setupTest', (options: {
  testName: string
  images?: number
  videos?: number
  prefix?: string
}) => {
  const { testName, images = 0, videos = 0, prefix = 'test' } = options

  cy.log(`🔧 Setting up test: ${testName} (${images} images, ${videos} videos)`)

  // Step 1: Create test directory
  return cy.task('createTestDir', testName).then((dirResult: any) => {
    const testDir = dirResult.test_dir
    cy.log(`📁 Created directory: ${testDir}`)

    // Step 2: Create media files
    return cy.task('createTestMedia', {
      testDir,
      images,
      videos,
      prefix,
      testName
    }).then((mediaResult: any) => {
      cy.log(`📸 Created ${mediaResult.image_paths.length} images`)
      cy.log(`🎬 Created ${mediaResult.video_paths.length} videos`)

      // Step 3: Verify all files exist (file system sync check)
      const allPaths = [...mediaResult.image_paths, ...mediaResult.video_paths]

      if (allPaths.length > 0) {
        return cy.task('checkFiles', {
          filePaths: allPaths,
          waitTimeout: 5000
        }).then((checkResult: any) => {
          if (!checkResult.all_exist) {
            cy.log(`⚠️ Warning: Some files not found after ${checkResult.wait_time_ms}ms`)
            cy.log(`Missing: ${checkResult.missing.join(', ')}`)
          } else {
            cy.log(`✅ All files verified (${checkResult.wait_time_ms}ms)`)
          }

          // Return result object
          return cy.wrap({
            testDir: testDir,
            imagePaths: mediaResult.image_paths,
            videoPaths: mediaResult.video_paths
          })
        })
      } else {
        // No files to verify
        return cy.wrap({
          testDir: testDir,
          imagePaths: [],
          videoPaths: []
        })
      }
    })
  })
})

Cypress.Commands.add('waitForFiles', (filePaths: string[], timeout: number = 5000) => {
  return cy.task('checkFiles', {
    filePaths,
    waitTimeout: timeout
  }).then((result: any) => {
    if (!result.all_exist) {
      throw new Error(`Files not found after ${timeout}ms: ${result.missing.join(', ')}`)
    }
    cy.log(`✅ All ${filePaths.length} files exist`)
    return null
  })
})

Cypress.Commands.add('cleanupTest', (testName?: string) => {
  return cy.task('cleanupTestData', testName || null).then(() => {
    cy.log(`Cleaned up test data${testName ? ` for ${testName}` : ''}`)
    return null
  })
})

Cypress.Commands.add('verifyDistribution', (testDir: string) => {
  return cy.task('verifyFileDistribution', testDir)
})

// Load test media by setting rootPath in backend settings
Cypress.Commands.add('loadTestMedia', (testDir: string) => {
  cy.log(`🔄 Loading test media from: ${testDir}`)

  // Step 1: Clear any existing working state for this test directory
  // This prevents state pollution from previous tests or failed test runs
  cy.request({
    method: 'DELETE',
    url: 'http://localhost:5001/photo-classifier/working-state',
    qs: { rootPath: testDir },
    failOnStatusCode: false // Don't fail if working state doesn't exist
  }).then(() => {
    cy.log('🧹 Cleared working state')
  })

  // Step 2: Set root path in photo classifier settings
  cy.request('PUT', 'http://localhost:5001/photo-classifier/settings', {
    rootPath: testDir
  })

  // Wait for backend to process
  cy.wait(500)

  // Step 3: Navigate to photo classifier
  // This will trigger a fresh load of the store with the new rootPath
  cy.visit('/photo-classifier')

  // Wait for dashboard to load (don't require group-card as it may not exist for empty directories)
  cy.wait(500)

  cy.log(`✅ Test media loaded from ${testDir}`)
  return cy.wrap(null)
})

// Reset PhotoClassifier store to clean state
// This is crucial for test isolation to prevent state pollution between tests
Cypress.Commands.add('resetPhotoClassifierStore', () => {
  cy.log('🧹 Resetting PhotoClassifier store')

  cy.window().then((win) => {
    // Access Pinia store through the Vue app instance
    // The store is attached to the global app instance
    if (win.__pinia) {
      // Get the photo classifier store
      const stores = win.__pinia.state.value
      if (stores.photoClassifier) {
        cy.log('📦 Found photoClassifier store, resetting...')

        // Reset all store state
        stores.photoClassifier.groupList = { groupList: [] }
        stores.photoClassifier.defaultGroup = { files: [] }
        stores.photoClassifier.currentGroupIndex = -1
        stores.photoClassifier.initialized = false

        cy.log('✅ Store reset complete')
      } else {
        cy.log('⚠️ photoClassifier store not found (may not be initialized yet)')
      }
    } else {
      cy.log('⚠️ Pinia not found in window (app may not be mounted yet)')
    }
  })

  return cy.wrap(null)
})

// Navigation commands

Cypress.Commands.add('goToNextImage', () => {
  cy.pressKey('ArrowRight')
  cy.wait(300) // Wait for UI to update
})

Cypress.Commands.add('goToPrevImage', () => {
  cy.pressKey('ArrowLeft')
  cy.wait(300) // Wait for UI to update
})

// Category marking commands

Cypress.Commands.add('markAs', (category: 'best' | 'better' | 'normal' | 'del') => {
  const keyMap = {
    'best': 'KeyZ',
    'better': 'KeyX',
    'normal': 'KeyC',
    'del': 'Backspace'
  }
  cy.pressKey(keyMap[category])
  cy.wait(200) // Wait for state update
})

// File distribution verification command
Cypress.Commands.add('verifyFileDistribution', (options: {
  testDir: string
  expected: {
    best?: number
    better?: number
    normal?: number
    del?: number
    remaining?: number
  }
  maxRetries?: number
  retryDelay?: number
}) => {
  const { testDir, expected, maxRetries = 10, retryDelay = 500 } = options

  cy.log('🔍 Verifying file distribution with retries')
  cy.log(`Expected: ${JSON.stringify(expected)}`)

  // Retry logic to handle file system delays
  const verifyWithRetry = (retryCount = 0): Cypress.Chainable<any> => {
    return cy.task('verifyFileDistribution', testDir).then((result: any) => {
      cy.log(`📊 Attempt ${retryCount + 1}/${maxRetries}: ${JSON.stringify(result)}`)

      // Check if result matches expected
      const matches = Object.keys(expected).every(key => {
        const expectedValue = expected[key as keyof typeof expected]
        const actualValue = result[key]
        return expectedValue === undefined || expectedValue === actualValue
      })

      if (matches) {
        cy.log('✅ File distribution verified successfully')
        return cy.wrap(result)
      } else if (retryCount < maxRetries - 1) {
        cy.log(`⏳ Retrying in ${retryDelay}ms...`)
        cy.wait(retryDelay)
        return verifyWithRetry(retryCount + 1)
      } else {
        // Final attempt failed, show detailed error
        cy.log('❌ File distribution verification failed')
        Object.keys(expected).forEach(key => {
          const expectedValue = expected[key as keyof typeof expected]
          const actualValue = result[key]
          if (expectedValue !== undefined && expectedValue !== actualValue) {
            cy.log(`  ${key}: expected ${expectedValue}, got ${actualValue}`)
          }
        })
        throw new Error(`File distribution mismatch after ${maxRetries} attempts. Expected: ${JSON.stringify(expected)}, Got: ${JSON.stringify(result)}`)
      }
    })
  }

  return verifyWithRetry()
})

// Group and UI interaction commands

Cypress.Commands.add('openGroupDrawer', () => {
  cy.contains('button', '显示Group').click()
  cy.get('.el-drawer').should('be.visible')
  cy.log('✅ Group drawer opened')
})

Cypress.Commands.add('clickGroupCardAdd', (groupIndex: number) => {
  cy.get('.group-card').eq(groupIndex).within(() => {
    cy.contains('button', 'Add').click()
  })
  cy.log(`✅ Clicked Add button for group ${groupIndex}`)
})

Cypress.Commands.add('toggleUnidentifiedFilter', () => {
  cy.get('.el-switch').click()
  cy.wait(300) // Wait for filter to apply
  cy.log('✅ Toggled unidentified filter')
})

Cypress.Commands.add('verifyIndexDisplay', (expected: string) => {
  cy.get('.header-progress').should('contain', expected)
  cy.log(`✅ Index display verified: ${expected}`)
})

Cypress.Commands.add('clickBatchSelectButton', () => {
  cy.contains('button', '批量选择').click()
  cy.url().should('include', '/batch-select')
  cy.log('✅ Navigated to batch select')
})

Cypress.Commands.add('clickBatchManageButton', () => {
  cy.contains('button', '批量管理').click()
  cy.wait(500) // Wait for page transition
  cy.log('✅ Clicked batch manage button')
})

Cypress.Commands.add('selectImageByIndex', (index: number) => {
  cy.get('.image-card').eq(index).click()
  cy.wait(100) // Wait for selection
  cy.log(`✅ Selected image at index ${index}`)
})

Cypress.Commands.add('shiftSelectImageRange', (startIndex: number, endIndex: number) => {
  cy.get('.image-card').eq(startIndex).click()
  cy.get('.image-card').eq(endIndex).click({ shiftKey: true })
  cy.wait(100)
  cy.log(`✅ Shift-selected images from ${startIndex} to ${endIndex}`)
})

Cypress.Commands.add('verifySelectionCount', (expected: number) => {
  cy.get('.header-right, .info-text').should('contain', expected.toString())
  cy.log(`✅ Selection count verified: ${expected}`)
})

Cypress.Commands.add('clickCreateNewGroup', () => {
  cy.contains('button', '创建新分组').click()
  cy.wait(300)
  cy.log('✅ Clicked create new group')
})

Cypress.Commands.add('clickAddToExistingGroup', () => {
  cy.contains('button', '添加到分组').click()
  cy.wait(300)
  cy.log('✅ Clicked add to existing group')
})

Cypress.Commands.add('clickClearSelection', () => {
  cy.contains('button', '清空选择').click()
  cy.wait(100)
  cy.log('✅ Clicked clear selection')
})

Cypress.Commands.add('clickRemoveSelected', () => {
  cy.contains('button', '移除选中').click()
  cy.wait(100)
  cy.log('✅ Clicked remove selected')
})

Cypress.Commands.add('confirmDialog', () => {
  cy.get('.el-message-box').within(() => {
    cy.contains('button', '确定').click()
  })
  cy.wait(300)
  cy.log('✅ Confirmed dialog')
})

Cypress.Commands.add('cancelDialog', () => {
  cy.get('.el-message-box').within(() => {
    cy.contains('button', '取消').click()
  })
  cy.wait(300)
  cy.log('✅ Cancelled dialog')
})

export {}

