# Cypress 测试快速开始

## 运行测试

```bash
# GUI 模式（开发）
npm run test:e2e:open

# Headless 模式（CI）
npm run test:e2e 2>&1 | tee ../log/cypress.log
npx cypress run --spec "cypress/e2e/photo-classifier/03-default-group-operations.cy.ts" 2>&1 | tee ../log/cypress.log
```

## 配置恢复命令

如果测试失败导致配置未恢复：

```bash
# 检查未恢复的快照
python backend/cypress_support/restore_config.py

# 恢复所有配置
python backend/cypress_support/restore_config.py --all

# 恢复特定工具
python backend/cypress_support/restore_config.py photo_classifier
```


# Cypress E2E 测试规范要求

本文档记录 Script Orchestra 项目的 Cypress E2E 测试最佳实践和通用规范要求。

## 目录
- [文件系统操作验证](#文件系统操作验证)
- [测试数据隔离](#测试数据隔离)
- [测试结构最佳实践](#测试结构最佳实践)
- [异步操作处理](#异步操作处理)
- [调试和日志](#调试和日志)
- [常见问题和解决方案](#常见问题和解决方案)

---

## 文件系统操作验证

许多 E2E 测试涉及文件系统操作（创建、移动、删除文件等），需要验证这些操作是否成功。文件系统的反应时间是**不固定的**，因此不能使用固定的等待时间。

### ❌ 错误做法：使用固定的 cy.wait()

```typescript
// 不要这样做
cy.clickButton('Move File')  // 触发文件移动操作
cy.wait(1000)  // 固定等待1秒
cy.verifyFileExists('target/file.txt')  // 验证文件是否存在
```

**问题**：
- 文件系统的反应时间因环境而异（本地开发、CI 环境、不同操作系统）
- 固定等待时间可能太短（导致测试不稳定）或太长（浪费测试时间）
- 测试在本地通过，但在 CI 环境失败

### ✅ 正确做法：使用带重试机制的后端 API 验证

**核心原则**：通过调用后端 API 检查文件系统状态，并使用重试机制等待操作完成。

#### 方案 1：封装带重试的自定义命令（推荐）

```typescript
// cypress/support/commands.ts
Cypress.Commands.add('verifyFileDistribution', (
  rootPath: string,
  expected: { [folder: string]: string[] },
  options = { maxRetries: 10, retryDelay: 300 }
) => {
  const { maxRetries, retryDelay } = options
  let attempt = 0

  function check() {
    attempt++
    cy.log(`Verifying file distribution (attempt ${attempt}/${maxRetries})`)

    return cy.request({
      method: 'GET',
      url: `http://localhost:5001/api/check-files`,
      qs: { rootPath },
      failOnStatusCode: false
    }).then((response) => {
      if (response.status === 200) {
        // 验证文件分布是否符合预期
        const actual = response.body.distribution
        const match = deepEqual(actual, expected)

        if (match) {
          cy.log('✅ File distribution verified')
          return true
        }
      }

      // 如果不匹配且还有重试机会，继续重试
      if (attempt < maxRetries) {
        cy.wait(retryDelay)
        return check()
      } else {
        throw new Error(`File distribution verification failed after ${maxRetries} attempts`)
      }
    })
  }

  return check()
})
```

**使用示例**：
```typescript
it('should move files correctly', () => {
  // 执行文件操作
  cy.clickButton('Move Files')

  // 使用带重试的验证（不需要固定 wait）
  cy.verifyFileDistribution(testDir, {
    'target-folder': ['file1.txt', 'file2.txt'],
    'another-folder': ['file3.txt']
  }, {
    maxRetries: 10,
    retryDelay: 300
  })
})
```

#### 方案 2：使用 Cypress 内置重试机制

如果验证逻辑简单，可以利用 Cypress 命令的自动重试：

```typescript
it('should create file', () => {
  cy.clickButton('Create File')

  // Cypress 会自动重试这个断言直到通过或超时
  cy.request('GET', `/api/file-exists?path=${filePath}`)
    .its('body.exists')
    .should('eq', true)
})
```

### 最佳实践总结

1. ✅ **永远不要**使用固定的 `cy.wait()` 等待文件系统操作
2. ✅ **优先使用**后端 API 检查文件状态（而不是前端 UI）
3. ✅ **实现重试机制**，适应不同环境的性能差异
4. ✅ **提供可配置的重试参数**（maxRetries、retryDelay）
5. ✅ **添加清晰的日志**，便于调试失败原因

---

## 测试数据隔离

测试数据隔离是确保测试独立性和可重复性的**关键**。必须在多个层面实现隔离。

### 为什么需要测试数据隔离

- **独立性**：测试之间不互相影响，可以任意顺序执行
- **可重复性**：同一个测试多次运行结果一致
- **并行执行**：支持并行运行多个测试
- **调试友好**：失败时容易定位问题

### 隔离层面

#### 1. 文件系统隔离

每个测试使用**独立的测试目录**，避免文件冲突。

```typescript
describe('File Operations', () => {
  let testDir: string

  beforeEach(() => {
    // 每个测试创建唯一目录（使用时间戳 + 随机字符串）
    testDir = `test_${Date.now()}_${Math.random().toString(36).substring(7)}`
    cy.createTestDir(testDir)
    cy.createTestFiles(testDir, ['file1.txt', 'file2.txt'])
  })

  afterEach(() => {
    // 测试后清理目录
    cy.cleanupTestDir(testDir)
  })

  it('should process files', () => {
    // 使用独立的 testDir
    cy.loadFiles(testDir)
    // ... 测试逻辑
  })
})
```

#### 2. 应用状态隔离

如果应用使用状态管理（Vuex、Pinia、Redux 等），必须在测试间重置状态。

**Vue + Pinia 示例**：
```typescript
// cypress/support/commands.ts
Cypress.Commands.add('resetAppStore', () => {
  cy.log('🧹 Resetting application store')

  cy.window().then((win) => {
    if (win.__pinia) {
      const stores = win.__pinia.state.value

      // 重置所有 store
      Object.keys(stores).forEach(storeKey => {
        const store = stores[storeKey]
        // 清空关键状态
        store.items = []
        store.selectedItems = []
        store.initialized = false
        // ... 根据实际情况重置
      })

      cy.log('✅ Store reset complete')
    }
  })
})
```

**使用方式**：
```typescript
beforeEach(() => {
  // ⚠️ 关键：每个测试前重置 store
  cy.resetAppStore()
})
```

#### 3. 后端状态隔离

如果后端保存持久化状态（配置文件、数据库等），需要在测试间清理。

```typescript
beforeEach(() => {
  // 清理后端状态文件
  cy.request({
    method: 'DELETE',
    url: 'http://localhost:5001/api/working-state',
    qs: { path: testDir },
    failOnStatusCode: false
  })

  // 或重置数据库
  cy.task('resetDatabase')
})
```

#### 4. 浏览器存储隔离

清理 localStorage、sessionStorage、cookies 等。

```typescript
beforeEach(() => {
  // Cypress 自动在每个测试前清理浏览器状态
  // 但也可以手动清理
  cy.clearLocalStorage()
  cy.clearCookies()
})
```

### 完整的测试隔离模板

```typescript
describe('Feature Tests', () => {
  let testDir: string

  // 测试套件开始前的一次性设置
  before(() => {
    cy.checkBackendHealth()  // 确保后端运行
  })

  // 每个测试前的设置
  beforeEach(() => {
    // 1. 健康检查
    cy.checkBackendHealth()

    // 2. 重置应用状态（关键！）
    cy.resetAppStore()

    // 3. 创建独立测试目录
    testDir = `test_feature_${Date.now()}`
    cy.createTestDir(testDir)
    cy.createTestFiles(testDir, 10)

    // 4. 清理后端状态
    cy.request({
      method: 'DELETE',
      url: '/api/working-state',
      qs: { path: testDir },
      failOnStatusCode: false
    })

    // 5. 加载测试数据
    cy.loadTestData(testDir)
  })

  // 每个测试后的清理
  afterEach(() => {
    // 清理测试目录
    cy.cleanupTestDir(testDir)
  })

  // 测试套件结束后的清理
  after(() => {
    // 全局清理（如果需要）
  })

  it('should do something independently', () => {
    // 测试逻辑
  })

  it('should do something else independently', () => {
    // 另一个独立的测试
  })
})
```

### 隔离检查清单

- [ ] 每个测试使用独立的文件系统路径
- [ ] 每个测试前重置应用状态（store/state）
- [ ] 每个测试前清理后端持久化状态
- [ ] 每个测试后清理创建的测试数据
- [ ] 测试可以任意顺序执行而不失败
- [ ] 测试可以单独运行（`it.only`）而不失败

---

## 测试结构最佳实践

### 1. 测试文件命名规范

使用数字前缀 + 功能描述的方式命名测试文件，便于按照测试执行顺序组织：

```
01-基础功能.cy.ts              # 按功能模块编号
02-用户交互.cy.ts
03-数据操作.cy.ts
04-边界情况.cy.ts
05-集成测试.cy.ts
```

**命名原则**：
- 使用连字符分隔单词
- 文件名清晰描述测试的功能模块
- 以 `.cy.ts` 或 `.cy.js` 结尾

### 2. 测试套件（describe）结构

### 2. 测试套件（describe）结构

标准的测试套件结构应该包含清晰的 setup 和 teardown 逻辑：

```typescript
describe('模块名称 - 功能描述', () => {
  let testData: SomeType

  // 测试套件开始前的一次性设置
  before(() => {
    cy.checkBackendHealth()  // 确保后端运行
    // 其他一次性准备工作
  })

  // 每个测试前的设置
  beforeEach(() => {
    // 1. 重置应用状态
    cy.resetAppStore()

    // 2. 准备测试数据
    testData = prepareTestData()

    // 3. 导航到测试页面
    cy.visit('/target-page')
  })

  // 每个测试后的清理
  afterEach(() => {
    // 清理测试产生的数据
    cy.cleanupTestData(testData)
  })

  // 测试套件结束后的清理
  after(() => {
    // 全局清理（如果需要）
  })

  it('should 做某件事', () => {
    // 测试逻辑
  })
})
```

### 3. 测试用例（it）编写原则

#### Arrange-Act-Assert 模式

```typescript
it('should successfully create a new item', () => {
  // Arrange - 准备测试数据和环境
  const itemName = 'Test Item'
  cy.visit('/items')
  cy.wait(500)

  // Act - 执行被测试的操作
  cy.get('[data-testid="create-button"]').click()
  cy.get('[data-testid="item-name"]').type(itemName)
  cy.get('[data-testid="submit"]').click()

  // Assert - 验证结果
  cy.get('[data-testid="item-list"]')
    .should('contain', itemName)
})
```

#### 测试命名规范

测试名称应该清晰描述**做什么**和**期望什么结果**：

```typescript
// ✅ 好的测试名称
it('should display error message when submitting empty form', () => {})
it('should filter items by category when category is selected', () => {})
it('should persist state after page refresh', () => {})
it('should handle concurrent requests without data loss', () => {})

// ❌ 不好的测试名称
it('test 1', () => {})
it('works', () => {})
it('check form', () => {})
it('button click', () => {})
```

#### 单一职责原则

每个测试只验证一个功能点：

```typescript
// ❌ 不好：一个测试验证多个功能
it('should handle all user operations', () => {
  cy.createUser()     // 创建用户
  cy.editUser()       // 编辑用户
  cy.deleteUser()     // 删除用户
  cy.restoreUser()    // 恢复用户
})

// ✅ 好：分成多个独立测试
it('should create user successfully', () => {
  cy.createUser()
  cy.verifyUserExists()
})

it('should edit user information', () => {
  cy.createUser()
  cy.editUser()
  cy.verifyUserUpdated()
})

it('should delete user', () => {
  cy.createUser()
  cy.deleteUser()
  cy.verifyUserDeleted()
})
```

### 4. 选择器最佳实践

#### 优先级顺序

1. **`data-testid` 属性**（最推荐）
   ```typescript
   cy.get('[data-testid="submit-button"]').click()
   ```

2. **有意义的 ARIA 属性**
   ```typescript
   cy.get('[aria-label="Close dialog"]').click()
   ```

3. **组件的角色**
   ```typescript
   cy.get('button').contains('Submit').click()
   ```

4. **避免使用的选择器**：
   - ❌ CSS 类名（可能变化）：`.btn-primary`
   - ❌ 复杂的 CSS 路径：`div > ul > li:nth-child(3)`
   - ❌ XPath（难以维护）

#### 添加 data-testid 到组件

```vue
<!-- Vue 组件示例 -->
<template>
  <div>
    <button data-testid="create-button" @click="create">
      Create
    </button>
    <input data-testid="search-input" v-model="search" />
    <div data-testid="results-list">
      <!-- 结果列表 -->
    </div>
  </div>
</template>
```

### 5. 等待和超时处理

#### 避免固定等待

```typescript
// ❌ 不好：固定等待
cy.click('[data-testid="load-data"]')
cy.wait(2000)  // 不知道等什么
cy.get('[data-testid="data-list"]').should('be.visible')

// ✅ 好：等待特定条件
cy.click('[data-testid="load-data"]')
cy.get('[data-testid="loading-spinner"]').should('not.exist')
cy.get('[data-testid="data-list"]').should('be.visible')
```

#### 合理使用 cy.wait()

只在以下场景使用短暂的固定等待：

1. **UI 动画完成**（通常 300-500ms）
   ```typescript
   cy.click('[data-testid="dropdown"]')
   cy.wait(300)  // 等待下拉动画
   cy.get('[data-testid="dropdown-menu"]').should('be.visible')
   ```

2. **框架响应延迟**（Vue/React 等）
   ```typescript
   cy.visit('/page')
   cy.wait(500)  // 等待 Vue 完成挂载和首次渲染
   cy.get('[data-testid="main-content"]').should('be.visible')
   ```

**注意**：永远不要用固定 wait 等待异步操作（API 调用、文件系统等）。

---

## 异步操作处理

E2E 测试中经常遇到异步操作（API 调用、文件处理、动画等），需要正确处理才能保证测试稳定性。

### 1. API 调用

#### 方案 A：等待 UI 反馈

```typescript
it('should load data from API', () => {
  cy.visit('/dashboard')

  // 等待加载状态出现
  cy.get('[data-testid="loading"]').should('be.visible')

  // 等待加载完成
  cy.get('[data-testid="loading"]').should('not.exist')

  // 验证数据已加载
  cy.get('[data-testid="data-list"]')
    .children()
    .should('have.length.gt', 0)
})
```

#### 方案 B：拦截 API 请求

```typescript
it('should handle API response', () => {
  // 拦截 API 请求
  cy.intercept('GET', '/api/items', {
    statusCode: 200,
    body: { items: [{ id: 1, name: 'Test' }] }
  }).as('getItems')

  cy.visit('/items')

  // 等待请求完成
  cy.wait('@getItems')

  // 验证 UI 更新
  cy.get('[data-testid="item-list"]')
    .should('contain', 'Test')
})
```

### 2. 文件系统操作

参考[文件系统操作验证](#文件系统操作验证)章节，使用带重试的后端 API 验证。

### 3. 动画和过渡

```typescript
// 等待元素变为可见并且动画完成
cy.get('[data-testid="modal"]')
  .should('be.visible')
  .and('have.css', 'opacity', '1')  // 等待淡入完成

// 或使用固定短暂等待
cy.get('[data-testid="modal"]').should('be.visible')
cy.wait(300)  // 等待动画完成
```

### 4. Debounced/Throttled 操作

```typescript
it('should handle debounced search', () => {
  // 输入搜索关键词
  cy.get('[data-testid="search-input"]')
    .type('test query')

  // 等待 debounce 延迟（例如 500ms）+ 一点 buffer
  cy.wait(600)

  // 验证搜索结果
  cy.get('[data-testid="search-results"]')
    .should('be.visible')
})
```

### 5. 轮询机制

对于需要轮询检查的场景（如文件处理状态），封装为自定义命令：

```typescript
// cypress/support/commands.ts
Cypress.Commands.add('waitForTaskComplete', (taskId: string, timeout = 30000) => {
  const startTime = Date.now()

  function checkStatus() {
    return cy.request(`/api/tasks/${taskId}/status`).then((response) => {
      if (response.body.status === 'completed') {
        return cy.wrap(response.body)
      }

      if (Date.now() - startTime > timeout) {
        throw new Error(`Task ${taskId} did not complete within ${timeout}ms`)
      }

      cy.wait(1000)
      return checkStatus()
    })
  }

  return checkStatus()
})
```

**使用示例**：
```typescript
it('should complete long-running task', () => {
  cy.request('POST', '/api/tasks/start', { type: 'process' })
    .then((response) => {
      const taskId = response.body.taskId

      // 轮询等待任务完成
      cy.waitForTaskComplete(taskId, 60000)

      // 验证结果
      cy.visit('/tasks')
      cy.get(`[data-testid="task-${taskId}"]`)
        .should('contain', 'Completed')
    })
})
```

---

## 调试和日志

### 1. 分层日志系统

为了便于调试测试失败，应该在多个层面添加日志：

#### 后端日志

在关键操作点添加详细日志：

```python
# Python/Flask 示例
@app.route('/api/process', methods=['POST'])
def process():
    data = request.json
    print(f"\n[API] ========== POST /api/process ==========")
    print(f"[API] Request data: {data}")

    try:
        result = do_processing(data)
        print(f"[API] ✓ SUCCESS: {result}")
        print("[API] ==========================================\n")
        return jsonify(result), 200
    except Exception as e:
        print(f"[API] ✗ ERROR: {str(e)}")
        print("[API] ==========================================\n")
        return jsonify({"error": str(e)}), 500
```

#### 前端日志

在 HTTP 请求和关键业务逻辑添加日志：

```typescript
// HTTP 层
export async function postRequest(url: string, data: any) {
  console.log(`[HTTP] POST ${url}`, data)

  try {
    const response = await axios.post(url, data)
    console.log(`[HTTP] POST ${url} - Status: ${response.status}`, response.data)
    return response.data
  } catch (error) {
    console.error(`[HTTP] POST ${url} - ERROR:`, error)
    throw error
  }
}

// Service 层
export async function processData(data: any) {
  console.log('[Service] processData - Input:', data)
  const result = await postRequest('/api/process', data)
  console.log('[Service] processData - Result:', result)
  return result
}
```

#### Cypress 测试日志

在测试中添加清晰的日志：

```typescript
it('should process data correctly', () => {
  cy.log('🔄 Starting data processing test')

  cy.get('[data-testid="input"]').type('test data')
  cy.log('✅ Input data entered')

  cy.get('[data-testid="submit"]').click()
  cy.log('📤 Submit button clicked')

  cy.get('[data-testid="result"]').should('contain', 'Success')
  cy.log('✅ Result verified')
})
```

**日志位置**：
- 后端日志：`/path/to/project/log/backend.log`
- Cypress 日志：`/path/to/project/log/cypress.log`
- 浏览器日志：开发者工具 Console

### 2. 调试技巧

#### 使用 cy.pause() 暂停执行

```typescript
it('should do something', () => {
  cy.visit('/page')
  cy.pause()  // 测试会在这里暂停，可以检查 UI 状态
  cy.get('[data-testid="button"]').click()
})
```

在暂停状态下，可以：
- 在浏览器中检查 DOM 状态
- 在 DevTools Console 中执行命令
- 点击 Cypress UI 中的"继续"按钮恢复执行

#### 使用 cy.debug() 输出调试信息

```typescript
cy.get('[data-testid="list"]')
  .debug()  // 在 DevTools 中查看元素详情
  .children()
  .should('have.length', 5)
```

#### 截图和视频

Cypress 会自动在失败时截图：

```typescript
// cypress.config.ts
export default defineConfig({
  e2e: {
    screenshotOnRunFailure: true,  // 失败时截图
    video: true,                    // 记录视频
    videoCompression: 32,           // 视频压缩率
  }
})
```

手动截图：

```typescript
it('should render correctly', () => {
  cy.visit('/page')
  cy.screenshot('page-loaded')  // 手动截图
  cy.get('[data-testid="content"]').screenshot('content-area')
})
```

#### 只运行特定测试

```typescript
// 只运行这一个测试
it.only('should test specific feature', () => {
  // ...
})

// 跳过这个测试
it.skip('should test another feature', () => {
  // ...
})

// 套件级别
describe.only('Feature A', () => {
  // 只运行这个套件
})
```

#### 查看网络请求

```typescript
it('should make API calls', () => {
  // 拦截并记录所有请求
  cy.intercept('**/api/**').as('apiCalls')

  cy.visit('/page')
  cy.get('[data-testid="load-data"]').click()

  // 在 Cypress UI 的 Routes 面板查看所有请求
  cy.wait('@apiCalls')
})
```

### 3. 常见调试场景

#### 场景 1：测试随机失败

**问题特征**：测试有时通过，有时失败

**可能原因**：
1. 使用了固定的 `cy.wait()` 而不是条件等待
2. 测试数据未正确隔离
3. 异步操作未正确处理

**调试步骤**：
```typescript
// 添加详细日志
it('should load data', () => {
  cy.log('Step 1: Visit page')
  cy.visit('/page')

  cy.log('Step 2: Wait for loading')
  cy.get('[data-testid="loading"]').should('be.visible')
  cy.get('[data-testid="loading"]').should('not.exist')

  cy.log('Step 3: Verify data')
  cy.get('[data-testid="data"]').should('be.visible')
})

// 检查网络请求
cy.intercept('GET', '/api/data').as('getData')
cy.wait('@getData').then((interception) => {
  cy.log('API Response:', interception.response)
})
```

#### 场景 2：元素找不到

**错误信息**：`Timed out retrying: Expected to find element: [data-testid="xxx"], but never found it.`

**可能原因**：
1. 元素还未渲染
2. 选择器错误
3. 元素在 iframe 中
4. 元素被 CSS 隐藏

**调试步骤**：
```typescript
// 检查页面 HTML
cy.get('body').then(($body) => {
  cy.log('Body HTML:', $body.html())
})

// 检查元素是否存在但不可见
cy.get('[data-testid="xxx"]', { timeout: 10000 })
  .should('exist')  // 先确认元素存在
  .should('be.visible')  // 再确认可见

// 检查是否在 iframe 中
cy.iframe('[data-testid="iframe-id"]')
  .find('[data-testid="xxx"]')
  .should('be.visible')
```

#### 场景 3：文件操作验证失败

参考[文件系统操作验证](#文件系统操作验证)章节。

关键调试点：
1. 检查后端日志确认文件操作是否执行
2. 增加重试次数和延迟
3. 手动检查文件系统状态

```typescript
// 添加详细日志到验证命令
cy.verifyFileDistribution(testDir, expected, {
  maxRetries: 20,  // 增加重试次数
  retryDelay: 500  // 增加延迟
}).then(() => {
  // 验证成功后的回调
  cy.log('✅ File distribution verified successfully')
}).catch((error) => {
  // 失败时记录详细信息
  cy.log('❌ File distribution verification failed:', error)
  cy.task('listFiles', testDir).then((files) => {
    cy.log('Actual files:', files)
  })
})
```

---

## 常见问题和解决方案

### Q1: 测试在 CI 环境中不稳定，但本地通过

**可能原因**：
- CI 环境资源有限，操作响应较慢
- 使用了固定的 `cy.wait()` 而不是条件等待
- 屏幕分辨率不同导致 UI 渲染问题

**解决方案**：
1. 使用条件等待而不是固定等待
   ```typescript
   // ❌ 不稳定
   cy.wait(1000)

   // ✅ 稳定
   cy.get('[data-testid="content"]').should('be.visible')
   ```

2. 增加超时时间
   ```typescript
   // cypress.config.ts
   export default defineConfig({
     e2e: {
       defaultCommandTimeout: 10000,  // 增加到 10 秒（默认 4 秒）
       pageLoadTimeout: 60000         // 页面加载超时 60 秒
     }
   })
   ```

3. 设置一致的视口大小
   ```typescript
   beforeEach(() => {
     cy.viewport(1920, 1080)  // 设置固定分辨率
   })
   ```

### Q2: 测试互相影响，前一个测试的状态影响后续测试

**可能原因**：
- 应用状态（store/state）未重置
- 测试数据未隔离（共用文件目录、数据库等）
- 浏览器存储（localStorage、cookies）未清理

**解决方案**：
参考[测试数据隔离](#测试数据隔离)章节，确保：
1. 每个测试前重置应用状态
2. 使用独立的测试数据目录
3. 清理后端持久化状态
4. Cypress 会自动清理浏览器存储（但可以手动确认）

### Q3: 元素存在但 Cypress 说找不到

**可能原因**：
- 元素在 Shadow DOM 中
- 元素在 iframe 中
- 元素被 CSS 完全隐藏（display: none）
- 选择器错误或过于复杂

**解决方案**：
```typescript
// 1. 检查元素是否真的存在
cy.get('body').then(($body) => {
  console.log($body.html())  // 打印整个页面 HTML
})

// 2. 如果在 iframe 中
cy.get('iframe[data-testid="my-iframe"]')
  .its('0.contentDocument.body')
  .should('not.be.empty')
  .then(cy.wrap)
  .find('[data-testid="target"]')

// 3. 忽略可见性检查（谨慎使用）
cy.get('[data-testid="hidden-element"]', { force: true })
  .click({ force: true })
```

### Q4: 文件系统操作验证总是超时

**可能原因**：
- 文件系统操作确实失败了
- 重试次数不够
- 后端 API 路径或参数错误

**解决方案**：
1. 检查后端日志确认操作是否执行
2. 增加重试次数和延迟
   ```typescript
   cy.verifyFileDistribution(testDir, expected, {
     maxRetries: 30,   // 增加到 30 次
     retryDelay: 1000  // 增加到 1 秒
   })
   ```
3. 手动验证后端 API 是否工作
   ```typescript
   cy.request('/api/check-files?path=' + testDir)
     .then((response) => {
       cy.log('API Response:', response.body)
     })
   ```

### Q5: 网络请求被缓存，测试数据不更新

**可能原因**：
- 浏览器缓存 GET 请求
- 后端返回了缓存头

**解决方案**：
```typescript
// 方案 1：禁用缓存
cy.visit('/page', {
  onBeforeLoad(win) {
    // 禁用缓存
    win.fetch = new Proxy(win.fetch, {
      apply(target, thisArg, args) {
        const [url, options = {}] = args
        options.cache = 'no-store'
        return Reflect.apply(target, thisArg, [url, options])
      }
    })
  }
})

// 方案 2：在 URL 中添加时间戳
cy.visit(`/page?_t=${Date.now()}`)

// 方案 3：使用 cy.intercept 强制不缓存
cy.intercept('GET', '/api/**', (req) => {
  req.headers['cache-control'] = 'no-cache'
})
```

### Q6: Cypress 命令执行顺序不符合预期

**可能原因**：
- 误解了 Cypress 的命令队列机制
- 混用同步和异步代码

**Cypress 命令是异步的**：

```typescript
// ❌ 错误：这不会按预期工作
let value
cy.get('[data-testid="value"]').then(($el) => {
  value = $el.text()
})
console.log(value)  // undefined - 这行会先执行

// ✅ 正确：使用 then 链式调用
cy.get('[data-testid="value"]')
  .then(($el) => {
    const value = $el.text()
    cy.log('Value:', value)
    // 在这里继续后续操作
  })

// ✅ 正确：使用 Cypress 别名
cy.get('[data-testid="value"]')
  .invoke('text')
  .as('value')

cy.get('@value').then((value) => {
  cy.log('Value:', value)
})
```

### Q7: 需要等待多个异步操作完成

**解决方案**：

```typescript
// 等待多个 API 请求
cy.intercept('GET', '/api/users').as('getUsers')
cy.intercept('GET', '/api/settings').as('getSettings')

cy.visit('/dashboard')

cy.wait(['@getUsers', '@getSettings'])  // 等待两个请求都完成
cy.get('[data-testid="dashboard"]').should('be.visible')
```

```typescript
// 等待多个 UI 元素
cy.get('[data-testid="user-list"]').should('be.visible')
cy.get('[data-testid="settings-panel"]').should('be.visible')
cy.get('[data-testid="notifications"]').should('be.visible')
// 所有 should 都通过后才继续
```

---

## 性能优化建议

### 1. 减少不必要的 cy.visit()

```typescript
// ❌ 低效：每个测试都重新访问页面
beforeEach(() => {
  cy.visit('/page')
})

// ✅ 高效：只在必要时访问
before(() => {
  cy.visit('/page')
})

beforeEach(() => {
  // 只重置状态
  cy.resetAppState()
})
```

### 2. 并行运行测试

```bash
# 使用 Cypress Dashboard 或其他工具并行运行
npm run cypress:run --record --parallel
```

### 3. 使用 cy.intercept stub 替代真实 API

```typescript
// 对于不需要测试 API 的场景，使用 stub 加快速度
cy.intercept('GET', '/api/slow-endpoint', {
  fixture: 'mock-data.json'
}).as('getData')

cy.visit('/page')
cy.wait('@getData')  // 立即返回 mock 数据
```

### 4. 减少固定等待时间

```typescript
// ❌ 慢：固定等待
cy.wait(2000)

// ✅ 快：条件等待（一旦条件满足立即继续）
cy.get('[data-testid="loading"]').should('not.exist')
```

---

## 测试 Checklist

在编写新测试或审查测试代码时，使用此检查清单：

### 测试隔离
- [ ] 每个测试使用独立的测试数据（文件目录、数据库记录等）
- [ ] beforeEach 中重置应用状态（store/state management）
- [ ] beforeEach 中清理后端持久化状态
- [ ] afterEach 中清理测试产生的数据
- [ ] 测试可以任意顺序执行而不失败
- [ ] 测试可以单独运行（`it.only`）而不失败

### 异步操作
- [ ] 文件系统操作使用带重试的后端 API 验证
- [ ] 不使用固定 `cy.wait()` 等待 API 调用或文件操作
- [ ] 使用条件等待（`.should()`）而不是固定等待
- [ ] 正确处理 debounced/throttled 操作

### 选择器和元素交互
- [ ] 优先使用 `data-testid` 属性作为选择器
- [ ] 避免使用脆弱的选择器（CSS 类、复杂路径）
- [ ] 在操作元素前等待元素可见
- [ ] 验证元素状态（enabled、visible 等）后再交互

### 测试质量
- [ ] 测试名称清晰描述功能和期望结果
- [ ] 每个测试只验证一个功能点（单一职责）
- [ ] 测试遵循 Arrange-Act-Assert 模式
- [ ] 添加了适当的日志便于调试
- [ ] 失败时提供有用的错误信息

### 性能
- [ ] 减少不必要的 `cy.visit()` 调用
- [ ] 使用 `cy.intercept` stub 加速不关键的 API 调用
- [ ] 避免过长的固定等待时间
- [ ] 考虑并行运行测试的可能性

### 代码质量
- [ ] 遵循项目的代码规范
- [ ] 提取重复代码为自定义命令或辅助函数
- [ ] 添加必要的注释解释复杂逻辑
- [ ] 测试代码易于理解和维护

---

## 模块特定规范

不同模块可能有特定的测试规范要求。请参考各模块目录下的 `cypress_test_case.md` 文件获取详细信息。

### Photo Classifier 特定规范

参考：[cypress/e2e/photo-classifier/cypress_test_case.md](photo-classifier/cypress_test_case.md)

**关键点**：
- Q/W 键会自动前进到下一张，不要在后面再调用 `cy.goToNextImage()`
- 每个测试前必须调用 `cy.resetPhotoClassifierStore()`
- 使用 `cy.verifyFileDistribution()` 验证文件移动操作

### 其他模块

随着项目发展，其他模块的特定规范会添加到此处。

---

## 总结

### 核心原则

1. ✅ **测试隔离**：每个测试独立运行，不依赖其他测试
2. ✅ **条件等待**：使用 `.should()` 和带重试的 API 验证，避免固定 `cy.wait()`
3. ✅ **清晰命名**：测试和变量名应该自解释
4. ✅ **单一职责**：每个测试只验证一个功能点
5. ✅ **优质选择器**：优先使用 `data-testid` 属性
6. ✅ **充分日志**：在关键步骤添加日志便于调试
7. ✅ **快速反馈**：优化测试性能，减少等待时间

### 持续改进

- 定期审查和更新测试代码
- 学习和分享测试最佳实践
- 记录新发现的坑和解决方案
- 保持文档更新

---

**文档版本**：1.0
**最后更新**：2026-05-18
**维护者**：Script Orchestra Team
