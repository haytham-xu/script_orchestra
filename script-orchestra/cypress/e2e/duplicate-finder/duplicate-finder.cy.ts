/**
 * Duplicate Finder E2E Tests
 *
 * Test Case 1: Settings Management
 */

/* eslint-disable @typescript-eslint/no-explicit-any */

/// <reference types="cypress" />

const BACKEND_URL = 'http://localhost:5001'
const TEST_BASE_DIR = Cypress.env('TEST_BASE_DIR') || '../backend/duplicate_finder/tests/e2e/test_runtime'

describe('Duplicate Finder', () => {
  before(() => {
    cy.request(`${BACKEND_URL}/health`).its('status').should('eq', 200)
  })

  /**
   * Test 1: Settings Management
   * Back up all settings -> modify all settings -> save -> reload -> verify -> restore -> reload -> verify restored
   */
  describe('1. Settings Management', () => {
    const testName = 'test_settings'
    const testDB = `${TEST_BASE_DIR}/${testName}/test.db`
    const testScanPath = `${TEST_BASE_DIR}/${testName}/scan`
    const testExcludePath = `${TEST_BASE_DIR}/${testName}/exclude`
    const testDelPath = `${TEST_BASE_DIR}/${testName}/to_del`
    const testPreferPath = `${TEST_BASE_DIR}/${testName}/prefer`

    const originalSettings: Record<string, any> = {}

    beforeEach(() => {
      cy.visit('/')
      cy.get('[data-testid="duplicate-finder"]', { timeout: 10000 }).click()
      cy.url().should('include', '/duplicate-finder')
    })

    it('should save, modify, and restore settings correctly', () => {
      cy.log('Backing up settings and recording all original values')
      cy.saveDuplicateFinderConfig()

      cy.contains('button', '⚙️ Settings').click()
      cy.get('.el-drawer').should('be.visible')

      cy.get('body').then(($body) => {
        originalSettings.scanFoldersCount = $body.find('.folder-item-drawer').length
      })

      cy.get('body').then(($body) => {
        originalSettings.excludeFoldersCount = $body.find('.exclude-item-drawer').length
      })

      cy.get('input[placeholder*="delete/folder"]').invoke('val').then((val) => {
        originalSettings.deleteTargetPath = val
      })

      cy.get('input[placeholder*="phash_cache.db"]').invoke('val').then((val) => {
        originalSettings.databasePath = val
      })

      cy.contains('label', 'Similarity Threshold').invoke('text').then((text) => {
        const match = text.match(/(\d+)%/)
        originalSettings.similarityThreshold = match ? match[1] : null
      })

      cy.contains('label', 'Max CPU Cores').invoke('text').then((text) => {
        const match = text.match(/(\d+) \/ /)
        originalSettings.maxCpuCores = match ? match[1] : null
      })

      cy.get('.phase-settings-group').first().within(() => {
        cy.contains('label', 'Worker Handler Size').parent().find('.el-input-number input').invoke('val').then((val) => {
          originalSettings.phase1WorkerHandler = val
        })
        cy.contains('label', 'DB Commit Batch').parent().find('.el-input-number input').invoke('val').then((val) => {
          originalSettings.phase1DBCommit = val
        })
        cy.contains('label', 'Progress Update Interval').parent().find('.el-input-number input').invoke('val').then((val) => {
          originalSettings.phase1ProgressInterval = val
        })
        cy.contains('label', 'IPC Chunk Size').parent().find('.el-input-number input').invoke('val').then((val) => {
          originalSettings.phase1IPCChunk = val
        })
        cy.contains('label', 'Scan Delay (s)').parent().find('.el-input-number input').invoke('val').then((val) => {
          originalSettings.phase1ScanDelay = val
        })
        cy.contains('label', 'Compute Delay (s)').parent().find('.el-input-number input').invoke('val').then((val) => {
          originalSettings.phase1ComputeDelay = val
        })
      })

      cy.get('.phase-settings-group').last().within(() => {
        cy.contains('label', 'Worker Handler Size').parent().find('.el-input-number input').invoke('val').then((val) => {
          originalSettings.phase2WorkerHandler = val
        })
        cy.contains('label', 'DB Commit Batch').parent().find('.el-input-number input').invoke('val').then((val) => {
          originalSettings.phase2DBCommit = val
        })
        cy.contains('label', 'Progress Update Interval').parent().find('.el-input-number input').invoke('val').then((val) => {
          originalSettings.phase2ProgressInterval = val
        })
        cy.contains('label', 'IPC Chunk Size').parent().find('.el-input-number input').invoke('val').then((val) => {
          originalSettings.phase2IPCChunk = val
        })
        cy.contains('label', 'Compare Delay (s)').parent().find('.el-input-number input').invoke('val').then((val) => {
          originalSettings.phase2CompareDelay = val
        })
      })

      cy.get('.settings-section-drawer').contains('Auto-Selection Rules').parent().within(() => {
        cy.contains('Auto-mark numbered copies').parent().find('input[type="checkbox"]').invoke('prop', 'checked').then((checked) => {
          originalSettings.autoMarkNumbered = checked
        })
        cy.contains('Auto-mark "copy" suffix').parent().find('input[type="checkbox"]').invoke('prop', 'checked').then((checked) => {
          originalSettings.autoMarkCopy = checked
        })
      })

      cy.get('body').then(($body) => {
        originalSettings.preferFoldersCount = $body.find('.prefer-folder-item').length
      })

      cy.log('All original values recorded')
      cy.get('.el-drawer__close-btn').click()

      cy.log('Modifying all settings')
      cy.contains('button', '⚙️ Settings').click()
      cy.get('.el-drawer').should('be.visible')

      cy.get('.settings-section-drawer').contains('📁 Scan Folders').parent().within(() => {
        cy.get('button').contains('Add Folder').click()
        cy.get('input[placeholder="Folder Path"]').last().clear().type(testScanPath)
      })

      cy.get('.settings-section-drawer').contains('🚫 Exclude Folders').parent().within(() => {
        cy.get('button').contains('Add Exclude Folder').click()
        cy.get('input[placeholder*="exclude/folder"]').last().clear().type(testExcludePath)
      })

      cy.get('input[placeholder*="delete/folder"]').clear().type(testDelPath)

      cy.contains('label', 'Similarity Threshold').parent().find('.el-slider__button').then($button => {
        const button = $button[0]
        const rect = button.getBoundingClientRect()
        cy.wrap($button)
          .trigger('mousedown', { which: 1, clientX: rect.x, clientY: rect.y })
          .trigger('mousemove', { which: 1, clientX: rect.x - 50, clientY: rect.y })
          .trigger('mouseup', { force: true })
      })

      cy.get('input[placeholder*="phash_cache.db"]').clear().type(testDB)

      cy.contains('label', 'Max CPU Cores').parent().find('.el-slider__button').then($button => {
        const button = $button[0]
        const rect = button.getBoundingClientRect()
        cy.wrap($button)
          .trigger('mousedown', { which: 1, clientX: rect.x, clientY: rect.y })
          .trigger('mousemove', { which: 1, clientX: rect.x + 50, clientY: rect.y })
          .trigger('mouseup', { force: true })
      })

      cy.get('.phase-settings-group').first().within(() => {
        cy.contains('label', 'Worker Handler Size').parent().find('.el-input-number input').clear().type('2')
        cy.contains('label', 'DB Commit Batch').parent().find('.el-input-number input').clear().type('200')
        cy.contains('label', 'Progress Update Interval').parent().find('.el-input-number input').clear().type('50')
        cy.contains('label', 'IPC Chunk Size').parent().find('.el-input-number input').clear().type('20')
        cy.contains('label', 'Scan Delay (s)').parent().find('.el-input-number input').clear().type('0.5')
        cy.contains('label', 'Compute Delay (s)').parent().find('.el-input-number input').clear().type('0.3')
      })

      cy.get('.phase-settings-group').last().within(() => {
        cy.contains('label', 'Worker Handler Size').parent().find('.el-input-number input').clear().type('3')
        cy.contains('label', 'DB Commit Batch').parent().find('.el-input-number input').clear().type('150')
        cy.contains('label', 'Progress Update Interval').parent().find('.el-input-number input').clear().type('60')
        cy.contains('label', 'IPC Chunk Size').parent().find('.el-input-number input').clear().type('15')
        cy.contains('label', 'Compare Delay (s)').parent().find('.el-input-number input').clear().type('0.2')
      })

      cy.get('.settings-section-drawer').contains('Auto-Selection Rules').parent().within(() => {
        cy.contains('Auto-mark numbered copies').parent().find('input[type="checkbox"]').check({ force: true })
        cy.contains('Auto-mark "copy" suffix').parent().find('input[type="checkbox"]').check({ force: true })
        cy.contains('button', 'Add Preferred Folder').click()
        cy.get('input[placeholder*="preferred/folder"]').last().type(testPreferPath)
      })

      cy.log('Saving settings')
      cy.contains('button', '💾 Save All Settings').click()
      cy.contains('.el-message', 'success', { timeout: 5000 }).should('exist')

      cy.log('Closing drawer and refreshing page')
      cy.get('.el-drawer__close-btn').click()
      cy.reload()

      cy.log('Verifying all saved settings after page refresh')
      cy.contains('button', '⚙️ Settings').click()
      cy.get('.el-drawer').should('be.visible')

      cy.get('body').then(($body) => {
        const folderItems = $body.find('.folder-item-drawer')
        expect(folderItems.length).to.equal(originalSettings.scanFoldersCount + 1)
      })
      cy.get('.settings-section-drawer').contains('📁 Scan Folders').parent().within(() => {
        cy.get('input[placeholder="Folder Path"]').last().invoke('val').should('include', 'test_settings/scan')
      })

      cy.get('body').then(($body) => {
        const excludeItems = $body.find('.exclude-item-drawer')
        expect(excludeItems.length).to.equal(originalSettings.excludeFoldersCount + 1)
      })
      cy.get('.settings-section-drawer').contains('🚫 Exclude Folders').parent().within(() => {
        cy.get('input[placeholder*="exclude/folder"]').last().invoke('val').should('include', 'test_settings/exclude')
      })

      cy.get('input[placeholder*="delete/folder"]').invoke('val').should('include', 'test_settings/to_del')
      cy.get('input[placeholder*="phash_cache.db"]').invoke('val').should('include', 'test_settings/test.db')

      cy.contains('label', 'Similarity Threshold').invoke('text').then((text) => {
        const match = text.match(/(\d+)%/)
        const currentValue = match ? match[1] : null
        expect(currentValue).to.not.equal(originalSettings.similarityThreshold)
      })

      cy.contains('label', 'Max CPU Cores').invoke('text').then((text) => {
        const match = text.match(/(\d+) \/ /)
        const currentValue = match ? match[1] : null
        expect(currentValue).to.not.equal(originalSettings.maxCpuCores)
      })

      cy.get('.phase-settings-group').first().within(() => {
        cy.contains('label', 'Worker Handler Size').parent().find('.el-input-number input').should('have.value', '2')
        cy.contains('label', 'DB Commit Batch').parent().find('.el-input-number input').should('have.value', '200')
        cy.contains('label', 'Progress Update Interval').parent().find('.el-input-number input').should('have.value', '50')
        cy.contains('label', 'IPC Chunk Size').parent().find('.el-input-number input').should('have.value', '20')
        cy.contains('label', 'Scan Delay (s)').parent().find('.el-input-number input').should('have.value', '0.5')
        cy.contains('label', 'Compute Delay (s)').parent().find('.el-input-number input').should('have.value', '0.3')
      })

      cy.get('.phase-settings-group').last().within(() => {
        cy.contains('label', 'Worker Handler Size').parent().find('.el-input-number input').should('have.value', '3')
        cy.contains('label', 'DB Commit Batch').parent().find('.el-input-number input').should('have.value', '150')
        cy.contains('label', 'Progress Update Interval').parent().find('.el-input-number input').should('have.value', '60')
        cy.contains('label', 'IPC Chunk Size').parent().find('.el-input-number input').should('have.value', '15')
        cy.contains('label', 'Compare Delay (s)').parent().find('.el-input-number input').should('have.value', '0.2')
      })

      cy.get('.settings-section-drawer').contains('Auto-Selection Rules').parent().within(() => {
        cy.contains('Auto-mark numbered copies').parent().find('input[type="checkbox"]').should('be.checked')
        cy.contains('Auto-mark "copy" suffix').parent().find('input[type="checkbox"]').should('be.checked')
        cy.get('input[placeholder*="preferred/folder"]').invoke('val').should('include', 'test_settings/prefer')
      })

      cy.get('body').then(($body) => {
        const preferItems = $body.find('.prefer-folder-item')
        expect(preferItems.length).to.equal(originalSettings.preferFoldersCount + 1)
      })

      cy.log('All settings verified successfully')

      cy.get('.el-drawer__close-btn').click()
      cy.log('Restoring original settings')
      cy.restoreDuplicateFinderConfig()

      cy.log('Refreshing page after restore')
      cy.reload()

      cy.log('Verifying all settings restored to original values')
      cy.contains('button', '⚙️ Settings').click()
      cy.get('.el-drawer').should('be.visible')

      cy.get('body').then(($body) => {
        const folderItems = $body.find('.folder-item-drawer')
        expect(folderItems.length).to.equal(originalSettings.scanFoldersCount)
      })

      cy.get('body').then(($body) => {
        const excludeItems = $body.find('.exclude-item-drawer')
        expect(excludeItems.length).to.equal(originalSettings.excludeFoldersCount)
      })

      cy.get('input[placeholder*="delete/folder"]').should('have.value', originalSettings.deleteTargetPath)
      cy.get('input[placeholder*="phash_cache.db"]').should('have.value', originalSettings.databasePath)

      cy.contains('label', 'Similarity Threshold').invoke('text').then((text) => {
        const match = text.match(/(\d+)%/)
        expect(match ? match[1] : null).to.equal(originalSettings.similarityThreshold)
      })

      cy.contains('label', 'Max CPU Cores').invoke('text').then((text) => {
        const match = text.match(/(\d+) \/ /)
        expect(match ? match[1] : null).to.equal(originalSettings.maxCpuCores)
      })

      cy.get('.phase-settings-group').first().within(() => {
        cy.contains('label', 'Worker Handler Size').parent().find('.el-input-number input')
          .should('have.value', originalSettings.phase1WorkerHandler)
        cy.contains('label', 'DB Commit Batch').parent().find('.el-input-number input')
          .should('have.value', originalSettings.phase1DBCommit)
        cy.contains('label', 'Progress Update Interval').parent().find('.el-input-number input')
          .should('have.value', originalSettings.phase1ProgressInterval)
        cy.contains('label', 'IPC Chunk Size').parent().find('.el-input-number input')
          .should('have.value', originalSettings.phase1IPCChunk)
        cy.contains('label', 'Scan Delay (s)').parent().find('.el-input-number input')
          .should('have.value', originalSettings.phase1ScanDelay)
        cy.contains('label', 'Compute Delay (s)').parent().find('.el-input-number input')
          .should('have.value', originalSettings.phase1ComputeDelay)
      })

      cy.get('.phase-settings-group').last().within(() => {
        cy.contains('label', 'Worker Handler Size').parent().find('.el-input-number input')
          .should('have.value', originalSettings.phase2WorkerHandler)
        cy.contains('label', 'DB Commit Batch').parent().find('.el-input-number input')
          .should('have.value', originalSettings.phase2DBCommit)
        cy.contains('label', 'Progress Update Interval').parent().find('.el-input-number input')
          .should('have.value', originalSettings.phase2ProgressInterval)
        cy.contains('label', 'IPC Chunk Size').parent().find('.el-input-number input')
          .should('have.value', originalSettings.phase2IPCChunk)
        cy.contains('label', 'Compare Delay (s)').parent().find('.el-input-number input')
          .should('have.value', originalSettings.phase2CompareDelay)
      })

      cy.get('.settings-section-drawer').contains('Auto-Selection Rules').parent().within(() => {
        if (originalSettings.autoMarkNumbered) {
          cy.contains('Auto-mark numbered copies').parent().find('input[type="checkbox"]').should('be.checked')
        } else {
          cy.contains('Auto-mark numbered copies').parent().find('input[type="checkbox"]').should('not.be.checked')
        }

        if (originalSettings.autoMarkCopy) {
          cy.contains('Auto-mark "copy" suffix').parent().find('input[type="checkbox"]').should('be.checked')
        } else {
          cy.contains('Auto-mark "copy" suffix').parent().find('input[type="checkbox"]').should('not.be.checked')
        }
      })

      cy.get('body').then(($body) => {
        const preferItems = $body.find('.prefer-folder-item')
        expect(preferItems.length).to.equal(originalSettings.preferFoldersCount)
      })

      cy.log('All settings restored to original values successfully')
      cy.get('.el-drawer__close-btn').click()
    })
  })
})
