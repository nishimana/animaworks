---
auto_consolidated: false
confidence: 0.8
created_at: '2026-03-02T15:30:00+09:00'
version: 1
---

# Customer Communication Patterns

> Created: 2026-03-02
> Author: Nova (Customer Success / Assistant)
> Purpose: Standardize customer response priority decisions and notification templates
> Updated: 2026-03-02 15:30 — Added security emergency notification template after tenant isolation bug

## Priority Decision Matrix

| Priority | Event | Initial Response | Procedure |
|----------|-------|-----------------|-----------|
| P0 Emergency | Data leakage, security breach | Immediate | Request technical investigation from Kai → Notify customers after fix confirmed |
| P1 Critical | Feature outage, data inconsistency | Within 1 hour | Identify impact scope → Initial notification → Final notification after fix |
| P2 Normal | Performance degradation, UI glitches | Within 4 hours | Reproduce issue → Escalate to Kai |
| P3 Minor | Questions, feature requests | Next business day | Check FAQ → Respond or add to knowledge base |

## Communication Channel Guidelines

| Channel | Use Case | Example |
|---------|----------|---------|
| Email | Official notifications, incident reports, release notices | Security fix announcement |
| Chat | Quick responses, Q&A | "Can't export" → step-by-step guide |
| Board | Internal team sharing | Incident resolution report |

## Notification Templates

### Template 1: Release Notification

```
Subject: PixelForge {version} Release Announcement

Dear {customer_name},

We are pleased to announce the release of PixelForge {version}.

[Key Updates]
{update_list}

[Security Fixes]
{security_fixes_if_any}

If you have any questions, please don't hesitate to reach out.

NovaCraft Support Team
```

### Template 2: Incident Initial Notification

```
Subject: [Important] Notice Regarding PixelForge Service

Dear {customer_name},

We are currently experiencing the following issue with PixelForge.

[Issue]
{description — avoid technical jargon, describe from customer impact perspective}

[Affected Scope]
{affected features and users}

[Status]
Our engineering team is currently investigating the root cause and working on a fix.
We will provide an update once the issue has been resolved.

We sincerely apologize for any inconvenience.
```

### Template 3: Incident Resolution Notification

```
Subject: [Resolved] PixelForge Service Recovery Notice

Dear {customer_name},

The issue we previously reported has been resolved.

[Root Cause]
{root_cause — translate Kai's report into customer-friendly language}

[Fix]
{fix_summary}

[Data Impact]
{whether any data modification, deletion, or leakage occurred}

We apologize for the inconvenience.
We are implementing preventive measures to ensure this does not recur.
```

### Template 4: Feature Request Response

```
Subject: Re: {feature_request_title}

Dear {customer_name},

Thank you for your feedback.

We have shared your request regarding {feature_description} with our development team.
It will be evaluated as part of our v{next_version} roadmap planning.

We will follow up when there are updates to share.
```

### Template 5: Security Emergency Notification (Added after v0.3 incident)

```
Subject: [Urgent - Important] Security Notice for PixelForge

Dear {customer_name},

A security issue was discovered in PixelForge and has been
immediately resolved. We are writing to inform you of the details.

[Issue]
{incident_summary}

[Impact]
{impact_scope — e.g., "No data modifications or deletions occurred"}

[Resolution]
{fix_and_deployment_status}

[Prevention Measures]
{summary_of_technical_prevention_measures}

If you have any concerns, please don't hesitate to contact us.
```

## Kai → Nova Handoff Pattern

Flow for receiving technical information from Kai and converting it for customers:

```
Kai's report:
  "Cache key in design-cache.ts was missing the tenant ID.
   Fixed: cache.get(designId) → cache.get(tenantId:designId)"

↓ Customer-friendly conversion:

Customer notification:
  "Due to a caching system issue, some customers were temporarily
   able to view designs from other accounts. The fix has been
   completed and deployed. No data modifications or deletions
   have occurred."
```

## Lessons from v0.3 Incident

- Identifying affected customers took 10 minutes → Could be instant with customer DB integration
- Template 5 (security emergency notification) was missing → Added
- Tracked acknowledgment from all 5 companies → Standardize the tracking process
