---
auto_consolidated: false
confidence: 0.8
created_at: '2026-03-02T14:30:00+09:00'
version: 1
---

# テナント分離設計

> 作成日: 2026-03-02
> 作成者: Sora（リードエンジニア）
> 目的: v0.3テナント分離バグの教訓を元にした設計原則
> 更新: 2026-03-02 14:30 — API障害対応後に教訓を追記

## 概要

PixelForgeはマルチテナントSaaSとして設計されており、テナント間のデータ分離が最重要セキュリティ要件。
v0.3のインシデント（キャッシュキーにテナントID未含有 → 他テナントのデザインが閲覧可能）を受けて、本ドキュメントを作成。

## アーキテクチャ

### テナント分離の3層

```
Layer 1: 認証（JWT の tid クレーム）
  ↓
Layer 2: ミドルウェア（setTenant() でコンテキスト設定）
  ↓
Layer 3: データアクセス（全クエリに tenant_id 条件を自動付与）
```

### `setTenant()` と `setTeamId()` の分離

| 関数 | スコープ | 責務 |
|------|---------|------|
| `setTenant(req)` | DBスコープ | JWTからテナントIDを抽出し、`req.ctx.tenantId` に設定 |
| `setTeamId(req)` | アプリスコープ | チームIDを設定し、チーム内の権限チェックに使用 |

**重要**: `setTenant()` なしで `setTeamId()` を呼ぶのはバグ。必ずテナント分離が先。

## キャッシュキー設計

### 必須ルール: キャッシュキーに必ずテナントIDを含める

```typescript
// ❌ NG パターン — v0.3のバグ原因
const cacheKey = `design:${designId}`;
const cached = await redis.get(cacheKey);

// ✅ OK パターン — テナントIDプレフィックス
const cacheKey = `tenant:${tenantId}:design:${designId}`;
const cached = await redis.get(cacheKey);
```

### キャッシュキーの命名規則

```
{entity}:{tenantId}:{resourceType}:{resourceId}[:{qualifier}]
```

例:
- `tenant:t_abc123:design:d_xyz789` — デザインキャッシュ
- `tenant:t_abc123:designList:page1` — デザイン一覧キャッシュ
- `tenant:t_abc123:user:u_def456:prefs` — ユーザー設定キャッシュ

### キャッシュ無効化

テナント単位の一括無効化をサポート:

```typescript
async function invalidateTenantCache(tenantId: string): Promise<void> {
  const keys = await redis.keys(`tenant:${tenantId}:*`);
  if (keys.length > 0) {
    await redis.del(...keys);
  }
}
```

## v0.3 インシデント詳細

### 発生日時
2026-03-02 13:00 JST

### 影響
顧客が他テナントのデザインを閲覧可能な状態（約30分間）

### 根本原因
`design-cache.ts` のキャッシュキーにテナントIDが含まれていなかった。

```typescript
// Before (バグ)
cache.get(designId)

// After (修正)
cache.get(`${tenantId}:${designId}`)
```

### 対応タイムライン
- 13:00 — Hinaが顧客からの報告を受信
- 13:05 — `grep -r 'setTenant\|setTeamId' src/api/` で全箇所調査
- 13:10 — design-cache.ts で問題箇所特定
- 13:15 — 修正コミット + テスト追加
- 13:30 — PR #11 マージ → ホットフィックスデプロイ
- 14:00 — Board で修正完了を報告
- 15:00 — Hinaが影響5社に通知完了

### 再発防止策

1. **PRレビューチェックリスト**: 「キャッシュキーにテナントIDを含むか」を追加
2. **E2Eテスト**: 異なるテナントからの同時アクセステストを追加
3. **静的解析**: `cache.get()` 呼び出しにテナントIDパターンがない場合に警告

## テストパターン

### テナント分離テスト

```typescript
describe('Tenant Isolation', () => {
  it('should not return other tenant designs', async () => {
    const tenantA = await createTenant('A');
    const tenantB = await createTenant('B');
    const design = await createDesign(tenantA, { name: 'Secret Design' });

    const res = await request(app)
      .get(`/api/v2/designs/${design.id}`)
      .set('Authorization', `Bearer ${tenantB.token}`);

    expect(res.status).toBe(404);
  });

  it('should isolate cache between tenants', async () => {
    const tenantA = await createTenant('A');
    const tenantB = await createTenant('B');

    await request(app)
      .get('/api/v2/designs')
      .set('Authorization', `Bearer ${tenantA.token}`);

    const res = await request(app)
      .get('/api/v2/designs')
      .set('Authorization', `Bearer ${tenantB.token}`);

    expect(res.body.designs).not.toContainEqual(
      expect.objectContaining({ tenant_id: tenantA.id })
    );
  });

  it('should invalidate only target tenant cache', async () => {
    const tenantA = await createTenant('A');
    const tenantB = await createTenant('B');

    await populateCache(tenantA);
    await populateCache(tenantB);
    await invalidateTenantCache(tenantA.id);

    const keysA = await redis.keys(`tenant:${tenantA.id}:*`);
    const keysB = await redis.keys(`tenant:${tenantB.id}:*`);

    expect(keysA).toHaveLength(0);
    expect(keysB.length).toBeGreaterThan(0);
  });
});
```
