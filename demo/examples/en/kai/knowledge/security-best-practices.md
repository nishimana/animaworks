---
auto_consolidated: false
confidence: 0.8
created_at: '2026-03-02T10:00:00+09:00'
version: 1
---

# PixelForge Security Best Practices

> Created: 2026-03-02
> Author: Kai (Lead Engineer)
> Purpose: Systematize findings from the v0.3 security audit
> References: OWASP Top 10 2025, OWASP API Security Top 10

## 1. Content Security Policy (CSP)

### Issue (Discovered in v0.3)

CSP headers were not configured. There was a risk of XSS injection.

### Resolution (PR #8)

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

### Implementation Details

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

**Key Points:**
- Using nonce-based approach for `script-src` (avoids `unsafe-inline`)
- `frame-ancestors 'none'` prevents clickjacking
- `upgrade-insecure-requests` auto-upgrades HTTP → HTTPS

### Tests

```typescript
describe('CSP Header', () => {
  it('should include nonce in script-src', async () => {
    const res = await request(app).get('/');
    const csp = res.headers['content-security-policy'];
    expect(csp).toMatch(/script-src 'self' 'nonce-[A-Za-z0-9+/=]+'/);
  });

  it('should block inline scripts without nonce', async () => {
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

## 2. CORS Configuration

### Issue (Discovered in v0.3)

CORS was set to `Access-Control-Allow-Origin: *`. Any origin could access the API.

### Resolution (PR #9)

Switched to whitelist approach:

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

**Key Points:**
- Never use `*` (security risk even when Credentials can't be combined with it)
- Origin whitelist should also be configurable via environment variables
- `Max-Age: 86400` reduces preflight request frequency

## 3. XSS Protection

### DOMPurify Sanitization

All user input insertion points into the DOM are sanitized:

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

### Additional Defense Layers

```typescript
res.setHeader('X-Content-Type-Options', 'nosniff');
res.setHeader('X-Frame-Options', 'DENY');
res.setHeader('X-XSS-Protection', '0');  // Superseded by CSP
res.setHeader('Referrer-Policy', 'strict-origin-when-cross-origin');
res.setHeader('Permissions-Policy', 'camera=(), microphone=(), geolocation=()');
```

## 4. API Rate Limiting

### Issue (Discovered in v0.3)

Rate limiting was not implemented. Risk of API abuse.

### Resolution (PR #10)

Implemented with Token Bucket + Redis:

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

## 5. Additional Security Measures

### SQL Injection Prevention

- ORM parameter binding is mandatory
- Raw SQL is prohibited (detected by ESLint rules)

### Dependency Vulnerability Management

```bash
npm audit --audit-level=high
npx better-npm-audit audit
```

- `npm audit` runs automatically in CI/CD
- CRITICAL/HIGH findings require immediate action (release blockers)

### Logging & Auditing

- All authentication failures are logged (with IP address and User-Agent)
- Admin operations are recorded in the audit log
- Personal information is never output to logs (masking applied)

## Checklist (For PR Reviews)

- [ ] Are CSP headers correctly configured?
- [ ] Is CORS using a whitelist approach?
- [ ] Is user input sanitized?
- [ ] Do cache keys include the tenant ID?
- [ ] Is rate limiting applied?
- [ ] Do error responses avoid exposing internal details?
- [ ] Are there no known vulnerabilities in dependencies?

## OWASP Top 10 Compliance Status

| # | Risk | Status |
|---|------|--------|
| A01 | Broken Access Control | ✅ Tenant isolation + RBAC |
| A02 | Cryptographic Failures | ✅ bcrypt + JWT signing |
| A03 | Injection | ✅ ORM + DOMPurify |
| A04 | Insecure Design | ✅ Mandatory security reviews |
| A05 | Security Misconfiguration | ✅ CSP + CORS + headers |
| A06 | Vulnerable Components | ✅ npm audit in CI |
| A07 | Authentication Failures | ✅ JWT + API Key dual auth |
| A08 | Data Integrity Failures | ✅ Signature verification |
| A09 | Logging & Monitoring | ✅ Audit logging |
| A10 | SSRF | ✅ URL validation + whitelist |
