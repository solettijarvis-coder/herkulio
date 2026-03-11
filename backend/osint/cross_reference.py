"""
CROSS_REFERENCE.py — Real Cross-Reference & Contradiction Detection Engine
============================================================================
Runs BETWEEN data extraction and AI synthesis.
Compares data across all sources, catches contradictions, validates consistency.

Three components:
  1. CrossReferencer — compares addresses, names, timelines, corporate data
  2. ContradictionDetector — explicit pattern rules for known red flag combos
  3. ConfidenceTagger — tags each fact with confidence level

Usage:
    from cross_reference import CrossReferencer, ContradictionDetector, ConfidenceTagger
    
    xref = CrossReferencer(extracted_data)
    xref_report = xref.run_all_checks()
    
    contradictions = ContradictionDetector(extracted_data, xref_report).detect()
    
    tagged = ConfidenceTagger(extracted_data).tag_all()
"""

import re
from datetime import datetime, date
from difflib import SequenceMatcher
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════════════
# ADDRESS NORMALIZATION
# ═══════════════════════════════════════════════════════════════════════════════

# Common abbreviation expansions
ADDR_ABBREVIATIONS = {
    "st": "street", "st.": "street", "ave": "avenue", "ave.": "avenue",
    "blvd": "boulevard", "blvd.": "boulevard", "dr": "drive", "dr.": "drive",
    "ln": "lane", "ln.": "lane", "ct": "court", "ct.": "court",
    "rd": "road", "rd.": "road", "pl": "place", "pl.": "place",
    "pkwy": "parkway", "hwy": "highway", "cir": "circle",
    "ste": "suite", "ste.": "suite", "apt": "apartment", "apt.": "apartment",
    "fl": "floor", "fl.": "floor", "bldg": "building", "bldg.": "building",
    "n": "north", "s": "south", "e": "east", "w": "west",
    "n.": "north", "s.": "south", "e.": "east", "w.": "west",
    "ne": "northeast", "nw": "northwest", "se": "southeast", "sw": "southwest",
}

VIRTUAL_OFFICE_SIGNALS = [
    "regus", "wework", "ipostal", "ups store", "the ups store", "mailboxes etc",
    "earth class mail", "anytime mailbox", "postal annex", "pak mail",
    "virtual office", "registered agent", "incfile", "northwest registered",
    "legalzoom", "suite 100", "suite 200", "suite 300", "pmb ", "box #",
    "po box", "p.o. box", "mail drop", "mail center",
    "800 n king", "1209 orange", "2711 centerville",  # Known DE shell addresses
    "251 little falls", "1000 n west", "1013 centre road",
    "850 new burton", "3500 south dupont", "108 west 13th",
]


def normalize_address(addr: str) -> str:
    """Normalize an address for comparison."""
    if not addr or not isinstance(addr, str):
        return ""
    # Lowercase
    addr = addr.lower().strip()
    # Remove extra whitespace
    addr = re.sub(r'\s+', ' ', addr)
    # Remove punctuation except hyphens
    addr = re.sub(r'[,\.\#]', ' ', addr)
    addr = re.sub(r'\s+', ' ', addr).strip()
    # Expand abbreviations
    words = addr.split()
    expanded = []
    for w in words:
        expanded.append(ADDR_ABBREVIATIONS.get(w, w))
    return " ".join(expanded)


def addresses_match(addr1: str, addr2: str, threshold: float = 0.75) -> bool:
    """Fuzzy match two addresses."""
    n1 = normalize_address(addr1)
    n2 = normalize_address(addr2)
    if not n1 or not n2:
        return False
    # Exact match after normalization
    if n1 == n2:
        return True
    # Fuzzy match
    ratio = SequenceMatcher(None, n1, n2).ratio()
    return ratio >= threshold


def is_virtual_office(addr: str) -> Optional[str]:
    """Check if address matches virtual office patterns. Returns signal if found."""
    if not addr:
        return None
    addr_lower = addr.lower()
    for signal in VIRTUAL_OFFICE_SIGNALS:
        if signal in addr_lower:
            return signal
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# NAME MATCHING
# ═══════════════════════════════════════════════════════════════════════════════

def normalize_name(name: str) -> str:
    """Normalize a person/company name for comparison."""
    if not name or not isinstance(name, str):
        return ""
    name = name.lower().strip()
    # Remove common suffixes
    for suffix in [" llc", " inc", " inc.", " corp", " corp.", " ltd", " ltd.",
                   " co", " co.", " group", " holdings", " partners",
                   " gmbh", " ag", " sa", " srl", " bv", " nv", " plc",
                   " pte", " pty"]:
        if name.endswith(suffix):
            name = name[:-len(suffix)].strip()
    # Remove punctuation
    name = re.sub(r'[,\.\-\'\"&]', ' ', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def names_match(name1: str, name2: str, threshold: float = 0.80) -> bool:
    """Fuzzy match two names."""
    n1 = normalize_name(name1)
    n2 = normalize_name(name2)
    if not n1 or not n2:
        return False
    if n1 == n2:
        return True
    # Check containment (one name inside the other)
    if n1 in n2 or n2 in n1:
        return True
    ratio = SequenceMatcher(None, n1, n2).ratio()
    return ratio >= threshold


# ═══════════════════════════════════════════════════════════════════════════════
# DATE PARSING
# ═══════════════════════════════════════════════════════════════════════════════

def parse_date_safe(date_str: str) -> Optional[date]:
    """Try multiple date formats."""
    if not date_str or not isinstance(date_str, str):
        return None
    date_str = date_str.strip()[:10]  # Take first 10 chars (YYYY-MM-DD or similar)
    formats = ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y%m%d", "%b %d, %Y", "%B %d, %Y"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except (ValueError, TypeError):
            continue
    # Try to extract year at minimum
    m = re.search(r'(\d{4})', date_str)
    if m:
        try:
            return date(int(m.group(1)), 1, 1)
        except ValueError:
            pass
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# CROSS REFERENCER
# ═══════════════════════════════════════════════════════════════════════════════

class CrossReferencer:
    """
    Compare data across all sources. Runs between extraction and synthesis.
    Produces matches, mismatches, and gaps that feed into the analysis prompt.
    """

    def __init__(self, data: dict):
        self.data = data
        self.matches = []
        self.mismatches = []
        self.gaps = []

    def run_all_checks(self) -> dict:
        """Run all cross-reference checks. Returns structured report."""
        self.check_addresses()
        self.check_names()
        self.check_timelines()
        self.check_corporate_consistency()
        self.check_online_vs_official()
        self.check_virtual_office()
        return {
            "matches": self.matches,
            "mismatches": self.mismatches,
            "gaps": self.gaps,
            "consistency_score": self._score(),
            "summary": self._summary(),
        }

    def check_addresses(self):
        """Collect and compare addresses from all sources."""
        addresses = {}

        # Corporate registry
        cr = self.data.get("corporate_records", {})
        if isinstance(cr, dict) and cr.get("principal_address"):
            addresses["corporate_registry"] = cr["principal_address"]
        if isinstance(cr, dict) and cr.get("registered_agent"):
            agent_addr = cr["registered_agent"]
            if len(str(agent_addr)) > 20:  # Likely includes address
                addresses["registered_agent"] = str(agent_addr)

        # Domain WHOIS
        di = self.data.get("domain_intel", {}) or self.data.get("domain_info", {})
        if isinstance(di, dict) and di.get("registrant_address"):
            addresses["domain_whois"] = di["registrant_address"]

        # Google Business
        gb = self.data.get("google_business", {})
        if isinstance(gb, dict) and gb.get("address"):
            addresses["google_business"] = gb["address"]

        if len(addresses) < 2:
            self.gaps.append("Only found address from 1 source — cannot cross-reference location")
            return

        # Compare all pairs
        addr_list = list(addresses.items())
        all_match = True
        for i in range(len(addr_list)):
            for j in range(i + 1, len(addr_list)):
                src1, a1 = addr_list[i]
                src2, a2 = addr_list[j]
                if addresses_match(a1, a2):
                    self.matches.append(
                        f"Address consistent: {src1} ↔ {src2}"
                    )
                else:
                    all_match = False
                    self.mismatches.append({
                        "type": "ADDRESS_MISMATCH",
                        "severity": "HIGH",
                        "detail": f"Different addresses: {src1}='{a1[:60]}' vs {src2}='{a2[:60]}'",
                        "sources": {src1: a1, src2: a2},
                    })

    def check_names(self):
        """Compare entity names across all sources."""
        names = {}

        cr = self.data.get("corporate_records", {})
        if isinstance(cr, dict) and cr.get("legal_name"):
            names["registry_legal"] = cr["legal_name"]

        # Officers
        officers = []
        if isinstance(cr, dict) and cr.get("officers_managers"):
            for o in cr["officers_managers"]:
                if isinstance(o, dict) and o.get("name"):
                    officers.append(o["name"])
                elif isinstance(o, str):
                    officers.append(o)

        # Social media names
        sm = self.data.get("social_media", {})
        if isinstance(sm, dict):
            li = sm.get("linkedin", {})
            if isinstance(li, dict) and li.get("name"):
                names["linkedin"] = li["name"]
            ig = sm.get("instagram", {})
            if isinstance(ig, dict) and ig.get("full_name"):
                names["instagram"] = ig["full_name"]

        if len(names) >= 2:
            name_list = list(names.items())
            for i in range(len(name_list)):
                for j in range(i + 1, len(name_list)):
                    s1, n1 = name_list[i]
                    s2, n2 = name_list[j]
                    if names_match(n1, n2):
                        self.matches.append(f"Name consistent: {s1} ↔ {s2}")
                    else:
                        self.mismatches.append({
                            "type": "NAME_MISMATCH",
                            "severity": "MEDIUM",
                            "detail": f"Name differs: {s1}='{n1}' vs {s2}='{n2}'",
                        })

        # Check if officer names match social profiles (for person searches)
        if officers and names:
            for officer in officers[:3]:
                for src, name in names.items():
                    if src == "registry_legal":
                        continue
                    if names_match(officer, name):
                        self.matches.append(f"Officer '{officer}' matches {src} profile")

    def check_timelines(self):
        """Verify temporal consistency across data points."""
        dates = {}

        cr = self.data.get("corporate_records", {})
        if isinstance(cr, dict) and cr.get("incorporation_date"):
            d = parse_date_safe(str(cr["incorporation_date"]))
            if d:
                dates["incorporated"] = d

        di = self.data.get("domain_intel", {}) or self.data.get("domain_info", {})
        if isinstance(di, dict):
            if di.get("registered"):
                d = parse_date_safe(str(di["registered"]))
                if d:
                    dates["domain_registered"] = d
            if di.get("wayback_earliest_snapshot"):
                snap = str(di["wayback_earliest_snapshot"])
                if len(snap) >= 8:
                    d = parse_date_safe(f"{snap[:4]}-{snap[4:6]}-{snap[6:8]}")
                    if d:
                        dates["first_web_presence"] = d

        today = date.today()

        # Flag: domain registered BEFORE company incorporated
        if "domain_registered" in dates and "incorporated" in dates:
            if dates["domain_registered"] < dates["incorporated"]:
                diff = (dates["incorporated"] - dates["domain_registered"]).days
                if diff > 30:  # More than a month before
                    self.mismatches.append({
                        "type": "TIMELINE_ANOMALY",
                        "severity": "MEDIUM",
                        "detail": f"Domain registered {diff} days BEFORE company incorporation",
                    })
                else:
                    self.matches.append("Domain and incorporation dates align (within 30 days)")

        # Flag: very new company
        if "incorporated" in dates:
            age_days = (today - dates["incorporated"]).days
            if age_days < 90:
                self.mismatches.append({
                    "type": "NEW_ENTITY",
                    "severity": "MEDIUM",
                    "detail": f"Company incorporated only {age_days} days ago",
                })
            elif age_days < 365:
                self.mismatches.append({
                    "type": "YOUNG_ENTITY",
                    "severity": "LOW",
                    "detail": f"Company less than 1 year old ({age_days} days)",
                })

        # Flag: very new domain
        if "domain_registered" in dates:
            domain_age = (today - dates["domain_registered"]).days
            if domain_age < 90:
                self.mismatches.append({
                    "type": "NEW_DOMAIN",
                    "severity": "HIGH",
                    "detail": f"Domain registered only {domain_age} days ago",
                })
            elif domain_age < 365:
                self.mismatches.append({
                    "type": "YOUNG_DOMAIN",
                    "severity": "MEDIUM",
                    "detail": f"Domain less than 1 year old ({domain_age} days)",
                })

        if len(dates) < 2:
            self.gaps.append("Limited date data — cannot verify temporal consistency")

    def check_corporate_consistency(self):
        """Compare data across multiple corporate registries."""
        cr = self.data.get("corporate_records", {})
        if not isinstance(cr, dict):
            return

        status = cr.get("status", "").lower()
        if status and status not in ("active", "good standing", "current"):
            self.mismatches.append({
                "type": "INACTIVE_ENTITY",
                "severity": "HIGH",
                "detail": f"Corporate status: '{cr.get('status')}' (not active)",
            })
        elif status:
            self.matches.append(f"Corporate status: {cr.get('status')}")

        # Check for shell indicators
        if not cr.get("officers_managers") and not cr.get("registered_agent"):
            self.gaps.append("No officers or registered agent found in corporate records")

    def check_online_vs_official(self):
        """Compare online claims vs official records."""
        sm = self.data.get("social_media", {})
        cr = self.data.get("corporate_records", {})

        if isinstance(sm, dict) and isinstance(cr, dict):
            # LinkedIn employee count vs PPP/official data
            li = sm.get("linkedin", {})
            if isinstance(li, dict) and li.get("connections"):
                connections = li.get("connections", 0)
                if isinstance(connections, int) and connections < 10:
                    self.mismatches.append({
                        "type": "THIN_NETWORK",
                        "severity": "LOW",
                        "detail": f"LinkedIn connections: {connections} (very thin professional network)",
                    })

        # Instagram followers vs posts ratio
        if isinstance(sm, dict):
            ig = sm.get("instagram", {})
            if isinstance(ig, dict):
                followers = ig.get("followers")
                posts = ig.get("posts")
                if isinstance(followers, (int, float)) and isinstance(posts, (int, float)):
                    if followers > 10000 and posts < 20:
                        self.mismatches.append({
                            "type": "SUSPICIOUS_FOLLOWERS",
                            "severity": "MEDIUM",
                            "detail": f"Instagram: {followers:,} followers but only {posts} posts — possible bought followers",
                        })

    def check_virtual_office(self):
        """Check all found addresses for virtual office signals."""
        addresses_to_check = []

        cr = self.data.get("corporate_records", {})
        if isinstance(cr, dict):
            if cr.get("principal_address"):
                addresses_to_check.append(("corporate_registry", cr["principal_address"]))
            if cr.get("registered_agent") and isinstance(cr["registered_agent"], str):
                addresses_to_check.append(("registered_agent", cr["registered_agent"]))

        for loc in (self.data.get("locations", []) or []):
            if isinstance(loc, str):
                addresses_to_check.append(("locations", loc))

        for source, addr in addresses_to_check:
            signal = is_virtual_office(addr)
            if signal:
                self.mismatches.append({
                    "type": "VIRTUAL_OFFICE",
                    "severity": "MEDIUM",
                    "detail": f"Virtual office signal in {source}: '{signal}' detected in '{addr[:80]}'",
                })

    def _score(self) -> int:
        """Calculate consistency score 0-100."""
        if not self.matches and not self.mismatches:
            return 50  # Unknown
        total_checks = len(self.matches) + len(self.mismatches)
        if total_checks == 0:
            return 50
        severity_weights = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
        mismatch_penalty = sum(
            severity_weights.get(m.get("severity", "MEDIUM"), 2)
            for m in self.mismatches if isinstance(m, dict)
        )
        raw_score = max(0, 100 - (mismatch_penalty * 8))
        return min(100, raw_score)

    def _summary(self) -> str:
        """One-line summary of cross-reference results."""
        n_match = len(self.matches)
        n_mismatch = len(self.mismatches)
        n_gap = len(self.gaps)
        high_mismatches = sum(1 for m in self.mismatches
                              if isinstance(m, dict) and m.get("severity") == "HIGH")

        if high_mismatches > 0:
            return f"⚠️ {high_mismatches} HIGH severity inconsistencies found across {n_match + n_mismatch} checks"
        elif n_mismatch > 0:
            return f"🟡 {n_mismatch} inconsistencies found, {n_match} data points confirmed"
        elif n_match > 0:
            return f"✅ {n_match} data points cross-referenced and consistent"
        else:
            return f"⚪ Limited data for cross-referencing ({n_gap} gaps)"


# ═══════════════════════════════════════════════════════════════════════════════
# CONTRADICTION DETECTOR — Explicit pattern rules
# ═══════════════════════════════════════════════════════════════════════════════

class ContradictionDetector:
    """
    Explicit pattern rules for known red flag combinations.
    Fires BEFORE synthesis so the AI can't miss these.
    """

    def __init__(self, data: dict, xref_report: dict = None):
        self.data = data
        self.xref = xref_report or {}
        self.contradictions = []

    def detect(self) -> list:
        """Run all contradiction checks. Returns list of flagged contradictions."""
        self._check_revenue_vs_size()
        self._check_domain_vs_history()
        self._check_marketplace_vs_claims()
        self._check_address_vs_claims()
        self._check_review_anomalies()
        self._check_multi_entity_patterns()
        self._check_financial_distress_vs_claims()
        return self.contradictions

    def _check_revenue_vs_size(self):
        """Revenue claims vs team size / employee count."""
        fs = self.data.get("financial_signals", {})
        sm = self.data.get("social_media", {})

        if isinstance(fs, dict) and fs.get("claimed_revenue"):
            li = sm.get("linkedin", {}) if isinstance(sm, dict) else {}
            if isinstance(li, dict) and li.get("employee_count"):
                try:
                    employees = int(str(li["employee_count"]).replace(",", ""))
                    if employees < 5 and "million" in str(fs["claimed_revenue"]).lower():
                        self.contradictions.append({
                            "type": "REVENUE_SIZE_MISMATCH",
                            "severity": "HIGH",
                            "detail": f"Claims revenue '{fs['claimed_revenue']}' but only {employees} employees visible on LinkedIn",
                            "significance": "Revenue claims may be fabricated or misleading",
                        })
                except (ValueError, TypeError):
                    pass

    def _check_domain_vs_history(self):
        """New domain + claims of long history."""
        di = self.data.get("domain_intel", {}) or self.data.get("domain_info", {})
        cr = self.data.get("corporate_records", {})

        if isinstance(di, dict) and isinstance(cr, dict):
            domain_age = di.get("age_years")
            inc_date = cr.get("incorporation_date")

            if domain_age is not None and isinstance(domain_age, (int, float)):
                if domain_age < 1:
                    # Check if company claims older history
                    if inc_date:
                        inc = parse_date_safe(str(inc_date))
                        if inc and (date.today() - inc).days > 365 * 3:
                            self.contradictions.append({
                                "type": "DOMAIN_AGE_VS_COMPANY_AGE",
                                "severity": "MEDIUM",
                                "detail": f"Domain is {domain_age} years old but company incorporated {inc_date} — possible rebrand or new entity",
                            })

                    # Very new domain is always notable
                    if domain_age < 0.5:
                        self.contradictions.append({
                            "type": "VERY_NEW_DOMAIN",
                            "severity": "HIGH",
                            "detail": f"Domain is only ~{int(domain_age * 12)} months old — high caution for any significant transaction",
                            "significance": "Legitimate established businesses rarely have domains under 6 months old",
                        })

    def _check_marketplace_vs_claims(self):
        """Claims to be a dealer but no marketplace footprint."""
        mp = self.data.get("marketplace_presence", {})
        wp = self.data.get("watch_platform_presence", {})

        has_marketplace = False
        if isinstance(mp, dict):
            ebay = mp.get("ebay_seller", {})
            if isinstance(ebay, dict) and ebay.get("found"):
                has_marketplace = True
            c24 = mp.get("chrono24_seller", {})
            if isinstance(c24, dict) and c24.get("found"):
                has_marketplace = True

        if isinstance(wp, dict):
            for platform, data in wp.items():
                if isinstance(data, dict) and data.get("found"):
                    has_marketplace = True
                    break

        # Check if target name suggests they're a dealer/seller
        target = str(self.data.get("target", "")).lower()
        dealer_signals = ["dealer", "watches", "timepiece", "collection",
                         "trading", "jewelry", "jewel", "luxury"]
        is_dealer_claim = any(s in target for s in dealer_signals)

        if is_dealer_claim and not has_marketplace:
            self.contradictions.append({
                "type": "NO_MARKETPLACE_PRESENCE",
                "severity": "HIGH",
                "detail": "Name suggests dealer/seller but ZERO marketplace presence (no eBay, Chrono24, or platform listings found)",
                "significance": "Legitimate dealers typically have verifiable marketplace history",
            })

    def _check_address_vs_claims(self):
        """Virtual office presented as headquarters."""
        # Check xref results for virtual office flags
        for mismatch in self.xref.get("mismatches", []):
            if isinstance(mismatch, dict) and mismatch.get("type") == "VIRTUAL_OFFICE":
                self.contradictions.append({
                    "type": "VIRTUAL_OFFICE_AS_HQ",
                    "severity": "MEDIUM",
                    "detail": mismatch.get("detail", "Virtual office detected"),
                    "significance": "Using a virtual office is legal but misleading if presented as a real office",
                })

    def _check_review_anomalies(self):
        """Suspiciously clean or suspicious review profiles."""
        fr = self.data.get("forum_reputation", {})
        if isinstance(fr, dict):
            sentiment = fr.get("overall_sentiment")
            mentions = fr.get("mentions", [])

            # Zero online presence
            if not mentions or len(mentions) == 0:
                self.contradictions.append({
                    "type": "ZERO_ONLINE_REPUTATION",
                    "severity": "MEDIUM",
                    "detail": "Zero forum mentions or reviews found anywhere online",
                    "significance": "Complete absence of online reputation is unusual for active businesses",
                })

    def _check_multi_entity_patterns(self):
        """Multiple entities with same owner / address (shell pattern)."""
        re_data = self.data.get("related_entities", [])
        if isinstance(re_data, list) and len(re_data) > 5:
            self.contradictions.append({
                "type": "MULTI_ENTITY_PATTERN",
                "severity": "MEDIUM",
                "detail": f"Found {len(re_data)} related entities — potential shell or entity churn pattern",
                "significance": "Multiple entities under one principal can indicate asset protection or fraud layering",
            })

    def _check_financial_distress_vs_claims(self):
        """Bankruptcy / liens / judgments exist while presenting as stable."""
        bk = self.data.get("bankruptcy", {})
        if isinstance(bk, dict) and bk.get("total_found", 0) > 0:
            self.contradictions.append({
                "type": "BANKRUPTCY_HISTORY",
                "severity": "HIGH",
                "detail": f"Bankruptcy filing(s) found: {bk.get('total_found')} record(s)",
                "significance": "Active or recent bankruptcy significantly increases transaction risk",
            })

        fc = self.data.get("federal_cases", {})
        if isinstance(fc, dict) and fc.get("total_found", 0) > 0:
            total = fc.get("total_found", 0)
            if total > 3:
                self.contradictions.append({
                    "type": "HEAVY_LITIGATION",
                    "severity": "HIGH",
                    "detail": f"{total} federal court cases found — heavily litigated entity",
                    "significance": "Frequent litigation is a strong risk signal",
                })


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIDENCE TAGGER
# ═══════════════════════════════════════════════════════════════════════════════

# Source authority levels
AUTHORITATIVE_SOURCES = {
    "sunbiz.org", "companies_house_uk", "zefix_ch", "pappers_fr",
    "opencorporates.com", "courtlistener.com", "sec_edgar",
    "ofac-api.com", "fec.gov", "propublica_ppp", "cfpb",
    "usaspending", "finra_brokercheck",
}

CLAIMED_SOURCES = {
    "website", "instagram", "linkedin", "facebook", "twitter",
    "self_reported", "bio", "about_page",
}


class ConfidenceTagger:
    """Tag each major data section with confidence level."""

    LEVELS = {
        "CONFIRMED": "✅ From authoritative/government source",
        "PROBABLE": "🟡 Multiple non-authoritative sources agree",
        "CLAIMED": "⚠️ Self-reported by the target (unverified)",
        "UNVERIFIED": "⚪ Single non-authoritative source",
        "NOT_FOUND": "❌ Searched but no data found",
    }

    def __init__(self, data: dict):
        self.data = data

    def tag_all(self) -> dict:
        """Return confidence tags for each major section."""
        tags = {}

        # Corporate records
        cr = self.data.get("corporate_records", {})
        if isinstance(cr, dict) and cr.get("legal_name"):
            tags["corporate_identity"] = "CONFIRMED"
        elif isinstance(cr, dict) and any(cr.values()):
            tags["corporate_identity"] = "PROBABLE"
        else:
            tags["corporate_identity"] = "NOT_FOUND"

        # OFAC / Sanctions
        ofac = self.data.get("ofac_status", {})
        if isinstance(ofac, dict) and ofac.get("status") in ("CLEAR", "HIT"):
            tags["sanctions_screening"] = "CONFIRMED"
        else:
            tags["sanctions_screening"] = "UNVERIFIED"

        # Court records
        fc = self.data.get("federal_cases", {})
        if isinstance(fc, dict) and fc.get("total_found") is not None:
            tags["legal_history"] = "CONFIRMED"
        else:
            tags["legal_history"] = "NOT_FOUND"

        # Online presence
        sm = self.data.get("social_media", {})
        op = self.data.get("online_presence", {})
        online_count = 0
        if isinstance(sm, dict):
            for v in sm.values():
                if isinstance(v, dict) and any(v.values()):
                    online_count += 1
        if isinstance(op, dict):
            for v in op.values():
                if v:
                    online_count += 1

        if online_count >= 3:
            tags["online_presence"] = "CONFIRMED"
        elif online_count >= 1:
            tags["online_presence"] = "PROBABLE"
        else:
            tags["online_presence"] = "NOT_FOUND"

        # Financial
        if self.data.get("financial_signals", {}).get("revenue_verified"):
            tags["financial_claims"] = "CONFIRMED"
        elif self.data.get("financial_signals", {}).get("claimed_revenue"):
            tags["financial_claims"] = "CLAIMED"
        else:
            tags["financial_claims"] = "NOT_FOUND"

        # Overall
        confirmed_count = sum(1 for v in tags.values() if v == "CONFIRMED")
        total = len(tags)
        if confirmed_count >= total * 0.6:
            tags["overall"] = "HIGH"
        elif confirmed_count >= total * 0.3:
            tags["overall"] = "MEDIUM"
        else:
            tags["overall"] = "LOW"

        return tags


# ═══════════════════════════════════════════════════════════════════════════════
# FORMAT FOR SYNTHESIS PROMPT
# ═══════════════════════════════════════════════════════════════════════════════

def format_for_synthesis(xref_report: dict, contradictions: list,
                          confidence_tags: dict) -> str:
    """
    Format cross-reference results into a text block for the AI synthesis prompt.
    This replaces dumping raw data — gives the AI structured analysis context.
    """
    lines = []
    lines.append("=== CROSS-REFERENCE ANALYSIS (Pre-Synthesis) ===")
    lines.append(f"Consistency Score: {xref_report.get('consistency_score', '?')}/100")
    lines.append(f"Summary: {xref_report.get('summary', 'N/A')}")
    lines.append("")

    # Matches
    if xref_report.get("matches"):
        lines.append("CONFIRMED MATCHES:")
        for m in xref_report["matches"]:
            lines.append(f"  ✅ {m}")
        lines.append("")

    # Mismatches
    if xref_report.get("mismatches"):
        lines.append("INCONSISTENCIES FOUND:")
        for m in xref_report["mismatches"]:
            if isinstance(m, dict):
                sev = m.get("severity", "?")
                emoji = "🔴" if sev == "HIGH" else "🟡" if sev == "MEDIUM" else "⚪"
                lines.append(f"  {emoji} [{sev}] {m.get('type', '?')}: {m.get('detail', '')}")
            else:
                lines.append(f"  ⚠️ {m}")
        lines.append("")

    # Gaps
    if xref_report.get("gaps"):
        lines.append("DATA GAPS:")
        for g in xref_report["gaps"]:
            lines.append(f"  ❓ {g}")
        lines.append("")

    # Contradictions
    if contradictions:
        lines.append("=== CONTRADICTION FLAGS ===")
        for c in contradictions:
            if isinstance(c, dict):
                sev = c.get("severity", "?")
                emoji = "🚨" if sev == "HIGH" else "⚠️" if sev == "MEDIUM" else "ℹ️"
                lines.append(f"  {emoji} {c.get('type', '?')}: {c.get('detail', '')}")
                if c.get("significance"):
                    lines.append(f"      → {c['significance']}")
        lines.append("")

    # Confidence
    if confidence_tags:
        lines.append("=== DATA CONFIDENCE ===")
        for section, level in confidence_tags.items():
            if section == "overall":
                continue
            emoji = {"CONFIRMED": "✅", "PROBABLE": "🟡", "CLAIMED": "⚠️",
                     "UNVERIFIED": "⚪", "NOT_FOUND": "❌"}.get(level, "?")
            lines.append(f"  {emoji} {section.replace('_', ' ').title()}: {level}")
        lines.append(f"  Overall Confidence: {confidence_tags.get('overall', '?')}")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# TEST
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Test with sample data
    test_data = {
        "target": "Acme Watches LLC",
        "corporate_records": {
            "legal_name": "Acme Watches LLC",
            "status": "Active",
            "incorporation_date": "2024-06-15",
            "principal_address": "1234 Brickell Ave Suite 200, Miami FL 33131",
            "officers_managers": [{"name": "John Dealer", "title": "Manager"}],
        },
        "domain_intel": {
            "registered": "2024-06-01",
            "age_years": 0.7,
        },
        "social_media": {
            "instagram": {"full_name": "Acme Watches", "followers": 15000, "posts": 12},
            "linkedin": {"name": "John Dealer", "connections": 8},
        },
        "marketplace_presence": {
            "ebay_seller": {"found": False},
            "chrono24_seller": {"found": False},
        },
        "watch_platform_presence": {},
        "forum_reputation": {"overall_sentiment": "none", "mentions": []},
        "ofac_status": {"status": "CLEAR"},
        "federal_cases": {"total_found": 0},
        "bankruptcy": {"total_found": 0},
        "financial_signals": {},
        "related_entities": [],
    }

    print("Running cross-reference engine on test data...\n")

    xref = CrossReferencer(test_data)
    xref_report = xref.run_all_checks()

    detector = ContradictionDetector(test_data, xref_report)
    contradictions = detector.detect()

    tagger = ConfidenceTagger(test_data)
    tags = tagger.tag_all()

    output = format_for_synthesis(xref_report, contradictions, tags)
    print(output)
