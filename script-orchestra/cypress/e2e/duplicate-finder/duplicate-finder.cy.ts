/**
 * Duplicate Finder E2E Tests
 *
 * Based on guide.md - Test Case 1: Settings Management
 */

/* eslint-disable @typescript-eslint/no-explicit-any */

/// <reference types="cypress" />

const BACKEND_URL = 'http://localhost:5001'
// 使用相对于项目根目录的路径
const TEST_BASE_DIR = Cypress.env('TEST_BASE_DIR') || '../backend/cypress_test_data/duplicate_finder'

describe('Duplicate Finder', () => {
  before(() => {
    // 确保后端服务启动
    cy.request(`${BACKEND_URL}/health`).its('status').should('eq', 200)
  })

  /**
   * Test 1: Settings Management
   * 备份设置并记录所有原始值 -> 修改所有设置 -> 保存 -> 刷新页面 -> 验证 -> 恢复设置 -> 刷新页面 -> 验证所有值恢复
   */
  describe('1. Settings Management', () => {
    const testName = 'test_settings'
    const testDB = `${TEST_BASE_DIR}/${testName}/test.db`
    const testScanPath = `${TEST_BASE_DIR}/${testName}/scan`
    const testExcludePath = `${TEST_BASE_DIR}/${testName}/exclude`
    const testDelPath = `${TEST_BASE_DIR}/${testName}/to_del`
    const testPreferPath = `${TEST_BASE_DIR}/${testName}/prefer`

    // 用于存储所有原始设置值
    const originalSettings: Record<string, any> = {}

    beforeEach(() => {
      cy.visit('/')
      cy.get('[data-testid="duplicate-finder"]', { timeout: 10000 }).click()
      cy.url().should('include', '/duplicate-finder')
    })

    it('should save, modify, and restore settings correctly', () => {
      // 1. 备份当前设置并记录所有原始值
      cy.log('📦 Backing up settings and recording all original values')
      cy.saveDuplicateFinderConfig()

      // 打开设置抽屉，记录所有原始值
      cy.contains('button', '⚙️ Settings').click()
      cy.get('.el-drawer').should('be.visible')

      // 记录 Scan Folders 数量
      cy.get('body').then(($body) => {
        const folderItems = $body.find('.folder-item-drawer')
        originalSettings.scanFoldersCount = folderItems.length
      })

      // 记录 Exclude Folders 数量
      cy.get('body').then(($body) => {
        const excludeItems = $body.find('.exclude-item-drawer')
        originalSettings.excludeFoldersCount = excludeItems.length
      })

      // 记录 Delete Target Path
      cy.get('input[placeholder*="delete/folder"]').invoke('val').then((val) => {
        originalSettings.deleteTargetPath = val
      })

      // 记录 Database Path
      cy.get('input[placeholder*="phash_cache.db"]').invoke('val').then((val) => {
        originalSettings.databasePath = val
      })

      // 记录 Similarity Threshold
      cy.contains('label', 'Similarity Threshold').invoke('text').then((text) => {
        const match = text.match(/(\d+)%/)
        originalSettings.similarityThreshold = match ? match[1] : null
      })

      // 记录 Max CPU Cores
      cy.contains('label', 'Max CPU Cores').invoke('text').then((text) => {
        const match = text.match(/(\d+) \/ /)
        originalSettings.maxCpuCores = match ? match[1] : null
      })

      // 记录 Phase 1 Performance Settings
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

      // 记录 Phase 2 Performance Settings
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

      // 记录 Auto-Selection Rules
      cy.get('.settings-section-drawer').contains('Auto-Selection Rules').parent().within(() => {
        cy.contains('Auto-mark numbered copies').parent().find('input[type="checkbox"]').invoke('prop', 'checked').then((checked) => {
          originalSettings.autoMarkNumbered = checked
        })
        cy.contains('Auto-mark "copy" suffix').parent().find('input[type="checkbox"]').invoke('prop', 'checked').then((checked) => {
          originalSettings.autoMarkCopy = checked
        })
      })

      // 记录 Prefer folders 数量（在Auto-Selection Rules外层）
      cy.get('body').then(($body) => {
        const preferItems = $body.find('.prefer-folder-item')
        originalSettings.preferFoldersCount = preferItems.length
      })

      cy.log('✅ All original values recorded')

      // 关闭抽屉
      cy.get('.el-drawer__close-btn').click()

      // 2. 重新打开设置抽屉，开始修改所有设置
      cy.log('⚙️ Modifying all settings')
      cy.contains('button', '⚙️ Settings').click()
      cy.get('.el-drawer').should('be.visible')

      // 2.1 修改Scan Folders
      cy.log('Setting Scan Folders')
      cy.get('.settings-section-drawer').contains('📁 Scan Folders').parent().within(() => {
        cy.get('button').contains('Add Folder').click()
        cy.get('input[placeholder="Folder Path"]').last().clear().type(testScanPath)
      })

      // 2.2 修改Exclude Folders
      cy.log('Setting Exclude Folders')
      cy.get('.settings-section-drawer').contains('🚫 Exclude Folders').parent().within(() => {
        cy.get('button').contains('Add Exclude Folder').click()
        cy.get('input[placeholder*="exclude/folder"]').last().clear().type(testExcludePath)
      })

      // 2.3 修改Delete Target Path
      cy.log('Setting Delete Target Path')
      cy.get('input[placeholder*="delete/folder"]').clear().type(testDelPath)

      // 2.4 修改Similarity Threshold (拖动slider)
      cy.log('Setting Similarity Threshold')
      cy.contains('label', 'Similarity Threshold').parent().find('.el-slider__button').then($button => {
        const button = $button[0]
        const rect = button.getBoundingClientRect()
        cy.wrap($button)
          .trigger('mousedown', { which: 1, clientX: rect.x, clientY: rect.y })
          .trigger('mousemove', { which: 1, clientX: rect.x - 50, clientY: rect.y })
          .trigger('mouseup', { force: true })
      })

      // 2.5 修改Database Path
      cy.log('Setting Database Path')
      cy.get('input[placeholder*="phash_cache.db"]').clear().type(testDB)

      // 2.6 修改Max CPU Cores (拖动slider)
      cy.log('Setting Max CPU Cores')
      cy.contains('label', 'Max CPU Cores').parent().find('.el-slider__button').then($button => {
        const button = $button[0]
        const rect = button.getBoundingClientRect()
        cy.wrap($button)
          .trigger('mousedown', { which: 1, clientX: rect.x, clientY: rect.y })
          .trigger('mousemove', { which: 1, clientX: rect.x + 50, clientY: rect.y })
          .trigger('mouseup', { force: true })
      })

      // 2.7 修改Performance Settings - Phase 1
      cy.log('Setting Phase 1 Performance')
      cy.get('.phase-settings-group').first().within(() => {
        cy.contains('label', 'Worker Handler Size').parent().find('.el-input-number input').clear().type('2')
        cy.contains('label', 'DB Commit Batch').parent().find('.el-input-number input').clear().type('200')
        cy.contains('label', 'Progress Update Interval').parent().find('.el-input-number input').clear().type('50')
        cy.contains('label', 'IPC Chunk Size').parent().find('.el-input-number input').clear().type('20')
        cy.contains('label', 'Scan Delay (s)').parent().find('.el-input-number input').clear().type('0.5')
        cy.contains('label', 'Compute Delay (s)').parent().find('.el-input-number input').clear().type('0.3')
      })

      // 2.8 修改Performance Settings - Phase 2
      cy.log('Setting Phase 2 Performance')
      cy.get('.phase-settings-group').last().within(() => {
        cy.contains('label', 'Worker Handler Size').parent().find('.el-input-number input').clear().type('3')
        cy.contains('label', 'DB Commit Batch').parent().find('.el-input-number input').clear().type('150')
        cy.contains('label', 'Progress Update Interval').parent().find('.el-input-number input').clear().type('60')
        cy.contains('label', 'IPC Chunk Size').parent().find('.el-input-number input').clear().type('15')
        cy.contains('label', 'Compare Delay (s)').parent().find('.el-input-number input').clear().type('0.2')
      })

      // 2.9 修改Auto-Selection Rules
      cy.log('Setting Auto-Selection Rules')
      cy.get('.settings-section-drawer').contains('Auto-Selection Rules').parent().within(() => {
        // 勾选 Auto-mark numbered copies
        cy.contains('Auto-mark numbered copies').parent().find('input[type="checkbox"]').check({ force: true })

        // 勾选 Auto-mark "copy" suffix
        cy.contains('Auto-mark "copy" suffix').parent().find('input[type="checkbox"]').check({ force: true })

        // 添加 Prefer folder
        cy.contains('button', 'Add Preferred Folder').click()
        cy.get('input[placeholder*="preferred/folder"]').last().type(testPreferPath)
      })

      // 3. 保存设置
      cy.log('💾 Saving settings')
      cy.contains('button', '💾 Save All Settings').click()
      cy.contains('.el-message', 'success', { timeout: 5000 }).should('exist')

      // 4. 关闭抽屉并刷新页面
      cy.log('🔄 Closing drawer and refreshing page')
      cy.get('.el-drawer__close-btn').click()
      cy.reload()

      // 5. 重新打开设置抽屉，验证所有设置已保存
      cy.log('🔍 Verifying all saved settings after page refresh')
      cy.contains('button', '⚙️ Settings').click()
      cy.get('.el-drawer').should('be.visible')

      // 验证 Scan Folders (数量+1 且最后一个是新添加的)
      cy.get('body').then(($body) => {
        const folderItems = $body.find('.folder-item-drawer')
        expect(folderItems.length).to.equal(originalSettings.scanFoldersCount + 1)
      })
      cy.get('.settings-section-drawer').contains('📁 Scan Folders').parent().within(() => {
        cy.get('input[placeholder="Folder Path"]').last().invoke('val').should('include', 'test_settings/scan')
      })

      // 验证 Exclude Folders (数量+1 且最后一个是新添加的)
      cy.get('body').then(($body) => {
        const excludeItems = $body.find('.exclude-item-drawer')
        expect(excludeItems.length).to.equal(originalSettings.excludeFoldersCount + 1)
      })
      cy.get('.settings-section-drawer').contains('🚫 Exclude Folders').parent().within(() => {
        cy.get('input[placeholder*="exclude/folder"]').last().invoke('val').should('include', 'test_settings/exclude')
      })

      // 验证 Delete Target Path
      cy.get('input[placeholder*="delete/folder"]').invoke('val').should('include', 'test_settings/to_del')

      // 验证 Database Path
      cy.get('input[placeholder*="phash_cache.db"]').invoke('val').should('include', 'test_settings/test.db')

      // 验证 Similarity Threshold (slider值已修改)
      cy.contains('label', 'Similarity Threshold').invoke('text').then((text) => {
        const match = text.match(/(\d+)%/)
        const currentValue = match ? match[1] : null
        expect(currentValue).to.not.equal(originalSettings.similarityThreshold)
      })

      // 验证 Max CPU Cores (slider值已修改)
      cy.contains('label', 'Max CPU Cores').invoke('text').then((text) => {
        const match = text.match(/(\d+) \/ /)
        const currentValue = match ? match[1] : null
        expect(currentValue).to.not.equal(originalSettings.maxCpuCores)
      })

      // 验证 Phase 1 Performance Settings
      cy.get('.phase-settings-group').first().within(() => {
        cy.contains('label', 'Worker Handler Size').parent().find('.el-input-number input').should('have.value', '2')
        cy.contains('label', 'DB Commit Batch').parent().find('.el-input-number input').should('have.value', '200')
        cy.contains('label', 'Progress Update Interval').parent().find('.el-input-number input').should('have.value', '50')
        cy.contains('label', 'IPC Chunk Size').parent().find('.el-input-number input').should('have.value', '20')
        cy.contains('label', 'Scan Delay (s)').parent().find('.el-input-number input').should('have.value', '0.5')
        cy.contains('label', 'Compute Delay (s)').parent().find('.el-input-number input').should('have.value', '0.3')
      })

      // 验证 Phase 2 Performance Settings
      cy.get('.phase-settings-group').last().within(() => {
        cy.contains('label', 'Worker Handler Size').parent().find('.el-input-number input').should('have.value', '3')
        cy.contains('label', 'DB Commit Batch').parent().find('.el-input-number input').should('have.value', '150')
        cy.contains('label', 'Progress Update Interval').parent().find('.el-input-number input').should('have.value', '60')
        cy.contains('label', 'IPC Chunk Size').parent().find('.el-input-number input').should('have.value', '15')
        cy.contains('label', 'Compare Delay (s)').parent().find('.el-input-number input').should('have.value', '0.2')
      })

      // 验证 Auto-Selection Rules
      cy.get('.settings-section-drawer').contains('Auto-Selection Rules').parent().within(() => {
        cy.contains('Auto-mark numbered copies').parent().find('input[type="checkbox"]').should('be.checked')
        cy.contains('Auto-mark "copy" suffix').parent().find('input[type="checkbox"]').should('be.checked')
        cy.get('input[placeholder*="preferred/folder"]').invoke('val').should('include', 'test_settings/prefer')
      })

      // 验证 Prefer folders 数量增加了1个
      cy.get('body').then(($body) => {
        const preferItems = $body.find('.prefer-folder-item')
        expect(preferItems.length).to.equal(originalSettings.preferFoldersCount + 1)
      })

      cy.log('✅ All settings verified successfully')

      // 6. 恢复原始设置
      cy.get('.el-drawer__close-btn').click()
      cy.log('🔄 Restoring original settings')
      cy.restoreDuplicateFinderConfig()

      // 7. 刷新页面
      cy.log('🔄 Refreshing page after restore')
      cy.reload()

      // 8. 重新打开设置抽屉，验证所有设置已恢复到原始值
      cy.log('🔍 Verifying all settings restored to original values')
      cy.contains('button', '⚙️ Settings').click()
      cy.get('.el-drawer').should('be.visible')

      // 验证 Scan Folders 恢复到原始数量
      cy.get('body').then(($body) => {
        const folderItems = $body.find('.folder-item-drawer')
        expect(folderItems.length).to.equal(originalSettings.scanFoldersCount)
      })

      // 验证 Exclude Folders 恢复到原始数量
      cy.get('body').then(($body) => {
        const excludeItems = $body.find('.exclude-item-drawer')
        expect(excludeItems.length).to.equal(originalSettings.excludeFoldersCount)
      })

      // 验证 Delete Target Path 恢复到原始值
      cy.get('input[placeholder*="delete/folder"]').should('have.value', originalSettings.deleteTargetPath)

      // 验证 Database Path 恢复到原始值
      cy.get('input[placeholder*="phash_cache.db"]').should('have.value', originalSettings.databasePath)

      // 验证 Similarity Threshold 恢复到原始值
      cy.contains('label', 'Similarity Threshold').invoke('text').then((text) => {
        const match = text.match(/(\d+)%/)
        expect(match ? match[1] : null).to.equal(originalSettings.similarityThreshold)
      })

      // 验证 Max CPU Cores 恢复到原始值
      cy.contains('label', 'Max CPU Cores').invoke('text').then((text) => {
        const match = text.match(/(\d+) \/ /)
        expect(match ? match[1] : null).to.equal(originalSettings.maxCpuCores)
      })

      // 验证 Phase 1 Performance Settings 恢复到原始值
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

      // 验证 Phase 2 Performance Settings 恢复到原始值
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

      // 验证 Auto-Selection Rules 恢复到原始值
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

      // 验证 Prefer folders 恢复到原始数量
      cy.get('body').then(($body) => {
        const preferItems = $body.find('.prefer-folder-item')
        expect(preferItems.length).to.equal(originalSettings.preferFoldersCount)
      })

      cy.log('✅ All settings restored to original values successfully')

      cy.get('.el-drawer__close-btn').click()
    })
  })
})
