import { defineConfig } from 'cypress'
import axios from 'axios'

const BACKEND_URL = 'http://localhost:5001'

export default defineConfig({
  e2e: {
    baseUrl: 'http://localhost:5173',
    specPattern: 'cypress/e2e/**/*.cy.{js,jsx,ts,tsx}',
    supportFile: 'cypress/support/e2e.ts',
    videosFolder: 'cypress/videos',
    screenshotsFolder: 'cypress/screenshots',
    fixturesFolder: 'cypress/fixtures',

    // 实验性功能
    experimentalStudio: true,  // 启用 Cypress Studio（可视化测试录制）

    // 设置视口大小
    viewportWidth: 1920,
    viewportHeight: 1080,

    // 设置超时时间
    defaultCommandTimeout: 10000,
    requestTimeout: 10000,
    responseTimeout: 30000,

    // 截图和视频配置
    video: true,  // 开启视频录制
    videoCompression: 32,  // 视频压缩质量（0-51，数字越小质量越高，文件越大）
    screenshotOnRunFailure: true,

    // 其他配置
    chromeWebSecurity: false,
    // 执行延迟（毫秒），用于放慢测试以便观察
    // 在 GUI 模式下可以在右上角调节速度，无需在这里设置
    // defaultCommandTimeout: 10000,  // 命令超时时间
    retries: {
      runMode: 2, // 在 CI 环境重试失败的测试
      openMode: 0  // 在开发环境不重试
    },

    setupNodeEvents(on, config) {
      // Cypress Tasks for test data management
      on('task', {
        // Browser console log output to terminal
        log(message) {
          console.log(message)
          return null
        },

        // Check if a file exists
        fileExists(filePath) {
          const fs = require('fs')
          return fs.existsSync(filePath)
        },

        // Health check
        async checkBackendHealth() {
          try {
            const response = await axios.get(`${BACKEND_URL}/api/cypress/health`)
            return response.data
          } catch (error) {
            console.error('❌ Backend health check failed:', error.message)
            throw error
          }
        },

        // Create test directory
        async createTestDir(testName) {
          try {
            const response = await axios.post(`${BACKEND_URL}/api/cypress/create-test-dir`, {
              test_name: testName
            })
            console.log(`✅ Created test directory: ${response.data.test_dir}`)
            return response.data
          } catch (error) {
            console.error('❌ Error creating test dir:', error.message)
            throw error
          }
        },

        // Create test media (images and videos)
        async createTestMedia({ testDir, images, videos, prefix, testName }) {
          try {
            const response = await axios.post(`${BACKEND_URL}/api/cypress/create-media`, {
              test_dir: testDir,
              images: images || 0,
              videos: videos || 0,
              prefix: prefix || 'test',
              test_name: testName || 'unknown'
            })
            console.log(`✅ Created ${response.data.total_created} media files`)
            return response.data
          } catch (error) {
            console.error('❌ Error creating test media:', error.message)
            throw error
          }
        },

        // Check if files exist (with wait/retry)
        async checkFiles({ filePaths, waitTimeout }) {
          try {
            const response = await axios.post(`${BACKEND_URL}/api/cypress/check-files`, {
              file_paths: filePaths,
              wait_timeout: waitTimeout || 5000
            })
            if (response.data.all_exist) {
              console.log(`✅ All ${filePaths.length} files verified (waited ${response.data.wait_time_ms}ms)`)
            } else {
              console.warn(`⚠️  Some files missing after ${response.data.wait_time_ms}ms:`, response.data.missing)
            }
            return response.data
          } catch (error) {
            console.error('❌ Error checking files:', error.message)
            throw error
          }
        },

        // Check directory
        async checkDirectory({ directory, expectedFiles, waitTimeout }) {
          try {
            const response = await axios.post(`${BACKEND_URL}/api/cypress/check-directory`, {
              directory: directory,
              expected_files: expectedFiles,
              wait_timeout: waitTimeout || 5000
            })
            console.log(`✅ Directory check: ${response.data.file_count} files found`)
            return response.data
          } catch (error) {
            console.error('❌ Error checking directory:', error.message)
            throw error
          }
        },

        // Verify file distribution
        async verifyFileDistribution(testDir) {
          try {
            const response = await axios.post(`${BACKEND_URL}/api/cypress/verify-distribution`, {
              test_dir: testDir
            })
            console.log(`✅ Distribution verified: best=${response.data.best}, better=${response.data.better}, normal=${response.data.normal}`)
            return response.data
          } catch (error) {
            console.error('❌ Error verifying file distribution:', error.message)
            throw error
          }
        },

        // Cleanup test data
        async cleanupTestData(testName) {
          try {
            const response = await axios.post(`${BACKEND_URL}/api/cypress/cleanup`, {
              test_name: testName || undefined
            })
            console.log(`✅ Cleaned up: ${response.data.path}`)
            return response.data
          } catch (error) {
            console.error('❌ Error cleaning up test data:', error.message)
            throw error
          }
        },

        // Configuration Management
        async saveConfigSnapshot(tool) {
          try {
            const response = await axios.post(`${BACKEND_URL}/api/cypress/config/snapshot`, {
              tool: tool
            })
            console.log(`✅ Config snapshot saved for ${tool}`)
            return response.data
          } catch (error) {
            console.error(`❌ Error saving config snapshot for ${tool}:`, error.message)
            throw error
          }
        },

        async setTestConfig({ tool, testConfig }) {
          try {
            const response = await axios.post(`${BACKEND_URL}/api/cypress/config/set-test`, {
              tool: tool,
              test_config: testConfig
            })
            console.log(`✅ Test config set for ${tool}`)
            return response.data
          } catch (error) {
            console.error(`❌ Error setting test config for ${tool}:`, error.message)
            throw error
          }
        },

        async restoreConfig(tool) {
          try {
            const response = await axios.post(`${BACKEND_URL}/api/cypress/config/restore`, {
              tool: tool
            })
            console.log(`✅ Config restored for ${tool}`)
            return response.data
          } catch (error) {
            console.error(`❌ Error restoring config for ${tool}:`, error.message)
            throw error
          }
        },

        async readSnapshot(tool) {
          try {
            const response = await axios.get(`${BACKEND_URL}/api/cypress/config/snapshot`, {
              params: { tool: tool }
            })
            console.log(`✅ Snapshot read for ${tool}`)
            return response.data
          } catch (error) {
            if (error.response?.status === 404) {
              console.log(`⚠️  No snapshot found for ${tool}`)
              return null
            }
            console.error(`❌ Error reading snapshot for ${tool}:`, error.message)
            throw error
          }
        }
      })

      return config
    }
  }
})
