---
auto_consolidated: false
confidence: 0.8
created_at: '2026-03-02T15:00:00+09:00'
version: 1
---

# Incident Response Procedure

> Created: 2026-03-02
> Author: Kai (Lead Engineer)
> Purpose: Standard procedure based on lessons from the Day 2 API incident (tenant isolation bug)
> Reference: Actual response timeline (13:00–15:00, full recovery in 2 hours)

## 5-Phase Response Flow

### Phase 1: Detection (Target: within 5 minutes)

**Triggers:**
- Customer report (via Nova)
- Monitoring alert (Datadog / PagerDuty)
- Anomaly report on Board

**Initial Actions:**
1. Post incident alert with ⚠️ on Board
2. Immediately report to Alex (intent: report)
3. Initial impact estimate

**Day 2 Actual:**
- 13:00 Report received from Nova
- 13:02 Alex shared with the team
- Initial response: 2 minutes

### Phase 2: Triage (Target: within 15 minutes)

**Steps:**
1. Check error logs
   ```bash
   tail -f /var/log/pixelforge/api.log | grep ERROR
   ```
2. Comprehensive code audit of related areas
   ```bash
   grep -r 'setTenant\|setTeamId' src/api/
   grep -r 'cache.get\|cache.set' src/api/
   ```
3. Check recent deployments and changes
   ```bash
   git log --oneline -20
   ```

**Day 2 Actual:**
- 13:05 `grep -r` to audit all tenant configuration points
- 13:10 Found missing tenant ID in cache key in design-cache.ts
- Triage time: 10 minutes

### Phase 3: Fix (Target: within 30 minutes)

**Steps:**
1. Create the fix
2. Add unit tests
3. Run all tests locally
4. Create PR → request review → merge

**Day 2 Actual:**
- 13:15 Fix committed + tests added
- 13:25 PR #11 created
- 13:30 Merged
- Fix time: 20 minutes

### Phase 4: Notification (Target: within 30 minutes after fix)

**Handoff Template for Nova:**

```
[Handoff to Nova]
Incident summary: {one line}
Root cause: {technical but customer-friendly language}
Fix status: {fixed / deployed}
Impact: {whether data leakage, modification, or deletion occurred}
Suggested customer notification:
  "{incident description} occurred, but {has been resolved}. {No impact} has been confirmed."
```

**Day 2 Actual:**
- 13:30 Reported fix to Alex + suggested Nova notification
- 13:35 Alex delegated notification to Nova
- 15:00 Nova completed notifications to 5 affected customers, all acknowledged
- Notification time: 1 hour 30 minutes (for 5 companies)

### Phase 5: Retrospective (Target: same day)

**Items to Record:**
1. Timeline (every step from detection to recovery)
2. Root cause analysis (5 Whys)
3. Prevention measures
4. Knowledge updates

**Day 2 Actual:**
- Created `knowledge/tenant-isolation-design.md` (including lessons learned)
- Added "Does the cache key include the tenant ID?" to PR review checklist
- Added tenant isolation tests to E2E suite

## Severity Classification

| Level | Definition | Response Time |
|-------|-----------|--------------|
| P0 (Critical) | Data leakage, full outage | Immediate |
| P1 (High) | Partial functionality down, data inconsistency | Within 1 hour |
| P2 (Medium) | Performance degradation | Within 4 hours |
| P3 (Low) | UI glitch, display issue | Next business day |

## Kai → Nova Coordination Pattern

Role distribution during incident response:

```
Kai: Detect → Triage → Fix → Report to Alex
      ↓
Alex: Decide → Delegate notification to Nova
      ↓
Nova: Identify affected customers → Send notifications → Track acknowledgments
```

**Key Points:**
- Kai includes a "suggested notification text for Nova" in the report to Alex
- Nova uses templates from `knowledge/customer-communication-patterns.md`
- After notification is complete, Nova reports back to Alex (including all acknowledgments)
