---
auto_consolidated: false
confidence: 0.8
created_at: '2026-03-02T10:00:00+09:00'
version: 1
---

# PixelForge API Architecture Design Principles

> Created: 2026-03-02
> Author: Kai (Lead Engineer)
> Purpose: Document unified REST API design rules and rationale

## Overview

The PixelForge API is built on RESTful design principles as a multi-tenant SaaS platform.
Security is enforced through four layers: authentication, authorization, tenant isolation, and rate limiting.

## Authentication

### JWT + API Key Dual Authentication

PixelForge employs dual authentication with JWT tokens and API Keys.

```
Authorization: Bearer <jwt_token>
X-API-Key: <api_key>
```

**JWT Token Structure:**
- `sub`: User ID
- `tid`: Tenant ID (required — foundation of tenant isolation)
- `roles`: Role array (`["admin", "designer"]`)
- `exp`: Expiration (default 1 hour)
- `iss`: `pixelforge-auth`

**API Key:**
- Issued per tenant
- Prefix: `pf_live_` (production) / `pf_test_` (testing)
- Stored as hash (bcrypt)
- Used for rate limit tier determination

### Authentication Flow

```
Client → POST /api/v2/auth/login (email, password)
       ← { access_token, refresh_token, expires_in }

Client → GET /api/v2/designs (Authorization: Bearer <token>, X-API-Key: <key>)
       ← Auth middleware validates → Tenant scope applied → Response
```

## Tenant Isolation

### Principle: Every data access must include the tenant ID

Reflects lessons learned from the v0.3 incident (cache key missing tenant ID).

**Database Layer:**
```typescript
const designs = await db.designs
  .where('tenant_id', '=', ctx.tenantId)  // Required
  .where('id', '=', designId)
  .first();
```

**Cache Layer:**
```typescript
// BAD: No tenant ID → risk of returning another tenant's data
cache.get(designId)

// GOOD: Tenant ID included as prefix
cache.get(`${tenantId}:${designId}`)
```

**Middleware:**
```typescript
export function setTenant(req: Request, res: Response, next: NextFunction) {
  const tenantId = req.jwt.tid;
  if (!tenantId) return res.status(403).json({ error: 'tenant_id_required' });
  req.ctx = { tenantId, userId: req.jwt.sub };
  next();
}
```

### `setTenant()` vs `setTeamId()` Distinction

| Function | Scope | Purpose |
|----------|-------|---------|
| `setTenant()` | DB scope | Automatically adds tenant_id condition to database queries |
| `setTeamId()` | Application scope | Checks permissions within a team (designer/viewer, etc.) |

**Important**: `setTenant()` is required on all API endpoints. `setTeamId()` is only needed when using team features.

## Rate Limiting

### Tier-Based Limits

| Tier | Requests/min | Burst | AI Generations/day |
|------|-------------|-------|-------------------|
| Free | 100 | 150 | 10 |
| Pro | 1,000 | 1,500 | 100 |
| Enterprise | Unlimited | Unlimited | 1,000 |

### Implementation: Token Bucket Algorithm

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

**Response Headers:**
```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 847
X-RateLimit-Reset: 1709344800
Retry-After: 30  (only on 429)
```

## Error Response Format

Follows RFC 7807 Problem Details for HTTP APIs:

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

### Standard Error Codes

| HTTP Status | Type Suffix | Description |
|-------------|------------|-------------|
| 400 | `/invalid-request` | Malformed request |
| 401 | `/authentication-required` | Invalid auth token |
| 403 | `/insufficient-permissions` | Insufficient privileges |
| 404 | `/resource-not-found` | Resource does not exist |
| 409 | `/conflict` | Conflict (concurrent edit, etc.) |
| 429 | `/rate-limit-exceeded` | Rate limit exceeded |
| 500 | `/internal-error` | Internal server error |

## API Versioning

- URL path-based: `/api/v2/...`
- Only major versions in URL
- Minor changes added with backward compatibility
- Old version (`/api/v1/`) deprecated after 6-month sunset period

## Performance Benchmarks

| Metric | Target | v0.4 Actual |
|--------|--------|-------------|
| p50 | < 50ms | 42ms |
| p95 | < 200ms | 147ms |
| p99 | < 500ms | 312ms |
| Error rate | < 0.1% | 0.02% |

## Related Documents

- `knowledge/security-best-practices.md` — Security implementation details
- `knowledge/tenant-isolation-design.md` — Tenant isolation detailed design
- `knowledge/e2e-testing-guide.md` — API testing strategy
