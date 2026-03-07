---
auto_consolidated: false
confidence: 0.8
created_at: '2026-03-03T10:00:00+09:00'
version: 1
---

# PixelForge E2E Testing Guide

> Created: 2026-03-03
> Author: Kai (Lead Engineer)
> Purpose: Standardize the Playwright-based testing strategy

## Test Framework

- **E2E**: Playwright (TypeScript)
- **Unit**: Vitest
- **API**: supertest + Vitest
- **Coverage**: v8 (istanbul-compatible output)

## Test Configuration

### 3-Tier Test Suite

| Suite | Duration | Scope | Trigger |
|-------|----------|-------|---------|
| `smoke` | ~2 min | 10 critical path tests | All PRs |
| `regression` | ~15 min | 50 known bug regression tests | Pre-release |
| `full` | ~45 min | All 142 tests | Final release verification |

### Directory Structure

```
tests/
├── e2e/
│   ├── smoke/           # Critical path tests
│   │   ├── auth.spec.ts
│   │   ├── design-crud.spec.ts
│   │   └── tenant-isolation.spec.ts
│   ├── regression/      # Regression tests
│   │   ├── cache-tenant-id.spec.ts  # v0.3 bug
│   │   └── concurrent-access.spec.ts
│   └── full/            # Full feature tests
│       ├── api/
│       ├── ui/
│       └── integration/
├── unit/
│   ├── services/
│   ├── middleware/
│   └── utils/
└── fixtures/
    ├── tenants.ts
    ├── designs.ts
    └── users.ts
```

## Playwright Configuration

```typescript
// playwright.config.ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 4 : undefined,
  reporter: [
    ['html'],
    ['junit', { outputFile: 'test-results/junit.xml' }],
  ],
  use: {
    baseURL: process.env.BASE_URL ?? 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit', use: { ...devices['Desktop Safari'] } },
  ],
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
  },
});
```

## Test Execution Commands

```bash
# Smoke tests (before PR merge)
npx playwright test --project=chromium tests/e2e/smoke/

# Regression tests (day before release)
npx playwright test tests/e2e/regression/

# Full tests (final release verification)
npx playwright test

# Full tests with coverage
npx vitest run --coverage
```

## CI/CD Integration (GitHub Actions)

```yaml
# .github/workflows/test.yml
name: Test Suite
on: [push, pull_request]

jobs:
  smoke:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - run: npm ci
      - run: npx playwright install --with-deps chromium
      - run: npx playwright test --project=chromium tests/e2e/smoke/

  full:
    if: github.ref == 'refs/heads/main' || startsWith(github.ref, 'refs/tags/v')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - run: npm ci
      - run: npx playwright install --with-deps
      - run: npx playwright test
      - run: npx vitest run --coverage
```

## Flaky Test Management

### Detection

```bash
# Repeat 10 times to detect flaky tests
npx playwright test --repeat-each=10 tests/e2e/smoke/
```

### Resolution Strategy

| Cause | Solution |
|-------|----------|
| Timing dependency | Use `waitForSelector` / `waitForResponse`. Fixed `sleep` is prohibited |
| Inter-test dependency | Initialize DB/cache in `beforeEach` |
| External API dependency | Mock with MSW (Mock Service Worker) |
| Browser differences | Define skip conditions per project |

### Retry Strategy

- CI: Up to 2 retries
- If retry succeeds → result is pass but marked as flaky
- Weekly root cause analysis of flaky tests → fix

## Coverage Targets

| Metric | Target | v0.4 Actual |
|--------|--------|-------------|
| Lines | ≥ 80% | 83.2% |
| Branches | ≥ 70% | 76.1% |
| Functions | ≥ 85% | 89.4% |

## Test Writing Guidelines

1. **AAA Pattern**: Arrange → Act → Assert
2. **One assertion per test**: Don't verify multiple things
3. **Use fixtures for test data**: No hardcoded values
4. **Always test tenant isolation**: Required when adding new API endpoints
5. **Use snapshots sparingly**: Fragile against UI structural changes

## v0.4 Test Results Summary

```
Tests:   142 passed, 0 failed
Time:    42.3 seconds
Coverage:
  Lines:      83.2%
  Branches:   76.1%
  Functions:  89.4%
  Statements: 82.8%
```
