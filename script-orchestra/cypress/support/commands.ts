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
       * Custom command to check if backend is ready
       * @example cy.checkBackendHealth()
       */
      checkBackendHealth(): Chainable<void>

      /**
       * Custom command to navigate to PhotoClassifier dashboard
       * @example cy.goToPhotoClassifier()
       */
      goToPhotoClassifier(): Chainable<void>

      /**
       * Custom command to navigate to default group
       * @example cy.goToDefaultGroup()
       */
      goToDefaultGroup(): Chainable<void>

      /**
       * Custom command to simulate keyboard key press
       * @example cy.pressKey('KeyX')
       */
      pressKey(keyCode: string): Chainable<void>

      /**
       * Custom command to mark all files as normal
       * @example cy.markAllNormal()
       */
      markAllNormal(): Chainable<void>

      /**
       * Custom command to apply changes
       * @example cy.applyChanges()
       */
      applyChanges(): Chainable<void>

      /**
       * Setup test environment with test directory and images
       * @example cy.setupTest('test_case_1', 5)
       */
      setupTest(testName: string, imageCount: number): Chainable<{ testDir: string; imagePaths: string[] }>

      /**
       * Load test images into PhotoClassifier by scanning directory
       * @example cy.loadTestImages(testDir)
       */
      loadTestImages(testDir: string): Chainable<void>

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

Cypress.Commands.add('checkBackendHealth', () => {
  // Removed health check - tests will fail naturally if backend is down
  // This avoids needing a specific healthcheck endpoint
  cy.log('Backend health check skipped - will be verified by actual API calls')
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

Cypress.Commands.add('setupTest', (testName: string, imageCount: number) => {
  return cy.task('createTestDir', testName).then((dirResult: any) => {
    const testDir = dirResult.test_dir

    return cy.task('createTestImages', { testDir, count: imageCount }).then((imageResult: any) => {
      // Create result object first
      const result = {
        testDir: testDir,
        imagePaths: imageResult.image_paths
      }

      // Log information
      cy.log(`Created test directory: ${testDir}`)
      cy.log(`Created ${imageResult.image_paths.length} test images`)

      // Return wrapped result to avoid mixing sync/async
      return cy.wrap(result)
    })
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

// Load test images by setting rootPath in backend settings
Cypress.Commands.add('loadTestImages', (testDir: string) => {
  cy.request('PUT', 'http://localhost:5001/photo-classifier/settings', {
    rootPath: testDir
  })

  cy.wait(500)

  cy.visit('/photo-classifier')

  // Return the last command in the chain
  return cy.get('.group-card', { timeout: 10000 }).should('exist').then(() => {
    cy.log(`Loaded test images from ${testDir}`)
  })
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

export {}
