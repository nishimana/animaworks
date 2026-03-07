---
auto_consolidated: false
confidence: 0.8
created_at: '2026-03-02T10:00:00+09:00'
version: 1
---

# PixelForge API アーキテクチャ設計原則

> 作成日: 2026-03-02
> 作成者: Sora（リードエンジニア）
> 目的: REST API設計の統一ルールと根拠を記録

## 概要

PixelForge APIはRESTful設計原則に基づき、マルチテナント対応のSaaSプラットフォームとして構築されている。
認証・認可・テナント分離・レート制限の4層で安全性を確保する。

## 認証方式

### JWT + API Key 二重認証

PixelForgeではJWTトークンとAPI Keyの二重認証を採用している。

```
Authorization: Bearer <jwt_token>
X-API-Key: <api_key>
```

**JWT トークン構造:**
- `sub`: ユーザーID
- `tid`: テナントID（必須 — テナント分離の基盤）
- `roles`: ロール配列（`["admin", "designer"]`）
- `exp`: 有効期限（デフォルト1時間）
- `iss`: `pixelforge-auth`

**API Key:**
- テナント単位で発行
- プレフィックス: `pf_live_` (本番) / `pf_test_` (テスト)
- ハッシュ化して保存（bcrypt）
- レート制限のTier判定に使用

### 認証フロー

```
Client → POST /api/v2/auth/login (email, password)
       ← { access_token, refresh_token, expires_in }

Client → GET /api/v2/designs (Authorization: Bearer <token>, X-API-Key: <key>)
       ← 認証ミドルウェアが検証 → テナントスコープ適用 → レスポンス
```

## テナント分離

### 原則: 全てのデータアクセスにテナントIDを含める

v0.3のインシデント（キャッシュキーにテナントID未含有）から学んだ教訓を反映。

**データベース層:**
```typescript
const designs = await db.designs
  .where('tenant_id', '=', ctx.tenantId)  // 必須
  .where('id', '=', designId)
  .first();
```

**キャッシュ層:**
```typescript
// NG: テナントID無し → 他テナントのデータを返す危険性
cache.get(designId)

// OK: テナントIDをプレフィックスに含める
cache.get(`${tenantId}:${designId}`)
```

**ミドルウェア:**
```typescript
export function setTenant(req: Request, res: Response, next: NextFunction) {
  const tenantId = req.jwt.tid;
  if (!tenantId) return res.status(403).json({ error: 'tenant_id_required' });
  req.ctx = { tenantId, userId: req.jwt.sub };
  next();
}
```

### `setTenant()` vs `setTeamId()` の違い

| 関数 | スコープ | 用途 |
|------|---------|------|
| `setTenant()` | DBスコープ | データベースクエリのWHERE句に自動付与 |
| `setTeamId()` | アプリケーションスコープ | チーム内の権限チェック（designer/viewer等） |

**重要**: `setTenant()` は全APIエンドポイントで必須。`setTeamId()` はチーム機能使用時のみ。

## レート制限

### Tier別制限値

| Tier | リクエスト/分 | バースト | AI生成/日 |
|------|-------------|---------|----------|
| Free | 100 | 150 | 10 |
| Pro | 1,000 | 1,500 | 100 |
| Enterprise | 無制限 | 無制限 | 1,000 |

### 実装: Token Bucket アルゴリズム

```typescript
interface RateLimitConfig {
  maxTokens: number;
  refillRate: number;  // tokens per second
  burstSize: number;
}

const TIER_CONFIGS: Record<string, RateLimitConfig> = {
  free:       { maxTokens: 100, refillRate: 1.67, burstSize: 150 },
  pro:        { maxTokens: 1000, refillRate: 16.67, burstSize: 1500 },
  enterprise: { maxTokens: Infinity, refillRate: Infinity, burstSize: Infinity },
};
```

**レスポンスヘッダー:**
```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 847
X-RateLimit-Reset: 1709344800
Retry-After: 30  (429の場合のみ)
```

## エラーレスポンス形式

RFC 7807 Problem Details for HTTP APIs に準拠:

```json
{
  "type": "https://api.pixelforge.dev/errors/rate-limit-exceeded",
  "title": "Rate Limit Exceeded",
  "status": 429,
  "detail": "You have exceeded 1000 requests per minute. Please retry after 30 seconds.",
  "instance": "/api/v2/designs/abc123",
  "retry_after": 30
}
```

### 標準エラーコード

| HTTP Status | type suffix | 説明 |
|-------------|------------|------|
| 400 | `/invalid-request` | リクエスト形式不正 |
| 401 | `/authentication-required` | 認証トークン無効 |
| 403 | `/insufficient-permissions` | 権限不足 |
| 404 | `/resource-not-found` | リソース不存在 |
| 409 | `/conflict` | 競合（同時編集等） |
| 429 | `/rate-limit-exceeded` | レート制限超過 |
| 500 | `/internal-error` | サーバー内部エラー |

## API バージョニング

- URLパスベース: `/api/v2/...`
- メジャーバージョンのみURLに含める
- マイナー変更は後方互換で追加
- 旧バージョン(`/api/v1/`)は6ヶ月の非推奨期間後に廃止

## パフォーマンス基準

| 指標 | 基準値 | v0.4実測値 |
|------|--------|-----------|
| p50 | < 50ms | 42ms |
| p95 | < 200ms | 147ms |
| p99 | < 500ms | 312ms |
| エラー率 | < 0.1% | 0.02% |

## 関連ドキュメント

- `knowledge/security-best-practices.md` — セキュリティ実装詳細
- `knowledge/tenant-isolation-design.md` — テナント分離の詳細設計
- `knowledge/e2e-testing-guide.md` — API テスト戦略
