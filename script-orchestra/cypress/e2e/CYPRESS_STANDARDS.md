# Cypress Testing Standards

This document defines common standards and best practices for writing Cypress E2E tests in this project.

## File System Verification

### Retry Mechanism

When verifying file operations (move, copy, delete), always use retry-based verification instead of fixed waits.

**✅ DO:**
```typescript
cy.verifyFileDistribution({
  testDir: testDir,
  expected: { normal: 4, remaining: 0 },
  maxRetries: 15,
  retryDelay: 1000
})
```

**❌ DON'T:**
```typescript
cy.wait(5000) // Fixed wait - brittle and unreliable
cy.verifyFileExists(filePath)
```

### Recommended Retry Parameters

| Operation Type | maxRetries | retryDelay (ms) | Total Wait Time |
|---------------|------------|-----------------|-----------------|
| Simple file move (1-5 files) | 15 | 1000 | up to 15s |
| Batch operations (5-10 files) | 20 | 1000 | up to 20s |
| Large batch (10+ files) | 40 | 2000 | up to 80s |
| Quick checks (UI state sync) | 10 | 500 | up to 5s |

### Why Retry Instead of Fixed Wait?

1. **File system operations are asynchronous** - timing varies by system load, disk speed, and OS
2. **CI/CD environments are slower** - what works locally may timeout in CI
3. **Retry mechanisms are self-optimizing** - they complete as soon as ready, rather than always waiting the maximum time
4. **Better failure diagnosis** - retries provide visibility into timing issues vs. functional bugs

### Implementation Pattern

Custom commands that interact with file system should follow this pattern:

```typescript
Cypress.Commands.add('verifyFileDistribution', (options) => {
  const { testDir, expected, maxRetries = 15, retryDelay = 1000 } = options

  function attemptVerification(retriesLeft) {
    cy.request('POST', '/api/cypress/verify-distribution', { testDir, expected })
      .then((response) => {
        if (response.body.success) {
          cy.log('✅ File distribution verified')
        } else if (retriesLeft > 0) {
          cy.wait(retryDelay)
          attemptVerification(retriesLeft - 1)
        } else {
          throw new Error(`File verification failed after ${maxRetries} retries`)
        }
      })
  }

  attemptVerification(maxRetries)
})
```

### Key Principle

**Never use fixed `cy.wait()` for file system operations.** File system timing is unpredictable and varies across environments. Always use retry-based verification with backend API checks.

---

## UI Synchronization

### Vue Reactivity Timing

When testing Vue applications, account for reactivity delays:

**✅ DO:**
```typescript
// After navigation
cy.get('.main-image').should('be.visible')
cy.wait(500) // Allow Vue to complete reactivity updates
```

**❌ DON'T:**
```typescript
// Immediately interact after navigation
cy.visit('/photo-classifier/default-group')
cy.get('.header').invoke('text') // May read stale state
```

### Recommended Wait Times

| Scenario | Wait Time | Reason |
|----------|-----------|---------|
| After page navigation | 500ms | Vue component mount + reactivity |
| After keyboard shortcuts (Q/W keys) | 300ms | State update + UI refresh |
| After drawer/modal open | 200ms | Animation complete |
| After filter toggle | 500ms | Data filtering + re-render |

---

## Test Isolation

### Store State Management

Always reset application state between tests:

```typescript
beforeEach(() => {
  cy.resetPhotoClassifierStore() // Clear Pinia/Vuex state
})
```

### Test Data Isolation

Each test should use independent directories:

**✅ DO:**
```typescript
it('test case 1', () => {
  cy.setupTest({ testName: 'test_mark_normal', images: 4 })
})

it('test case 2', () => {
  cy.setupTest({ testName: 'test_mark_del', images: 4 })
})
```

**❌ DON'T:**
```typescript
const SHARED_DIR = '/tmp/test-data'

it('test case 1', () => {
  cy.setupTest({ testDir: SHARED_DIR, images: 4 })
})

it('test case 2', () => {
  cy.setupTest({ testDir: SHARED_DIR, images: 4 }) // Polluted by test 1
})
```

---

## Keyboard Interaction Patterns

### Auto-Advancing Keys

Some keyboard shortcuts auto-advance to the next item:

- **Q key**: Create new group → auto-advance
- **W key**: Add to current group → auto-advance

**✅ DO:**
```typescript
cy.pressKey('KeyQ') // Creates group AND advances
cy.wait(300)
// Now at next file
```

**❌ DON'T:**
```typescript
cy.pressKey('KeyQ')
cy.goToNextImage() // Double advance - skips a file!
```

---

## Common Anti-Patterns

### ❌ Fixed Waits for File Operations
```typescript
cy.wait(5000)
cy.verifyFileExists(path)
```

### ❌ Shared Test Data
```typescript
const SHARED_DIR = '/tmp/shared'
// Used across multiple tests - leads to test pollution
```

### ❌ Missing Store Reset
```typescript
// No beforeEach hook
it('test 1', () => { /* modifies store */ })
it('test 2', () => { /* inherits polluted state */ })
```

### ❌ Ignoring Auto-Advance
```typescript
cy.pressKey('KeyQ')
cy.goToNextImage() // Double advance - skips a file
```

### ❌ No Retry Logic for File System
```typescript
cy.exec('mv file.txt dest/')
cy.exec('ls dest/file.txt') // May fail if OS hasn't synced
```

---

## Photo Classifier Specific Standards

### Test Data Isolation

- Each test MUST use an independent `testName` to create isolated directories
- Call `cy.resetPhotoClassifierStore()` in `beforeEach` to clear Pinia store state
- Loading test media automatically cleans up `.photo_classifier_working_state.json`

### Keyboard Shortcuts

| Key | Action | Auto-Advance? |
|-----|--------|---------------|
| Z | Mark as best | No |
| X | Mark as better | No |
| C | Mark as normal | No |
| Backspace | Mark as del | No |
| Enter | Apply changes | No |
| Arrow Left/Right | Navigate | No |
| **Q** | Create new group | **Yes** |
| **W** | Add to current group | **Yes** |

**Critical**: Q and W keys automatically advance to the next file. Do NOT call `cy.goToNextImage()` after pressing these keys.

### UI Wait Times

After page navigation or transitions, wait for both:
1. Main element visible (e.g., `.main-image`)
2. Additional 500ms for Vue reactivity

```typescript
cy.get('.main-image').should('be.visible')
cy.wait(500) // Vue reactivity
```

After Q/W key presses:
```typescript
cy.pressKey('KeyQ')
cy.wait(300) // State update + UI refresh
```

### Best Practices

**✅ DO:**
1. Use independent testName for each test
2. Call `cy.resetPhotoClassifierStore()` in beforeEach
3. Use `cy.verifyFileDistribution()` instead of fixed `cy.wait()`
4. Wait 300ms after Q/W keys, don't call `cy.goToNextImage()`
5. Wait for `.main-image` visible + 500ms after page transitions
6. Use sufficient retries for file system sync

**❌ DON'T:**
1. Share state between tests
2. Use fixed `cy.wait()` for file operations
3. Manually advance after Q/W keys (causes file skipping)
4. Hard-code file paths (use `cy.setupTest()` returned paths)
5. Forget to call `cy.resetPhotoClassifierStore()`

---

## Version History

- **v1.0** (2026-05-27): Initial standards document
  - File system verification guidelines with retry mechanism
  - UI synchronization patterns for Vue applications
  - Test isolation requirements
  - Keyboard interaction standards
  - Common anti-patterns documentation
- **v1.1** (2026-05-27): Added Photo Classifier specific standards
  - Test data isolation requirements
  - Keyboard shortcuts reference table
  - UI wait times guidelines
  - Best practices checklist
