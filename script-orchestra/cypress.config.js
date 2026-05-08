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

    // 设置视口大小
    viewportWidth: 1920,
    viewportHeight: 1080,

    // 设置超时时间
    defaultCommandTimeout: 10000,
    requestTimeout: 10000,
    responseTimeout: 30000,

    // 截图和视频配置
    video: false,
    screenshotOnRunFailure: true,

    // 其他配置
    chromeWebSecurity: false,
    retries: {
      runMode: 2, // 在 CI 环境重试失败的测试
      openMode: 0  // 在开发环境不重试
    },

    setupNodeEvents(on, config) {
      // Task: Create test directory
      on('task', {
        async createTestDir(testName) {
          try {
            const response = await axios.post(`${BACKEND_URL}/api/test/create-dir`, {
              test_name: testName
            })
            return response.data
          } catch (error) {
            console.error('Error creating test dir:', error.message)
            throw error
          }
        },

        async createTestImages({ testDir, count }) {
          try {
            const response = await axios.post(`${BACKEND_URL}/api/test/create-images`, {
              test_dir: testDir,
              count: count
            })
            return response.data
          } catch (error) {
            console.error('Error creating test images:', error.message)
            throw error
          }
        },

        async cleanupTestData(testName) {
          try {
            const response = await axios.post(`${BACKEND_URL}/api/test/cleanup`, {
              test_name: testName || undefined
            })
            return response.data
          } catch (error) {
            console.error('Error cleaning up test data:', error.message)
            throw error
          }
        },

        async verifyFileDistribution(testDir) {
          try {
            const response = await axios.post(`${BACKEND_URL}/api/test/verify`, {
              test_dir: testDir
            })
            return response.data
          } catch (error) {
            console.error('Error verifying file distribution:', error.message)
            throw error
          }
        }
      })

      return config
    }
  }
})
