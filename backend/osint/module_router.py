"""
MODULE_ROUTER.py — Intelligent Module Selection Engine for Herkulio Intelligence
=================================================================================
Decides WHICH modules to fire based on:
  - Target type (person / company / organization / watch)
  - Geographic location (country + state/province)
  - Industry (auto-detected or specified)
  - Available context (what identifiers we have)
  - Search depth (quick / standard / deep)

Replaces the "fire everything" pattern in osint.py main().
Saves 40-60% of API costs by skipping irrelevant modules.
Improves accuracy by not polluting synthesis with noise.

Usage:
    from module_router import select_modules, detect_industry, resolve_geography
    
    geo = resolve_geography(target, country="CA", state="BC", city="Vancouver")
    industry = detect_industry(target, url="https://example.com")
    modules, skipped = select_modules(
        target_type="company", industry=industry, geo=geo,
        context={"url": "https://...", "email": "..."}, depth="standard"
    )
"""

import re
from typing import Optional

# ═══════════════════════════════════════════════════════════════════════════════
# GEOGRAPHY
# ═══════════════════════════════════════════════════════════════════════════════

# Country detection keywords
COUNTRY_KEYWORDS = {
    "US": ["usa", "united states", "america", "american"],
    "CA": ["canada", "canadian"],
    "UK": ["uk", "united kingdom", "england", "scotland", "wales", "britain", "british"],
    "CH": ["switzerland", "swiss", "suisse", "schweiz"],
    "FR": ["france", "french", "française"],
    "DE": ["germany", "german", "deutsch", "deutschland"],
    "IT": ["italy", "italian", "italia"],
    "NL": ["netherlands", "dutch", "holland"],
    "AE": ["uae", "dubai", "abu dhabi", "emirates", "sharjah"],
    "HK": ["hong kong"],
    "SG": ["singapore"],
    "JP": ["japan", "japanese", "tokyo"],
    "AU": ["australia", "australian"],
}

# State/province → country + region code
STATE_MAP = {
    # US States
    "FL": ("US", "US-FL"), "CA": ("US", "US-CA"), "NY": ("US", "US-NY"),
    "TX": ("US", "US-TX"), "NV": ("US", "US-NV"), "DE": ("US", "US-DE"),
    "WY": ("US", "US-WY"), "IL": ("US", "US-IL"), "GA": ("US", "US-GA"),
    "NJ": ("US", "US-NJ"), "PA": ("US", "US-PA"), "OH": ("US", "US-OH"),
    "CO": ("US", "US-CO"), "WA": ("US", "US-WA"), "MA": ("US", "US-MA"),
    "AZ": ("US", "US-AZ"), "MI": ("US", "US-MI"), "NC": ("US", "US-NC"),
    "TN": ("US", "US-TN"), "MN": ("US", "US-MN"),
    "FLORIDA": ("US", "US-FL"), "CALIFORNIA": ("US", "US-CA"),
    "NEW YORK": ("US", "US-NY"), "TEXAS": ("US", "US-TX"),
    # Canadian Provinces
    "BC": ("CA", "CA-BC"), "ON": ("CA", "CA-ON"), "QC": ("CA", "CA-QC"),
    "AB": ("CA", "CA-AB"), "MB": ("CA", "CA-MB"), "SK": ("CA", "CA-SK"),
    "NS": ("CA", "CA-NS"), "NB": ("CA", "CA-NB"),
    "BRITISH COLUMBIA": ("CA", "CA-BC"), "ONTARIO": ("CA", "CA-ON"),
    "QUEBEC": ("CA", "CA-QC"), "ALBERTA": ("CA", "CA-AB"),
    # UK Regions
    "ENGLAND": ("UK", "UK"), "SCOTLAND": ("UK", "UK"), "WALES": ("UK", "UK"),
    # Swiss Cantons
    "GENEVA": ("CH", "CH"), "ZURICH": ("CH", "CH"), "ZUG": ("CH", "CH"),
    "BERN": ("CH", "CH"), "BASEL": ("CH", "CH"),
}

# City → country + region
CITY_MAP = {
    # US Cities
    "miami": ("US", "US-FL"), "orlando": ("US", "US-FL"), "tampa": ("US", "US-FL"),
    "fort lauderdale": ("US", "US-FL"), "boca raton": ("US", "US-FL"),
    "aventura": ("US", "US-FL"), "jacksonville": ("US", "US-FL"),
    "new york": ("US", "US-NY"), "manhattan": ("US", "US-NY"), "brooklyn": ("US", "US-NY"),
    "los angeles": ("US", "US-CA"), "san francisco": ("US", "US-CA"),
    "san diego": ("US", "US-CA"), "beverly hills": ("US", "US-CA"),
    "houston": ("US", "US-TX"), "dallas": ("US", "US-TX"), "austin": ("US", "US-TX"),
    "las vegas": ("US", "US-NV"), "chicago": ("US", "US-IL"), "atlanta": ("US", "US-GA"),
    # Canadian Cities
    "vancouver": ("CA", "CA-BC"), "victoria": ("CA", "CA-BC"),
    "toronto": ("CA", "CA-ON"), "ottawa": ("CA", "CA-ON"), "mississauga": ("CA", "CA-ON"),
    "montreal": ("CA", "CA-QC"), "laval": ("CA", "CA-QC"), "quebec city": ("CA", "CA-QC"),
    "calgary": ("CA", "CA-AB"), "edmonton": ("CA", "CA-AB"),
    "winnipeg": ("CA", "CA-MB"), "halifax": ("CA", "CA-NS"),
    # UK Cities
    "london": ("UK", "UK"), "manchester": ("UK", "UK"), "birmingham": ("UK", "UK"),
    "leeds": ("UK", "UK"), "glasgow": ("UK", "UK"), "edinburgh": ("UK", "UK"),
    # European Cities
    "paris": ("FR", "FR"), "lyon": ("FR", "FR"), "marseille": ("FR", "FR"),
    "berlin": ("DE", "DE"), "munich": ("DE", "DE"), "frankfurt": ("DE", "DE"),
    "hamburg": ("DE", "DE"), "cologne": ("DE", "DE"),
    "milan": ("IT", "IT"), "rome": ("IT", "IT"), "florence": ("IT", "IT"),
    "amsterdam": ("NL", "NL"), "rotterdam": ("NL", "NL"),
    "geneva": ("CH", "CH"), "zurich": ("CH", "CH"), "basel": ("CH", "CH"),
    "lugano": ("CH", "CH"), "bern": ("CH", "CH"),
    # Middle East / Asia
    "dubai": ("AE", "AE"), "abu dhabi": ("AE", "AE"),
    "singapore": ("SG", "SG"),
    "hong kong": ("HK", "HK"),
    "tokyo": ("JP", "JP"), "osaka": ("JP", "JP"),
    # Australia
    "sydney": ("AU", "AU"), "melbourne": ("AU", "AU"), "brisbane": ("AU", "AU"),
    "perth": ("AU", "AU"),
}


def resolve_geography(target: str, country: str = None, state: str = None,
                       city: str = None) -> dict:
    """
    Resolve geographic context from all available signals.
    Returns: {"country": "US", "region": "US-FL", "city": "Miami", "countries": ["US"]}
    """
    detected_country = None
    detected_region = None
    detected_countries = set()

    # 1. Explicit country
    if country:
        c = country.upper().strip()
        # Normalize common aliases
        aliases = {"USA": "US", "GB": "UK", "BRITAIN": "UK", "SWISS": "CH",
                   "DEUTSCHLAND": "DE", "ITALIA": "IT", "HONGKONG": "HK"}
        c = aliases.get(c, c)
        if c in COUNTRY_KEYWORDS or len(c) == 2:
            detected_country = c
            detected_countries.add(c)

    # 2. Explicit state/province
    if state:
        s = state.upper().strip()
        if s in STATE_MAP:
            c, r = STATE_MAP[s]
            detected_country = detected_country or c
            detected_region = r
            detected_countries.add(c)

    # 3. City lookup
    if city:
        city_lower = city.lower().strip()
        if city_lower in CITY_MAP:
            c, r = CITY_MAP[city_lower]
            detected_country = detected_country or c
            detected_region = detected_region or r
            detected_countries.add(c)

    # 4. Target name keyword scan
    target_lower = target.lower()
    for c_code, keywords in COUNTRY_KEYWORDS.items():
        for kw in keywords:
            if kw in target_lower:
                detected_countries.add(c_code)
                if not detected_country:
                    detected_country = c_code
                break

    # City keywords in target
    for city_name, (c_code, region) in CITY_MAP.items():
        if city_name in target_lower:
            detected_countries.add(c_code)
            if not detected_country:
                detected_country = c_code
                detected_region = region

    # Default to US if nothing detected
    if not detected_country:
        detected_country = "US"
        detected_countries.add("US")

    return {
        "country": detected_country,
        "region": detected_region,
        "city": city,
        "countries": sorted(detected_countries),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# INDUSTRY DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

INDUSTRY_KEYWORDS = {
    "watches": [
        "watch", "watches", "chrono", "rolex", "patek", "audemars", "piguet",
        "omega", "cartier", "breitling", "iwc", "tudor", "dealer", "horology",
        "timepiece", "timepieces", "horloger", "wristwatch", "chronograph",
        "watchmaker", "jeweler", "jeweller", "horological",
    ],
    "jewelry": [
        "jewel", "jewelry", "jewellery", "diamond", "gemstone", "gold",
        "silver", "platinum", "ring", "necklace", "bracelet", "gemologist",
    ],
    "restaurant": [
        "restaurant", "cafe", "café", "kitchen", "grill", "bistro", "diner",
        "food", "catering", "pizzeria", "sushi", "bakery", "bar", "pub",
        "tavern", "trattoria", "brasserie", "eatery", "gastropub",
    ],
    "finance": [
        "capital", "fund", "invest", "advisory", "wealth", "securities",
        "asset management", "hedge", "trading", "broker", "brokerage",
        "financial", "banking", "venture", "private equity", "portfolio",
    ],
    "crypto": [
        "crypto", "blockchain", "token", "defi", "exchange", "web3",
        "bitcoin", "ethereum", "nft", "dao", "mining", "staking",
    ],
    "real_estate": [
        "realty", "property", "properties", "real estate", "development",
        "construction", "homes", "apartments", "condo", "builder",
        "contractor", "renovation", "architecture", "housing",
    ],
    "healthcare": [
        "medical", "health", "clinic", "hospital", "pharma", "dental",
        "doctor", "physician", "surgeon", "therapy", "wellness",
        "pharmaceutical", "biotech", "diagnostics",
    ],
    "legal": [
        "law", "legal", "attorney", "counsel", "solicitor", "barrister",
        "advocate", "litigation", "arbitration", "notary", "paralegal",
    ],
    "tech": [
        "tech", "software", "digital", "app", "platform", "saas", "ai",
        "cloud", "data", "cyber", "startup", "io", "labs", "systems",
    ],
    "construction": [
        "construction", "contractor", "building", "plumbing", "electrical",
        "roofing", "hvac", "masonry", "demolition", "excavation",
        "engineering", "civil", "general contractor",
    ],
    "retail": [
        "store", "shop", "retail", "boutique", "outlet", "ecommerce",
        "marketplace", "wholesale", "distributor", "supply",
    ],
    "hospitality": [
        "hotel", "motel", "resort", "inn", "lodge", "hospitality",
        "tourism", "travel", "airbnb", "vacation", "rental",
    ],
    "automotive": [
        "auto", "car", "vehicle", "dealer", "dealership", "motor",
        "automotive", "garage", "mechanic", "parts", "tire",
    ],
    "luxury": [
        "luxury", "haute", "couture", "maison", "atelier", "bespoke",
        "premium", "exclusive", "prestige", "high-end",
    ],
}

# Entity type suffixes that override industry detection
ENTITY_TYPE_SUFFIXES = {
    "llc": "company", "inc": "company", "corp": "company", "ltd": "company",
    "gmbh": "company", "ag": "company", "sa": "company", "srl": "company",
    "bv": "company", "nv": "company", "plc": "company", "pty": "company",
    "sarl": "company", "sas": "company", "spa": "company",
}


def detect_industry(target: str, url: str = None, notes: str = None,
                     explicit: str = None) -> list:
    """
    Auto-detect industry from target name, URL, and notes.
    Returns list of detected industries, e.g. ["watches", "luxury"]
    """
    if explicit:
        explicit_lower = explicit.lower().strip()
        # Map common inputs
        mapping = {
            "watch": "watches", "jewelry": "jewelry", "jewellery": "jewelry",
            "restaurant": "restaurant", "food": "restaurant",
            "finance": "finance", "investment": "finance", "banking": "finance",
            "crypto": "crypto", "blockchain": "crypto",
            "real estate": "real_estate", "realestate": "real_estate",
            "property": "real_estate",
            "healthcare": "healthcare", "medical": "healthcare",
            "law": "legal", "legal": "legal",
            "tech": "tech", "software": "tech", "saas": "tech",
            "construction": "construction", "contractor": "construction",
            "luxury": "luxury",
        }
        if explicit_lower in mapping:
            return [mapping[explicit_lower]]
        # Check if it's a direct key
        if explicit_lower in INDUSTRY_KEYWORDS:
            return [explicit_lower]
        return [explicit_lower]

    # Scan target name
    text = target.lower()
    if url:
        text += " " + url.lower()
    if notes:
        text += " " + notes.lower()

    matches = []
    for industry, keywords in INDUSTRY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            matches.append((industry, score))

    # Sort by score descending
    matches.sort(key=lambda x: -x[1])

    if matches:
        # Return top matches (max 3)
        return [m[0] for m in matches[:3]]

    return ["general"]


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE REGISTRY — Which modules exist and when they should fire
# ═══════════════════════════════════════════════════════════════════════════════

MODULE_REGISTRY = {
    # ── ALWAYS FIRE (regardless of context) ────────────────────────────────
    "ofac_check": {
        "always": True,
        "types": ["company", "person", "organization"],
        "label": "OFAC Sanctions",
    },
    "eu_un_sanctions": {
        "always": True,
        "types": ["company", "person", "organization"],
        "label": "EU/UN Sanctions",
    },
    "icij_offshore": {
        "always": True,
        "types": ["company", "person", "organization"],
        "label": "ICIJ Offshore Leaks",
    },
    "interpol_check": {
        "always": True,
        "types": ["person"],
        "label": "Interpol Red Notices",
    },
    "opencorporates": {
        "always": True,
        "types": ["company", "organization"],
        "label": "OpenCorporates Global",
    },
    "news_archive": {
        "always": True,
        "types": ["company", "person", "organization"],
        "label": "News Archive",
    },
    "google_business": {
        "always": True,
        "types": ["company", "organization"],
        "label": "Google Business Intel",
    },
    "linkedin_intel": {
        "always": True,
        "types": ["person"],
        "label": "LinkedIn Intel",
    },
    "forum_reputation": {
        "always": True,
        "types": ["company", "person"],
        "label": "Forum & Review Reputation",
    },
    "related_entities": {
        "always": True,
        "types": ["company", "person"],
        "label": "Related Entities",
    },

    # ── CORPORATE REGISTRIES (geo-scoped) ──────────────────────────────────
    "sunbiz_fl": {
        "geo": ["US-FL"],
        "types": ["company"],
        "label": "Florida Sunbiz",
    },
    "us_national_registry": {
        "geo_country": ["US"],
        "types": ["company"],
        "label": "US National Business Registry",
    },
    "companies_house_uk": {
        "geo_country": ["UK"],
        "types": ["company"],
        "label": "UK Companies House",
    },
    "zefix_ch": {
        "geo_country": ["CH"],
        "types": ["company"],
        "label": "Swiss Zefix Registry",
    },
    "pappers_fr": {
        "geo_country": ["FR"],
        "types": ["company"],
        "label": "France PAPPERS Registry",
    },
    "global_registries": {
        "geo_country_exclude": ["US", "UK", "CH", "FR"],
        "types": ["company"],
        "label": "Global Registry Search",
        "note": "Fires for non-US/UK/CH/FR countries",
    },

    # ── COURT & LEGAL (geo-scoped) ─────────────────────────────────────────
    "federal_courts": {
        "geo_country": ["US"],
        "types": ["company", "person"],
        "label": "US Federal Courts (CourtListener)",
    },
    "bankruptcy_search": {
        "geo_country": ["US"],
        "types": ["company", "person"],
        "label": "US Bankruptcy Records",
    },
    "state_courts": {
        "geo_country": ["US"],
        "types": ["company", "person"],
        "label": "US State Court Records",
    },
    "federal_enforcement": {
        "geo_country": ["US"],
        "types": ["company", "person"],
        "label": "DOJ/FBI/FTC/SEC Enforcement",
    },
    "sec_edgar": {
        "geo_country": ["US"],
        "types": ["company"],
        "label": "SEC EDGAR Filings",
        "industry": ["finance", "crypto", "tech"],
        "industry_fallback": True,  # still fires if no industry match but depth=deep
    },

    # ── FINANCIAL (geo + industry scoped) ──────────────────────────────────
    "finra_brokercheck": {
        "geo_country": ["US"],
        "types": ["company", "person"],
        "industry": ["finance", "crypto"],
        "label": "FINRA BrokerCheck",
    },
    "fec_donations": {
        "geo_country": ["US"],
        "types": ["person"],
        "label": "FEC Political Donations",
        "depth_min": "standard",
    },
    "ppp_loans": {
        "geo_country": ["US"],
        "types": ["company"],
        "label": "PPP Loan Database",
        "depth_min": "standard",
    },
    "usaspending": {
        "geo_country": ["US"],
        "types": ["company"],
        "label": "USA Spending / Govt Contracts",
        "depth_min": "deep",
    },
    "cfpb_complaints": {
        "geo_country": ["US"],
        "types": ["company"],
        "industry": ["finance", "crypto"],
        "label": "CFPB Consumer Complaints",
    },

    # ── WATCH / LUXURY INDUSTRY ────────────────────────────────────────────
    "chrono24_seller": {
        "industry": ["watches", "jewelry", "luxury"],
        "types": ["company", "person"],
        "label": "Chrono24 Dealer Profile",
    },
    "watch_platforms": {
        "industry": ["watches", "jewelry", "luxury"],
        "types": ["company", "person"],
        "label": "Watch Platform Presence",
    },
    "ebay_seller": {
        "industry": ["watches", "jewelry", "luxury", "retail"],
        "types": ["company", "person"],
        "label": "eBay Seller Profile",
    },
    "ebay_sold_listings": {
        "industry": ["watches", "jewelry", "luxury", "retail"],
        "types": ["company", "person"],
        "label": "eBay Sold History",
    },

    # ── PROFESSIONAL LICENSES (industry scoped) ───────────────────────────
    "contractor_license": {
        "industry": ["construction", "real_estate"],
        "types": ["company", "person"],
        "label": "Contractor License Check",
    },
    "medical_board": {
        "industry": ["healthcare"],
        "types": ["person"],
        "label": "Medical Board / License",
    },
    "professional_licenses": {
        "types": ["company", "person"],
        "depth_min": "standard",
        "label": "Professional License Check",
    },

    # ── DOMAIN / WEB (requires URL) ────────────────────────────────────────
    "domain_intel": {
        "requires": ["url"],
        "types": ["company", "person"],
        "label": "Domain WHOIS + RDAP + SSL",
    },
    "theharvester": {
        "requires": ["url"],
        "types": ["company"],
        "label": "theHarvester (emails, subdomains)",
    },
    "whatweb_scan": {
        "requires": ["url"],
        "types": ["company"],
        "label": "WhatWeb Tech Stack",
        "depth_min": "standard",
    },
    "nmap_scan": {
        "requires": ["url"],
        "types": ["company"],
        "label": "Nmap Port Scan",
        "depth_min": "deep",
    },
    "wayback_history": {
        "requires": ["url"],
        "types": ["company"],
        "label": "Wayback Machine History",
    },

    # ── EMAIL INTEL (requires email) ───────────────────────────────────────
    "holehe_check": {
        "requires": ["email"],
        "types": ["person"],
        "label": "Holehe Platform Registrations",
    },
    "h8mail_breach": {
        "requires": ["email"],
        "types": ["person"],
        "label": "h8mail Breach Check",
    },
    "ghunt_google": {
        "requires": ["email"],
        "types": ["person"],
        "label": "GHunt Google Account",
        "depth_min": "deep",
    },
    "email_discovery": {
        "types": ["company", "person"],
        "label": "Email Discovery",
        "depth_min": "standard",
    },

    # ── PHONE INTEL (requires phone) ───────────────────────────────────────
    "phone_deep": {
        "requires": ["phone"],
        "types": ["person"],
        "label": "Phone Intelligence (PhoneInfoga)",
    },
    "phone_reverse": {
        "requires": ["phone"],
        "types": ["person"],
        "label": "Phone Reverse Lookup",
    },

    # ── SOCIAL / USERNAME (requires handle) ────────────────────────────────
    "username_osint": {
        "requires_any": ["handle", "instagram", "twitter"],
        "types": ["person"],
        "label": "Username OSINT (Maigret)",
    },
    "instaloader_profile": {
        "requires_any": ["handle", "instagram"],
        "types": ["person"],
        "label": "Instagram Deep Profile",
    },
    "instagram_intel": {
        "types": ["person", "company"],
        "label": "Instagram Search",
    },

    # ── GENERAL INTEL ──────────────────────────────────────────────────────
    "property_records": {
        "geo_country": ["US"],
        "types": ["person"],
        "label": "Property Records",
        "depth_min": "standard",
    },
    "data_breach": {
        "types": ["company", "person"],
        "label": "Data Breach Check",
        "depth_min": "standard",
    },
    "breach_directory": {
        "requires_any": ["email", "url"],
        "types": ["person", "company"],
        "label": "Breach Directory Check",
        "depth_min": "deep",
    },
    "voter_registration": {
        "geo_country": ["US"],
        "types": ["person"],
        "label": "Voter Registration",
        "depth_min": "deep",
    },
    "bbb_lookup": {
        "geo_country": ["US", "CA"],
        "types": ["company"],
        "label": "BBB Profile",
    },
    "ripoffreport": {
        "types": ["company"],
        "label": "Ripoff Report",
    },
    "uspto_trademark": {
        "geo_country": ["US"],
        "types": ["company"],
        "label": "USPTO Trademark",
        "depth_min": "standard",
    },
    "employer_reviews": {
        "types": ["company"],
        "label": "Glassdoor/Indeed Reviews",
        "depth_min": "deep",
    },
    "crunchbase_intel": {
        "types": ["company"],
        "industry": ["tech", "finance", "crypto"],
        "label": "Crunchbase / Startup Intel",
        "depth_min": "deep",
    },

    # ── RESTAURANT / HOSPITALITY SPECIFIC ──────────────────────────────────
    "health_inspection": {
        "industry": ["restaurant", "hospitality"],
        "types": ["company"],
        "label": "Health Inspection Records",
    },
    "liquor_license": {
        "industry": ["restaurant", "hospitality"],
        "types": ["company"],
        "label": "Liquor License Check",
    },
    "yelp_opentable": {
        "industry": ["restaurant", "hospitality"],
        "types": ["company"],
        "label": "Yelp / OpenTable Reviews",
    },
}

# Depth ranking for comparison
DEPTH_RANK = {"quick": 0, "standard": 1, "deep": 2}


def select_modules(target_type: str, industry: list, geo: dict,
                    context: dict = None, depth: str = "standard") -> tuple:
    """
    Select which modules to fire based on target context.
    
    Args:
        target_type: "company", "person", "organization", "watch"
        industry: list of detected industries, e.g. ["watches", "luxury"]
        geo: output from resolve_geography()
        context: dict of available identifiers {"url": "...", "email": "...", etc}
        depth: "quick", "standard", "deep"
    
    Returns:
        (selected_modules: list[str], skipped: list[tuple[str, str]])
    """
    ctx = context or {}
    country = geo.get("country", "US")
    region = geo.get("region")
    countries = geo.get("countries", ["US"])
    depth_level = DEPTH_RANK.get(depth, 1)

    selected = []
    skipped = []

    for module_id, rules in MODULE_REGISTRY.items():
        skip_reason = None

        # --- Type check ---
        if "types" in rules and target_type not in rules["types"]:
            # Watch type maps to company for module purposes
            effective_type = "company" if target_type == "watch" else target_type
            if effective_type not in rules["types"]:
                skip_reason = f"type mismatch ({target_type} not in {rules['types']})"
                skipped.append((module_id, skip_reason))
                continue

        # --- Always-fire modules ---
        if rules.get("always"):
            selected.append(module_id)
            continue

        # --- Depth check ---
        if "depth_min" in rules:
            min_depth = DEPTH_RANK.get(rules["depth_min"], 0)
            if depth_level < min_depth:
                skip_reason = f"depth {depth} < required {rules['depth_min']}"
                skipped.append((module_id, skip_reason))
                continue

        # --- Geographic check ---
        # Check specific region (e.g. US-FL)
        if "geo" in rules:
            if region not in rules["geo"]:
                skip_reason = f"geo mismatch ({region} not in {rules['geo']})"
                skipped.append((module_id, skip_reason))
                continue

        # Check country level
        if "geo_country" in rules:
            if not any(c in rules["geo_country"] for c in countries):
                skip_reason = f"country mismatch ({countries} vs {rules['geo_country']})"
                skipped.append((module_id, skip_reason))
                continue

        # Check country exclusion (for "everything except US/UK/CH/FR")
        if "geo_country_exclude" in rules:
            non_excluded = [c for c in countries if c not in rules["geo_country_exclude"]]
            if not non_excluded:
                skip_reason = f"all countries excluded ({countries})"
                skipped.append((module_id, skip_reason))
                continue

        # --- Industry check ---
        if "industry" in rules:
            if not any(ind in rules["industry"] for ind in industry):
                # Check if industry_fallback allows it in deep mode
                if rules.get("industry_fallback") and depth == "deep":
                    pass  # Allow through
                else:
                    skip_reason = f"industry mismatch ({industry} vs {rules['industry']})"
                    skipped.append((module_id, skip_reason))
                    continue

        # --- Required context check ---
        if "requires" in rules:
            missing = [f for f in rules["requires"] if not ctx.get(f)]
            if missing:
                skip_reason = f"missing required: {missing}"
                skipped.append((module_id, skip_reason))
                continue

        if "requires_any" in rules:
            if not any(ctx.get(f) for f in rules["requires_any"]):
                skip_reason = f"missing all of: {rules['requires_any']}"
                skipped.append((module_id, skip_reason))
                continue

        # Passed all checks — include this module
        selected.append(module_id)

    return selected, skipped


def format_routing_summary(selected: list, skipped: list, geo: dict,
                            industry: list, depth: str) -> str:
    """Human-readable routing summary for reports and logging."""
    lines = [
        f"🎯 Routing: {len(selected)} modules selected, {len(skipped)} skipped",
        f"   Country: {geo.get('country', '?')} | Region: {geo.get('region', 'N/A')} | Industry: {', '.join(industry)}",
        f"   Depth: {depth}",
        "",
        "Selected modules:",
    ]
    for m in selected:
        label = MODULE_REGISTRY.get(m, {}).get("label", m)
        lines.append(f"  ✅ {label}")

    if skipped:
        lines.append("")
        lines.append("Skipped (with reason):")
        for module_id, reason in skipped[:15]:  # Cap at 15 to keep it readable
            label = MODULE_REGISTRY.get(module_id, {}).get("label", module_id)
            lines.append(f"  ⏭️  {label} — {reason}")
        if len(skipped) > 15:
            lines.append(f"  ... and {len(skipped) - 15} more")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# QUICK TEST
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Test 1: Watch dealer in Miami
    print("=" * 60)
    print("TEST 1: Watch dealer in Miami, FL")
    geo1 = resolve_geography("Acme Watches LLC", state="FL", city="Miami")
    ind1 = detect_industry("Acme Watches LLC", notes="watch dealer")
    sel1, skip1 = select_modules("company", ind1, geo1, {"url": "https://rccrown.com"}, "deep")
    print(format_routing_summary(sel1, skip1, geo1, ind1, "deep"))

    print("\n" + "=" * 60)
    print("TEST 2: Restaurant in Vancouver, BC")
    geo2 = resolve_geography("Pasta Palace", country="CA", state="BC", city="Vancouver")
    ind2 = detect_industry("Pasta Palace Restaurant")
    sel2, skip2 = select_modules("company", ind2, geo2, {}, "standard")
    print(format_routing_summary(sel2, skip2, geo2, ind2, "standard"))

    print("\n" + "=" * 60)
    print("TEST 3: Law firm in London, UK")
    geo3 = resolve_geography("Smith & Associates LLP", country="UK", city="London")
    ind3 = detect_industry("Smith & Associates LLP")
    sel3, skip3 = select_modules("company", ind3, geo3, {"url": "https://smithlaw.co.uk"}, "standard")
    print(format_routing_summary(sel3, skip3, geo3, ind3, "standard"))

    print("\n" + "=" * 60)
    print("TEST 4: Person with minimal context")
    geo4 = resolve_geography("John Smith")
    ind4 = detect_industry("John Smith")
    sel4, skip4 = select_modules("person", ind4, geo4, {}, "quick")
    print(format_routing_summary(sel4, skip4, geo4, ind4, "quick"))
