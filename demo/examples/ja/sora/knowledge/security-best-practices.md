---
auto_consolidated: false
confidence: 0.8
created_at: '2026-03-02T10:00:00+09:00'
version: 1
---

# PixelForge セキュリティベストプラクティス

> 作成日: 2026-03-02
> 作成者: Sora（リードエンジニア）
> 目的: v0.3セキュリティ監査で得た知見を体系化
> 参照: OWASP Top 10 2025, OWASP API Security Top 10

## 1. Content Security Policy (CSP)

### 問題（v0.3で発覚）

CSPヘッダーが未設定だった。XSSインジェクションのリスクがあった。

### 対応（PR #8）

```
Content-Security-Policy:
  default-src 'self';
  script-src 'self' 'nonce-{random}';
  style-src 'self' 'unsafe-inline';
  img-src 'self' data: https://cdn.pixelforge.dev;
  font-src 'self' https://fonts.gstatic.com;
  connect-src 'self' https://api.pixelforge.dev wss://ws.pixelforge.dev;
  frame-ancestors 'none';
  base-uri 'self';
  form-action 'self';
  upgrade-insecure-requests;
```

### 実装詳細

```typescript
import { randomBytes } from 'crypto';

export function cspMiddleware(req: Request, res: Response, next: NextFunction) {
  const nonce = randomBytes(16).toString('base64');
  res.locals.cspNonce = nonce;

  res.setHeader('Content-Security-Policy', [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}'`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: https://cdn.pixelforge.dev",
    "font-src 'self' https://fonts.gstatic.com",
    "connect-src 'self' https://api.pixelforge.dev wss://ws.pixelforge.dev",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "upgrade-insecure-requests"
  ].join('; '));

  next();
}
```

**ポイント:**
- `script-src` にnonce方式を採用（`unsafe-inline` を避ける）
- `frame-ancestors 'none'` でクリックジャッキング防止
- `upgrade-insecure-requests` でHTTP→HTTPS自動昇格

### テスト

```typescript
describe('CSP Header', () => {
  it('should include nonce in script-src', async () => {
    const res = await request(app).get('/');
    const csp = res.headers['content-security-policy'];
    expect(csp).toMatch(/script-src 'self' 'nonce-[A-Za-z0-9+/=]+'/);
  });

  it('should block inline scripts without nonce', async () => {
    // Playwright E2E test
    const violations = await page.evaluate(() => {
      return new Promise(resolve => {
        document.addEventListener('securitypolicyviolation', e => resolve(e));
        const script = document.createElement('script');
        script.textContent = 'alert(1)';
        document.body.appendChild(script);
      });
    });
    expect(violations).toBeDefined();
  });
});
```

## 2. CORS設定

### 問題（v0.3で発覚）

CORS設定が `Access-Control-Allow-Origin: *` だった。任意のオリジンからAPIにアクセス可能。

### 対応（PR #9）

ホワイトリスト方式に変更:

```typescript
const ALLOWED_ORIGINS = [
  'https://app.pixelforge.dev',
  'https://staging.pixelforge.dev',
  ...(process.env.NODE_ENV === 'development' ? ['http://localhost:3000'] : []),
];

export function corsMiddleware(req: Request, res: Response, next: NextFunction) {
  const origin = req.headers.origin;
  if (origin && ALLOWED_ORIGINS.includes(origin)) {
    res.setHeader('Access-Control-Allow-Origin', origin);
    res.setHeader('Access-Control-Allow-Credentials', 'true');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, PATCH, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-API-Key');
    res.setHeader('Access-Control-Max-Age', '86400');
  }

  if (req.method === 'OPTIONS') {
    return res.sendStatus(204);
  }
  next();
}
```

**ポイント:**
- `*` は絶対に使わない（Credentialsと併用不可でもセキュリティリスク）
- オリジンホワイトリストを環境変数でも管理可能にする
- `Max-Age: 86400` でpreflight頻度を削減

## 3. XSS対策

### DOMPurify によるサニタイズ

ユーザー入力をDOMに挿入する全箇所でサニタイズ:

```typescript
import DOMPurify from 'dompurify';

const PURIFY_CONFIG = {
  ALLOWED_TAGS: ['b', 'i', 'em', 'strong', 'a', 'p', 'br', 'ul', 'ol', 'li'],
  ALLOWED_ATTR: ['href', 'title', 'target'],
  ALLOW_DATA_ATTR: false,
};

export function sanitize(dirty: string): string {
  return DOMPurify.sanitize(dirty, PURIFY_CONFIG);
}
```

### 追加防御層

```typescript
res.setHeader('X-Content-Type-Options', 'nosniff');
res.setHeader('X-Frame-Options', 'DENY');
res.setHeader('X-XSS-Protection', '0');  // CSPで代替
res.setHeader('Referrer-Policy', 'strict-origin-when-cross-origin');
res.setHeader('Permissions-Policy', 'camera=(), microphone=(), geolocation=()');
```

## 4. APIレート制限

### 問題（v0.3で発覚）

レート制限が未実装。API乱用のリスク。

### 対応（PR #10）

Token Bucket + Redis で実装:

```typescript
import Redis from 'ioredis';

const redis = new Redis(process.env.REDIS_URL);

export async function rateLimitMiddleware(req: Request, res: Response, next: NextFunction) {
  const tier = req.apiKey?.tier ?? 'free';
  const config = TIER_CONFIGS[tier];
  const key = `ratelimit:${req.apiKey?.id ?? req.ip}`;

  const now = Date.now();
  const bucket = await redis.hgetall(key);

  let tokens = bucket.tokens ? parseFloat(bucket.tokens) : config.maxTokens;
  const lastRefill = bucket.lastRefill ? parseInt(bucket.lastRefill) : now;

  const elapsed = (now - lastRefill) / 1000;
  tokens = Math.min(config.maxTokens, tokens + elapsed * config.refillRate);

  if (tokens < 1) {
    const retryAfter = Math.ceil((1 - tokens) / config.refillRate);
    res.setHeader('Retry-After', retryAfter.toString());
    res.setHeader('X-RateLimit-Limit', config.maxTokens.toString());
    res.setHeader('X-RateLimit-Remaining', '0');
    return res.status(429).json({
      type: 'https://api.pixelforge.dev/errors/rate-limit-exceeded',
      title: 'Rate Limit Exceeded',
      status: 429,
      detail: `Rate limit exceeded. Retry after ${retryAfter} seconds.`,
      retry_after: retryAfter,
    });
  }

  tokens -= 1;
  await redis.hmset(key, { tokens: tokens.toString(), lastRefill: now.toString() });
  await redis.expire(key, 120);

  res.setHeader('X-RateLimit-Limit', config.maxTokens.toString());
  res.setHeader('X-RateLimit-Remaining', Math.floor(tokens).toString());
  next();
}
```

## 5. その他のセキュリティ対策

### SQL インジェクション防止

- ORMのパラメータバインディングを必須化
- 生SQL禁止（ESLintルールで検出）

### 依存関係の脆弱性管理

```bash
npm audit --audit-level=high
npx better-npm-audit audit
```

- CI/CDで `npm audit` を自動実行
- CRITICAL/HIGHは即時対応（リリースブロッカー）

### ログ・監査

- 認証失敗は全てログ（IPアドレス、User-Agent付き）
- 管理者操作は監査ログに記録
- 個人情報はログに出力しない（マスキング処理）

## チェックリスト（PRレビュー用）

- [ ] CSPヘッダーが正しく設定されているか
- [ ] CORSオリジンがホワイトリスト方式か
- [ ] ユーザー入力はサニタイズされているか
- [ ] キャッシュキーにテナントIDが含まれているか
- [ ] レート制限が適用されているか
- [ ] エラーレスポンスに内部情報が含まれていないか
- [ ] 依存関係に既知の脆弱性がないか

## OWASP Top 10 対応状況

| # | リスク | 対応状況 |
|---|--------|---------|
| A01 | Broken Access Control | ✅ テナント分離 + RBAC |
| A02 | Cryptographic Failures | ✅ bcrypt + JWT署名 |
| A03 | Injection | ✅ ORM + DOMPurify |
| A04 | Insecure Design | ✅ セキュリティレビュー必須化 |
| A05 | Security Misconfiguration | ✅ CSP + CORS + ヘッダー |
| A06 | Vulnerable Components | ✅ npm audit CI |
| A07 | Authentication Failures | ✅ JWT + API Key二重認証 |
| A08 | Data Integrity Failures | ✅ 署名検証 |
| A09 | Logging & Monitoring | ✅ 監査ログ |
| A10 | SSRF | ✅ URL検証 + ホワイトリスト |
