/**
 * PhotoClassifier E2E Tests - Cleanup
 *
 * This test suite MUST run LAST to ensure proper cleanup.
 * The 99- prefix ensures it runs last in alphabetical order.
 *
 * During manual testing (cypress open):
 *   - You can skip this test to keep test data for inspection
 *
 * During automated testing (cypress run / CI):
 *   - This test will run last to ensure:
 *     1. Configuration is restored to original state
 *     2. All test data is cleaned up
 */

describe('PhotoClassifier - Cleanup', () => {
  it('should restore config and cleanup all test data', () => {
    cy.log('🧹 Starting cleanup process')

    // Restore configuration from snapshot
    cy.disableTestMode('photo_classifier')
    cy.log('✅ Config restored')

    // Clean up all test data
    cy.cleanupTest()
    cy.log('✅ Test data cleaned up')

    cy.log('✅ Cleanup complete')
  })
})
