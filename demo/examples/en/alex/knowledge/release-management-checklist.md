---
auto_consolidated: false
confidence: 0.8
created_at: '2026-03-04T14:30:00+09:00'
version: 1
---

# PixelForge Release Management Checklist

> Created: 2026-03-04
> Author: Alex (Product Manager)
> Purpose: Standard procedures based on v0.3 release experience

## Release Criteria

### MUST (Release Blockers)
1. **Security**: Zero open CRITICAL/HIGH issues
2. **Testing**: All E2E tests pass, coverage >= 80%
3. **Performance**: API response p95 < 200ms
4. **Data**: All tenant isolation tests pass

### SHOULD (Best Effort)
1. All CHANGELOG sections documented
2. Documentation updated
3. Customer notification templates prepared

## Release Procedure

### Phase 1: Day Before Release
- [ ] Request security audit from Kai
- [ ] Ask Nova to prepare customer notification templates
- [ ] Review and decide on all open PRs
- [ ] Smoke test on staging environment

### Phase 2: Release Day
- [ ] Receive security audit results from Kai
- [ ] Confirm all test results (E2E + unit)
- [ ] Final CHANGELOG review
- [ ] Create release tag (instruct Kai)
- [ ] Instruct Nova to send customer notifications
- [ ] Report completion to CEO

## Lessons from v0.3
- Security audit must be requested the day before — doing it on release day caused chaos in v0.2
- Customer notifications get better reception when bug fix details are included
- Never skip staging environment smoke tests
