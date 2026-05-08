/**
 * Copy of Test 1 - Different filename
 */

describe('Copy Test 1', () => {
  before(() => {
    cy.cleanupTest()
  })

  after(() => {
    cy.cleanupTest()
  })

  beforeEach(() => {
    cy.checkBackendHealth()
  })

  it('should create 3 groups from 5 images', () => {
    const testName = 'copy_test_1_groups'

    cy.setupTest(testName, 5).then((setup) => {
      cy.log(`Test directory: ${setup.testDir}`)

      cy.loadTestImages(setup.testDir)

      cy.goToDefaultGroup()

      cy.get('.pc-default-group-view').should('be.visible')

      cy.pressKey('KeyQ')
      cy.wait(500)

      cy.goToNextImage()
      cy.pressKey('KeyQ')
      cy.wait(500)

      cy.goToNextImage()
      cy.pressKey('KeyQ')
      cy.wait(500)

      cy.contains('button', '显示Group').click()
      cy.get('.group-card').should('have.length', 3)

      cy.cleanupTest(testName)
    })
  })
})
