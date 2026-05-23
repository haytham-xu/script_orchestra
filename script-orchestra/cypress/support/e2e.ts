// ***********************************************************
// This example support/e2e.ts is processed and
// loaded automatically before your test files.
//
// This is a great place to put global configuration and
// behavior that modifies Cypress.
//
// You can change the location of this file or turn off
// automatically serving support files with the
// 'supportFile' configuration option.
//
// You can read more here:
// https://on.cypress.io/configuration
// ***********************************************************

// Import commands.js using ES2015 syntax:
import './commands'

// Alternatively you can use CommonJS syntax:
// require('./commands')

// 收集浏览器 console 日志
let browserLogs: string[] = []

// 捕获浏览器 console.log 并收集
Cypress.on('window:before:load', (win) => {
  const originalLog = win.console.log
  const originalError = win.console.error
  const originalWarn = win.console.warn

  win.console.log = function (...args) {
    // 调用原始的 console.log
    originalLog.apply(win.console, args)

    // 收集日志
    const message = args.map(arg =>
      typeof arg === 'object' ? JSON.stringify(arg) : String(arg)
    ).join(' ')

    const timestamp = new Date().toISOString()
    browserLogs.push(`[${timestamp}] LOG: ${message}`)
  }

  win.console.error = function (...args) {
    originalError.apply(win.console, args)
    const message = args.map(arg =>
      typeof arg === 'object' ? JSON.stringify(arg) : String(arg)
    ).join(' ')
    const timestamp = new Date().toISOString()
    browserLogs.push(`[${timestamp}] ERROR: ${message}`)
  }

  win.console.warn = function (...args) {
    originalWarn.apply(win.console, args)
    const message = args.map(arg =>
      typeof arg === 'object' ? JSON.stringify(arg) : String(arg)
    ).join(' ')
    const timestamp = new Date().toISOString()
    browserLogs.push(`[${timestamp}] WARN: ${message}`)
  }
})

// 每个测试开始前输出标记
beforeEach(() => {
  // 在每个测试前清除本地存储和 cookies
  cy.clearLocalStorage()
  cy.clearCookies()

  // 标记测试开始
  const testTitle = Cypress.currentTest.title
  browserLogs.push(`\n========== TEST START: ${testTitle} ==========`)
})

// 每个测试结束后输出收集的日志
afterEach(function() {
  const testTitle = this.currentTest?.title || 'Unknown Test'
  const testState = this.currentTest?.state || 'unknown'

  browserLogs.push(`========== TEST END: ${testTitle} (${testState}) ==========\n`)

  // 输出所有收集的日志到 Node 终端
  if (browserLogs.length > 0) {
    cy.task('log', browserLogs.join('\n'), { log: false })
    // 清空日志数组，准备下一个测试
    browserLogs = []
  }
})
