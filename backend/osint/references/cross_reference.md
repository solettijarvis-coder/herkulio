# Cross-Reference Methodology

## Core Principle

**Facts in isolation are meaningless.**

- Facts that contradict each other = **red flag**
- Facts that reinforce each other = **confidence**
- Facts that are absent = **unknown** (not necessarily negative)

---

## Mandatory Cross-Checks

### Entity ↔ Person

| Check | Red Flag if... |
|-------|----------------|
| Registered agent name | Doesn't match person claiming ownership |
| Incorporation date | Doesn't match "started business" claim |
| Principal address | Doesn't match claimed operating location |
| Other entities | Same person registered to multiple suspect entities |

### Claims ↔ Marketplace

| Claim | Verification | Red Flag if... |
|-------|-------------|----------------|
| "$10M annual volume" | Chrono24 + eBay sold history | No marketplace presence |
| "20 years in business" | Wayback Machine website history | Domain < 2 years |
| "Physical store" | Google Street View | No street view match |
| "Staff of 10" | LinkedIn employees | No employees found |

### Phone ↔ Entity

| Check | Red Flag |
|-------|----------|
| Carrier type | VoIP/burner for supposedly major dealer |
| State match | Phone area code doesn't match claimed state |
| History | Recently ported number |

### Email ↔ Domain ↔ WHOIS

| Check | Red Flag |
|-------|----------|
| Email domain | Gmail/Yahoo for B2B business |
| WHOIS creation | Domain created after claimed founding date |
| WHOIS privacy | Privacy protection on B2B dealer domain |
| Email ↔ Website | Email domain doesn't match website domain |

### Social ↔ Claims

| Check | Red Flag |
|-------|----------|
| Follower count | < 5% of claimed customer base |
| Post history | Sudden burst (bought account) or < 6 months old |
| Location tags | Don't match claimed physical location |
| Engagement rate | < 1% (bought followers) |
| Testimonials | All from accounts with < 100 followers |

### Court ↔ Associates

| Check | Action |
|-------|--------|
| Target | Check federal and state courts |
| Associates | Check known business partners |
| Family | Check immediate family members (shell company risk) |
| Prior entities | Check dissolved/inactive entities |

---

## Correlation Triggers

**These combinations trigger deeper investigation:**

### 🔴 Immediate Deep Dive
- FL entity INACTIVE but still soliciting
- OFAC clear but ICIJ hit on family member
- Zero marketplace presence + high volume claims
- Domain < 12 months + "established dealer" claims
- Multiple entity names for one person

### 🟠 Concern Level
- Address mismatch across filings
- Phone number recently ported
- Email domain doesn't match website
- Social media recently created
- Property records don't match claimed location

### 🟡 Minor Flags
- Single data source only
- Limited web presence
- New entity with good explanation

---

## Confidence Boosters

**These increase confidence in findings:**

| Finding | Confidence Boost |
|---------|-----------------|
| 5+ sources confirm same fact | +20% |
| Physical address verified 3 ways | +15% |
| Marketplace data matches claims | +15% |
| Industry press mentions over years | +10% |
| Clean court + sanctions + adverse media | +10% |
| Real phone + email domain match | +10% |

---

## Correlation Matrix

When you find these, check for:

| Finding | Check Also |
|---------|-----------|
| OFAC match | Family members, associated entities |
| ICIJ hit | All entities listed as UBO/director |
| Bankruptcy | Prior business entities |
| Virtual office | Other entities at same address |
| Recently created domain | Wayback Machine history |
| Zero social media | Marketplace presence, web mentions |
| Gmail email | WHOIS domain age, business registration |

---

## Documentation

Always record:
1. **Sources checked** (full list)
2. **Data points found** (with dates)
3. **Contradictions** (exact conflicts)
4. **Correlations** (reinforcing facts)
5. **Gaps** (what you couldn't verify)

This creates an audit trail and helps with confidence scoring.
