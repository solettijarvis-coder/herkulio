# Investigation Methodology — Herkulio Intelligence

Standard operating procedure for all investigations.

## Step 1: Classify Target

Determine investigation type:

| Type | Indicators | Modules |
|------|-----------|---------|
| **Company** | LLC, Inc, Corp, Ltd, gallery, jeweler, trading, holdings | Corporate registry, sanctions, litigation |
| **Person** | Individual dealer, broker, owner, collector | Person search, social, financial |
| **Mixed** | Company + known owner | Run BOTH company AND person |
| **Watch** | Reference number, model name | Market pricing, authenticity checks |
| **Transaction** | Deal in progress | Counterparty + watch + terms |

## Step 2: Gather Identifiers

**Collect ALL available info before searching:**

Required:
- Full legal name (not nickname)
- State/country of registration/residence

Optional but valuable:
- Website URL
- Phone number(s)
- Email address(es)
- Social media handles (Instagram, LinkedIn, Twitter)
- Known associates or related entities
- Physical address
- Business registration number
- Bank details (for transaction verification)

**More identifiers = deeper, more accurate report.**

## Step 3: Execute Investigation

### Always Run (Standard Depth)

1. **Corporate Registry** — State-specific database
2. **OFAC/SDN Sanctions** — US Treasury
3. **UN/EU Sanctions** — International
4. **ICIJ Offshore Leaks** — Pandora Papers, Panama Papers
5. **Web Research** — Serper/Tavily for news, reviews, adverse media
6. **Domain Intel** — WHOIS, Wayback Machine
7. **OpenCorporates** — Global company database

### Conditional (Based on Identifiers)

**If email provided:**
- holehe (120+ platform registrations)
- h8mail (breach databases)
- ghunt (Google account OSINT)
- socialscan (username availability)

**If URL/domain provided:**
- theHarvester (emails, subdomains)
- whatweb (tech stack)
- nmap (open ports)
- waybackpy (historical snapshots)

**If phone provided:**
- phoneinfoga (carrier, VoIP detection)
- Reverse lookup

**If social handle provided:**
- maigret (300+ platforms)
- instaloader (deep Instagram)
- socialscan

### Deep Depth (+$0.05, for >$10K transactions)

Everything above PLUS:
- 2x query volume per module
- BBB + RipoffReport + CFPB complaints
- CourtListener federal cases
- PACER bankruptcy records
- SEC Edgar filings
- FINRA BrokerCheck
- FEC political donations
- PPP loan records
- Property records
- Extended social analysis

## Step 4: Cross-Reference Findings

Look for correlations and contradictions:

### Correlations (Strengthen Confidence)
- Same phone on website + corporate filing
- Address matches across multiple sources
- Business email domain matches registered domain

### Contradictions (Red Flags)
- Different addresses on different filings
- Name mismatch between corporate and website
- Phone carrier doesn't match claimed location

### Gaps (Unknowns)
- No social media for claimed established dealer
- No property records in claimed city
- Zero web presence for claimed business

## Step 5: Apply Red Flag Framework

Reference: `red_flags.md`

Check findings against:
- 🔴 Critical flags (immediate disqualifiers)
- 🟠 High risk flags
- 🟡 Medium risk flags
- 🟢 Green flags (positive indicators)

## Step 6: Calculate Risk Score

Formula:
```
Base: 50 (neutral)
+ Critical flag: +30 each
+ High flag: +20 each
+ Medium flag: +10 each
+ Low flag: +3 each
- Green flags: -5 each (up to -20)
= Final score 0-100
```

Map to level:
- 90-100: CRITICAL
- 75-89: HIGH
- 50-74: MEDIUM
- 25-49: LOW
- 0-24: MINIMAL

## Step 7: Generate Verdict

Structure:

**RISK LEVEL**: [Critical/High/Medium/Low/Minimal]
**CONFIDENCE**: [0-100%]

**SUMMARY**: 2-3 sentence executive summary

**KEY FINDINGS**:
- Bullet points of most important discoveries

**RED FLAGS**: [If any]
- List with severity

**GREEN FLAGS**: [If any]
- Positive indicators

**RECOMMENDATIONS**:
- Specific actions to take

**DATA QUALITY**:
- Sources checked: N
- Contradictions: Y/N
- Completeness: High/Medium/Low

## Step 8: Deliver Report

Formats:
- JSON (API)
- Markdown (human-readable)
- PDF (formal documentation)

Always save to Herkulio memory for future reference.
