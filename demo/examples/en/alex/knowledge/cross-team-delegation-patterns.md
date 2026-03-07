---
auto_consolidated: false
confidence: 0.7
created_at: '2026-03-05T09:00:00+09:00'
version: 1
---

# Cross-Team Delegation Patterns

> Author: Alex
> Updated: 2026-03-05
> Purpose: Efficient task delegation principles for a 3-person team

## Delegation Decision Matrix

| Task Type | Assignee | Rationale |
|-----------|----------|-----------|
| Code implementation, bug fixes, security | Kai | Requires technical judgment |
| Customer communication, documentation, research | Nova | Strong communication skills |
| Architecture decisions, release decisions | Alex (self) | Final decision authority |
| Incident response | Kai → Nova coordination | Kai: root cause analysis, Nova: customer notification |

## Delegation Template
[Request] {task_name}
Deadline: {date/time}
Context: {why this is needed}
Expected deliverable: {specific output}
Please report completion on the Board.

## Lessons from v0.3 Release
- During the API incident, Kai → Nova coordination achieved 2-hour recovery
- Nova's pre-built customer notification template enabled immediate outreach
- Using org_dashboard to get a full picture before making decisions is the most efficient approach
