"""
PATTERN_DETECTOR.py — Behavioral Fraud Pattern Detection
==========================================================
Codified knowledge of how fraudsters operate in specific industries.
Checks every target against known fraud pattern templates.

Each pattern is a set of signals. If enough signals match, the pattern
triggers and gets flagged in the report.

This is what veteran investigators do intuitively — we're codifying it.
"""

from typing import Optional


# ═══════════════════════════════════════════════════════════════════════════════
# PATTERN DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════════

WATCH_FRAUD_PATTERNS = {
    "ghost_dealer": {
        "name": "Ghost Dealer",
        "description": "Claims to be a dealer but has zero verifiable marketplace presence",
        "severity": "HIGH",
        "min_signals": 3,
        "signals": [
            ("no_chrono24", "No Chrono24 dealer profile or listings"),
            ("no_ebay", "No eBay seller profile or transaction history"),
            ("no_forum_presence", "Zero mentions on WatchUSeek, Reddit, or watch forums"),
            ("no_watchrecon", "Not found on WatchRecon or Subdial"),
            ("dealer_claims", "Name or marketing suggests dealer/seller status"),
            ("pressure_tactics", "Urgency language: 'act now', 'only today', 'wire immediately'"),
        ],
    },
    "identity_fabrication": {
        "name": "Identity Fabrication",
        "description": "Social media presence appears manufactured or purchased",
        "severity": "HIGH",
        "min_signals": 2,
        "signals": [
            ("bought_followers", "Instagram follower/post ratio > 500:1"),
            ("new_social", "Social media accounts created within last 6 months"),
            ("stock_photos", "Profile photos appear generic or stock"),
            ("no_engagement", "Posts have zero or near-zero engagement despite followers"),
            ("lifestyle_posts_only", "Only luxury lifestyle content, no actual business content"),
        ],
    },
    "shell_entity": {
        "name": "Shell Entity Pattern",
        "description": "Entity appears to be a shell company or front",
        "severity": "HIGH",
        "min_signals": 3,
        "signals": [
            ("virtual_office", "Registered at known virtual office / mail drop"),
            ("new_entity", "Incorporated within last 6 months"),
            ("no_employees", "No employees visible on LinkedIn or elsewhere"),
            ("privacy_domain", "Domain registered with privacy protection"),
            ("new_domain", "Domain registered within last 6 months"),
            ("entity_churn", "Owner has 3+ entities registered in rapid succession"),
            ("different_state_reg", "Registered in Delaware/Wyoming but claims to operate elsewhere"),
        ],
    },
    "consignment_scam": {
        "name": "Consignment/Advance Fee Pattern",
        "description": "Classic consignment fraud: takes watches, delays payment, disappears",
        "severity": "CRITICAL",
        "min_signals": 2,
        "signals": [
            ("wire_only", "Demands wire transfer, refuses escrow or PayPal"),
            ("no_references", "Cannot provide verifiable transaction references"),
            ("too_good_price", "Offering prices 15-25% below market"),
            ("new_relationship", "First contact, no prior history"),
            ("ghost_dealer", "Ghost Dealer pattern also triggered"),
        ],
    },
}

FINANCE_FRAUD_PATTERNS = {
    "unregistered_advisor": {
        "name": "Unregistered Investment Advisor",
        "description": "Offering investment advice without proper registration",
        "severity": "HIGH",
        "min_signals": 2,
        "signals": [
            ("no_finra", "Not found in FINRA BrokerCheck"),
            ("no_sec", "No SEC registration or filings"),
            ("investment_claims", "Claims to manage money or offer investment returns"),
            ("guaranteed_returns", "Promises guaranteed or unrealistic returns"),
        ],
    },
    "ponzi_indicators": {
        "name": "Ponzi Scheme Indicators",
        "description": "Classic Ponzi scheme warning signs",
        "severity": "CRITICAL",
        "min_signals": 3,
        "signals": [
            ("guaranteed_returns", "Promises consistent high returns"),
            ("referral_heavy", "Heavy emphasis on recruiting new investors"),
            ("withdrawal_issues", "Reports of delayed or denied withdrawals"),
            ("vague_strategy", "Cannot explain investment strategy clearly"),
            ("no_audited_financials", "No audited financial statements"),
            ("sec_complaints", "SEC complaints or enforcement actions"),
        ],
    },
}

GENERAL_FRAUD_PATTERNS = {
    "reputation_astroturfing": {
        "name": "Reputation Astroturfing",
        "description": "Artificially clean or manufactured reputation",
        "severity": "MEDIUM",
        "min_signals": 2,
        "signals": [
            ("only_positive_reviews", "Only positive reviews, zero negative across all platforms"),
            ("recent_reviews_only", "All reviews posted within last 3 months"),
            ("generic_review_text", "Review text appears generic or templated"),
            ("no_forum_presence", "No organic mentions on forums or social media"),
            ("paid_press", "Only press coverage is paid/sponsored content"),
        ],
    },
    "identity_theft_business": {
        "name": "Business Identity Theft",
        "description": "Using another company's reputation or registration",
        "severity": "HIGH",
        "min_signals": 2,
        "signals": [
            ("name_similar", "Company name very similar to established business"),
            ("address_mismatch", "Website address differs from registered address"),
            ("domain_mismatch", "Domain doesn't match the registered company name"),
            ("officer_mismatch", "Officers on website differ from registry records"),
        ],
    },
    "serial_entity_creator": {
        "name": "Serial Entity Creator",
        "description": "Person creates multiple entities in rapid succession — potential asset layering",
        "severity": "MEDIUM",
        "min_signals": 2,
        "signals": [
            ("multi_entity", "3+ entities registered to same person"),
            ("different_industries", "Entities span unrelated industries"),
            ("short_lifespan", "Previous entities dissolved within 1-2 years"),
            ("same_address", "Multiple entities at same address"),
        ],
    },
}

REAL_ESTATE_FRAUD_PATTERNS = {
    "title_fraud": {
        "name": "Title Fraud / Property Scam",
        "severity": "CRITICAL",
        "min_signals": 2,
        "signals": [
            ("no_license", "No real estate license found"),
            ("no_mls", "Not listed in MLS or local real estate board"),
            ("pressure_close", "Rushing to close without proper inspection"),
            ("wire_instructions", "Sending wire instructions via email (BEC risk)"),
        ],
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# PATTERN MATCHER
# ═══════════════════════════════════════════════════════════════════════════════

class PatternDetector:
    """
    Check investigation data against known fraud patterns.
    Returns list of triggered patterns with matched signals.
    """

    def __init__(self, report: dict, industry: list = None):
        self.report = report
        self.industry = industry or ["general"]
        self.triggered = []

    def detect_all(self) -> list:
        """Run all applicable pattern checks."""
        seen_patterns = set()

        # Always check general patterns
        self._check_patterns(GENERAL_FRAUD_PATTERNS)
        seen_patterns.update(p["pattern_id"] for p in self.triggered)

        # Industry-specific (skip already-triggered pattern IDs)
        for ind in self.industry:
            if ind in ("watches", "jewelry", "luxury"):
                self._check_patterns(WATCH_FRAUD_PATTERNS, skip=seen_patterns)
            elif ind in ("finance", "crypto", "investment"):
                self._check_patterns(FINANCE_FRAUD_PATTERNS, skip=seen_patterns)
            elif ind in ("real_estate", "property"):
                self._check_patterns(REAL_ESTATE_FRAUD_PATTERNS, skip=seen_patterns)
            seen_patterns.update(p["pattern_id"] for p in self.triggered)

        return self.triggered

    def _check_patterns(self, pattern_set: dict, skip: set = None):
        """Check report data against a set of patterns."""
        skip = skip or set()
        for pattern_id, pattern in pattern_set.items():
            if pattern_id in skip:
                continue
            matched_signals = []

            for signal_id, signal_desc in pattern["signals"]:
                if self._check_signal(signal_id):
                    matched_signals.append({
                        "id": signal_id,
                        "description": signal_desc,
                    })

            if len(matched_signals) >= pattern["min_signals"]:
                self.triggered.append({
                    "pattern_id": pattern_id,
                    "name": pattern["name"],
                    "description": pattern.get("description", ""),
                    "severity": pattern["severity"],
                    "signals_matched": len(matched_signals),
                    "signals_required": pattern["min_signals"],
                    "signals_total": len(pattern["signals"]),
                    "matched": matched_signals,
                    "confidence": round(len(matched_signals) / len(pattern["signals"]), 2),
                })

    def _check_signal(self, signal_id: str) -> bool:
        """Check if a specific signal is present in the report data."""
        r = self.report

        # Marketplace signals
        if signal_id == "no_chrono24":
            mp = r.get("marketplace_presence", {})
            c24 = mp.get("chrono24", {}) or mp.get("chrono24_seller", {})
            return isinstance(c24, dict) and not c24.get("found")

        if signal_id == "no_ebay":
            mp = r.get("marketplace_presence", {})
            ebay = mp.get("ebay", {}) or mp.get("ebay_seller", {})
            return isinstance(ebay, dict) and not ebay.get("found")

        if signal_id == "no_forum_presence":
            fr = r.get("forum_reputation", {})
            return isinstance(fr, dict) and fr.get("overall_sentiment") in (None, "none")

        if signal_id == "no_watchrecon":
            wp = r.get("watch_platform_presence", {})
            if isinstance(wp, dict):
                for platform, data in wp.items():
                    if isinstance(data, dict) and data.get("found"):
                        return False
            return True

        if signal_id == "dealer_claims":
            target = r.get("target", "").lower()
            return any(w in target for w in ["dealer", "watch", "timepiece", "collection",
                                              "trading", "luxury", "chrono"])

        # Social media signals
        if signal_id == "bought_followers":
            sm = r.get("social_media", {})
            ig = sm.get("instagram", {}) if isinstance(sm, dict) else {}
            if isinstance(ig, dict):
                followers = ig.get("followers")
                posts = ig.get("posts")
                if isinstance(followers, (int, float)) and isinstance(posts, (int, float)):
                    if posts > 0 and followers / posts > 500:
                        return True
            return False

        if signal_id == "no_engagement":
            # Would need engagement data — default to False
            return False

        # Entity signals
        if signal_id == "virtual_office":
            xref = r.get("cross_reference", {})
            mismatches = xref.get("mismatches", []) if isinstance(xref, dict) else []
            return any(m.get("type") == "VIRTUAL_OFFICE" for m in mismatches if isinstance(m, dict))

        if signal_id in ("new_entity", "new_domain"):
            cr = r.get("corporate_records", {})
            di = r.get("domain_intel", {}) or r.get("domain_info", {})
            if signal_id == "new_entity" and isinstance(cr, dict):
                inc = cr.get("incorporation_date", "")
                if inc:
                    from cross_reference import parse_date_safe
                    from datetime import date
                    d = parse_date_safe(str(inc))
                    if d and (date.today() - d).days < 180:
                        return True
            if signal_id == "new_domain" and isinstance(di, dict):
                age = di.get("age_years")
                if isinstance(age, (int, float)) and age < 0.5:
                    return True
            return False

        if signal_id == "no_employees":
            sm = r.get("social_media", {})
            li = sm.get("linkedin", {}) if isinstance(sm, dict) else {}
            if isinstance(li, dict):
                connections = li.get("connections")
                if isinstance(connections, int) and connections < 5:
                    return True
            return False

        if signal_id == "privacy_domain":
            di = r.get("domain_intel", {}) or r.get("domain_info", {})
            return isinstance(di, dict) and di.get("privacy_protected") is True

        if signal_id == "multi_entity":
            re_data = r.get("related_entities", [])
            return isinstance(re_data, list) and len(re_data) >= 3

        if signal_id == "entity_churn":
            return self._check_signal("multi_entity")

        # Financial signals
        if signal_id == "no_finra":
            finra = r.get("finra_brokercheck", {})
            return isinstance(finra, dict) and finra.get("total", 0) == 0

        if signal_id == "no_sec":
            sec = r.get("sec_filings", {})
            return isinstance(sec, dict) and sec.get("total_hits", 0) == 0

        # Generic signals
        if signal_id in ("wire_only", "pressure_tactics", "too_good_price",
                          "guaranteed_returns", "no_references", "new_relationship",
                          "referral_heavy", "withdrawal_issues", "vague_strategy",
                          "no_audited_financials", "recent_reviews_only",
                          "generic_review_text", "paid_press", "stock_photos",
                          "lifestyle_posts_only", "new_social",
                          "name_similar", "address_mismatch", "domain_mismatch",
                          "officer_mismatch", "different_industries", "short_lifespan",
                          "same_address", "only_positive_reviews",
                          "no_license", "no_mls", "pressure_close", "wire_instructions",
                          "sec_complaints", "investment_claims", "different_state_reg"):
            # These require context from notes or can't be auto-detected yet
            # Check notes and contradictions for signals
            notes = str(r.get("_meta", {}).get("notes", "")).lower()
            contradictions = r.get("contradictions", [])
            red_flags = r.get("red_flags", [])

            signal_keywords = {
                "wire_only": ["wire", "wire transfer"],
                "pressure_tactics": ["urgent", "act now", "today only", "limited time"],
                "too_good_price": ["below market", "too cheap", "below retail"],
                "guaranteed_returns": ["guaranteed", "guaranteed return"],
                "sec_complaints": ["sec", "enforcement", "complaint"],
                "investment_claims": ["invest", "returns", "portfolio"],
            }

            keywords = signal_keywords.get(signal_id, [])
            if keywords:
                all_text = notes + " " + " ".join(str(f) for f in red_flags)
                return any(kw in all_text for kw in keywords)

            return False

        # Ghost dealer meta-check
        if signal_id == "ghost_dealer":
            return any(t.get("pattern_id") == "ghost_dealer" for t in self.triggered)

        return False


def format_pattern_results(triggered: list) -> str:
    """Format triggered patterns for display."""
    if not triggered:
        return ""

    lines = ["", "🔍 BEHAVIORAL PATTERN ANALYSIS"]
    lines.append("─" * 40)

    for pattern in triggered:
        sev = pattern.get("severity", "?")
        emoji = "🚨" if sev == "CRITICAL" else "🔴" if sev == "HIGH" else "🟡"
        conf = pattern.get("confidence", 0)
        conf_pct = f"{conf * 100:.0f}%"

        lines.append(f"  {emoji} {pattern['name']} [{sev}] — {conf_pct} match")
        lines.append(f"     {pattern.get('description', '')}")
        lines.append(f"     Signals: {pattern['signals_matched']}/{pattern['signals_total']} matched")
        for sig in pattern.get("matched", []):
            lines.append(f"       • {sig['description']}")
        lines.append("")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# TEST
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Test with Acme Watches-like data (known fraud pattern)
    test_report = {
        "target": "Crown Watches LLC",
        "marketplace_presence": {
            "ebay": {"found": False},
            "chrono24": {"found": False},
        },
        "watch_platform_presence": {},
        "forum_reputation": {"overall_sentiment": "none"},
        "social_media": {
            "instagram": {"followers": 15000, "posts": 12},
            "linkedin": {"connections": 3},
        },
        "domain_intel": {"age_years": 0.3, "privacy_protected": True},
        "corporate_records": {"incorporation_date": "2025-11-01"},
        "cross_reference": {
            "mismatches": [
                {"type": "VIRTUAL_OFFICE", "severity": "MEDIUM"},
            ]
        },
        "related_entities": [
            {"name": "Crown Capital"}, {"name": "Crown Holdings"}, {"name": "Crown Trading"},
        ],
        "contradictions": [],
        "red_flags": [],
    }

    detector = PatternDetector(test_report, industry=["watches", "luxury"])
    triggered = detector.detect_all()

    print("Pattern Detection Test: 'Crown Watches LLC'")
    print(format_pattern_results(triggered))
    print(f"\nTotal patterns triggered: {len(triggered)}")
