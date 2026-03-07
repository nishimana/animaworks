---
auto_consolidated: false
confidence: 0.8
created_at: '2026-03-02T14:30:00+09:00'
version: 1
---

# Tenant Isolation Design

> Created: 2026-03-02
> Author: Kai (Lead Engineer)
> Purpose: Design principles based on lessons from the v0.3 tenant isolation bug
> Updated: 2026-03-02 14:30 — Added lessons learned after API incident response

## Overview

PixelForge is designed as a multi-tenant SaaS platform where data isolation between tenants is the most critical security requirement. This document was created in response to the v0.3 incident (cache key missing tenant ID → other tenants' designs became viewable).

## Architecture

### Three Layers of Tenant Isolation

```
Layer 1: Authentication (JWT tid claim)
  ↓
Layer 2: Middleware (setTenant() sets context)
  ↓
Layer 3: Data Access (tenant_id condition auto-applied to all queries)
```

### Separation of `setTenant()` and `setTeamId()`

| Function | Scope | Responsibility |
|----------|-------|---------------|
| `setTenant(req)` | DB scope | Extracts tenant ID from JWT and sets `req.ctx.tenantId` |
| `setTeamId(req)` | App scope | Sets team ID for intra-team permission checks |

**Important**: Calling `setTeamId()` without `setTenant()` is a bug. Tenant isolation must always come first.

## Cache Key Design

### Mandatory Rule: Always include the tenant ID in cache keys

```typescript
// ❌ BAD — Root cause of the v0.3 bug
const cacheKey = `design:${designId}`;
const cached = await redis.get(cacheKey);

// ✅ GOOD — Tenant ID prefix
const cacheKey = `tenant:${tenantId}:design:${designId}`;
const cached = await redis.get(cacheKey);
```

### Cache Key Naming Convention

```
{entity}:{tenantId}:{resourceType}:{resourceId}[:{qualifier}]
```

Examples:
- `tenant:t_abc123:design:d_xyz789` — Design cache
- `tenant:t_abc123:designList:page1` — Design list cache
- `tenant:t_abc123:user:u_def456:prefs` — User preferences cache

### Cache Invalidation

Supports bulk invalidation per tenant:

```typescript
async function invalidateTenantCache(tenantId: string): Promise<void> {
  const keys = await redis.keys(`tenant:${tenantId}:*`);
  if (keys.length > 0) {
    await redis.del(...keys);
  }
}
```

## v0.3 Incident Details

### Date/Time
2026-03-02 13:00 JST

### Impact
Customers could view designs belonging to other tenants (approximately 30 minutes).

### Root Cause
Cache key in `design-cache.ts` did not include the tenant ID.

```typescript
// Before (bug)
cache.get(designId)

// After (fix)
cache.get(`${tenantId}:${designId}`)
```

### Response Timeline
- 13:00 — Nova received customer report
- 13:05 — `grep -r 'setTenant\|setTeamId' src/api/` to audit all locations
- 13:10 — Identified the problem in design-cache.ts
- 13:15 — Fix committed + tests added
- 13:30 — PR #11 merged → hotfix deployed
- 14:00 — Reported fix completion on Board
- 15:00 — Nova completed notifications to all 5 affected customers

### Prevention Measures

1. **PR review checklist**: Added "Does the cache key include the tenant ID?"
2. **E2E tests**: Added concurrent access tests across different tenants
3. **Static analysis**: Warning when `cache.get()` calls lack the tenant ID pattern

## Test Patterns

### Tenant Isolation Tests

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
