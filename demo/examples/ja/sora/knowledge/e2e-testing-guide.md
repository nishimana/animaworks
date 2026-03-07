---
auto_consolidated: false
confidence: 0.8
created_at: '2026-03-03T10:00:00+09:00'
version: 1
---

# PixelForge E2Eテストガイド

> 作成日: 2026-03-03
> 作成者: Sora（リードエンジニア）
> 目的: Playwrightベースのテスト戦略を標準化

## テストフレームワーク

- **E2E**: Playwright (TypeScript)
- **ユニット**: Vitest
- **API**: supertest + Vitest
- **カバレッジ**: v8 (istanbul互換出力)

## テスト構成

### 3段階テストスイート

| スイート | 実行時間 | 対象 | トリガー |
|---------|---------|------|---------|
| `smoke` | ~2分 | クリティカルパス10件 | 全PR |
| `regression` | ~15分 | 既知バグの回帰テスト50件 | リリース前 |
| `full` | ~45分 | 全テスト142件 | リリース最終確認 |

### ディレクトリ構成

```
tests/
├── e2e/
│   ├── smoke/           # クリティカルパステスト
│   │   ├── auth.spec.ts
│   │   ├── design-crud.spec.ts
│   │   └── tenant-isolation.spec.ts
│   ├── regression/      # 回帰テスト
│   │   ├── cache-tenant-id.spec.ts  # v0.3 bug
│   │   └── concurrent-access.spec.ts
│   └── full/            # 全機能テスト
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

## Playwrightの設定

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

## テスト実行コマンド

```bash
# Smokeテスト（PRマージ前）
npx playwright test --project=chromium tests/e2e/smoke/

# 回帰テスト（リリース前日）
npx playwright test tests/e2e/regression/

# 全テスト（リリース最終確認）
npx playwright test

# カバレッジ付き全テスト
npx vitest run --coverage
```

## CI/CD統合（GitHub Actions）

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

## フレーキーテスト対応

### 検出

```bash
# 10回繰り返し実行でフレーキーを検出
npx playwright test --repeat-each=10 tests/e2e/smoke/
```

### 対処方針

| 原因 | 対処 |
|------|------|
| タイミング依存 | `waitForSelector` / `waitForResponse` を使う。固定 `sleep` 禁止 |
| テスト間依存 | `beforeEach` でDB/キャッシュを初期化 |
| 外部API依存 | MSW (Mock Service Worker) でモック |
| ブラウザ差異 | プロジェクトごとにスキップ条件を定義 |

### リトライ戦略

- CI: 最大2回リトライ
- リトライ成功 → 結果はパスだがフレーキーとしてマーク
- 週次でフレーキーテストを根本原因分析 → 修正

## カバレッジ基準

| 指標 | 基準 | v0.4実績 |
|------|------|---------|
| ライン | ≥ 80% | 83.2% |
| ブランチ | ≥ 70% | 76.1% |
| 関数 | ≥ 85% | 89.4% |

## テスト作成ガイドライン

1. **AAA パターン**: Arrange → Act → Assert
2. **1テスト1アサーション**: 複数のことを検証しない
3. **テストデータはフィクスチャ**: ハードコードしない
4. **テナント分離を必ずテスト**: 新APIエンドポイント追加時は必須
5. **スナップショットは控えめに**: UIの構造変更で壊れやすい

## v0.4 テスト結果サマリー

```
Tests:   142 passed, 0 failed
Time:    42.3 seconds
Coverage:
  Lines:      83.2%
  Branches:   76.1%
  Functions:  89.4%
  Statements: 82.8%
```
