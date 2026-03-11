"""
REPORT_FORMATTER.py — Tiered Intelligence Report Output
==========================================================
Replaces the 400-line print_report() with a clean, tiered format:

  TIER 1: Executive Briefing (always shown — 10-15 lines)
  TIER 2: Key Findings (always shown — organized by importance)
  TIER 3: Evidence Sections (only sections WITH findings, grouped by meaning)
  TIER 4: Methodology & Confidence (end of report)

Key principles:
  - HIDE empty modules (don't show "PPP LOANS: 0 found")
  - GROUP by meaning, not by tool name
  - Show what MATTERS, not everything we checked
  - Competing scenarios instead of single verdict
"""


def format_report(report: dict) -> str:
    """Format a report dict into clean, tiered text output."""
    lines = []

    # ═══════════════════════════════════════════════════════════════════
    # TIER 1: EXECUTIVE BRIEFING
    # ═══════════════════════════════════════════════════════════════════

    target = report.get("target", "Unknown")
    target_type = report.get("type", "unknown")
    risk = report.get("risk_rating", "UNKNOWN")
    risk_confidence = report.get("risk_confidence", "UNKNOWN")

    risk_emoji = {
        "LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🔴", "CRITICAL": "🚨"
    }.get(risk, "⚪")

    lines.append("━" * 60)
    lines.append("  HERKULIO INTELLIGENCE REPORT")
    lines.append(f"  Target: {target}")
    lines.append(f"  Type: {target_type.title()} | Date: {_today()}")
    lines.append("━" * 60)
    lines.append("")
    lines.append(f"  {risk_emoji} VERDICT: {risk} RISK")
    lines.append(f"  Confidence: {risk_confidence}")
    lines.append("")

    # Executive summary
    summary = report.get("executive_summary") or report.get("summary", "")
    if summary:
        lines.append("  SUMMARY")
        for line in _wrap(summary, 56):
            lines.append(f"  {line}")
    lines.append("")

    # Risk reasoning
    reasoning = report.get("risk_reasoning", "")
    if reasoning:
        lines.append(f"  WHY: {reasoning}")
        lines.append("")

    # Top findings
    top = report.get("top_findings", [])
    if top:
        lines.append("  TOP FINDINGS")
        for i, f in enumerate(top[:5], 1):
            lines.append(f"  {i}. {f}")
        lines.append("")

    # Recommended action
    action = report.get("recommended_action", "")
    if action:
        lines.append(f"  💡 RECOMMENDATION: {action}")
        lines.append("")

    lines.append("━" * 60)

    # ═══════════════════════════════════════════════════════════════════
    # TIER 2: COMPETING SCENARIOS
    # ═══════════════════════════════════════════════════════════════════

    scenarios = report.get("competing_scenarios", [])
    if scenarios:
        lines.append("")
        lines.append("  COMPETING SCENARIOS")
        lines.append("  ─────────────────────")
        for s in scenarios:
            if isinstance(s, dict):
                prob = s.get("probability", "?")
                name = s.get("scenario", "Unknown")
                lines.append(f"  [{prob}] {name}")
                for_list = s.get("evidence_for", [])
                against_list = s.get("evidence_against", [])
                for e in for_list[:3]:
                    lines.append(f"    ✓ {e}")
                for e in against_list[:3]:
                    lines.append(f"    ✗ {e}")
                lines.append("")

    # ═══════════════════════════════════════════════════════════════════
    # TIER 2: KEY SIGNALS (Red Flags, Green Flags, Unresolved)
    # ═══════════════════════════════════════════════════════════════════

    red_flags = report.get("red_flags", [])
    green_flags = report.get("green_flags", [])
    unresolved = report.get("unresolved_questions", [])

    if red_flags:
        lines.append("")
        lines.append("  🚩 RED FLAGS")
        for f in red_flags:
            lines.append(f"  ⚠️  {f}")

    if green_flags:
        lines.append("")
        lines.append("  ✅ GREEN FLAGS")
        for f in green_flags:
            lines.append(f"  ✓  {f}")

    if unresolved:
        lines.append("")
        lines.append("  ❓ UNRESOLVED")
        for q in unresolved:
            lines.append(f"  •  {q}")

    # ═══════════════════════════════════════════════════════════════════
    # TIER 3: EVIDENCE SECTIONS (grouped by meaning, only non-empty)
    # ═══════════════════════════════════════════════════════════════════

    lines.append("")
    lines.append("━" * 60)
    lines.append("  DETAILED EVIDENCE")
    lines.append("━" * 60)

    # --- Identity & Registration ---
    identity_content = _build_identity_section(report)
    if identity_content:
        lines.append("")
        lines.append("  📋 IDENTITY & REGISTRATION")
        lines.extend(identity_content)

    # --- People & Connections ---
    people_content = _build_people_section(report)
    if people_content:
        lines.append("")
        lines.append("  👤 PEOPLE & CONNECTIONS")
        lines.extend(people_content)

    # --- Legal & Compliance ---
    legal_content = _build_legal_section(report)
    if legal_content:
        lines.append("")
        lines.append("  ⚖️  LEGAL & COMPLIANCE")
        lines.extend(legal_content)

    # --- Financial ---
    financial_content = _build_financial_section(report)
    if financial_content:
        lines.append("")
        lines.append("  💰 FINANCIAL")
        lines.extend(financial_content)

    # --- Marketplace & Reputation ---
    market_content = _build_marketplace_section(report)
    if market_content:
        lines.append("")
        lines.append("  🛒 MARKETPLACE & REPUTATION")
        lines.extend(market_content)

    # --- Digital Footprint ---
    digital_content = _build_digital_section(report)
    if digital_content:
        lines.append("")
        lines.append("  🌐 DIGITAL FOOTPRINT")
        lines.extend(digital_content)

    # --- Cross-Reference Results ---
    xref_content = _build_xref_section(report)
    if xref_content:
        lines.append("")
        lines.append("  🔗 CROSS-REFERENCE ANALYSIS")
        lines.extend(xref_content)

    # --- Behavioral Patterns ---
    patterns = report.get("behavioral_patterns", [])
    if patterns:
        lines.append("")
        lines.append("  🔍 BEHAVIORAL PATTERN ANALYSIS")
        for p in patterns:
            if isinstance(p, dict):
                sev = p.get("severity", "?")
                emoji = "🚨" if sev == "CRITICAL" else "🔴" if sev == "HIGH" else "🟡"
                conf = p.get("confidence", 0)
                lines.append(f"  {emoji} {p.get('name', '?')} [{sev}] — {conf*100:.0f}% match")
                lines.append(f"     {p.get('description', '')}")
                for sig in p.get("matched", [])[:5]:
                    if isinstance(sig, dict):
                        lines.append(f"       • {sig.get('description', '')}")
                lines.append("")

    # --- Prior Knowledge ---
    prior = report.get("prior_knowledge", {})
    if isinstance(prior, dict) and prior.get("has_prior_knowledge"):
        lines.append("")
        lines.append("  ⚡ PRIOR KNOWLEDGE")
        for hit in prior.get("prior_hits", [])[:5]:
            if isinstance(hit, dict):
                lines.append(f"  • {hit.get('match_type', '?')}: '{hit.get('value', '?')}' — seen {hit.get('times_seen', 0)}x before")
                flags = hit.get("risk_flags", [])
                if flags:
                    lines.append(f"    ⚠️ Prior flags: {', '.join(str(f) for f in flags[:3])}")
        for inv in prior.get("linked_investigations", [])[:3]:
            if isinstance(inv, dict):
                risk_emoji = {"HIGH": "🔴", "CRITICAL": "🚨", "MEDIUM": "🟡", "LOW": "🟢"}.get(inv.get("risk_rating", ""), "⚪")
                lines.append(f"  {risk_emoji} Linked: {inv.get('target', '?')} — {inv.get('risk_rating', '?')} ({inv.get('timestamp', '?')[:10]})")

    # --- Contradictions ---
    contradictions = report.get("contradictions", [])
    if contradictions:
        lines.append("")
        lines.append("  🚨 CONTRADICTION FLAGS")
        for c in contradictions:
            if isinstance(c, dict):
                sev = c.get("severity", "?")
                emoji = "🔴" if sev == "HIGH" else "🟡" if sev == "MEDIUM" else "⚪"
                lines.append(f"  {emoji} {c.get('detail', '')}")
                if c.get("significance"):
                    lines.append(f"     → {c['significance']}")

    # ═══════════════════════════════════════════════════════════════════
    # TIER 4: METHODOLOGY & CONFIDENCE
    # ═══════════════════════════════════════════════════════════════════

    lines.append("")
    lines.append("━" * 60)
    lines.append("  METHODOLOGY & CONFIDENCE")
    lines.append("━" * 60)

    # Confidence tags
    tags = report.get("confidence_tags", {})
    if tags:
        lines.append("")
        for section, level in tags.items():
            if section == "overall":
                continue
            emoji = {"CONFIRMED": "✅", "PROBABLE": "🟡", "CLAIMED": "⚠️",
                     "UNVERIFIED": "⚪", "NOT_FOUND": "❌"}.get(level, "?")
            lines.append(f"  {emoji} {section.replace('_', ' ').title()}: {level}")
        overall = tags.get("overall", "?")
        lines.append(f"  Overall Data Confidence: {overall}")

    # Data gaps
    gaps = report.get("data_gaps", [])
    if gaps:
        lines.append("")
        lines.append("  Data Gaps:")
        for g in gaps:
            lines.append(f"  • {g}")

    # Meta
    meta = report.get("_meta", {})
    if meta:
        lines.append("")
        lines.append(f"  Synthesis: {meta.get('synthesis_version', 'v1')}")
        lines.append(f"  Extract Model: {meta.get('extract_model', '?')}")
        lines.append(f"  Analyze Model: {meta.get('analyze_model', '?')}")
        lines.append(f"  Risk Tier: {meta.get('risk_tier_used', '?')}")
        lines.append(f"  Time: {meta.get('total_time_seconds', '?')}s")
        lines.append(f"  Cost: ${meta.get('total_cost_usd', 0):.4f}")
        xref_score = meta.get("cross_ref_consistency")
        if xref_score is not None:
            lines.append(f"  Cross-Ref Score: {xref_score}/100")
        contra = meta.get("contradictions_found", 0)
        high = meta.get("high_severity_flags", 0)
        if contra:
            lines.append(f"  Contradictions: {contra} ({high} HIGH)")
        patterns_count = meta.get("patterns_triggered", 0)
        if patterns_count:
            pattern_names = meta.get("pattern_names", [])
            lines.append(f"  Patterns Triggered: {patterns_count} ({', '.join(pattern_names)})")
        if meta.get("modules_selected"):
            lines.append(f"  Modules: {meta['modules_selected']} selected, {meta.get('modules_skipped', 0)} skipped")
        if meta.get("results_before_filter") and meta.get("results_after_filter"):
            lines.append(f"  Results: {meta['results_before_filter']} raw → {meta['results_after_filter']} after filtering ({meta.get('filter_rate', '?')})")
        if meta.get("prior_knowledge_hits"):
            lines.append(f"  Prior Knowledge: {meta['prior_knowledge_hits']} hit(s) from previous investigations")

    lines.append("")
    lines.append("━" * 60)
    lines.append("")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION BUILDERS — Only return content if there's something to show
# ═══════════════════════════════════════════════════════════════════════════════

def _build_identity_section(report: dict) -> list:
    """Corporate registration + identity."""
    lines = []
    cr = report.get("corporate_records", {})
    if not isinstance(cr, dict):
        return lines

    fields = [
        ("legal_name", "Legal Name"),
        ("entity_type", "Type"),
        ("document_number", "Doc #"),
        ("ein_fein", "EIN/FEIN"),
        ("incorporation_date", "Incorporated"),
        ("status", "Status"),
        ("registered_state", "State"),
        ("principal_address", "Address"),
        ("registered_agent", "Reg. Agent"),
    ]
    for key, label in fields:
        val = cr.get(key)
        if val:
            lines.append(f"  {label:<20} {val}")

    officers = cr.get("officers_managers", [])
    if officers:
        lines.append(f"  {'Officers':<20}", )
        for o in officers[:5]:
            if isinstance(o, dict):
                lines.append(f"  {'':20} {o.get('name', '?')} ({o.get('title', '?')})")
            elif isinstance(o, str):
                lines.append(f"  {'':20} {o}")

    return lines


def _build_people_section(report: dict) -> list:
    """People found with their roles and assessments."""
    lines = []
    people = report.get("people", [])
    if not people:
        return lines

    for p in people[:8]:
        if isinstance(p, dict):
            name = p.get("name", "?")
            role = p.get("role", "")
            assessment = p.get("assessment", "")
            bg = p.get("background", "")
            line = f"  • {name}"
            if role:
                line += f" — {role}"
            if bg:
                line += f" | {bg}"
            lines.append(line)
            if assessment:
                lines.append(f"    Assessment: {assessment}")

    # Owner profiles
    op = report.get("owner_profiles", {})
    if isinstance(op, dict) and op.get("profiles"):
        lines.append("")
        lines.append("  Owner Deep Profiles:")
        for owner, profile in op.get("profiles", {}).items():
            if isinstance(profile, dict):
                sigs = profile.get("signal_summary", {})
                total = sigs.get("total_red_signal_count", 0)
                if total == 0:
                    lines.append(f"  ✅ {owner}: No red signals detected")
                else:
                    lines.append(f"  ⚠️  {owner}: {total} red signal(s)")
                    for cat in ["criminal_signals", "fraud_signals", "financial_distress_signals"]:
                        items = sigs.get(cat, [])
                        if items:
                            lines.append(f"     {cat.replace('_', ' ').title()}: {', '.join(items[:3])}")

    return lines


def _build_legal_section(report: dict) -> list:
    """Sanctions, courts, enforcement — combined."""
    lines = []

    # OFAC
    ofac = report.get("ofac_status", {})
    if isinstance(ofac, dict):
        status = ofac.get("status", "UNKNOWN")
        emoji = "🟢" if status == "CLEAR" else "🔴" if status == "HIT" else "⚪"
        lines.append(f"  OFAC Sanctions: {emoji} {status}")
        if ofac.get("matches"):
            for m in ofac["matches"][:3]:
                if isinstance(m, dict):
                    lines.append(f"    ⚠️ MATCH: {m.get('name')} (score: {m.get('score')})")

    # Federal cases — only if found
    fc = report.get("federal_cases", {})
    if isinstance(fc, dict):
        total = fc.get("total_found", 0)
        if total > 0:
            lines.append(f"  Federal Court Cases: {total} found")
            for c in (fc.get("cases") or [])[:3]:
                if isinstance(c, dict):
                    lines.append(f"    • {c.get('case_name', '?')} | {c.get('date_filed', '?')}")

    # Bankruptcy — only if found
    bk = report.get("bankruptcy", {})
    if isinstance(bk, dict) and bk.get("total_found", 0) > 0:
        lines.append(f"  Bankruptcy: {bk['total_found']} filing(s)")

    # Legal history
    lh = report.get("legal_history", [])
    if lh and isinstance(lh, list):
        lines.append("  Legal History:")
        for item in lh[:5]:
            lines.append(f"    • {item}")

    return lines


def _build_financial_section(report: dict) -> list:
    """Financial signals — only non-empty."""
    lines = []
    fs = report.get("financial_signals", {})
    if not isinstance(fs, dict):
        return lines

    if fs.get("claimed_revenue"):
        verified = "✅ verified" if fs.get("revenue_verified") else "⚠️ unverified"
        lines.append(f"  Revenue: {fs['claimed_revenue']} ({verified})")

    for field, label in [("bankruptcies", "Bankruptcies"), ("liens_judgments", "Liens/Judgments")]:
        if fs.get(field):
            lines.append(f"  {label}: {fs[field]}")

    return lines


def _build_marketplace_section(report: dict) -> list:
    """eBay, Chrono24, forums, Google reviews — combined."""
    lines = []

    # Marketplace
    mp = report.get("marketplace_presence", {})
    if isinstance(mp, dict):
        ebay = mp.get("ebay", {}) or mp.get("ebay_seller", {})
        if isinstance(ebay, dict) and ebay.get("found"):
            score = ebay.get("feedback_score", "?")
            pct = ebay.get("positive_pct", "?")
            lines.append(f"  eBay: {score} feedback | {pct}% positive")
        elif isinstance(ebay, dict) and ebay.get("found") is False:
            lines.append(f"  eBay: ❌ Not found")

        c24 = mp.get("chrono24", {}) or mp.get("chrono24_seller", {})
        if isinstance(c24, dict) and c24.get("found"):
            listings = c24.get("listings", "?")
            lines.append(f"  Chrono24: {listings} listings")
        elif isinstance(c24, dict) and c24.get("found") is False:
            lines.append(f"  Chrono24: ❌ Not found")

    # Forum reputation — only if there's actual content
    fr = report.get("forum_reputation", {})
    if isinstance(fr, dict):
        sentiment = fr.get("overall_sentiment")
        if sentiment and sentiment != "none":
            emoji = {"positive": "✅", "negative": "⚠️", "mixed": "🟡"}.get(sentiment, "⚪")
            lines.append(f"  Forum Reputation: {emoji} {sentiment.upper()}")

    # Google Business
    sm = report.get("social_media", {})
    if isinstance(sm, dict):
        gb_rating = sm.get("google_business_rating")
        gb_count = sm.get("google_review_count")
        if gb_rating:
            lines.append(f"  Google Business: {gb_rating}⭐ ({gb_count or '?'} reviews)")

    return lines


def _build_digital_section(report: dict) -> list:
    """Domain, social media, online presence — combined."""
    lines = []

    # Domain
    di = report.get("domain_intel", {}) or report.get("domain_info", {})
    if isinstance(di, dict) and di.get("domain"):
        lines.append(f"  Domain: {di['domain']}")
        if di.get("age_years") is not None:
            lines.append(f"  Domain Age: {di['age_years']} years")
        if di.get("registrar"):
            lines.append(f"  Registrar: {di['registrar']}")
        if di.get("privacy_protected") is not None:
            lines.append(f"  Privacy: {'Protected' if di['privacy_protected'] else 'Public'}")

    # Online presence
    op = report.get("online_presence", {})
    if isinstance(op, dict):
        for platform in ["website", "instagram", "linkedin", "facebook"]:
            val = op.get(platform)
            if val:
                lines.append(f"  {platform.title()}: {val}")

    # Social media details
    sm = report.get("social_media", {})
    if isinstance(sm, dict):
        ig = sm.get("instagram", {})
        if isinstance(ig, dict) and (ig.get("followers") or ig.get("url")):
            followers = ig.get("followers", "?")
            posts = ig.get("posts", "?")
            lines.append(f"  Instagram: {followers} followers | {posts} posts")

        li = sm.get("linkedin", {})
        if isinstance(li, dict) and (li.get("connections") or li.get("url")):
            conn = li.get("connections", "?")
            lines.append(f"  LinkedIn: {conn} connections")

    return lines


def _build_xref_section(report: dict) -> list:
    """Cross-reference analysis results."""
    lines = []
    xref = report.get("cross_reference", {})
    if not isinstance(xref, dict):
        return lines

    score = xref.get("consistency_score")
    if score is not None:
        lines.append(f"  Consistency Score: {score}/100")

    summary = xref.get("summary")
    if summary:
        lines.append(f"  {summary}")

    matches = xref.get("matches", [])
    if matches:
        lines.append("")
        lines.append("  Confirmed:")
        for m in matches[:5]:
            lines.append(f"    ✅ {m}")

    mismatches = xref.get("mismatches", [])
    if mismatches:
        lines.append("")
        lines.append("  Inconsistencies:")
        for m in mismatches[:5]:
            if isinstance(m, dict):
                sev = m.get("severity", "?")
                emoji = "🔴" if sev == "HIGH" else "🟡" if sev == "MEDIUM" else "⚪"
                lines.append(f"    {emoji} {m.get('detail', '')}")

    return lines


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _today() -> str:
    from datetime import date
    return date.today().isoformat()


def _wrap(text: str, width: int = 56) -> list:
    """Word-wrap text to width."""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        if len(current) + len(word) + 1 > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}" if current else word
    if current:
        lines.append(current)
    return lines


# ═══════════════════════════════════════════════════════════════════════════════
# TEST
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    test_report = {
        "target": "Acme Watches LLC",
        "type": "company",
        "risk_rating": "HIGH",
        "risk_confidence": "HIGH",
        "executive_summary": "Acme Watches LLC presents significant risk indicators. The entity was incorporated only 9 months ago, has zero marketplace presence despite claiming to be a watch dealer, and operates from a virtual office address. The owner's Instagram shows 15,000 followers with only 12 posts, suggesting purchased followers.",
        "risk_reasoning": "Multiple HIGH severity flags: no marketplace footprint, virtual office, bought followers pattern, and zero online reputation.",
        "competing_scenarios": [
            {
                "scenario": "A: New but legitimate small dealer",
                "probability": "20%",
                "evidence_for": ["Active FL registration", "Real person identified as owner", "OFAC clear"],
                "evidence_against": ["Zero marketplace history", "Virtual office", "Follower/post ratio suspicious"]
            },
            {
                "scenario": "B: Front entity or fraud vehicle",
                "probability": "55%",
                "evidence_for": ["Virtual office", "No marketplace presence", "Bought followers", "New entity"],
                "evidence_against": ["Active registration", "Named officer"]
            },
            {
                "scenario": "C: Legitimate but very early stage",
                "probability": "25%",
                "evidence_for": ["Recent incorporation could mean just starting"],
                "evidence_against": ["Claims to be established", "Marketing suggests longer history"]
            }
        ],
        "top_findings": [
            "Zero marketplace presence on eBay, Chrono24, or any watch platform despite dealer claims",
            "Virtual office address (Regus) presented as business location",
            "Instagram: 15,000 followers with only 12 posts — high probability of purchased followers"
        ],
        "red_flags": [
            "No eBay, Chrono24, or watch platform history",
            "Virtual office at Brickell Ave Suite 200 (known Regus location)",
            "Instagram follower/post ratio indicates purchased followers",
            "Zero forum mentions or reviews anywhere online",
            "Company incorporated only 9 months ago"
        ],
        "green_flags": [
            "OFAC sanctions check: CLEAR",
            "Active Florida registration",
            "Named officer on record (John Dealer)"
        ],
        "unresolved_questions": [
            "Owner's previous business history unknown",
            "No transaction history available for verification",
            "Claimed inventory not verifiable"
        ],
        "recommended_action": "Do NOT transact without independent verification. Request: (1) proof of inventory via timestamped photos, (2) references from 3+ completed transactions, (3) bank reference letter. Consider escrow for any transaction.",
        "corporate_records": {
            "legal_name": "Acme Watches LLC",
            "status": "Active",
            "incorporation_date": "2024-06-15",
            "principal_address": "1234 Brickell Ave Suite 200, Miami FL 33131",
            "officers_managers": [{"name": "John Dealer", "title": "Manager"}],
        },
        "ofac_status": {"status": "CLEAR"},
        "federal_cases": {"total_found": 0},
        "bankruptcy": {"total_found": 0},
        "marketplace_presence": {
            "ebay": {"found": False},
            "chrono24": {"found": False},
        },
        "social_media": {
            "instagram": {"followers": 15000, "posts": 12, "full_name": "Acme Watches"},
            "linkedin": {"connections": 8},
        },
        "domain_intel": {
            "domain": "rccrown.com",
            "age_years": 0.7,
            "registrar": "Namecheap",
            "privacy_protected": True,
        },
        "forum_reputation": {"overall_sentiment": "none"},
        "cross_reference": {
            "consistency_score": 28,
            "summary": "⚠️ 5 inconsistencies found across 9 checks",
            "matches": [
                "Corporate status: Active",
                "Officer name matches LinkedIn profile",
            ],
            "mismatches": [
                {"severity": "MEDIUM", "detail": "Virtual office signal detected"},
                {"severity": "MEDIUM", "detail": "Instagram: 15K followers but 12 posts"},
                {"severity": "LOW", "detail": "LinkedIn: only 8 connections"},
            ],
        },
        "contradictions": [
            {"severity": "HIGH", "detail": "No marketplace presence despite dealer claims",
             "significance": "Legitimate dealers have verifiable transaction history"},
            {"severity": "MEDIUM", "detail": "Virtual office presented as business location",
             "significance": "Legal but misleading if presented as real office"},
        ],
        "confidence_tags": {
            "corporate_identity": "CONFIRMED",
            "sanctions_screening": "CONFIRMED",
            "legal_history": "CONFIRMED",
            "online_presence": "PROBABLE",
            "financial_claims": "NOT_FOUND",
            "overall": "MEDIUM",
        },
        "_meta": {
            "synthesis_version": "v2_two_pass",
            "extract_model": "google/gemini-2.5-flash",
            "analyze_model": "anthropic/claude-sonnet-4-6",
            "risk_tier_used": "high",
            "total_time_seconds": 12.3,
            "total_cost_usd": 0.0234,
            "cross_ref_consistency": 28,
            "contradictions_found": 2,
            "high_severity_flags": 1,
        },
    }

    print(format_report(test_report))
