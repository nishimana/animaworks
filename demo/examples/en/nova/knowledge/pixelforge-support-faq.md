---
auto_consolidated: false
confidence: 0.8
created_at: '2026-03-03T16:00:00+09:00'
version: 1
---

# PixelForge Support FAQ

> Created: 2026-03-03
> Author: Nova (Customer Success / Assistant)
> Purpose: Common inquiries, response templates, and escalation criteria
> Target: Post-v0.4 release support

## FAQ List

### Q1: My design won't save

**Response:**
Please try clearing your browser cache and attempting again.
If the issue persists, please provide us with:
- Your browser name and version
- Design size (number of elements)
- Screenshot of any error messages

**Escalation criteria:** If occurring across multiple tenants simultaneously → Escalate to Kai as P1

---

### Q2: I can't export my design

**Response:**
PixelForge supports the following export formats: PNG, SVG, PDF, JPEG.
For large designs (500+ elements), processing may take longer.
If it hasn't completed after 5 minutes, please let us know.

**Escalation criteria:** If a server error (500) occurs → Report to Kai as P2

---

### Q3: AI generation isn't working / is slow

**Response:**
AI generation has daily limits per tier:
- Free: 10/day
- Pro: 100/day
- Enterprise: 1,000/day

If you've reached your limit, it will reset the next day.
If generation fails within your limit, try a shorter, more specific prompt.

**Escalation criteria:** If generation fails within tier limits → Report to Kai as P2

---

### Q4: I want to change my plan

**Response:**
You can change your plan from Admin Panel > Account Settings > Change Plan.
- Upgrade: Takes effect immediately (prorated)
- Downgrade: Takes effect at the next billing period

**Escalation criteria:** Billing-related bugs → Contact finance team as P1

---

### Q5: I can't invite team members

**Response:**
Team member invitations can be sent from Admin Panel > Team Settings > Invite Members.
If the invitation email doesn't arrive:
1. Check the spam/junk folder
2. Verify the email address is correct
3. For corporate email, ask your IT department to whitelist the pixelforge.dev domain

**Escalation criteria:** Invitation link errors → Report to Kai as P3

---

### Q6: How to get an API key

**Response:**
You can generate API keys from Admin Panel > API Settings > Generate Key.
- Test environment: `pf_test_` prefix
- Production environment: `pf_live_` prefix

For security, keys are displayed only once. If lost, please regenerate.

**Escalation criteria:** Persistent API authentication errors → Report to Kai as P2

---

### Q7: How to use templates

**Response:**
You can select and customize templates from the template gallery.
1. Go to Dashboard > Templates
2. Browse by category or search
3. Click "Use this template"
4. Customize text, images, and colors

**Escalation criteria:** Template display issues → Report to Kai as P3

---

### Q8: I want to delete my account

**Response:**
Account deletion can be requested from Admin Panel > Account Settings > Delete Account.
There is a 30-day grace period during which you can cancel the deletion.
Please note that data cannot be recovered after deletion.

**Escalation criteria:** Data export requests → Handle manually

---

### Q9: I can see other users' designs (occurred in v0.3)

**Response:**
The tenant isolation bug that occurred in v0.3 has been fixed (v0.3.1 hotfix).
No data modifications or deletions occurred.
The service is now operating normally.

If you have any concerns, please don't hesitate to contact us.

**Escalation criteria:** If it recurs → Escalate to Kai immediately as P0

---

### Q10: Multi-language support

**Response:**
The PixelForge UI currently supports English and Japanese.
AI generation supports multilingual prompts — you can enter prompts in your preferred language.

**Escalation criteria:** Translation errors → Record as P3

## Support Flow

```
Inquiry received
  ↓
FAQ match? → Yes → Send template response
  ↓ No
Check escalation criteria
  ↓
P0/P1 → Escalate to Kai immediately + Report to Alex
P2    → Report to Kai (next heartbeat is OK)
P3    → Record and include in weekly summary
```
