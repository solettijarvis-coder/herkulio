# Verdict Framework — Risk Scoring & Recommendations

## Risk Tiers

### 🔴 CRITICAL — Do Not Transact

**Any of:**
- OFAC/SDN match on target or primary associate
- ICIJ Offshore Leaks hit (Pandora, Panama Papers) as UBO/director
- Active federal fraud case (wire fraud, money laundering, Ponzi)
- Interpol notice
- SEC/CFTC enforcement action
- Entity INACTIVE while actively soliciting
- Claims unverifiable by marketplace/web presence
- Registered agent privacy proxy + no physical verification

**Recommendation:**
> "**STOP — Do not proceed.** {Specific finding} indicates {specific risk}. Risk of {loss type}. Alternative: {if any}."

---

### 🟠 HIGH — Proceed Only with Extreme Caution

**Any of:**
- Entity < 12 months old claiming established history
- Multiple state registrations with mismatched principals
- Domain < 1 year for supposedly established brand
- Zero marketplace presence despite high volume claims
- Virtual office address as primary location
- Multiple civil judgments (unpaid debts)
- Prior undisclosed bankruptcy
- Fake social media presence

**Recommendation:**
> "**HIGH RISK — Proceed only if:**
> - Escrow service mandatory
> - Physical verification completed
> - Trade references from 3+ recent transactions
> - Initial deal <$5K to test relationship
> 
> Require {specific verification} before proceeding."

---

### 🟡 MEDIUM — Proceed with Conditions

**Any of:**
- New entity with limited verifiable history
- Marketplace presence below claimed volume
- Minor court/civil record not directly fraud-related
- Missing key verification (address unconfirmed)
- Recently created social media
- Domain recently registered but plausible explanation

**Recommendation:**
> "**MEDIUM RISK — Conditions:**
> - Use escrow for transactions >$5K
> - Request proof of physical location (video call, utility bill)
> - Verify at least 2 trade references
> - Start with smaller transaction
> 
> Standard commercial terms with verification."

---

### 🟢 LOW — Standard Precautions

**All of:**
- Entity active, registered correctly
- No OFAC/ICIJ/court flags on target or associates
- Marketplace presence roughly consistent with claims
- Contact info resolves to real person/business
- Some minor gaps in data but no red flags

**Recommendation:**
> "**LOW RISK — Standard commercial terms appropriate.**
> No significant adverse findings. Recommend:
> - Standard escrow for transactions >$10K
> - Document all communications
> - Standard due diligence sufficient."

---

### ✅ MINIMAL — Proceed with Confidence

**All of:**
- Entity active, long registration history
- Physical address verified (Street View, property records)
- Strong marketplace presence matching claims
- Verified email domain
- Real phone (landline or mobile, not VoIP)
- No court records, no adverse media
- Industry press mentions over multiple years

**Recommendation:**
> "**MINIMAL RISK — Proceed with standard commercial precautions.**
> All verification checks positive. Standard watch industry practices appropriate."

---

## Confidence Scoring

| Confidence | Criteria | Action |
|------------|----------|--------|
| **95%+** | 5+ independent sources confirm | High certainty |
| **80-94%** | 3-4 sources, consistent | Good confidence |
| **60-79%** | 1-2 sources, no contradictions | Moderate confidence |
| **40-59%** | Limited data, no contradictions | Low confidence, note gaps |
| **<40%**** | Insufficient data or contradictions | Flag for deeper investigation |

**Important:** A HIGH RISK finding with LOW confidence = flag but don't terminate. Investigate further.

---

## Report Structure

### Executive Summary (1 paragraph)
- One sentence verdict
- Risk tier
- Confidence level
- Bottom-line recommendation

### Identity Verification (1 paragraph)
- Legal entity status
- Principals identified
- Registration history
- Physical location verification

### Red Flags (if any)
- Specific findings
- Source citations
- Severity

### Compliance Check (1 paragraph)
- OFAC/ICIJ status
- Court records
- Regulatory actions
- Exact status (not generic)

### Industry Presence (1 paragraph)
- Marketplace verification
- Social media analysis
- Web presence
- Volume consistency check

### Verdict (1 sentence)
Risk tier + specific recommendation + confidence.

---

## Example Verdicts

**Critical:**
> "CRITICAL RISK — Entity matched on OFAC SDN list. Do not proceed under any circumstances. Confidence: 99%."

**High:**
> "HIGH RISK — Entity registered 3 months ago but claims 15-year history. Domain created 2 months ago. No marketplace presence. Proceed only with full escrow and physical verification. Confidence: 85%."

**Medium:**
> "MEDIUM RISK — New entity (8 months) but verifiable physical address and limited Chrono24 presence. Recommend escrow and references. Confidence: 75%."

**Low:**
> "LOW RISK — Active entity, clean records, moderate marketplace presence. Standard precautions recommended. Confidence: 80%."

**Minimal:**
> "MINIMAL RISK — 10-year established entity, verified address, strong marketplace presence, no adverse findings. Standard commercial terms. Confidence: 95%."
