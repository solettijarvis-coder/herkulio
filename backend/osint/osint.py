#!/usr/bin/env python3
"""
OSINT Engine — Jarvis v7
Usage: python3 osint.py "Isaac Mayer" --url https://www.isaacmayerfj.com/ [--type company|person|watch] [--state FL]
Cost: ~$0.05-0.06/report (Serper + Gemini Flash)
New in v7: SQLite caching, FINRA, USPTO, BBB, Ripoff Report, EU/UN Sanctions, Confidence Scoring
"""

import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser

# ── Config ─────────────────────────────────────────────────────────────────────
# Load from .env if available, fall back to hardcoded (legacy)
try:
    from dotenv import load_dotenv as _ldenv
    _ldenv(os.path.join(os.path.dirname(__file__), '.env'))
except ImportError:
    pass
TAVILY_KEY     = os.environ.get("TAVILY_API_KEY", "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")
SERPER_KEY     = os.environ.get("SERPER_API_KEY", "6d763846acdb8e4351709eef9635c20c59923f40")
OPENROUTER_KEY = None  # loaded from auth-profiles.json at runtime
SYNTH_MODEL    = "google/gemini-2.5-flash"
OUTPUT_DIR     = os.path.join(os.path.dirname(__file__), "reports")
CACHE_DB       = os.path.join(os.path.dirname(__file__), "reports_cache.db")
CACHE_TTL_DAYS = 7
SERPER_CREDITS_USED = 0   # tracked per run

# ── State Registry URLs ─────────────────────────────────────────────────────────
STATE_REGISTRY = {
    "FL": "https://search.sunbiz.org/Inquiry/CorporationSearch/SearchResults?inquiryType=EntityName&searchTerm={encoded}",
    "CA": "https://bizfileonline.sos.ca.gov/search/business",
    "NY": "https://apps.dos.ny.gov/publicInquiry/",
    "TX": "https://direct.sos.state.tx.us/corp_inquiry/corp_inquiry-entity.asp",
    "DE": "https://icis.corp.delaware.gov/ecorp/entitysearch/namesearch.aspx",
    "WY": "https://wyobiz.wyo.gov/Business/FilingSearch.aspx",
    "NV": "https://esos.nv.gov/EntitySearch/OnlineEntitySearch",
}

# ── Query Templates ─────────────────────────────────────────────────────────────
# ── Dynamic Query Builder ────────────────────────────────────────────────────────
def build_queries(target: str, target_type: str, context: dict = None) -> list:
    """
    Build laser-targeted search queries using all available intake context.
    Context fields: email, phone, url, country, state, city, address, dob,
    aliases, company_number, industry, linkedin, instagram, twitter, ebay,
    relationship, notes, concerns, industry
    """
    ctx = context or {}
    queries = []
    loc = ""
    if ctx.get("city"):     loc += f" {ctx['city']}"
    if ctx.get("state"):    loc += f" {ctx['state']}"
    if ctx.get("country"):  loc += f" {ctx['country']}"
    loc = loc.strip()
    loc_q = f" {loc}" if loc else ""

    if target_type == "company":
        # Country-specific registry terms
        country = (ctx.get("country") or "").upper()
        reg_term = {
            "CA": "corporation incorporated Ontario Alberta BC Canada",
            "UK": "Ltd PLC company registered England Wales",
            "AU": "Pty Ltd ACN ABN ASIC Australia",
            "HK": "Limited company registered Hong Kong CR",
            "SG": "Pte Ltd UEN ACRA Singapore",
            "DE": "GmbH AG Handelsregister Germany",
            "FR": "SARL SAS SIREN SIRET France",
            "CH": "AG GmbH SA Zefix Switzerland",
            "IT": "SRL SPA codice fiscale Italy",
            "NL": "BV NV KVK Netherlands",
            "AE": "LLC FZE FZC trade license Dubai UAE",
            "JP": "KK kabushiki gaisha Japan",
        }.get(country, "LLC corporation business registration")

        queries += [
            f'"{target}" company overview history{loc_q}',
            f'"{target}" owner founder CEO director president{loc_q}',
            f'"{target}" {reg_term}{loc_q}',
            f'site:opencorporates.com "{target}"',
            f'"{target}" reviews complaints Trustpilot Google{loc_q}',
            f'"{target}" fraud scam lawsuit legal action{loc_q}',
            f'"{target}" Instagram LinkedIn Facebook social media',
            f'"{target}" address phone contact{loc_q}',
            f'"{target}" revenue employees annual report clients',
            f'"{target}" lien judgment debt default{loc_q}',
            f'"{target}" news press 2024 2025 2026',
            f'"{target}" license certificate standing{loc_q}',
        ]
        # Country-specific court/legal searches
        if country == "CA":
            queries += [
                f'"{target}" canada lawsuit court ontario superior',
                f'"{target}" canada revenue agency CRA tax',
                f'"{target}" better business bureau canada complaint',
            ]
        elif country == "UK":
            queries += [
                f'"{target}" uk court claim county court judgment CCJ',
                f'"{target}" companies house dissolved struck off',
                f'"{target}" HMRC tax UK',
            ]
        elif country == "AU":
            queries += [
                f'"{target}" australia ASIC action court federal',
                f'"{target}" ACCC fair trading australia complaint',
            ]
        elif country in ("HK","SG","AE","JP"):
            queries += [
                f'"{target}" {country} court arbitration commercial dispute',
                f'"{target}" {country} regulatory action fine penalty',
            ]

        # Industry-specific queries
        industry = (ctx.get("industry") or "").lower()
        if industry in ("finance", "crypto", "investment", "fund"):
            queries += [
                f'"{target}" SEC enforcement FINRA fine suspended',
                f'"{target}" hedge fund investor accredited securities',
                f'"{target}" crypto exchange token ICO rug pull',
            ]
        elif industry in ("real estate", "realestate", "property"):
            queries += [
                f'"{target}" real estate developer property foreclosure',
                f'"{target}" HOA complaints tenant landlord lawsuit',
            ]
        elif industry in ("luxury", "watches", "jewelry", "art"):
            queries += [
                f'"{target}" authentication counterfeit fake replica',
                f'"{target}" chrono24 dealer ebay seller watches',
            ]
        elif industry in ("healthcare", "medical", "pharma"):
            queries += [
                f'"{target}" FDA warning letter recall violation',
                f'"{target}" medical license board disciplinary',
            ]
        # Email-seeded queries
        if ctx.get("email"):
            domain = ctx["email"].split("@")[-1] if "@" in ctx["email"] else ""
            if domain:
                queries.append(f'site:{domain} OR "{domain}" company owner')
                queries.append(f'"{ctx["email"]}" contact registered')
        # Phone-seeded
        if ctx.get("phone"):
            queries.append(f'"{ctx["phone"]}" business contact owner')
        # Address-seeded
        if ctx.get("address"):
            queries.append(f'"{ctx["address"]}" business registered office')
        # Company number
        if ctx.get("company_number"):
            queries.append(f'"{ctx["company_number"]}" company registration')
        # Concerns
        if ctx.get("concerns"):
            queries.append(f'"{target}" {ctx["concerns"]}')

    elif target_type == "person":
        queries += [
            f'"{target}" professional background career{loc_q}',
            f'"{target}" business owner company director{loc_q}',
            f'"{target}" arrested charged indicted criminal court',
            f'"{target}" lawsuit sued plaintiff defendant civil{loc_q}',
            f'"{target}" fraud scheme scam financial crime',
            f'"{target}" LinkedIn profile employer',
            f'"{target}" Instagram social media',
            f'"{target}" address property real estate{loc_q}',
            f'"{target}" bankruptcy chapter 7 11 foreclosure',
            f'"{target}" tax lien IRS judgment debt',
            f'"{target}" news article press 2024 2025 2026',
            f'"{target}" sex offender registry',
            f'"{target}" license revoked suspended professional',
            f'"{target}" net worth wealth assets',
            f'site:opencorporates.com "{target}"',
            f'"{target}" divorce court filing asset division',
        ]
        # DOB-enhanced identity
        if ctx.get("dob"):
            queries.append(f'"{target}" born {ctx["dob"]} background')
        # Aliases
        for alias in (ctx.get("aliases") or [])[:2]:
            queries.append(f'"{alias}" background criminal lawsuit')
            queries.append(f'"{alias}" OR "{target}" fraud scam')
        # Known company
        if ctx.get("company"):
            queries.append(f'"{target}" "{ctx["company"]}" director officer role')
            queries.append(f'"{target}" "{ctx["company"]}" lawsuit complaint')
        # Email-seeded
        if ctx.get("email"):
            queries.append(f'"{ctx["email"]}" owner registered accounts')
        # Phone-seeded
        if ctx.get("phone"):
            queries.append(f'"{ctx["phone"]}" owner name person')
        # Concerns
        if ctx.get("concerns"):
            queries.append(f'"{target}" {ctx["concerns"]}')

    elif target_type in ("organization", "ngo", "government"):
        queries += [
            f'"{target}" organization overview mission',
            f'"{target}" leadership board directors officers',
            f'"{target}" funding donors financials 990',
            f'"{target}" controversy scandal investigation',
            f'"{target}" IRS 501c3 tax exempt registration',
            f'"{target}" lawsuit complaint regulatory action',
            f'"{target}" news 2024 2025 2026',
        ]

    else:  # generic fallback
        queries += [
            f'"{target}" overview background',
            f'"{target}" owner director officer',
            f'"{target}" fraud scam complaint lawsuit',
            f'"{target}" news 2024 2025 2026',
            f'site:opencorporates.com "{target}"',
        ]

    # Deduplicate
    seen = set()
    unique = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            unique.append(q)
    return unique


# Legacy template dict — kept for backward compatibility
QUERY_TEMPLATES = {
    "company": ['"{target}" company overview', '"{target}" owner founder',
                '"{target}" fraud lawsuit court', '"{target}" news 2024 2025'],
    "person":  ['"{target}" background', '"{target}" arrested criminal',
                '"{target}" lawsuit', '"{target}" fraud'],
    "watch":   ['{target} watch price 2026', '{target} chrono24 price',
                '{target} watch sold auction'],
}

# ── Sunbiz Direct Lookup (Florida) ──────────────────────────────────────────────
class SunbizParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_table = False
        self.data = []
        self.current = []

    def handle_starttag(self, tag, attrs):
        if tag in ("table", "tr", "td", "th"):
            if tag == "table":
                self.in_table = True
            if tag in ("td", "th"):
                self.current = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.current:
            self.data.append(" ".join(self.current).strip())
            self.current = []

    def handle_data(self, data):
        if self.in_table:
            stripped = data.strip()
            if stripped:
                self.current.append(stripped)


def sunbiz_lookup(company_name: str) -> dict:
    """Directly query Florida Sunbiz for corporate records."""
    encoded = urllib.parse.quote(company_name)
    url = f"https://search.sunbiz.org/Inquiry/CorporationSearch/SearchResults?inquiryType=EntityName&searchTerm={encoded}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=15)
        html = resp.read().decode("utf-8", errors="ignore")

        # Extract entity links and names
        matches = re.findall(
            r'SearchResultDetail[^"]*aggregateId=([^&"]+)[^"]*">([^<]+)</a',
            html
        )
        results = []
        for agg_id, name in matches[:5]:
            results.append({"name": name.strip(), "aggregate_id": agg_id})

        # Try to get detail for first match
        detail = {}
        detail_match = re.search(
            r'href="(/Inquiry/CorporationSearch/SearchResultDetail[^"]+)"',
            html
        )
        if detail_match:
            detail_url = "https://search.sunbiz.org" + detail_match.group(1).replace("&amp;", "&")
            try:
                req2 = urllib.request.Request(detail_url, headers={"User-Agent": "Mozilla/5.0"})
                resp2 = urllib.request.urlopen(req2, timeout=15)
                detail_html = resp2.read().decode("utf-8", errors="ignore")

                # Parse key fields
                fields = {
                    "document_number": r"Document Number\s*</label>\s*<span[^>]*>([^<]+)",
                    "fei_ein": r"FEI/EIN Number\s*</label>\s*<span[^>]*>([^<]+)",
                    "date_filed": r"Date Filed\s*</label>\s*<span[^>]*>([^<]+)",
                    "status": r"Status\s*</label>\s*<span[^>]*>([^<]+)",
                    "principal_address": r"Principal Address\s*</p>\s*([\s\S]*?)</p>",
                    "registered_agent": r"Registered Agent Name & Address\s*</p>\s*<p[^>]*>([\s\S]*?)</p>",
                }
                for field, pattern in fields.items():
                    m = re.search(pattern, detail_html, re.IGNORECASE)
                    if m:
                        val = re.sub(r"<[^>]+>", " ", m.group(1)).strip()
                        val = re.sub(r"\s+", " ", val)
                        detail[field] = val

                # Extract authorized persons / managers
                officers = re.findall(
                    r"Title\s*(MGR|VP|CEO|CFO|PA|PRES|DIR|MGRM|MGR-M)[^<]*</span>\s*<br/>\s*<span[^>]*>([^<]+)",
                    detail_html, re.IGNORECASE
                )
                if officers:
                    detail["officers"] = [{"title": t, "name": n.strip()} for t, n in officers]

                detail["source_url"] = detail_url
            except Exception as e:
                detail["detail_error"] = str(e)

        return {
            "source": "sunbiz.org",
            "search_results": results,
            "detail": detail,
        }
    except Exception as e:
        return {"source": "sunbiz.org", "error": str(e)}


def opencorporates_lookup(company_name: str, state: str = None) -> dict:
    """Query OpenCorporates for corporate records across all jurisdictions."""
    encoded = urllib.parse.quote(company_name)
    url = f"https://api.opencorporates.com/v0.4/companies/search?q={encoded}&per_page=5"
    if state:
        # Map state abbrev to jurisdiction
        state_map = {"FL": "us_fl", "CA": "us_ca", "NY": "us_ny", "TX": "us_tx",
                     "DE": "us_de", "WY": "us_wy", "NV": "us_nv"}
        jur = state_map.get(state.upper())
        if jur:
            url += f"&jurisdiction_code={jur}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        companies = data.get("results", {}).get("companies", [])
        results = []
        for c in companies[:5]:
            co = c.get("company", {})
            results.append({
                "name": co.get("name"),
                "number": co.get("company_number"),
                "jurisdiction": co.get("jurisdiction_code"),
                "status": co.get("current_status"),
                "incorporation_date": co.get("incorporation_date"),
                "registered_address": co.get("registered_address_in_full"),
                "company_type": co.get("company_type"),
                "opencorporates_url": co.get("opencorporates_url"),
            })
        return {"source": "opencorporates.com", "results": results}
    except Exception as e:
        return {"source": "opencorporates.com", "error": str(e)}


# ── Serper Search (primary — $0.001/query) ──────────────────────────────────────
def serper_search(query: str, max_results: int = 5) -> list:
    global SERPER_CREDITS_USED
    payload = json.dumps({"q": query, "num": max_results}).encode()
    req = urllib.request.Request(
        "https://google.serper.dev/search",
        data=payload,
        headers={
            "X-API-KEY": SERPER_KEY,
            "Content-Type": "application/json",
        },
    )
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        SERPER_CREDITS_USED += data.get("credits", 1)
        results = []
        for r in data.get("organic", [])[:max_results]:
            results.append({
                "title": r.get("title", ""),
                "url": r.get("link", ""),
                "content": r.get("snippet", ""),
            })
        # also pull knowledge graph if present
        kg = data.get("knowledgeGraph", {})
        if kg.get("description"):
            results.insert(0, {
                "title": f"[KG] {kg.get('title', '')} — {kg.get('type', '')}",
                "url": kg.get("website", ""),
                "content": kg.get("description", "")[:500],
            })
        return results
    except Exception as e:
        # Fallback to Tavily if Serper fails
        return tavily_search_fallback(query, max_results)


def tavily_search_fallback(query: str, max_results: int = 5) -> list:
    payload = json.dumps({
        "api_key": TAVILY_KEY,
        "query": query,
        "search_depth": "advanced",
        "max_results": max_results,
    }).encode()
    req = urllib.request.Request(
        "https://api.tavily.com/search",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=20)
        data = json.loads(resp.read())
        return [
            {"title": r.get("title", ""), "url": r.get("url", ""), "content": r.get("content", "")[:500]}
            for r in data.get("results", [])
        ]
    except Exception as e:
        return [{"error": str(e), "query": query}]


def run_searches_parallel(queries: list, corporate_jobs: list = None) -> tuple:
    """Run all Serper queries + corporate lookups in parallel."""
    search_results = {}
    corporate_results = {}

    all_jobs = []
    for q in queries:
        all_jobs.append(("serper", q))
    if corporate_jobs:
        for label, fn, *args in corporate_jobs:
            all_jobs.append(("corporate", label, fn, args))

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {}
        for job in all_jobs:
            if job[0] == "serper":
                f = executor.submit(serper_search, job[1])
                futures[f] = ("serper", job[1])
            else:
                _, label, fn, args = job
                f = executor.submit(fn, *args)
                futures[f] = ("corporate", label)

        for future in as_completed(futures):
            kind, key = futures[future]
            if kind == "serper":
                search_results[key] = future.result()
            else:
                corporate_results[key] = future.result()

    return search_results, corporate_results




# ── EU Registry: Companies House (UK) ───────────────────────────────────────────
def companies_house_lookup(company_name: str) -> dict:
    """Query UK Companies House free API."""
    encoded = urllib.parse.quote(company_name)
    url = f"https://api.company-information.service.gov.uk/search/companies?q={encoded}&items_per_page=5"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        items = data.get("items", [])
        results = []
        for item in items[:5]:
            addr = item.get("registered_office_address", {})
            results.append({
                "name": item.get("title"),
                "company_number": item.get("company_number"),
                "status": item.get("company_status"),
                "type": item.get("company_type"),
                "date_of_creation": item.get("date_of_creation"),
                "address": ", ".join(filter(None, [
                    addr.get("address_line_1"), addr.get("locality"),
                    addr.get("postal_code"), addr.get("country")
                ])),
                "url": f"https://find-and-update.company-information.service.gov.uk/company/{item.get('company_number')}"
            })
        return {"source": "companies_house_uk", "results": results}
    except Exception as e:
        return {"source": "companies_house_uk", "error": str(e)}


# ── EU Registry: Zefix (Switzerland) ────────────────────────────────────────────
def zefix_lookup(company_name: str) -> dict:
    """Query Swiss Zefix commercial registry."""
    payload = json.dumps({"name": company_name, "maxEntries": 5, "activeOnly": False}).encode()
    req = urllib.request.Request(
        "https://www.zefix.ch/ZefixREST/api/v1/firm/search.json",
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "Mozilla/5.0"}
    )
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        results = []
        for item in (data if isinstance(data, list) else data.get("list", []))[:5]:
            results.append({
                "name": item.get("name"),
                "uid": item.get("uid"),
                "legal_form": item.get("legalForm", {}).get("name", {}).get("de") if isinstance(item.get("legalForm"), dict) else item.get("legalForm"),
                "status": item.get("status"),
                "municipality": item.get("municipality"),
                "canton": item.get("cantonAbbreviation"),
                "url": f"https://www.zefix.ch/en/search/entity/list/firm/{item.get('uid', '').replace('CHE-', '').replace('.', '')}" if item.get("uid") else None
            })
        return {"source": "zefix_ch", "results": results}
    except Exception as e:
        return {"source": "zefix_ch", "error": str(e)}


# ── EU Registry: PAPPERS (France only) ──────────────────────────────────────────
def pappers_lookup(company_name: str) -> dict:
    """Query French PAPPERS registry — only for French entities."""
    encoded = urllib.parse.quote(company_name)
    url = f"https://api.pappers.fr/v2/recherche?q={encoded}&nombre=5"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        results = []
        for item in data.get("resultats", [])[:5]:
            siege = item.get("siege", {})
            results.append({
                "name": item.get("denomination") or item.get("nom_complet"),
                "siren": item.get("siren"),
                "legal_form": item.get("forme_juridique"),
                "city": siege.get("ville"),
                "department": siege.get("departement"),
                "status": item.get("statut_rcs"),
                "creation_date": item.get("date_creation"),
                "url": f"https://www.pappers.fr/entreprise/{item.get('siren')}" if item.get("siren") else None
            })
        return {"source": "pappers_fr", "results": results}
    except Exception as e:
        return {"source": "pappers_fr", "error": str(e)}


# ── eBay Seller Profile ──────────────────────────────────────────────────────────
def ebay_seller_lookup(seller_name: str) -> dict:
    """Scrape eBay seller profile page."""
    slug = seller_name.lower().replace(" ", "").replace("'", "")
    url = f"https://www.ebay.com/usr/{urllib.parse.quote(slug)}"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html"
        })
        resp = urllib.request.urlopen(req, timeout=15)
        html = resp.read().decode("utf-8", errors="ignore")
        result = {"seller_id": slug, "url": url, "found": False}
        # Feedback score
        m = re.search(r'"feedbackScore"[:\s]+(\d+)', html)
        if not m:
            m = re.search(r'(\d[\d,]+)\s*feedback', html, re.IGNORECASE)
        if m:
            result["feedback_score"] = int(m.group(1).replace(",", ""))
            result["found"] = True
        # Positive %
        m = re.search(r'([\d.]+)%\s*[Pp]ositive', html)
        if m:
            result["positive_pct"] = float(m.group(1))
        # Member since
        m = re.search(r'[Mm]ember since[:\s]+([A-Za-z]+ \d{4}|\d{4})', html)
        if m:
            result["member_since"] = m.group(1)
        # Items for sale
        m = re.search(r'(\d[\d,]*)\s+items? for sale', html, re.IGNORECASE)
        if m:
            result["items_count"] = int(m.group(1).replace(",", ""))
        return result
    except Exception as e:
        # Fallback: Serper search for eBay seller
        results = serper_search(f"site:ebay.com/usr {seller_name} feedback score", 3)
        return {"source": "ebay_serper_fallback", "found": False, "search_results": results[:2], "error": str(e)}


# ── Chrono24 Seller Profile ──────────────────────────────────────────────────────
def chrono24_seller_lookup(seller_name: str) -> dict:
    """Look up Chrono24 dealer profile via Serper (Chrono24 blocks scrapers)."""
    results = serper_search(f'site:chrono24.com "{seller_name}" dealer', 5)
    c24_results = [r for r in results if "chrono24.com" in r.get("url", "")]
    if not c24_results:
        results2 = serper_search(f'"{seller_name}" chrono24 dealer listings watches', 5)
        c24_results = [r for r in results2 if "chrono24.com" in r.get("url", "")]
    output = {"source": "chrono24", "found": bool(c24_results), "results": []}
    for r in c24_results[:3]:
        output["results"].append({
            "title": r.get("title"),
            "url": r.get("url"),
            "snippet": r.get("content", "")[:200]
        })
    # Try to extract listing count from snippets
    for r in c24_results:
        m = re.search(r'(\d+)\s+(?:watches?|listings?|items?)', r.get("content", ""), re.IGNORECASE)
        if m:
            output["listings_count"] = int(m.group(1))
            break
    return output


# ── Forum & Review Reputation ────────────────────────────────────────────────────
def forum_reputation_lookup(target: str) -> dict:
    """Search forums and review sites for reputation signals."""
    queries = [
        f'"{target}" site:watchuseek.com',
        f'"{target}" site:reddit.com watches dealer review',
        f'"{target}" trustpilot OR bbb.org review rating',
        f'"{target}" reviews complaints scam fraud warning',
    ]
    all_results = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {ex.submit(serper_search, q, 4): q for q in queries}
        for f in as_completed(futures):
            try:
                all_results.extend(f.result())
            except Exception:
                pass
    mentions = []
    for r in all_results[:12]:
        if r.get("url") and r.get("title"):
            mentions.append({
                "title": r["title"],
                "url": r["url"],
                "snippet": r.get("content", "")[:150]
            })
    # Basic sentiment from snippets
    text = " ".join(r.get("content", "") for r in all_results).lower()
    pos = sum(text.count(w) for w in ["great", "excellent", "trusted", "legit", "recommended", "positive", "good"])
    neg = sum(text.count(w) for w in ["scam", "fraud", "fake", "avoid", "warning", "complaint", "issue", "problem"])
    if not mentions:
        sentiment = "none"
    elif neg > pos + 2:
        sentiment = "negative"
    elif pos > neg + 2:
        sentiment = "positive"
    else:
        sentiment = "mixed"
    return {"source": "forum_reputation", "mentions": mentions, "overall_sentiment": sentiment}


# ── Phone Reverse Lookup ─────────────────────────────────────────────────────────
def phone_reverse_lookup(phone: str) -> dict:
    """Reverse lookup a phone number via Serper."""
    queries = [
        f'"{phone}" owner name business',
        f'"{phone}" site:whitepages.com OR site:spokeo.com',
    ]
    all_results = []
    for q in queries:
        all_results.extend(serper_search(q, 4))
    sources = [{"title": r["title"], "url": r["url"], "snippet": r.get("content","")[:150]}
               for r in all_results[:6] if r.get("url")]
    # Try to extract possible owner from first snippet
    possible_owner = None
    for r in all_results[:3]:
        m = re.search(r'registered to\s+([A-Z][a-z]+ [A-Z][a-z]+)', r.get("content",""))
        if m:
            possible_owner = m.group(1)
            break
    return {"phone": phone, "possible_owner": possible_owner, "sources": sources}


# ── Related Entities ─────────────────────────────────────────────────────────────
def related_entities_lookup(target: str) -> dict:
    """Find other businesses or entities related to the target."""
    queries = [
        f'"{target}" affiliated related companies business entities',
        f'"{target}" owner director other company business',
    ]
    all_results = []
    with ThreadPoolExecutor(max_workers=2) as ex:
        futures = {ex.submit(serper_search, q, 5): q for q in queries}
        for f in as_completed(futures):
            try:
                all_results.extend(f.result())
            except Exception:
                pass
    entities = []
    seen_urls = set()
    for r in all_results[:10]:
        url = r.get("url","")
        if url and url not in seen_urls:
            seen_urls.add(url)
            entities.append({
                "title": r.get("title",""),
                "url": url,
                "snippet": r.get("content","")[:150]
            })
    return {"source": "related_entities", "results": entities}



# ── OFAC Sanctions Check ─────────────────────────────────────────────────────────
def ofac_check(name: str) -> dict:
    """Check OFAC SDN (Specially Designated Nationals) list — US Treasury free API."""
    encoded = urllib.parse.quote(name)
    url = f"https://api.ofac-api.com/v4/search?apiKey=free&name={encoded}&minScore=85"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        matches = data.get("results", [])
        if matches:
            return {
                "status": "HIT",
                "matches": [{"name": m.get("name"), "score": m.get("score"), "type": m.get("sdnType"), "programs": m.get("programs")} for m in matches[:3]],
                "source": "ofac-api.com"
            }
        return {"status": "CLEAR", "source": "ofac-api.com"}
    except Exception:
        # Fallback: query Treasury SDN list directly via Serper
        results = serper_search(f'site:home.treasury.gov/policy-issues/financial-sanctions/sdn-list "{name}"', 3)
        hit = any(name.lower() in r.get("content","").lower() for r in results)
        return {"status": "HIT_POSSIBLE" if hit else "CLEAR", "source": "serper_fallback", "note": "verify manually"}


# ── Federal Court Records (CourtListener) ────────────────────────────────────────
def courtlistener_search(name: str) -> dict:
    """Search CourtListener free API for federal court cases."""
    encoded = urllib.parse.quote(f'"{name}"')
    # Search parties
    url_party = f"https://www.courtlistener.com/api/rest/v3/parties/?name={encoded}&format=json"
    # Search dockets
    url_docket = f"https://www.courtlistener.com/api/rest/v3/dockets/?party_name={encoded}&format=json&page_size=5"
    results = {"source": "courtlistener.com", "cases": [], "party_hits": 0}
    try:
        req = urllib.request.Request(url_docket, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        count = data.get("count", 0)
        results["total_cases_found"] = count
        for d in data.get("results", [])[:5]:
            results["cases"].append({
                "case_name": d.get("case_name"),
                "court": d.get("court"),
                "date_filed": d.get("date_filed"),
                "nature_of_suit": d.get("nature_of_suit"),
                "url": f"https://www.courtlistener.com{d.get('absolute_url','')}" if d.get("absolute_url") else None
            })
    except Exception as e:
        results["error"] = str(e)
    # Supplement with Serper for news about lawsuits
    serper_hits = serper_search(f'"{name}" lawsuit indictment court case federal 2023 2024 2025', 5)
    results["news_mentions"] = [{"title": r["title"], "url": r["url"], "snippet": r.get("content","")[:200]} for r in serper_hits[:4] if r.get("url")]
    return results


# ── Bankruptcy Search ─────────────────────────────────────────────────────────────
def bankruptcy_search(name: str) -> dict:
    """Search PACER bankruptcy records via CourtListener + Serper."""
    encoded = urllib.parse.quote(f'"{name}"')
    url = f"https://www.courtlistener.com/api/rest/v3/dockets/?party_name={encoded}&court_type=bankruptcy&format=json&page_size=5"
    results = {"source": "courtlistener_bankruptcy", "filings": []}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        results["total_found"] = data.get("count", 0)
        for d in data.get("results", [])[:3]:
            results["filings"].append({
                "case_name": d.get("case_name"),
                "chapter": d.get("chapter"),
                "date_filed": d.get("date_filed"),
                "court": d.get("court"),
                "url": f"https://www.courtlistener.com{d.get('absolute_url','')}" if d.get("absolute_url") else None
            })
    except Exception as e:
        results["error"] = str(e)
    # Serper supplement
    bk_hits = serper_search(f'"{name}" bankruptcy chapter 7 11 13 filed petition', 4)
    results["serper_mentions"] = [{"title": r["title"], "url": r["url"]} for r in bk_hits[:3] if r.get("url")]
    return results


# ── Domain Intelligence ──────────────────────────────────────────────────────────
def domain_intel(domain_or_url: str) -> dict:
    """Fetch WHOIS via RDAP, Wayback Machine age, and crt.sh for related domains."""
    # Clean domain
    domain = domain_or_url.replace("https://","").replace("http://","").replace("www.","").split("/")[0].strip()
    if not domain or "." not in domain:
        return {"error": "no valid domain"}
    result = {"domain": domain}
    # RDAP (free, no key)
    try:
        rdap_url = f"https://rdap.org/domain/{domain}"
        req = urllib.request.Request(rdap_url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        # Registration dates
        for event in data.get("events", []):
            if event.get("eventAction") == "registration":
                result["registered"] = event.get("eventDate","")[:10]
            if event.get("eventAction") == "expiration":
                result["expires"] = event.get("eventDate","")[:10]
        # Calculate age
        if result.get("registered"):
            from datetime import date
            try:
                reg_year = int(result["registered"][:4])
                result["age_years"] = date.today().year - reg_year
            except Exception:
                pass
        # Registrar
        for entity in data.get("entities", []):
            if "registrar" in (entity.get("roles") or []):
                vcard = entity.get("vcardArray", [])
                if isinstance(vcard, list) and len(vcard) > 1:
                    for v in vcard[1]:
                        if v[0] == "fn":
                            result["registrar"] = v[3]
        # Privacy
        status = " ".join(data.get("status", []))
        result["privacy_protected"] = "clientTransferProhibited" in status or "redacted" in str(data).lower()
    except Exception as e:
        result["rdap_error"] = str(e)
    # Wayback Machine — first snapshot
    try:
        wb_url = f"http://archive.org/wayback/available?url={domain}&timestamp=20100101"
        req = urllib.request.Request(wb_url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=10)
        wb_data = json.loads(resp.read())
        snap = wb_data.get("archived_snapshots", {}).get("closest", {})
        if snap.get("available"):
            result["wayback_earliest_snapshot"] = snap.get("timestamp","")[:8]
            result["wayback_url"] = snap.get("url")
    except Exception:
        pass
    # crt.sh — related domains via SSL cert
    try:
        crt_url = f"https://crt.sh/?q=%.{domain}&output=json"
        req = urllib.request.Request(crt_url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=15)
        certs = json.loads(resp.read())
        related = set()
        for c in certs[:50]:
            name = c.get("name_value","").lower()
            for n in name.split("\n"):
                n = n.strip().lstrip("*.")
                if n and n != domain and "." in n:
                    related.add(n)
        result["related_domains_via_ssl"] = sorted(related)[:10]
    except Exception:
        pass
    return result


# ── Virtual Office Detector ──────────────────────────────────────────────────────
VIRTUAL_OFFICE_SIGNALS = [
    "regus", "wework", "ipostal", "ups store", "the ups store", "mailboxes etc",
    "earth class mail", "anytime mailbox", "postal annex", "pak mail",
    "virtual office", "registered agent", "incfile", "northwest registered",
    "legalzoom", "suite 100", "suite 200", "suite 300", "pmb ", "box #",
    "800 n king", "1209 orange", "2711 centerville",  # known DE shell addresses
    "251 little falls", "1000 n west",
]

def virtual_office_check(addresses: list) -> dict:
    """Check if any address matches known virtual office / mail drop signals."""
    flags = []
    for addr in (addresses or []):
        if isinstance(addr, dict):
            addr = addr.get("address") or addr.get("principal_address") or str(addr)
        addr_lower = addr.lower()
        for signal in VIRTUAL_OFFICE_SIGNALS:
            if signal in addr_lower:
                flags.append({"address": addr, "signal": signal})
                break
    return {"virtual_office_detected": bool(flags), "flags": flags}


# ── All US State Registries (Serper-based) ────────────────────────────────────────
def us_state_registry_search(company_name: str, states: list = None) -> dict:
    """Search US state business registries via Serper for non-FL states."""
    if not states:
        states = ["CA", "NY", "DE", "WY", "NV", "TX", "CO", "OH", "NJ", "MA"]
    state_urls = {
        "CA": "bizfile.sos.ca.gov",
        "NY": "apps.dos.ny.gov",
        "DE": "icis.corp.delaware.gov",
        "WY": "wyobiz.wyo.gov",
        "NV": "esos.nv.gov",
        "TX": "direct.sos.state.tx.us",
        "CO": "sos.state.co.us",
        "OH": "sos.state.oh.us",
        "NJ": "njportal.com/DOR/BusinessRecords",
        "MA": "corp.sec.state.ma.us",
    }
    results = {}
    queries = []
    for state in states[:5]:  # cap at 5 states to control Serper credits
        site = state_urls.get(state, "")
        if site:
            queries.append((state, f'site:{site} "{company_name}"'))
        else:
            queries.append((state, f'"{company_name}" {state} corporation LLC business registration secretary of state'))
    # Also try OpenCorporates multi-state
    queries.append(("opencorporates", f'site:opencorporates.com "{company_name}"'))
    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(serper_search, q, 5): label for label, q in queries}
        for f in as_completed(futures):
            label = futures[f]
            try:
                hits = f.result()
                if hits:
                    results[label] = [{"title": r["title"], "url": r["url"], "snippet": r.get("content","")[:200]} for r in hits[:3]]
            except Exception:
                pass
    return {"source": "us_state_registries", "results": results}


# ── SEC EDGAR Search ─────────────────────────────────────────────────────────────
def sec_edgar_search(name: str) -> dict:
    """Search SEC EDGAR for company or person filings — free API."""
    encoded = urllib.parse.quote(name)
    url = f"https://efts.sec.gov/LATEST/search-index?q=%22{encoded}%22&dateRange=custom&startdt=2015-01-01&forms=10-K,S-1,8-K,D,ADV&hits.hits._source=period_of_report,entity_name,file_date,form_type,file_num"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Jarvis/1.0 research@jarvis.local", "Accept": "application/json"})
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        hits = data.get("hits", {}).get("hits", [])
        results = []
        for h in hits[:5]:
            src = h.get("_source", {})
            results.append({
                "entity": src.get("entity_name"),
                "form": src.get("form_type"),
                "date": src.get("file_date"),
                "url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={encoded}&type=&dateb=&owner=include&count=10"
            })
        return {"source": "sec_edgar", "total_hits": data.get("hits",{}).get("total",{}).get("value",0), "filings": results}
    except Exception as e:
        return {"source": "sec_edgar", "error": str(e)}


# ── News Archive Search ───────────────────────────────────────────────────────────
def news_archive_search(name: str) -> dict:
    """Structured news search with date-filtered queries."""
    queries = [
        f'"{name}" news 2025 2026',
        f'"{name}" news 2023 2024',
        f'"{name}" arrested charged indicted sued',
    ]
    all_news = []
    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = {ex.submit(serper_search, q, 5): q for q in queries}
        for f in as_completed(futures):
            try:
                for r in f.result():
                    if r.get("url") and r.get("title"):
                        all_news.append({"title": r["title"], "url": r["url"], "snippet": r.get("content","")[:200]})
            except Exception:
                pass
    # Deduplicate by URL
    seen = set()
    deduped = []
    for item in all_news:
        if item["url"] not in seen:
            seen.add(item["url"])
            deduped.append(item)
    return {"source": "news_archive", "articles": deduped[:10]}



# ── LinkedIn Profile Intel ───────────────────────────────────────────────────────
def linkedin_intel(name: str, url: str = None) -> dict:
    """Pull LinkedIn profile data via Serper."""
    queries = []
    if url and "linkedin.com" in url:
        queries.append(f'site:linkedin.com "{name}" profile')
    queries.append(f'"{name}" linkedin.com profile connections experience')
    queries.append(f'site:linkedin.com/in "{name}"')
    all_results = []
    for q in queries[:2]:
        all_results.extend(serper_search(q, 5))
    li_results = [r for r in all_results if "linkedin.com" in r.get("url","")]
    result = {"source": "linkedin_serper", "found": bool(li_results), "profiles": []}
    for r in li_results[:3]:
        snippet = r.get("content","")
        # Extract signals from snippet
        connections = None
        m = re.search(r'(\d[\d,]+)\s+connections?', snippet, re.IGNORECASE)
        if m:
            connections = int(m.group(1).replace(",",""))
        result["profiles"].append({
            "url": r.get("url"),
            "title": r.get("title"),
            "snippet": snippet[:300],
            "connections": connections
        })
    return result


# ── Instagram Activity ───────────────────────────────────────────────────────────
def instagram_intel(name: str, handle: str = None) -> dict:
    """Pull Instagram presence via Serper."""
    queries = []
    if handle:
        queries.append(f'site:instagram.com/{handle.lstrip("@")}')
    queries.append(f'"{name}" site:instagram.com followers posts watches')
    queries.append(f'instagram.com "{name}" luxury watches dealer')
    all_results = []
    for q in queries[:2]:
        all_results.extend(serper_search(q, 5))
    ig_results = [r for r in all_results if "instagram.com" in r.get("url","")]
    result = {"source": "instagram_serper", "found": bool(ig_results), "profiles": []}
    for r in ig_results[:3]:
        snippet = r.get("content","")
        followers = None
        posts = None
        m = re.search(r'([\d.,]+[KkMm]?)\s+[Ff]ollowers?', snippet)
        if m:
            followers = m.group(1)
        m2 = re.search(r'([\d,]+)\s+[Pp]osts?', snippet)
        if m2:
            posts = m2.group(1)
        result["profiles"].append({
            "url": r.get("url"),
            "title": r.get("title"),
            "snippet": snippet[:200],
            "followers": followers,
            "posts": posts
        })
    return result


# ── Google Business Profile ──────────────────────────────────────────────────────
def google_business_intel(name: str) -> dict:
    """Pull Google Business reviews and rating via Serper knowledge graph."""
    results = serper_search(f'"{name}" google reviews rating stars business', 5)
    # Also try maps
    maps_results = serper_search(f'"{name}" site:maps.google.com OR site:g.co reviews', 3)
    all_r = results + maps_results
    result = {"source": "google_business", "found": False}
    for r in all_r:
        snippet = r.get("content","")
        # Rating
        m = re.search(r'([\d.]+)\s*(?:out of\s*)?(?:stars?|/5)', snippet, re.IGNORECASE)
        if m:
            result["rating"] = float(m.group(1))
            result["found"] = True
        # Review count
        m2 = re.search(r'([\d,]+)\s+(?:Google\s+)?reviews?', snippet, re.IGNORECASE)
        if m2:
            result["review_count"] = int(m2.group(1).replace(",",""))
            result["found"] = True
        if result.get("rating") and result.get("review_count"):
            break
    result["snippets"] = [{"title": r.get("title"), "url": r.get("url"), "snippet": r.get("content","")[:150]} for r in all_r[:3]]
    return result


# ── eBay Completed/Sold Listings ─────────────────────────────────────────────────
def ebay_sold_listings(name: str) -> dict:
    """Search eBay completed/sold listings for a dealer or watch reference."""
    queries = [
        f'site:ebay.com/itm "{name}" sold completed',
        f'"{name}" ebay sold completed listing price watches',
    ]
    all_results = []
    for q in queries:
        all_results.extend(serper_search(q, 5))
    ebay_hits = [r for r in all_results if "ebay.com" in r.get("url","")]
    prices = []
    for r in ebay_hits:
        snippet = r.get("content","")
        m = re.findall(r'\$[\d,]+(?:\.\d{2})?', snippet)
        prices.extend(m[:3])
    return {
        "source": "ebay_sold_serper",
        "found": bool(ebay_hits),
        "listing_count": len(ebay_hits),
        "prices_found": prices[:10],
        "listings": [{"title": r.get("title"), "url": r.get("url"), "snippet": r.get("content","")[:150]} for r in ebay_hits[:4]]
    }


# ── Watch Platform Presence (WatchRecon, Subdial, etc.) ─────────────────────────
def watch_platform_presence(name: str) -> dict:
    """Check presence on secondary watch platforms."""
    platforms = {
        "watchrecon": "site:watchrecon.com",
        "subdial": "site:subdial.com",
        "hodinkee_shop": "site:hodinkee.com/collections",
        "crown_caliber": "site:crownandcaliber.com",
        "watchbox": "site:thewatchbox.com",
        "timezone": "site:timezone.com",
        "watchuseek_bst": 'site:watchuseek.com/forums/watches-sale-trade',
    }
    results = {}
    queries = [(platform, f'{site} "{name}"') for platform, site in platforms.items()]
    with ThreadPoolExecutor(max_workers=7) as ex:
        futures = {ex.submit(serper_search, q, 3): label for label, q in queries}
        for f in as_completed(futures):
            label = futures[f]
            try:
                hits = f.result()
                if hits:
                    results[label] = {
                        "found": True,
                        "count": len(hits),
                        "top_url": hits[0].get("url") if hits else None,
                        "snippet": hits[0].get("content","")[:150] if hits else None
                    }
                else:
                    results[label] = {"found": False}
            except Exception:
                results[label] = {"found": False, "error": "search failed"}
    return {"source": "watch_platforms", "platforms": results}


# ── FEC Political Donation Records ───────────────────────────────────────────────
def fec_lookup(name: str) -> dict:
    """Check FEC (Federal Election Commission) donation records — free API."""
    encoded = urllib.parse.quote(name)
    url = f"https://api.open.fec.gov/v1/schedules/schedule_a/?contributor_name={encoded}&per_page=5&api_key=DEMO_KEY"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        results = data.get("results", [])
        total = data.get("pagination", {}).get("count", 0)
        donations = []
        for r in results[:5]:
            donations.append({
                "contributor": r.get("contributor_name"),
                "amount": r.get("contribution_receipt_amount"),
                "date": r.get("contribution_receipt_date"),
                "committee": r.get("committee", {}).get("name") if isinstance(r.get("committee"), dict) else r.get("committee_id"),
                "employer": r.get("contributor_employer"),
                "occupation": r.get("contributor_occupation"),
            })
        return {"source": "fec.gov", "total_donations": total, "donations": donations}
    except Exception as e:
        return {"source": "fec.gov", "error": str(e), "total_donations": 0}


# ── PPP Loan Database (ProPublica) ───────────────────────────────────────────────
def ppp_loan_lookup(name: str) -> dict:
    """Check ProPublica PPP loan database — free, no key."""
    encoded = urllib.parse.quote(name)
    url = f"https://projects.propublica.org/coronavirus/bailouts/search.json?q={encoded}"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
            "Referer": "https://projects.propublica.org/coronavirus/bailouts/"
        })
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        loans = data if isinstance(data, list) else data.get("data", []) or data.get("results", [])
        results = []
        for loan in loans[:5]:
            results.append({
                "business_name": loan.get("business_name") or loan.get("name"),
                "amount": loan.get("amount") or loan.get("loan_amount"),
                "jobs_retained": loan.get("jobs_retained"),
                "lender": loan.get("lender"),
                "state": loan.get("state"),
                "date_approved": loan.get("date_approved"),
            })
        return {"source": "propublica_ppp", "total_found": len(results), "loans": results}
    except Exception as e:
        # Fallback serper
        hits = serper_search(f'"{name}" PPP loan SBA paycheck protection program', 3)
        return {"source": "propublica_serper_fallback", "error": str(e),
                "mentions": [{"title": r["title"], "url": r["url"]} for r in hits[:3]]}


# ── Data Breach Check (HaveIBeenPwned-style) ─────────────────────────────────────
def data_breach_check(name: str, domain: str = None) -> dict:
    """Check if email/domain appears in known data breaches via Serper."""
    queries = []
    if domain:
        queries.append(f'"{domain}" data breach leaked email database')
    queries.append(f'"{name}" data breach leaked password email exposed')
    all_results = []
    for q in queries:
        all_results.extend(serper_search(q, 4))
    breach_signals = []
    for r in all_results:
        snippet = (r.get("content","") + r.get("title","")).lower()
        if any(w in snippet for w in ["breach", "leaked", "exposed", "hacked", "dump", "haveibeenpwned"]):
            breach_signals.append({"title": r.get("title"), "url": r.get("url"), "snippet": r.get("content","")[:150]})
    return {
        "source": "breach_serper",
        "breach_signals_found": len(breach_signals),
        "mentions": breach_signals[:4]
    }


# ── Email Discovery ──────────────────────────────────────────────────────────────
def email_discovery(name: str, domain: str = None) -> dict:
    """Discover likely email formats and any publicly visible emails."""
    results = {"source": "email_discovery", "emails_found": [], "formats": []}
    if domain:
        # Common formats
        parts = name.lower().split()
        if len(parts) >= 2:
            first, last = parts[0], parts[-1]
            results["formats"] = [
                f"{first}@{domain}",
                f"{first}.{last}@{domain}",
                f"{first[0]}{last}@{domain}",
                f"{last}@{domain}",
            ]
        # Serper search for exposed emails
        hits = serper_search(f'"{name}" email "@{domain}" contact', 5)
        for r in hits:
            emails = re.findall(r'[\w\.\-]+@[\w\.\-]+\.[a-zA-Z]{2,}', r.get("content","") + r.get("url",""))
            for e in emails:
                if domain.lower() in e.lower() and e not in results["emails_found"]:
                    results["emails_found"].append(e)
    # General search for any public email
    hits2 = serper_search(f'"{name}" email contact "@" watches dealer', 5)
    for r in hits2:
        emails = re.findall(r'[\w\.\-]+@[\w\.\-]+\.[a-zA-Z]{2,}', r.get("content",""))
        for e in emails:
            if e not in results["emails_found"] and len(results["emails_found"]) < 5:
                results["emails_found"].append(e)
    return results


# ── Property Records ─────────────────────────────────────────────────────────────
def property_records_lookup(name: str) -> dict:
    """Search for property ownership via Serper (county assessor, Zillow, etc.)."""
    queries = [
        f'"{name}" property owner real estate county assessor',
        f'"{name}" home owner zillow redfin trulia address',
    ]
    all_results = []
    for q in queries:
        all_results.extend(serper_search(q, 4))
    properties = []
    seen_urls = set()
    for r in all_results:
        url = r.get("url","")
        if url and url not in seen_urls:
            seen_urls.add(url)
            if any(site in url for site in ["zillow","redfin","trulia","realtor","assessor","property","county"]):
                properties.append({"title": r.get("title"), "url": url, "snippet": r.get("content","")[:150]})
    return {"source": "property_serper", "found": bool(properties), "records": properties[:4]}


# ── Kali OSINT Tools Integration ────────────────────────────────────────────────
def theharvester_lookup(domain: str) -> dict:
    """Run theHarvester against a domain for emails, subdomains, people."""
    if not domain:
        return {"error": "no domain"}
    try:
        domain_clean = domain.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]
        cmd = [
            "theHarvester", "-d", domain_clean,
            "-b", "bing,crtsh,duckduckgo,dnsdumpster,certspotter,hackertarget",
            "-l", "50"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
        output = result.stdout + result.stderr
        emails = list(set(re.findall(r'[\w\.\-]+@[\w\.\-]+\.\w+', output)))
        hosts = list(set(re.findall(r'(?:^|\s)([\w\-]+\.[\w\.\-]+\w)(?:\s|$)', output, re.MULTILINE)))
        hosts = [h for h in hosts if domain_clean in h and len(h) > len(domain_clean)]
        people = re.findall(r'(?:Name|Person|People):\s*(.+)', output, re.IGNORECASE)
        return {
            "emails_found": emails[:20],
            "subdomains": hosts[:20],
            "people": people[:10],
            "raw_length": len(output),
            "source": "theHarvester"
        }
    except subprocess.TimeoutExpired:
        return {"error": "timeout", "source": "theHarvester"}
    except Exception as e:
        return {"error": str(e), "source": "theHarvester"}


def username_osint(handle: str) -> dict:
    """Check a username across social platforms using maigret."""
    if not handle:
        return {"error": "no handle"}
    try:
        handle_clean = handle.lstrip("@").strip()
        cmd = ["python3", "-m", "maigret", handle_clean, "--json", "maigret_tmp.json",
               "--top-sites", "50", "--no-progressbar", "--no-color"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60,
                                cwd="/tmp")
        found_sites = []
        import glob as _glob
        for f in _glob.glob("/tmp/maigret_tmp*.json"):
            try:
                with open(f) as fh:
                    data = json.load(fh)
                for site, info in data.items():
                    if isinstance(info, dict) and info.get("status") == "Claimed":
                        found_sites.append({"site": site, "url": info.get("url_user", "")})
                os.remove(f)
            except Exception:
                pass
        return {"handle": handle_clean, "found_on": found_sites[:30], "source": "maigret"}
    except subprocess.TimeoutExpired:
        return {"error": "timeout", "source": "maigret"}
    except Exception as e:
        return {"error": str(e), "source": "maigret"}


def holehe_email_check(email: str) -> dict:
    """Check which platforms an email is registered on using holehe."""
    if not email or "@" not in email:
        return {"error": "invalid email"}
    try:
        result = subprocess.run(
            ["holehe", "--only-used", "--no-color", email],
            capture_output=True, text=True, timeout=60
        )
        platforms = re.findall(r'\[\+\]\s+(\S+)', result.stdout)
        return {"email": email, "registered_on": platforms, "count": len(platforms), "source": "holehe"}
    except Exception as e:
        return {"error": str(e), "source": "holehe"}


def phoneinfoga_lookup(phone: str) -> dict:
    """Deep phone number OSINT using phoneinfoga or fallback to Serper."""
    if not phone:
        return {"error": "no phone"}
    phone_clean = re.sub(r'[^\d\+]', '', phone)
    # Try phoneinfoga if installed
    try:
        result = subprocess.run(
            ["phoneinfoga", "scan", "-n", phone_clean],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout:
            return {"phone": phone_clean, "raw": result.stdout[:1000], "source": "phoneinfoga"}
    except FileNotFoundError:
        pass
    # Fallback: Serper search
    results = serper_search(f'phone number "{phone}" owner name carrier location', max_results=3)
    return {"phone": phone_clean, "serper_results": results, "source": "serper_fallback"}



# ── h8mail — Email Breach Intelligence ─────────────────────────────────────────
def h8mail_lookup(email: str) -> dict:
    """Check email against breach databases using h8mail."""
    try:
        r = subprocess.run(
            ["h8mail", "-t", email, "--json", "/tmp/h8mail_out.json"],
            capture_output=True, text=True, timeout=45
        )
        try:
            data = json.load(open("/tmp/h8mail_out.json"))
            breaches = []
            for entry in data:
                if entry.get("data"):
                    breaches.extend(entry["data"][:5])
            return {"email": email, "breaches_found": len(breaches) > 0, "breach_data": breaches[:10], "source": "h8mail"}
        except:
            pass
        return {"email": email, "raw": r.stdout[:800], "source": "h8mail"}
    except subprocess.TimeoutExpired:
        return {"error": "timeout", "source": "h8mail"}
    except Exception as e:
        return {"error": str(e), "source": "h8mail"}

# ── WhatWeb — Website Fingerprinting ───────────────────────────────────────────
def whatweb_scan(url: str) -> dict:
    """Fingerprint website — tech stack, CMS, server, plugins."""
    try:
        r = subprocess.run(
            ["whatweb", "--log-json=/tmp/whatweb_out.json", "-a", "3", url],
            capture_output=True, text=True, timeout=30
        )
        try:
            with open("/tmp/whatweb_out.json") as f:
                lines = [l.strip() for l in f if l.strip()]
            data = json.loads(lines[-1]) if lines else {}
            plugins = list(data.get("plugins", {}).keys())
            return {"url": url, "technologies": plugins, "raw": r.stdout[:500], "source": "whatweb"}
        except:
            return {"url": url, "raw": r.stdout[:800], "source": "whatweb"}
    except subprocess.TimeoutExpired:
        return {"error": "timeout", "source": "whatweb"}
    except Exception as e:
        return {"error": str(e), "source": "whatweb"}

# ── Nmap — Network/Port Exposure ────────────────────────────────────────────────
def nmap_scan(target: str) -> dict:
    """Light port scan — detect exposed services."""
    try:
        r = subprocess.run(
            ["nmap", "-sV", "--open", "-p", "80,443,8080,8443,21,22,25,3306,5432",
             "--host-timeout", "15s", "-T3", target],
            capture_output=True, text=True, timeout=45
        )
        open_ports = re.findall(r"(\d+/tcp)\s+open\s+(\S+)\s*(.*)", r.stdout)
        return {
            "target": target,
            "open_ports": [{"port": p, "service": s, "version": v.strip()} for p,s,v in open_ports],
            "raw": r.stdout[:600], "source": "nmap"
        }
    except subprocess.TimeoutExpired:
        return {"error": "timeout", "source": "nmap"}
    except Exception as e:
        return {"error": str(e), "source": "nmap"}

# ── Socialscan — Username/Email Platform Check ─────────────────────────────────
def socialscan_check(query: str) -> dict:
    """Check username/email across social platforms."""
    try:
        r = subprocess.run(
            ["socialscan", query, "--view-by", "platform"],
            capture_output=True, text=True, timeout=30
        )
        taken     = re.findall(r"(\w+)\s+\|\s+Taken", r.stdout)
        available = re.findall(r"(\w+)\s+\|\s+Available", r.stdout)
        return {"query": query, "registered_on": taken, "available_on": available, "source": "socialscan"}
    except subprocess.TimeoutExpired:
        return {"error": "timeout", "source": "socialscan"}
    except Exception as e:
        return {"error": str(e), "source": "socialscan"}

# ── GHunt — Google Account OSINT ────────────────────────────────────────────────
def ghunt_lookup(email: str) -> dict:
    """Google account OSINT — profile, maps, photos, activity."""
    try:
        r = subprocess.run(
            ["ghunt", "email", email, "--json", "/tmp/ghunt_out.json"],
            capture_output=True, text=True, timeout=45
        )
        try:
            data = json.load(open("/tmp/ghunt_out.json"))
            return {"email": email, "google_data": data, "source": "ghunt"}
        except:
            return {"email": email, "raw": r.stdout[:800], "source": "ghunt"}
    except subprocess.TimeoutExpired:
        return {"error": "timeout", "source": "ghunt"}
    except Exception as e:
        return {"error": str(e), "source": "ghunt"}



# ── Instaloader — Deep Instagram Intelligence ────────────────────────────────
def instaloader_profile(handle: str) -> dict:
    """Pull full Instagram profile data using instaloader."""
    try:
        import instaloader
        handle_clean = handle.lstrip("@").strip()
        L = instaloader.Instaloader(download_pictures=False, download_videos=False,
                                     download_video_thumbnails=False, save_metadata=False,
                                     quiet=True)
        profile = instaloader.Profile.from_username(L.context, handle_clean)
        return {
            "handle": handle_clean,
            "full_name": profile.full_name,
            "biography": profile.biography,
            "followers": profile.followers,
            "following": profile.followees,
            "posts": profile.mediacount,
            "is_private": profile.is_private,
            "is_verified": profile.is_verified,
            "external_url": profile.external_url,
            "business_category": profile.business_category_name,
            "is_business": profile.is_business_account,
            "profile_pic_url": profile.profile_pic_url,
            "source": "instaloader"
        }
    except Exception as e:
        return {"error": str(e), "source": "instaloader"}

# ── Waybackpy — Domain History Intelligence ──────────────────────────────────
def wayback_history(url: str) -> dict:
    """Check Wayback Machine history — when did this site appear? What changed?"""
    try:
        import waybackpy
        domain = re.sub(r"https?://(www\.)?", "", url).split("/")[0]
        cdx = waybackpy.WaybackMachineCDXServerAPI(f"http://{domain}", user_agent="Mozilla/5.0")
        snapshots = list(cdx.snapshots())
        if not snapshots:
            return {"domain": domain, "found": False, "source": "waybackpy"}
        oldest = snapshots[0]
        newest = snapshots[-1]
        return {
            "domain": domain,
            "found": True,
            "total_snapshots": len(snapshots),
            "oldest_snapshot": str(oldest.datetime_timestamp) if hasattr(oldest, "datetime_timestamp") else oldest.timestamp,
            "newest_snapshot": str(newest.datetime_timestamp) if hasattr(newest, "datetime_timestamp") else newest.timestamp,
            "oldest_url": oldest.archive_url,
            "source": "waybackpy"
        }
    except Exception as e:
        return {"error": str(e), "source": "waybackpy"}


# ── SQLite Cache ────────────────────────────────────────────────────────────────
def init_cache():
    conn = sqlite3.connect(CACHE_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS report_cache (
            cache_key TEXT PRIMARY KEY,
            target TEXT,
            target_type TEXT,
            report_json TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id TEXT PRIMARY KEY,
            target TEXT,
            target_type TEXT,
            region TEXT,
            risk_rating TEXT,
            risk_score INTEGER,
            red_flags_count INTEGER,
            summary TEXT,
            full_report TEXT,
            cost_usd REAL,
            time_seconds REAL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            tags TEXT DEFAULT '[]'
        )
    """)
    conn.commit()
    conn.close()


def get_cached_report(target: str, target_type: str):
    cache_key = hashlib.md5(f"{target.lower().strip()}:{target_type}".encode()).hexdigest()
    try:
        conn = sqlite3.connect(CACHE_DB)
        row = conn.execute(
            "SELECT report_json, created_at FROM report_cache WHERE cache_key = ? AND datetime(created_at, '+7 days') > datetime('now')",
            (cache_key,)
        ).fetchone()
        conn.close()
        if row:
            report = json.loads(row[0])
            if "_meta" not in report:
                report["_meta"] = {}
            report["_meta"]["cache_hit"] = True
            report["_meta"]["cached_at"] = row[1]
            return report
    except Exception:
        pass
    return None


def save_to_cache(target: str, target_type: str, report: dict):
    cache_key = hashlib.md5(f"{target.lower().strip()}:{target_type}".encode()).hexdigest()
    report_id = hashlib.md5(f"{target}{time.time()}".encode()).hexdigest()[:16]
    try:
        conn = sqlite3.connect(CACHE_DB)
        conn.execute(
            "INSERT OR REPLACE INTO report_cache (cache_key, target, target_type, report_json) VALUES (?,?,?,?)",
            (cache_key, target, target_type, json.dumps(report))
        )
        meta = report.get("_meta", {})
        conn.execute(
            "INSERT OR IGNORE INTO reports (id, target, target_type, risk_rating, risk_score, red_flags_count, summary, full_report, cost_usd, time_seconds) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                report_id, target, target_type,
                report.get("risk_rating"),
                len(report.get("red_flags", [])) * 10,
                len(report.get("red_flags", [])),
                report.get("summary", "")[:500],
                json.dumps(report),
                meta.get("total_cost_usd", 0),
                meta.get("total_time_seconds", 0),
            )
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


# ── FINRA BrokerCheck ────────────────────────────────────────────────────────────
def finra_brokercheck(name: str) -> dict:
    """Check FINRA BrokerCheck for broker/dealer registrations and complaints."""
    encoded = urllib.parse.quote(name)
    url = f"https://api.brokercheck.finra.org/search/individual?query={encoded}&hl=true&includePrevious=true&nRows=5&start=0&wt=json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        hits = data.get("hits", {}).get("hits", [])
        results = []
        for h in hits[:3]:
            src = h.get("_source", {})
            results.append({
                "name": src.get("ind_firstname", "") + " " + src.get("ind_lastname", ""),
                "crd_number": src.get("ind_source_id"),
                "current_employer": src.get("ind_bc_scope"),
                "disclosures": src.get("ind_disc_cl", "0"),
                "exams_passed": src.get("ind_exms_list", []),
                "url": f"https://brokercheck.finra.org/individual/summary/{src.get('ind_source_id', '')}",
            })
        return {"source": "finra_brokercheck", "total": data.get("hits", {}).get("total", 0), "results": results}
    except Exception as e:
        hits = serper_search(f'site:brokercheck.finra.org "{name}"', 3)
        return {"source": "finra_serper", "error": str(e), "total": 0,
                "results": [{"title": r["title"], "url": r["url"]} for r in hits[:3]]}


# ── USPTO Trademark Search ────────────────────────────────────────────────────────
def uspto_trademark_search(name: str) -> dict:
    """Search USPTO for trademark registrations."""
    results = serper_search(f'site:tmsearch.uspto.gov "{name}" trademark registration', 5)
    tess_hits = [r for r in results if "uspto.gov" in r.get("url", "")]
    results2 = serper_search(f'"{name}" trademark registered USPTO brand', 5)
    all_hits = tess_hits + results2
    trademarks = []
    seen = set()
    for r in all_hits[:6]:
        url = r.get("url", "")
        if url not in seen:
            seen.add(url)
            trademarks.append({
                "title": r.get("title", ""),
                "url": url,
                "snippet": r.get("content", "")[:200]
            })
    return {
        "source": "uspto_trademark",
        "found": bool(tess_hits),
        "results": trademarks[:5]
    }


# ── BBB Direct Lookup ────────────────────────────────────────────────────────────
def bbb_lookup(name: str, state: str = None) -> dict:
    """Scrape BBB profile for rating, complaints, accreditation."""
    query = f'site:bbb.org "{name}" rating complaints'
    if state:
        query += f" {state}"
    results = serper_search(query, 5)
    bbb_hits = [r for r in results if "bbb.org" in r.get("url", "")]
    result = {"source": "bbb.org", "found": bool(bbb_hits), "url": None,
              "rating": None, "complaints": None, "accredited": None}
    for r in bbb_hits[:2]:
        snippet = r.get("content", "")
        result["url"] = r.get("url")
        m = re.search(r'\b([AF][+-]?)\b', snippet)
        if m:
            result["rating"] = m.group(1)
        m2 = re.search(r'(\d+)\s+complaint', snippet, re.IGNORECASE)
        if m2:
            result["complaints"] = int(m2.group(1))
        if "accredited" in snippet.lower():
            result["accredited"] = True
        result["snippet"] = snippet[:300]
        if result["rating"]:
            break
    return result


# ── Ripoff Report ────────────────────────────────────────────────────────────────
def ripoffreport_lookup(name: str) -> dict:
    """Search Ripoff Report for complaints."""
    results = serper_search(f'site:ripoffreport.com "{name}"', 5)
    rr_hits = [r for r in results if "ripoffreport.com" in r.get("url", "")]
    return {
        "source": "ripoffreport.com",
        "found": bool(rr_hits),
        "complaint_count": len(rr_hits),
        "complaints": [{"title": r.get("title", ""), "url": r.get("url", ""),
                        "snippet": r.get("content", "")[:200]} for r in rr_hits[:4]]
    }


# ── EU + UN Sanctions Check ──────────────────────────────────────────────────────
def eu_un_sanctions_check(name: str) -> dict:
    """Check EU Consolidated Sanctions List + UN Sanctions via Serper."""
    queries = [
        f'"European Union" sanctions list "{name}" consolidated',
        f'site:sanctionsmap.eu "{name}"',
        f'"United Nations" sanctions "{name}" committee',
        f'site:un.org/securitycouncil/sanctions "{name}"',
    ]
    all_results = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {ex.submit(serper_search, q, 3): q for q in queries}
        for f in as_completed(futures):
            try:
                all_results.extend(f.result())
            except Exception:
                pass
    eu_hits = [r for r in all_results if any(d in r.get("url", "")
               for d in ["europa.eu", "un.org", "sanctionsmap.eu", "sanctionslist"])]
    has_hit = bool(eu_hits)
    return {
        "source": "eu_un_sanctions_serper",
        "status": "HIT_POSSIBLE" if has_hit else "CLEAR",
        "hits": [{"title": r.get("title", ""), "url": r.get("url", ""),
                  "snippet": r.get("content", "")[:200]} for r in eu_hits[:3]]
    }


# ── Voter Registration Lookup ────────────────────────────────────────────────────
def voter_registration_lookup(name: str, state: str = "FL") -> dict:
    """Search public voter registration records — confirms identity and address."""
    queries = [
        f'"{name}" voter registration {state} public record',
        f'"{name}" registered voter {state} address party',
    ]
    all_results = []
    for q in queries[:2]:
        all_results.extend(serper_search(q, 4))
    voter_hits = []
    for r in all_results:
        snippet = r.get("content", "").lower()
        if any(w in snippet for w in ["registered", "voter", "party", "precinct",
                                       "democrat", "republican", "independent"]):
            voter_hits.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("content", "")[:200]
            })
    return {
        "source": "voter_registration_serper",
        "found": bool(voter_hits),
        "state": state,
        "records": voter_hits[:3]
    }


# ── Confidence Scoring ───────────────────────────────────────────────────────────
def score_report_confidence(report: dict) -> dict:
    """Add data confidence scores to each major report section."""
    scores = {}

    # Corporate records confidence
    cr = report.get("corporate_records", {})
    cr_fields = ["legal_name", "document_number", "ein_fein", "status", "principal_address"]
    cr_filled = sum(1 for f in cr_fields if cr.get(f))
    scores["corporate_records"] = {
        "score": round(cr_filled / len(cr_fields) * 100),
        "level": "VERIFIED" if cr_filled >= 4 else "PROBABLE" if cr_filled >= 2 else "UNVERIFIED",
        "fields_confirmed": cr_filled,
        "fields_total": len(cr_fields)
    }

    # Identity confidence
    people = report.get("people", [])
    officers = cr.get("officers_managers", [])
    id_score = min(100, len(people) * 35 + (30 if officers else 0))
    scores["identity"] = {
        "score": id_score,
        "level": "VERIFIED" if id_score >= 70 else "PROBABLE" if id_score >= 35 else "UNVERIFIED",
        "people_found": len(people),
        "officers_found": len(officers)
    }

    # Online presence confidence
    sm = report.get("social_media", {})
    mp = report.get("marketplace_presence", {})
    di = report.get("domain_intel", {})
    online_signals = sum([
        bool(sm.get("instagram", {}).get("followers") if isinstance(sm.get("instagram"), dict) else sm.get("instagram")),
        bool(sm.get("linkedin", {}).get("url") if isinstance(sm.get("linkedin"), dict) else sm.get("linkedin")),
        bool(mp.get("ebay_seller", {}).get("feedback_score") if isinstance(mp.get("ebay_seller"), dict) else False),
        bool(mp.get("chrono24_seller", {}).get("listings_count") if isinstance(mp.get("chrono24_seller"), dict) else False),
        bool(di.get("age_years") if isinstance(di, dict) else False),
    ])
    scores["online_presence"] = {
        "score": min(100, online_signals * 20),
        "level": "VERIFIED" if online_signals >= 3 else "PROBABLE" if online_signals >= 1 else "UNVERIFIED",
        "signals_found": online_signals
    }

    # Legal compliance confidence
    ofac = report.get("ofac_status", {})
    fc = report.get("federal_cases", {})
    bk = report.get("bankruptcy", {})
    ofac_clear = ofac.get("status") == "CLEAR" if isinstance(ofac, dict) else False
    court_checked = fc.get("total_found") is not None if isinstance(fc, dict) else False
    bk_checked = bk.get("total_found") is not None if isinstance(bk, dict) else False
    scores["legal_compliance"] = {
        "score": (34 if ofac_clear else 0) + (33 if court_checked else 0) + (33 if bk_checked else 0),
        "level": "VERIFIED" if (ofac_clear and court_checked and bk_checked) else "PROBABLE" if court_checked else "UNVERIFIED",
        "ofac_checked": ofac_clear,
        "courts_checked": court_checked,
        "bankruptcy_checked": bk_checked
    }

    # Overall
    avg = sum(s["score"] for s in scores.values()) / max(len(scores), 1)
    scores["overall"] = {
        "score": round(avg),
        "level": "HIGH" if avg >= 70 else "MEDIUM" if avg >= 40 else "LOW",
        "note": "Confidence reflects data coverage, not risk level"
    }

    return scores


# ── Load OpenRouter Key ─────────────────────────────────────────────────────────
def load_openrouter_key() -> str:
    try:
        auth_path = os.path.expanduser(
            "~/.openclaw/agents/main/agent/auth-profiles.json"
        )
        with open(auth_path) as f:
            d = json.load(f)
        for p in d.get("profiles", {}).values():
            k = p.get("key", "")
            if k.startswith("sk-or"):
                return k
    except Exception:
        pass
    return os.environ.get("OPENROUTER_API_KEY", "")


# ── Haiku Synthesis ─────────────────────────────────────────────────────────────
def synthesize_with_haiku(target: str, target_type: str, raw_results: dict,
                           corporate_data: dict = None, notes: str = None) -> dict:
    # Compact search results
    context_parts = []
    for query, results in raw_results.items():
        context_parts.append(f"QUERY: {query}")
        for r in results[:3]:
            if "error" in r:
                continue
            context_parts.append(f"  [{r.get('title','')}] {r.get('url','')}")
            context_parts.append(f"  {r.get('content','')[:300]}")
    search_context = "\n".join(context_parts)[:10000]

    # Compact corporate registry data
    corp_context = ""
    if corporate_data:
        corp_parts = ["\n\n=== CORPORATE REGISTRY DATA (OFFICIAL) ==="]
        for source, data in corporate_data.items():
            corp_parts.append(f"\nSOURCE: {source}")
            corp_parts.append(json.dumps(data, indent=2)[:3000])
        corp_context = "\n".join(corp_parts)

    system_prompt = """You are an OSINT analyst specializing in corporate intelligence and due diligence.
Given web search results AND official corporate registry data, produce a structured intelligence report in JSON.

Output ONLY valid JSON with these exact fields:
{
  "target": "name/entity",
  "type": "company|person|watch",
  "summary": "2-3 sentence executive summary",
  "corporate_records": {
    "legal_name": null,
    "entity_type": null,
    "document_number": null,
    "ein_fein": null,
    "incorporation_date": null,
    "status": null,
    "registered_state": null,
    "principal_address": null,
    "registered_agent": null,
    "officers_managers": [],
    "parent_entities": [],
    "opencorporates_url": null
  },
  "key_facts": [],
  "people": [{"name": "", "role": "", "background": "", "red_flags": ""}],
  "locations": [],
  "online_presence": {
    "website": null,
    "instagram": null,
    "linkedin": null,
    "facebook": null,
    "ebay": null,
    "chrono24": null,
    "other": []
  },
  "financial_signals": {
    "claimed_revenue": null,
    "revenue_verified": false,
    "ucc_liens": null,
    "judgments": null,
    "bankruptcies": null
  },
  "legal_history": [],
  "red_flags": [],
  "green_flags": [],
  "risk_rating": "LOW|MEDIUM|HIGH|CRITICAL",
  "risk_notes": "",
  "recommended_action": "",
  "eu_records": {
    "companies_house": null,
    "zefix": null,
    "pappers": null
  },
  "marketplace_presence": {
    "ebay_seller": {"url": null, "feedback_score": null, "positive_pct": null, "member_since": null, "items_count": null},
    "chrono24_seller": {"url": null, "listings_count": null, "location": null}
  },
  "forum_reputation": {
    "overall_sentiment": null,
    "watchuseek": null,
    "reddit": null,
    "trustpilot": null,
    "bbb": null,
    "mentions": []
  },
  "related_entities": [],
  "domain_info": {
    "domain": null,
    "age_years": null,
    "registrar": null,
    "privacy_protected": null
  },
  "phone_lookup": null,
  "ofac_status": {"status": "CLEAR|HIT|UNKNOWN", "matches": []},
  "federal_cases": {"total_found": 0, "cases": [], "news_mentions": []},
  "bankruptcy": {"total_found": 0, "filings": []},
  "us_state_registries": {},
  "sec_filings": {"total_hits": 0, "filings": []},
  "news_archive": [],
  "domain_intel": {"domain": null, "registered": null, "age_years": null, "registrar": null, "privacy_protected": null, "wayback_earliest_snapshot": null, "related_domains_via_ssl": []},
  "virtual_office": {"detected": false, "flags": []},
  "social_media": {
    "linkedin": {"url": null, "connections": null, "current_employer": null},
    "instagram": {"url": null, "followers": null, "posts": null, "handle": null},
    "google_business_rating": null,
    "google_review_count": null
  },
  "watch_platform_presence": {},
  "ebay_sold_history": {"listing_count": null, "prices": []},
  "fec_donations": {"total_donations": 0, "donations": []},
  "ppp_loans": {"found": false, "loans": []},
  "data_breach": {"breach_signals": 0, "mentions": []},
  "email_discovery": {"emails_found": [], "formats": []},
  "property_records": [],
  "data_gaps": [],
  "sources": []
}

Be precise. Use null for missing fields. Extract exact document numbers, EINs, addresses from registry data.
Populate eu_records from EU corporate registry data if present. Populate marketplace_presence from eBay/Chrono24 lookup data.
Populate forum_reputation from forum search results. Populate related_entities from related entity searches.
Populate ofac_status from OFAC check data. Populate federal_cases from CourtListener data and news mentions of lawsuits.
Populate bankruptcy from bankruptcy search data. Populate us_state_registries from state registry results.
Populate sec_filings from SEC EDGAR data. Populate news_archive from news search results.
Populate domain_intel from RDAP/Wayback/crt.sh data. Populate virtual_office from address analysis.
Populate social_media from LinkedIn/Instagram intel data. Populate watch_platform_presence from watch platform searches.
Populate ebay_sold_history from eBay sold listings. Populate fec_donations from FEC data.
Populate ppp_loans from PPP loan data. Populate data_breach from breach check results.
Populate email_discovery from email search results. Populate property_records from property searches."""

    extra_context = ""
    if corporate_data.get("theharvester"):
        th = corporate_data["theharvester"]
        extra_context += f"\n=== THEHARVESTER RESULTS ===\nEmails: {th.get('emails_found', [])}\nSubdomains: {th.get('subdomains', [])}\n"
    if corporate_data.get("holehe_check"):
        he = corporate_data["holehe_check"]
        extra_context += f"\n=== EMAIL PLATFORM REGISTRATIONS (holehe) ===\nEmail {he.get('email')} registered on: {he.get('registered_on', [])}\n"
    if corporate_data.get("username_osint"):
        uo = corporate_data["username_osint"]
        extra_context += f"\n=== USERNAME PRESENCE (maigret) ===\nHandle @{uo.get('handle')} found on: {[s['site'] for s in uo.get('found_on', [])]}\n"
    if corporate_data.get("phone_deep"):
        pd = corporate_data["phone_deep"]
        extra_context += f"\n=== PHONE INTEL ===\n{json.dumps(pd)}\n"
    if corporate_data.get("h8mail_breach"):
        hm = corporate_data["h8mail_breach"]
        extra_context += f"\n=== EMAIL BREACH (h8mail) ===\nBreaches found: {hm.get('breaches_found')}\nData: {hm.get('breach_data',[])}\n"
    if corporate_data.get("ghunt_google"):
        gh = corporate_data["ghunt_google"]
        extra_context += f"\n=== GOOGLE ACCOUNT (ghunt) ===\n{json.dumps(gh)[:500]}\n"
    if corporate_data.get("whatweb_scan"):
        ww = corporate_data["whatweb_scan"]
        extra_context += f"\n=== WEBSITE TECH STACK (whatweb) ===\nTechnologies: {ww.get('technologies',[])}\n"
    if corporate_data.get("nmap_scan"):
        nm = corporate_data["nmap_scan"]
        ports = nm.get("open_ports",[])
        if ports:
            extra_context += f"\n=== NETWORK EXPOSURE (nmap) ===\nOpen ports: {ports}\n"
    for key in corporate_data:
        if key.startswith("socialscan_"):
            sc = corporate_data[key]
            if sc.get("registered_on"):
                extra_context += f"\n=== SOCIAL PRESENCE (socialscan: {sc.get('query')}) ===\nRegistered on: {sc.get('registered_on',[])}\n"
        if key.startswith("instaloader_"):
            ig = corporate_data[key]
            if not ig.get("error"):
                extra_context += (f"\n=== INSTAGRAM DEEP DATA (instaloader) ===\n"
                    f"Handle: @{ig.get('handle')} | Name: {ig.get('full_name')} | "
                    f"Followers: {ig.get('followers'):,} | Posts: {ig.get('posts')} | "
                    f"Private: {ig.get('is_private')} | Verified: {ig.get('is_verified')} | "
                    f"Business: {ig.get('is_business')} | Category: {ig.get('business_category')}\n"
                    f"Bio: {ig.get('biography','')}\n"
                    f"External URL: {ig.get('external_url','')}\n")
    if corporate_data.get("wayback_history"):
        wb = corporate_data["wayback_history"]
        if wb.get("found"):
            extra_context += (f"\n=== DOMAIN HISTORY (Wayback Machine) ===\n"
                f"Total snapshots: {wb.get('total_snapshots')} | "
                f"First seen: {wb.get('oldest_snapshot')} | "
                f"Last seen: {wb.get('newest_snapshot')}\n"
                f"Oldest archive: {wb.get('oldest_url')}\n")
        else:
            extra_context += f"\n=== DOMAIN HISTORY === Domain not found in Wayback Machine (new/scrubbed)\n"
    if corporate_data.get("finra"):
        extra_context += f"\n=== FINRA BROKERCHECK ===\n{json.dumps(corporate_data['finra'])}\n"
    if corporate_data.get("bbb"):
        extra_context += f"\n=== BBB PROFILE ===\n{json.dumps(corporate_data['bbb'])}\n"
    if corporate_data.get("ripoffreport"):
        extra_context += f"\n=== RIPOFF REPORT ===\n{json.dumps(corporate_data['ripoffreport'])}\n"
    if corporate_data.get("eu_un_sanctions"):
        extra_context += f"\n=== EU/UN SANCTIONS ===\n{json.dumps(corporate_data['eu_un_sanctions'])}\n"
    if corporate_data.get("voter_registration"):
        extra_context += f"\n=== VOTER REGISTRATION ===\n{json.dumps(corporate_data['voter_registration'])}\n"
    if corporate_data.get("uspto_trademark"):
        extra_context += f"\n=== USPTO TRADEMARK ===\n{json.dumps(corporate_data['uspto_trademark'])}\n"
    if corporate_data.get("us_national_registry"):
        extra_context += f"\n=== US NATIONAL BUSINESS REGISTRY (OpenCorporates/SAM.gov/State/EDGAR) ===\n{json.dumps(corporate_data['us_national_registry'])}\n"
    if corporate_data.get("state_courts"):
        extra_context += f"\n=== STATE COURT RECORDS ===\n{json.dumps(corporate_data['state_courts'])}\n"
    if corporate_data.get("icij"):
        d = corporate_data["icij"]
        if d.get("found"):
            extra_context += f"\n=== ⚠️ ICIJ OFFSHORE LEAKS HIT ===\n{json.dumps(d)}\n"
    if corporate_data.get("federal_enforcement"):
        d = corporate_data["federal_enforcement"]
        if d.get("has_findings"):
            extra_context += f"\n=== ⚠️ FEDERAL ENFORCEMENT ACTIONS ===\n{json.dumps(d)}\n"
    if corporate_data.get("pro_licenses"):
        extra_context += f"\n=== PROFESSIONAL LICENSES ===\n{json.dumps(corporate_data['pro_licenses'])}\n"
    if corporate_data.get("cfpb"):
        extra_context += f"\n=== CFPB COMPLAINTS ===\n{json.dumps(corporate_data['cfpb'])}\n"
    if corporate_data.get("employer_reviews"):
        extra_context += f"\n=== EMPLOYER REVIEWS (Glassdoor/Indeed) ===\n{json.dumps(corporate_data['employer_reviews'])}\n"
    if corporate_data.get("crunchbase"):
        extra_context += f"\n=== CRUNCHBASE / STARTUP INTEL ===\n{json.dumps(corporate_data['crunchbase'])}\n"
    if corporate_data.get("usaspending"):
        extra_context += f"\n=== USA SPENDING / GOVT CONTRACTS ===\n{json.dumps(corporate_data['usaspending'])}\n"
    if corporate_data.get("interpol"):
        d = corporate_data["interpol"]
        if d.get("has_any_hits") or d.get("red_notice_found"):
            extra_context += f"\n=== ⚠️ INTERPOL / FUGITIVE CHECK ===\n{json.dumps(d)}\n"
    if corporate_data.get("breach_directory"):
        d = corporate_data["breach_directory"]
        if d.get("breaches_found"):
            extra_context += f"\n=== DATA BREACH HITS ===\n{json.dumps(d)}\n"

    # Build rich context block from all intake fields
    intake_lines = []
    for field, val in (corporate_data.get("_intake_ctx") or {}).items():
        if val:
            intake_lines.append(f"  {field}: {val}")
    if notes:
        intake_lines.append(f"  analyst_notes: {notes}")
    notes_context = ("\n\n=== INTAKE CONTEXT (analyst-provided) ===\n" + "\n".join(intake_lines) + "\n") if intake_lines else ""

    user_prompt = f"""OSINT target: {target} (type: {target_type})

=== WEB SEARCH RESULTS ===
{search_context}
{corp_context}
{extra_context}
{notes_context}
Produce the complete JSON report now."""

    payload = json.dumps({
        "model": SYNTH_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 6000,
    }).encode()

    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {OPENROUTER_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://jarvis.local",
            "X-Title": "Jarvis OSINT Engine",
        },
    )
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        data = json.loads(resp.read())
        content = data["choices"][0]["message"]["content"].strip()
        usage = data.get("usage", {})

        # Parse JSON from response
        # Strip markdown code fences if present
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        content = content.strip()

        report = json.loads(content)
        haiku_cost = round(
            usage.get("prompt_tokens", 0) * 0.00000025
            + usage.get("completion_tokens", 0) * 0.00000125,
            6,
        )
        serper_cost = round(SERPER_CREDITS_USED * 0.001, 4)
        report["_meta"] = {
            "model": SYNTH_MODEL,
            "tokens_in": usage.get("prompt_tokens", 0),
            "tokens_out": usage.get("completion_tokens", 0),
            "haiku_cost_usd": haiku_cost,
            "serper_credits_used": SERPER_CREDITS_USED,
            "serper_cost_usd": serper_cost,
            "total_cost_usd": round(haiku_cost + serper_cost, 4),
            "queries_run": len(raw_results),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        # Add confidence scoring
        try:
            report["confidence_scores"] = score_report_confidence(report)
        except Exception:
            pass
        return report
    except json.JSONDecodeError:
        # Try to salvage truncated JSON
        try:
            last_brace = content.rfind("}\n}")
            if last_brace > 0:
                content = content[:last_brace + 2]
                report = json.loads(content)
                report["_meta"] = {
                    "model": SYNTH_MODEL,
                    "note": "truncated_repaired",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                return report
        except Exception:
            pass
        return {"error": "JSON parse failed — response truncated", "raw": content[-300:]}
    except Exception as e:
        return {"error": str(e)}


# ── Pretty Print ────────────────────────────────────────────────────────────────
def print_report(report: dict):
    if "error" in report and "target" not in report:
        print(f"\n❌ Error: {report['error']}")
        return

    risk_emoji = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🔴", "CRITICAL": "🚨"}.get(
        report.get("risk_rating", ""), "⚪"
    )

    print("\n" + "="*62)
    print(f"  OSINT: {report.get('target', 'Unknown')}")
    print("="*62)
    print(f"\n📋 SUMMARY\n{report.get('summary', 'N/A')}")

    # Corporate Records
    cr = report.get("corporate_records", {})
    if cr and any(v for v in cr.values() if v):
        print("\n🏛  CORPORATE RECORDS")
        fields = [
            ("legal_name",         "Legal Name"),
            ("entity_type",        "Type"),
            ("document_number",    "Doc #"),
            ("ein_fein",           "EIN/FEIN"),
            ("incorporation_date", "Incorporated"),
            ("status",             "Status"),
            ("registered_state",   "State"),
            ("principal_address",  "Address"),
            ("registered_agent",   "Reg. Agent"),
            ("opencorporates_url", "OpenCorp URL"),
        ]
        for key, label in fields:
            val = cr.get(key)
            if val:
                print(f"  {label:<20} {val}")
        if cr.get("officers_managers"):
            print(f"  {'Officers/Managers':<20}", end="")
            for o in cr["officers_managers"]:
                if isinstance(o, dict):
                    print(f"{o.get('name','?')} ({o.get('title','?')})", end="  ")
                else:
                    print(str(o), end="  ")
            print()
        if cr.get("parent_entities"):
            print(f"  {'Parent Entities':<20} {', '.join(cr['parent_entities'])}")

    if report.get("key_facts"):
        print("\n🔑 KEY FACTS")
        for f in report["key_facts"]:
            print(f"  • {f}")

    if report.get("people"):
        print("\n👤 PEOPLE")
        for p in report["people"]:
            flags = f" ⚠️ {p.get('red_flags')}" if p.get("red_flags") else ""
            print(f"  • {p.get('name')} — {p.get('role')} | {p.get('background','')}{flags}")

    if report.get("locations"):
        print("\n📍 LOCATIONS")
        for loc in report["locations"]:
            print(f"  • {loc}")

    op = report.get("online_presence", {})
    if op and any(v for v in op.values() if v):
        print("\n🌐 ONLINE PRESENCE")
        for k, v in op.items():
            if v and k != "other":
                print(f"  • {k:<12} {v}")
        for item in (op.get("other") or []):
            print(f"  • other       {item}")

    fs = report.get("financial_signals", {})
    if fs and any(v for v in fs.values() if v):
        print("\n💰 FINANCIAL SIGNALS")
        if fs.get("claimed_revenue"):
            verified = "✅ verified" if fs.get("revenue_verified") else "⚠️ unverified"
            print(f"  • Revenue: {fs['claimed_revenue']} ({verified})")
        for field in ("ucc_liens", "judgments", "bankruptcies"):
            if fs.get(field):
                print(f"  • {field.replace('_',' ').title()}: {fs[field]}")

    if report.get("legal_history"):
        print("\n⚖️  LEGAL HISTORY")
        for item in report["legal_history"]:
            print(f"  • {item}")

    if report.get("red_flags"):
        print("\n🚩 RED FLAGS")
        for f in report["red_flags"]:
            print(f"  ⚠️  {f}")

    if report.get("green_flags"):
        print("\n✅ GREEN FLAGS")
        for f in report["green_flags"]:
            print(f"  ✓  {f}")

    print(f"\n{risk_emoji} RISK: {report.get('risk_rating')} — {report.get('risk_notes')}")
    print(f"\n💡 NEXT STEP\n{report.get('recommended_action')}")

    # EU Records
    eu = report.get("eu_records", {})
    eu_data = {k: v for k, v in (eu or {}).items() if v}
    if eu_data:
        print("\n🇪🇺 EU CORPORATE RECORDS")
        for reg, val in eu_data.items():
            if isinstance(val, dict):
                for item in (val.get("results") or [val])[:2]:
                    name = item.get("name","")
                    num = item.get("company_number") or item.get("uid") or item.get("siren","")
                    status = item.get("status","")
                    addr = item.get("address") or item.get("municipality","")
                    print(f"  [{reg.upper()}] {name} | #{num} | {status} | {addr}")
            else:
                print(f"  {reg}: {val}")

    # Marketplace presence
    mp = report.get("marketplace_presence", {})
    if mp and any(v for v in mp.values() if v):
        print("\n🛒 MARKETPLACE PRESENCE")
        ebay = mp.get("ebay_seller", {})
        if ebay and ebay.get("feedback_score"):
            print(f"  eBay: {ebay.get('feedback_score')} feedback | {ebay.get('positive_pct','?')}% positive | since {ebay.get('member_since','?')} | {ebay.get('items_count','?')} items")
            if ebay.get("url"):
                print(f"  URL: {ebay['url']}")
        c24 = mp.get("chrono24_seller", {})
        if c24 and c24.get("listings_count"):
            print(f"  Chrono24: {c24.get('listings_count')} listings | {c24.get('location','')}")
            if c24.get("url"):
                print(f"  URL: {c24['url']}")

    # Forum reputation
    fr = report.get("forum_reputation", {})
    if fr and fr.get("overall_sentiment") and fr.get("overall_sentiment") != "none":
        sentiment_emoji = {"positive": "✅", "negative": "⚠️", "mixed": "🟡"}.get(fr.get("overall_sentiment",""), "⚪")
        print(f"\n💬 FORUM & REVIEW REPUTATION: {sentiment_emoji} {(fr.get('overall_sentiment') or '').upper()}")
        for m in (fr.get("mentions") or [])[:4]:
            if isinstance(m, dict):
                print(f"  • {m.get('title','')} — {m.get('url','')}")
            else:
                print(f"  • {m}")

    # Related entities
    re_data = report.get("related_entities", [])
    if re_data:
        print("\n🔗 RELATED ENTITIES")
        for ent in re_data[:5]:
            if isinstance(ent, dict):
                name = ent.get("name") or ent.get("title","")
                rel = ent.get("relationship","")
                src = ent.get("source") or ent.get("url","")
                print(f"  • {name} {('— ' + rel) if rel else ''} | {src}")

    # Domain info
    di = report.get("domain_info", {})
    if di and any(v for v in di.values() if v):
        print("\n🌍 DOMAIN INFO")
        if di.get("domain"):
            print(f"  Domain: {di['domain']}")
        if di.get("age_years"):
            print(f"  Age: {di['age_years']} years")
        if di.get("registrar"):
            print(f"  Registrar: {di['registrar']}")
        if di.get("privacy_protected") is not None:
            print(f"  Privacy: {'Protected' if di['privacy_protected'] else 'Public'}")

    # OFAC
    ofac = report.get("ofac_status", {})
    if ofac:
        status = ofac.get("status","UNKNOWN")
        emoji = "🟢" if status == "CLEAR" else "🔴" if status == "HIT" else "⚪"
        print(f"\n🏦 OFAC SANCTIONS: {emoji} {status}")
        if ofac.get("matches"):
            for m in ofac["matches"]:
                print(f"  ⚠️  MATCH: {m.get('name')} | Score: {m.get('score')} | Programs: {m.get('programs')}")

    # Federal courts
    fc = report.get("federal_cases", {})
    if fc:
        total = fc.get("total_found", 0)
        if total or fc.get("cases") or fc.get("news_mentions"):
            print(f"\n⚖️  FEDERAL COURT RECORDS: {total} case(s) found")
            for c in (fc.get("cases") or [])[:4]:
                if isinstance(c, dict):
                    print(f"  • {c.get('case_name','')} | {c.get('court','')} | Filed: {c.get('date_filed','')}")
                    if c.get("url"):
                        print(f"    {c['url']}")
            if fc.get("news_mentions"):
                print("  News mentions:")
                for n in fc["news_mentions"][:3]:
                    if isinstance(n, dict):
                        print(f"  • {n.get('title','')} — {n.get('url','')}")

    # Bankruptcy
    bk = report.get("bankruptcy", {})
    if bk and (bk.get("total_found",0) or bk.get("filings") or bk.get("serper_mentions")):
        print(f"\n💸 BANKRUPTCY: {bk.get('total_found',0)} filing(s)")
        for f_ in (bk.get("filings") or [])[:3]:
            if isinstance(f_, dict):
                print(f"  • {f_.get('case_name','')} | Ch.{f_.get('chapter','')} | {f_.get('date_filed','')}")

    # News archive
    news = report.get("news_archive", [])
    if news:
        print(f"\n📰 NEWS ARCHIVE ({len(news)} articles)")
        for a in (news if isinstance(news, list) else [])[:5]:
            if isinstance(a, dict):
                print(f"  • {a.get('title','')} — {a.get('url','')}")

    # US State registries
    states = report.get("us_state_registries", {})
    if states and any(v for v in states.values() if v):
        print("\n🏛️  US STATE REGISTRIES")
        for state, hits in states.items():
            if hits and isinstance(hits, list):
                for h in hits[:2]:
                    if isinstance(h, dict):
                        print(f"  [{state.upper()}] {h.get('title','')} — {h.get('url','')}")

    # SEC filings
    sec = report.get("sec_filings", {})
    if sec and sec.get("total_hits",0):
        print(f"\n📈 SEC EDGAR: {sec.get('total_hits',0)} filing(s)")
        for f_ in (sec.get("filings") or [])[:3]:
            if isinstance(f_, dict):
                print(f"  • {f_.get('entity','')} | {f_.get('form','')} | {f_.get('date','')}")

    # Virtual office
    vo = report.get("virtual_office", {})
    if vo and vo.get("detected"):
        print("\n⚠️  VIRTUAL OFFICE DETECTED")
        for flag in (vo.get("flags") or [])[:3]:
            if isinstance(flag, dict):
                print(f"  ⚠️  {flag.get('address','')} — signal: '{flag.get('signal','')}'")

    # Social media
    sm = report.get("social_media", {})
    if sm and any(v for v in sm.values() if v):
        print("\n📱 SOCIAL MEDIA")
        li = sm.get("linkedin", {})
        if li and (li.get("url") or li.get("connections")):
            print(f"  LinkedIn: {li.get('url','')} | Connections: {li.get('connections','?')} | Employer: {li.get('current_employer','?')}")
        ig = sm.get("instagram", {})
        if ig and (ig.get("url") or ig.get("followers")):
            print(f"  Instagram: {ig.get('url','')} | Followers: {ig.get('followers','?')} | Posts: {ig.get('posts','?')}")
        if sm.get("google_business_rating"):
            print(f"  Google Business: {sm['google_business_rating']}⭐ ({sm.get('google_review_count','?')} reviews)")

    # Watch platform presence
    wp = report.get("watch_platform_presence", {})
    if wp:
        found_platforms = [p for p, v in wp.items() if isinstance(v, dict) and v.get("found")]
        missing_platforms = [p for p, v in wp.items() if isinstance(v, dict) and not v.get("found")]
        if found_platforms or missing_platforms:
            print("\n⌚ WATCH PLATFORM PRESENCE")
            for p in found_platforms:
                v = wp[p]
                print(f"  ✅ {p}: {v.get('top_url','')}")
            for p in missing_platforms:
                print(f"  ❌ {p}: not found")

    # eBay sold history
    es = report.get("ebay_sold_history", {})
    if es and es.get("listing_count"):
        print(f"\n💰 EBAY SOLD HISTORY: {es.get('listing_count',0)} listings found")
        if es.get("prices"):
            print(f"  Prices seen: {', '.join(es['prices'][:6])}")

    # FEC donations
    fec = report.get("fec_donations", {})
    if fec and fec.get("total_donations",0):
        print(f"\n🗳️  FEC POLITICAL DONATIONS: {fec['total_donations']} total")
        for d in (fec.get("donations") or [])[:3]:
            if isinstance(d, dict):
                print(f"  • ${d.get('amount','?')} → {d.get('committee','?')} | {d.get('date','?')} | Employer: {d.get('employer','?')}")

    # PPP loans
    ppp = report.get("ppp_loans", {})
    if ppp and ppp.get("loans"):
        print(f"\n💵 PPP LOANS: {len(ppp.get('loans',[]))} found")
        for loan in (ppp.get("loans") or [])[:3]:
            if isinstance(loan, dict):
                print(f"  • {loan.get('business_name','?')} | ${loan.get('amount','?')} | Jobs: {loan.get('jobs_retained','?')} | {loan.get('state','?')}")

    # Data breach
    db = report.get("data_breach", {})
    if db and db.get("breach_signals",0):
        print(f"\n🔓 DATA BREACH SIGNALS: {db['breach_signals']} mention(s)")
        for m in (db.get("mentions") or [])[:3]:
            if isinstance(m, dict):
                print(f"  • {m.get('title','')} — {m.get('url','')}")

    # Email discovery
    ed = report.get("email_discovery", {})
    if ed and (ed.get("emails_found") or ed.get("formats")):
        print("\n📧 EMAIL INTEL")
        if ed.get("emails_found"):
            print(f"  Found: {', '.join(ed['emails_found'][:4])}")
        if ed.get("formats"):
            print(f"  Likely formats: {', '.join(ed['formats'][:3])}")

    # Property records
    pr = report.get("property_records", [])
    if pr:
        print(f"\n🏠 PROPERTY RECORDS: {len(pr)} record(s) found")
        for rec in (pr if isinstance(pr, list) else [])[:3]:
            if isinstance(rec, dict):
                print(f"  • {rec.get('title','')} — {rec.get('url','')}")

    if report.get("data_gaps"):
        print("\n🔍 DATA GAPS")
        for g in report["data_gaps"]:
            print(f"  • {g}")

    # v10 modules
    fed = report.get("federal_enforcement", {})
    if fed and fed.get("has_findings"):
        print(f"\n🏛️  FEDERAL ENFORCEMENT ACTIONS ⚠️")
        for agency, hits in (fed.get("findings") or {}).items():
            for h in hits[:2]:
                print(f"  [{agency}] {h.get('title','')} — {h.get('url','')}")

    icij = report.get("icij_offshore_leaks", {})
    if icij and icij.get("found"):
        print(f"\n🏝️  ICIJ OFFSHORE LEAKS ⚠️  FOUND")
        if icij.get("entities"):
            print(f"  Entities: {', '.join(icij['entities'][:4])}")
        for m in (icij.get("serper_mentions") or [])[:3]:
            print(f"  • {m.get('title','')} — {m.get('url','')}")
    else:
        print("\n🏝️  ICIJ Offshore Leaks: CLEAR")

    interp = report.get("interpol_check", {})
    if interp:
        if interp.get("red_notice_found"):
            print("\n🚨 INTERPOL RED NOTICE FOUND")
            for n in (interp.get("findings",{}).get("interpol_api") or [])[:2]:
                print(f"  • {n.get('name','')} | DOB: {n.get('dob','')} | Charges: {n.get('charges','')}")
        elif interp.get("has_any_hits"):
            print("\n⚠️  INTERPOL/FUGITIVE: Possible hits — verify manually")
        else:
            print("\n✅ Interpol/Fugitive: CLEAR")

    sc = report.get("state_courts", {})
    if sc and sc.get("total_results", 0):
        print(f"\n⚖️  STATE COURT RECORDS: {sc.get('total_results',0)} result(s)")
        for state_key, hits in (sc.get("results") or {}).items():
            for h in hits[:2]:
                print(f"  [{state_key.upper()}] {h.get('title','')} — {h.get('url','')}")

    cfpb = report.get("cfpb_complaints", {})
    if cfpb and cfpb.get("total_complaints", 0):
        print(f"\n📋 CFPB COMPLAINTS: {cfpb['total_complaints']} total")
        for c in (cfpb.get("complaints") or [])[:3]:
            print(f"  • {c.get('product','')} | {c.get('issue','')} | {c.get('date','')}")

    lic = report.get("professional_licenses", {})
    if lic and lic.get("revocation_signals"):
        print(f"\n⚠️  LICENSE CONCERNS: {', '.join(lic['revocation_signals'])}")

    er = report.get("employer_reviews", {})
    if er:
        if er.get("red_flags_in_reviews"):
            print(f"\n⚠️  EMPLOYEE REVIEW RED FLAGS: {', '.join(er['red_flags_in_reviews'])}")
        if er.get("ratings"):
            for k, v in list(er["ratings"].items())[:3]:
                if isinstance(v, float):
                    print(f"  {k}: {v}⭐")

    usa = report.get("usaspending_contracts", {})
    if usa and usa.get("contracts_found", 0):
        print(f"\n🏛️  GOVT CONTRACTS: {usa['contracts_found']} contract(s) | Total: ${usa.get('total_value',0):,.0f}")

    cb = report.get("crunchbase_intel", {})
    if cb and cb.get("funding_signals"):
        fs = cb["funding_signals"]
        print(f"\n💼 STARTUP/FUNDING: {fs.get('amount_str','?')} raised | Employees: {fs.get('employee_count','?')}")

    # Owner profiles
    op_data = report.get("owner_profiles", {})
    if op_data and op_data.get("owners_found"):
        print(f"\n👑 OWNER / PRINCIPAL PROFILES ({len(op_data['owners_found'])} found)")
        for owner in op_data.get("owners_found", []):
            print(f"  Identified: {owner}")
        for owner, profile in op_data.get("profiles", {}).items():
            sigs = profile.get("signal_summary", {})
            total = sigs.get("total_red_signal_count", 0)
            criminal = sigs.get("criminal_signals", [])
            fraud = sigs.get("fraud_signals", [])
            financial = sigs.get("financial_distress_signals", [])
            civil = sigs.get("civil_litigation_signals", [])
            print(f"\n  ── {owner} ──")
            if total == 0:
                print(f"  ✅ No red signals detected across {profile.get('queries_run',0)} searches")
            else:
                print(f"  ⚠️  {total} red signal(s) detected")
            if criminal:
                print(f"  🚨 Criminal: {', '.join(criminal[:5])}")
            if fraud:
                print(f"  🚨 Fraud: {', '.join(fraud[:5])}")
            if financial:
                print(f"  ⚠️  Financial distress: {', '.join(financial[:4])}")
            if civil:
                print(f"  ⚠️  Civil litigation: {', '.join(civil[:4])}")
            # Top results
            for category, key in [("Criminal/Legal", "criminal_legal"), ("Fraud", "fraud_financial_crime"),
                                    ("Civil", "civil_litigation"), ("Bankruptcy/Financial", "financial_distress"),
                                    ("News", "news_and_press")]:
                items = profile.get(key, [])
                if items:
                    print(f"  [{category}]")
                    for item in items[:3]:
                        print(f"    • {item.get('title','')} — {item.get('url','')}")

    # Confidence scores
    cs = report.get("confidence_scores", {})
    if cs:
        overall = cs.get("overall", {})
        print(f"\n📊 DATA CONFIDENCE: {overall.get('level','?')} ({overall.get('score',0)}/100)")
        for section, data in cs.items():
            if section != "overall" and isinstance(data, dict):
                level = data.get("level", "?")
                score = data.get("score", 0)
                emoji = "✅" if level == "VERIFIED" else "🟡" if level == "PROBABLE" else "⚪"
                print(f"  {emoji} {section.replace('_', ' ').title():<25} {level} ({score}/100)")

    meta = report.get("_meta", {})
    if meta:
        cache_note = " [CACHED]" if meta.get("cache_hit") else ""
        print(f"\n💸 TOTAL COST: ${meta.get('total_cost_usd', 0):.4f}{cache_note}")
        print(f"   ├─ Serper: {meta.get('serper_credits_used', 0)} credits × $0.001 = ${meta.get('serper_cost_usd', 0):.4f}")
        print(f"   ├─ Haiku:  {meta.get('tokens_in', 0)}in / {meta.get('tokens_out', 0)}out = ${meta.get('haiku_cost_usd', 0):.4f}")
        print(f"   └─ Queries fired: {meta.get('queries_run', 0)}")
    print("="*62 + "\n")


# ── Save Report ─────────────────────────────────────────────────────────────────
def save_report(report: dict, target: str):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    slug = target.lower().replace(" ", "_").replace("/", "_")[:40]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{slug}.json"
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w") as f:
        json.dump(report, f, indent=2)
    return path


# ── Main ────────────────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════
# v8 UPGRADES: Global Registry Intelligence + Deep Person Profiling
# ═══════════════════════════════════════════════════════════════════════════════

# ── Country Intelligence Engine ──────────────────────────────────────────────────
COUNTRY_SIGNALS = {
    "CA": {  # Canada
        "keywords": ["canada", "canadian", "ontario", "toronto", "vancouver", "montreal",
                     "alberta", "british columbia", "quebec", "inc.", "ltd.", "calgary",
                     "ottawa", "edmonton", "winnipeg", "halifax"],
        "registry_url": "https://www.ic.gc.ca/app/scr/cc/CorporationsCanada/fdrlCrpSrch.html",
        "registry_name": "Corporations Canada",
        "jurisdiction": "ca",
    },
    "AU": {  # Australia
        "keywords": ["australia", "australian", "sydney", "melbourne", "brisbane", "perth",
                     "adelaide", "pty ltd", "pty. ltd", "abn", "acn", "nsw", "victoria",
                     "queensland", "western australia"],
        "registry_url": "https://www.abr.business.gov.au/",
        "registry_name": "ASIC / ABN Lookup",
        "jurisdiction": "au",
    },
    "HK": {  # Hong Kong
        "keywords": ["hong kong", "hk", "kowloon", "central", "wan chai", "causeway bay",
                     "tsim sha tsui", "mong kok"],
        "registry_url": "https://www.cr.gov.hk/en/companies_registry/",
        "registry_name": "Hong Kong Companies Registry",
        "jurisdiction": "hk",
    },
    "SG": {  # Singapore
        "keywords": ["singapore", "sg", "pte ltd", "pte. ltd", "orchard", "raffles",
                     "marina bay", "jurong", "tampines"],
        "registry_url": "https://www.acra.gov.sg/",
        "registry_name": "ACRA Singapore",
        "jurisdiction": "sg",
    },
    "DE": {  # Germany
        "keywords": ["germany", "german", "deutschland", "gmbh", "ag", "berlin", "munich",
                     "münchen", "hamburg", "frankfurt", "cologne", "köln", "düsseldorf",
                     "stuttgart", "dortmund", "essen"],
        "registry_url": "https://www.unternehmensregister.de/",
        "registry_name": "Unternehmensregister Germany",
        "jurisdiction": "de",
    },
    "IT": {  # Italy
        "keywords": ["italy", "italian", "italia", "milan", "milano", "rome", "roma",
                     "florence", "firenze", "venice", "venezia", "naples", "napoli",
                     "turin", "torino", "s.r.l.", "s.p.a.", "srl", "spa"],
        "registry_url": "https://www.registro.it/",
        "registry_name": "Registro Imprese Italy",
        "jurisdiction": "it",
    },
    "NL": {  # Netherlands
        "keywords": ["netherlands", "dutch", "holland", "amsterdam", "rotterdam",
                     "the hague", "den haag", "eindhoven", "bv", "b.v.", "nv", "n.v."],
        "registry_url": "https://www.kvk.nl/",
        "registry_name": "KVK Netherlands Chamber of Commerce",
        "jurisdiction": "nl",
    },
    "JP": {  # Japan
        "keywords": ["japan", "japanese", "tokyo", "osaka", "kyoto", "yokohama",
                     "nagoya", "sapporo", "kobe", "kabushiki", "k.k.", "yugen"],
        "registry_url": "https://www.houjin-bangou.nta.go.jp/",
        "registry_name": "Japan Corporate Number",
        "jurisdiction": "jp",
    },
    "AE": {  # UAE / Dubai
        "keywords": ["uae", "dubai", "abu dhabi", "sharjah", "ajman", "emirates",
                     "difc", "freezone", "free zone", "jebel ali"],
        "registry_url": "https://www.dubaided.gov.ae/",
        "registry_name": "Dubai DED / UAE Registry",
        "jurisdiction": "ae",
    },
    "CH": {  # Switzerland (already have Zefix but expand)
        "keywords": ["switzerland", "swiss", "geneva", "zurich", "zürich", "basel",
                     "bern", "lugano", "lausanne", "ag", "gmbh", "sa", "sàrl"],
        "registry_url": "https://www.zefix.ch/",
        "registry_name": "Zefix Switzerland",
        "jurisdiction": "ch",
    },
    "UK": {  # UK (already have Companies House but expand)
        "keywords": ["uk", "united kingdom", "england", "scotland", "wales", "london",
                     "manchester", "birmingham", "leeds", "glasgow", "ltd", "plc",
                     "limited", "llp"],
        "registry_url": "https://find-and-update.company-information.service.gov.uk/",
        "registry_name": "Companies House UK",
        "jurisdiction": "gb",
    },
    "FR": {  # France (already have PAPPERS but expand)
        "keywords": ["france", "french", "paris", "lyon", "marseille", "toulouse",
                     "nice", "bordeaux", "nantes", "strasbourg", "sarl", "sas", "sa"],
        "registry_url": "https://www.pappers.fr/",
        "registry_name": "PAPPERS France",
        "jurisdiction": "fr",
    },
}

def detect_country(target: str, country_hint: str = None) -> list:
    """
    Detect likely country/countries from target name + optional hint.
    Returns list of detected country codes, US always included as fallback.
    """
    detected = set()

    # Explicit hint overrides
    if country_hint:
        hint_upper = country_hint.upper()
        # Map common aliases
        alias_map = {
            "UK": "UK", "GB": "UK", "ENGLAND": "UK", "BRITAIN": "UK",
            "CH": "CH", "SWISS": "CH", "SWITZERLAND": "CH",
            "FR": "FR", "FRANCE": "FR",
            "DE": "DE", "GERMANY": "DE", "DEUTSCH": "DE",
            "CA": "CA", "CANADA": "CA",
            "AU": "AU", "AUSTRALIA": "AU",
            "HK": "HK", "HONGKONG": "HK", "HONG KONG": "HK",
            "SG": "SG", "SINGAPORE": "SG",
            "IT": "IT", "ITALY": "IT",
            "NL": "NL", "NETHERLANDS": "NL", "DUTCH": "NL",
            "JP": "JP", "JAPAN": "JP",
            "AE": "AE", "UAE": "AE", "DUBAI": "AE",
            "US": "US", "USA": "US", "UNITED STATES": "US",
        }
        for key, val in alias_map.items():
            if key in hint_upper:
                detected.add(val)

    # Keyword scan on target name
    target_lower = target.lower()
    for country_code, config in COUNTRY_SIGNALS.items():
        for kw in config["keywords"]:
            if kw in target_lower:
                detected.add(country_code)
                break

    # Always check US + OpenCorporates globally
    detected.add("US")

    return list(detected)


def global_registry_search(company_name: str, countries: list) -> dict:
    """
    Hit the right corporate registries based on detected countries.
    Uses direct APIs where available, Serper as fallback.
    """
    results = {}

    for country in countries:
        if country == "US":
            continue  # handled by Sunbiz + OpenCorporates already
        if country == "UK":
            continue  # handled by companies_house_lookup already
        if country == "CH":
            continue  # handled by zefix_lookup already
        if country == "FR":
            continue  # handled by pappers_lookup already

        config = COUNTRY_SIGNALS.get(country, {})
        registry_name = config.get("registry_name", country)
        jurisdiction = config.get("jurisdiction", country.lower())

        # OpenCorporates covers most jurisdictions via API
        oc = opencorporates_lookup(company_name, None)
        if oc.get("results"):
            results[f"opencorporates_{country.lower()}"] = oc

        # Jurisdiction-specific approaches
        if country == "CA":
            hits = serper_search(
                f'site:corporationscanada.ic.gc.ca "{company_name}" OR '
                f'"{company_name}" canada corporation registration business number', 5
            )
            results["canada_registry"] = {
                "source": registry_name,
                "results": [{"title": r["title"], "url": r["url"], "snippet": r.get("content","")[:200]}
                            for r in hits[:4] if r.get("url")]
            }
            # Also check province-level (Ontario is biggest)
            hits2 = serper_search(f'"{company_name}" ontario business registry OR alberta registry OR BC registry', 4)
            if hits2:
                results["canada_provincial"] = {
                    "source": "Canada Provincial Registries",
                    "results": [{"title": r["title"], "url": r["url"], "snippet": r.get("content","")[:200]}
                                for r in hits2[:3] if r.get("url")]
                }

        elif country == "AU":
            # ASIC free API
            encoded = urllib.parse.quote(company_name)
            try:
                url = f"https://api.asic.gov.au/v1/company/search?q={encoded}"
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
                resp = urllib.request.urlopen(req, timeout=15)
                data = json.loads(resp.read())
                results["asic_australia"] = {"source": "ASIC Australia", "data": data}
            except Exception:
                # Fallback to ABN lookup via Serper
                hits = serper_search(f'site:abr.business.gov.au "{company_name}" OR "{company_name}" ABN ACN australia company', 5)
                results["australia_registry"] = {
                    "source": registry_name,
                    "results": [{"title": r["title"], "url": r["url"], "snippet": r.get("content","")[:200]}
                                for r in hits[:4] if r.get("url")]
                }

        elif country == "HK":
            hits = serper_search(f'site:cr.gov.hk "{company_name}" OR "{company_name}" hong kong company registration CR number', 5)
            results["hongkong_registry"] = {
                "source": registry_name,
                "results": [{"title": r["title"], "url": r["url"], "snippet": r.get("content","")[:200]}
                            for r in hits[:4] if r.get("url")]
            }

        elif country == "SG":
            # ACRA via Serper
            hits = serper_search(f'site:acra.gov.sg "{company_name}" OR "{company_name}" singapore UEN company registration', 5)
            results["singapore_acra"] = {
                "source": registry_name,
                "results": [{"title": r["title"], "url": r["url"], "snippet": r.get("content","")[:200]}
                            for r in hits[:4] if r.get("url")]
            }

        elif country == "DE":
            # Unternehmensregister via Serper
            hits = serper_search(f'site:unternehmensregister.de "{company_name}" OR "{company_name}" handelsregister germany HRB HRA', 5)
            results["germany_registry"] = {
                "source": registry_name,
                "results": [{"title": r["title"], "url": r["url"], "snippet": r.get("content","")[:200]}
                            for r in hits[:4] if r.get("url")]
            }

        elif country == "IT":
            hits = serper_search(f'"{company_name}" registro imprese italy codice fiscale partita IVA', 5)
            results["italy_registry"] = {
                "source": registry_name,
                "results": [{"title": r["title"], "url": r["url"], "snippet": r.get("content","")[:200]}
                            for r in hits[:4] if r.get("url")]
            }

        elif country == "NL":
            hits = serper_search(f'site:kvk.nl "{company_name}" OR "{company_name}" KVK netherlands chamber of commerce', 5)
            results["netherlands_kvk"] = {
                "source": registry_name,
                "results": [{"title": r["title"], "url": r["url"], "snippet": r.get("content","")[:200]}
                            for r in hits[:4] if r.get("url")]
            }

        elif country == "JP":
            hits = serper_search(f'"{company_name}" japan corporate number houjin touki', 5)
            results["japan_registry"] = {
                "source": registry_name,
                "results": [{"title": r["title"], "url": r["url"], "snippet": r.get("content","")[:200]}
                            for r in hits[:4] if r.get("url")]
            }

        elif country == "AE":
            hits = serper_search(f'"{company_name}" UAE license DED trade license dubai company formation', 5)
            results["uae_registry"] = {
                "source": registry_name,
                "results": [{"title": r["title"], "url": r["url"], "snippet": r.get("content","")[:200]}
                            for r in hits[:4] if r.get("url")]
            }

    return {"source": "global_registry_engine", "countries_checked": countries, "registries": results}


# ── Deep Person Profile Module ────────────────────────────────────────────────────
def deep_person_profile(name: str, company: str = None, location: str = None,
                         email: str = None, phone: str = None, url: str = None) -> dict:
    """
    Full deep-dive on an individual. Runs 25+ targeted person-specific searches
    covering criminal, financial, civil, professional, and reputational history.
    """
    loc_ctx = f" {location}" if location else ""
    co_ctx  = f' "{company}"' if company else ""

    queries = [
        # Criminal & legal
        f'"{name}" arrested charged indicted criminal court',
        f'"{name}" mugshot arrest record police',
        f'"{name}" conviction sentenced probation parole felony misdemeanor',
        f'"{name}" restraining order domestic violence',
        f'"{name}"{co_ctx} fraud wire fraud money laundering scheme',
        f'"{name}" securities fraud ponzi scheme investment fraud',
        # Civil litigation
        f'"{name}" lawsuit sued plaintiff defendant civil court{loc_ctx}',
        f'"{name}" judgment lien debt collection garnishment',
        f'"{name}" divorce proceedings asset division court filing',
        f'"{name}"{co_ctx} breach of contract dispute settlement',
        # Financial
        f'"{name}" bankruptcy chapter 7 11 petition filed',
        f'"{name}" tax lien IRS delinquent federal state',
        f'"{name}" foreclosure property seized repossessed',
        f'"{name}" net worth wealth assets estimated',
        # Professional history
        f'"{name}" professional background career history employer',
        f'"{name}"{co_ctx} CEO founder owner director officer role',
        f'"{name}" fired terminated resigned controversy',
        f'"{name}" license revoked suspended disciplinary action',
        # Reputation & news
        f'"{name}" complaint review scam warning fraud alert',
        f'"{name}" news article press 2023 2024 2025 2026',
        f'"{name}" expose investigation journalist report',
        # Personal identity verification
        f'"{name}"{loc_ctx} age born birthday DOB',
        f'"{name}"{loc_ctx} home address property owner{loc_ctx}',
        # Corporate connections
        f'"{name}" company director shareholder board member',
        f'site:opencorporates.com "{name}"',
    ]

    # Run all queries in parallel
    all_results = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(serper_search, q, 5): q for q in queries}
        for f in as_completed(futures):
            q = futures[f]
            try:
                all_results[q] = f.result()
            except Exception:
                all_results[q] = []

    # Extract structured signals
    all_snippets = " ".join(
        r.get("content","") + " " + r.get("title","")
        for results in all_results.values()
        for r in results
    ).lower()

    # Criminal signals
    criminal_keywords = ["arrested", "charged", "indicted", "convicted", "sentenced",
                         "felony", "misdemeanor", "mugshot", "probation", "parole",
                         "criminal record", "police", "defendant criminal"]
    criminal_hits = [kw for kw in criminal_keywords if kw in all_snippets]

    # Fraud signals
    fraud_keywords = ["fraud", "ponzi", "scheme", "scam", "wire fraud", "money laundering",
                      "securities violation", "sec enforcement", "finra bar", "indicted"]
    fraud_hits = [kw for kw in fraud_keywords if kw in all_snippets]

    # Financial distress signals
    financial_distress = ["bankruptcy", "chapter 7", "chapter 11", "foreclosure",
                          "tax lien", "irs lien", "judgment", "garnishment", "repossessed"]
    financial_hits = [kw for kw in financial_distress if kw in all_snippets]

    # Civil litigation signals
    civil_keywords = ["lawsuit", "sued", "plaintiff", "defendant", "settlement",
                      "breach of contract", "restraining order", "divorce", "court order"]
    civil_hits = [kw for kw in civil_keywords if kw in all_snippets]

    # Top results per category
    def extract_top(query_keywords: list, max_results: int = 5) -> list:
        relevant = []
        seen = set()
        for q, results in all_results.items():
            if any(kw in q.lower() for kw in query_keywords):
                for r in results:
                    url_key = r.get("url","")
                    if url_key and url_key not in seen and r.get("title"):
                        seen.add(url_key)
                        relevant.append({
                            "title": r.get("title",""),
                            "url": url_key,
                            "snippet": r.get("content","")[:250]
                        })
        return relevant[:max_results]

    return {
        "source": "deep_person_profile",
        "subject": name,
        "company_context": company,
        "location_context": location,
        "signal_summary": {
            "criminal_signals": criminal_hits,
            "fraud_signals": fraud_hits,
            "financial_distress_signals": financial_hits,
            "civil_litigation_signals": civil_hits,
            "total_red_signal_count": len(criminal_hits) + len(fraud_hits) + len(financial_hits) + len(civil_hits)
        },
        "criminal_legal": extract_top(["arrested", "charged", "criminal", "convicted", "mugshot"]),
        "fraud_financial_crime": extract_top(["fraud", "ponzi", "scheme", "money laundering", "securities"]),
        "civil_litigation": extract_top(["lawsuit", "sued", "plaintiff", "judgment", "breach"]),
        "financial_distress": extract_top(["bankruptcy", "tax lien", "foreclosure", "judgment", "garnishment"]),
        "professional_history": extract_top(["career", "employer", "director", "founder", "terminated"]),
        "news_and_press": extract_top(["news", "article", "expose", "investigation", "press"]),
        "all_results_count": sum(len(v) for v in all_results.values()),
        "queries_run": len(queries),
    }


# ── Owner Extraction + Auto Person Profile ────────────────────────────────────────
def extract_and_profile_owners(target: str, corporate_data: dict, search_results: dict) -> dict:
    """
    Extract owner/principal names from corporate data and web results,
    then run deep_person_profile on each one found.
    """
    owner_names = set()

    # Pull from Sunbiz officers
    sunbiz = corporate_data.get("sunbiz_fl", {})
    for officer in sunbiz.get("detail", {}).get("officers", []):
        if isinstance(officer, dict) and officer.get("name"):
            owner_names.add(officer["name"].strip().title())

    # Pull from OpenCorporates
    for result in corporate_data.get("opencorporates", {}).get("results", []):
        if isinstance(result, dict):
            officers = result.get("officers", []) or []
            for o in officers:
                if isinstance(o, dict) and o.get("name"):
                    owner_names.add(o["name"].strip().title())

    # Pull from web search snippets — look for owner/founder/CEO patterns
    all_text = " ".join(
        r.get("content","") + " " + r.get("title","")
        for results in search_results.values()
        for r in results
    )
    # Pattern: "Founded by X", "CEO X", "Owner X", "Founder X"
    patterns = [
        r'(?:founded by|ceo|owner|founder|president|director|principal)[:\s]+([A-Z][a-z]+ [A-Z][a-z]+(?:\s[A-Z][a-z]+)?)',
        r'([A-Z][a-z]+ [A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\s*,?\s*(?:CEO|founder|owner|president|director)',
    ]
    for pattern in patterns:
        matches = re.findall(pattern, all_text)
        for m in matches[:5]:
            if len(m) > 5 and len(m) < 50:
                owner_names.add(m.strip().title())

    if not owner_names:
        return {"source": "owner_profiles", "owners_found": [], "profiles": {}}

    # Profile each owner (cap at 3 to control Serper spend)
    profiles = {}
    for name in list(owner_names)[:3]:
        # Extract location context from corporate data
        loc = None
        addr = sunbiz.get("detail", {}).get("principal_address","")
        if addr:
            state_match = re.search(r'\b([A-Z]{2})\b', addr)
            if state_match:
                loc = state_match.group(1)
        profiles[name] = deep_person_profile(name, company=target, location=loc)

    return {
        "source": "owner_profiles",
        "owners_found": list(owner_names),
        "profiles": profiles
    }


# ═══════════════════════════════════════════════════════════════════════════════
# v10 UPGRADES: State Courts, ICIJ, DOJ, Licenses, CFPB, Glassdoor,
#               BreachDirectory, Crunchbase, USASpending, Interpol
# ═══════════════════════════════════════════════════════════════════════════════

# ── 1. State Court Records ───────────────────────────────────────────────────────
STATE_COURT_URLS = {
    "FL": "myflcourtaccess.com",
    "CA": "courts.ca.gov",
    "NY": "iapps.courts.state.ny.us",
    "TX": "search.txcourts.gov",
    "GA": "oscn.net",
    "NJ": "njcourts.gov",
    "IL": "illinoiscourts.gov",
    "PA": "ujsportal.pacourts.us",
    "NC": "nccourts.gov",
    "OH": "supremecourt.ohio.gov",
}

def state_court_search(name: str, states: list = None) -> dict:
    """Search state court public portals for civil and criminal cases."""
    if not states:
        states = ["FL", "CA", "NY", "TX"]
    results = {}
    queries = []
    for s in states[:5]:
        site = STATE_COURT_URLS.get(s, "")
        if site:
            queries.append((s, f'site:{site} "{name}"'))
        queries.append((f"{s}_general", f'"{name}" {s} state court case lawsuit criminal civil filing 2020 2021 2022 2023 2024 2025'))
    # DOJ state-level
    queries.append(("doj_state", f'"{name}" state attorney general complaint lawsuit investigation'))

    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(serper_search, q, 5): label for label, q in queries}
        for f in as_completed(futures):
            label = futures[f]
            try:
                hits = f.result()
                if hits:
                    results[label] = [{"title": r["title"], "url": r["url"],
                                       "snippet": r.get("content","")[:200]} for r in hits[:3]]
            except Exception:
                pass

    total_hits = sum(len(v) for v in results.values())
    return {
        "source": "state_courts",
        "states_checked": states,
        "total_results": total_hits,
        "results": results
    }


# ── 2. ICIJ Offshore Leaks (Panama/Pandora/Paradise Papers) ─────────────────────
def icij_offshore_leaks(name: str) -> dict:
    """
    Search ICIJ Offshore Leaks database — Panama Papers, Pandora Papers,
    Paradise Papers, Bahamas Leaks, FinCEN Files. Free public database.
    """
    encoded = urllib.parse.quote(name)
    url = f"https://offshoreleaks.icij.org/search?q={encoded}&c=&j=&d="
    result = {"source": "icij_offshore_leaks", "found": False, "entities": [], "url": url}

    # Try direct scrape
    try:
        req = urllib.request.Request(
            f"https://offshoreleaks.icij.org/search?q={encoded}",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                     "Accept": "text/html"}
        )
        resp = urllib.request.urlopen(req, timeout=15)
        html = resp.read().decode("utf-8", errors="ignore")
        # Look for result count
        m = re.search(r'([\d,]+)\s+(?:results?|entities)', html, re.IGNORECASE)
        if m:
            result["result_count"] = int(m.group(1).replace(",",""))
            result["found"] = result["result_count"] > 0
        # Extract entity names
        entity_matches = re.findall(r'class="[^"]*name[^"]*"[^>]*>([^<]+)<', html)
        for e in entity_matches[:5]:
            clean = e.strip()
            if clean and len(clean) > 3:
                result["entities"].append(clean)
    except Exception:
        pass

    # Always supplement with Serper
    serper_hits = serper_search(
        f'site:offshoreleaks.icij.org "{name}" OR '
        f'"panama papers" "{name}" OR "pandora papers" "{name}" OR '
        f'"paradise papers" "{name}"', 5
    )
    icij_hits = [r for r in serper_hits if "icij.org" in r.get("url","") or
                 any(p in r.get("content","").lower() for p in
                     ["panama papers","pandora papers","paradise papers","offshore leaks","fincen"])]
    if icij_hits:
        result["found"] = True
        result["serper_mentions"] = [{"title": r["title"], "url": r["url"],
                                      "snippet": r.get("content","")[:200]} for r in icij_hits[:4]]

    return result


# ── 3. DOJ + Federal Agency Press Releases ──────────────────────────────────────
def doj_federal_enforcement(name: str) -> dict:
    """
    Search DOJ press releases, FBI, FTC, SEC, CFTC, FinCEN, OCC enforcement actions.
    These are the gold standard — if the government published it, it happened.
    """
    agencies = [
        ("DOJ",   f'site:justice.gov "{name}"'),
        ("FBI",   f'site:fbi.gov "{name}"'),
        ("FTC",   f'site:ftc.gov "{name}" action complaint'),
        ("SEC",   f'site:sec.gov/litigation "{name}"'),
        ("CFTC",  f'site:cftc.gov "{name}" enforcement action'),
        ("FinCEN",f'site:fincen.gov "{name}"'),
        ("OCC",   f'site:occ.gov "{name}" enforcement'),
        ("CFPB",  f'site:consumerfinance.gov "{name}" enforcement action'),
        ("HHS_OIG",f'site:oig.hhs.gov "{name}" fraud'),
        ("USAO",  f'"United States Attorney" "{name}" charged indicted convicted press release'),
    ]
    results = {}
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(serper_search, q, 5): label for label, q in agencies}
        for f in as_completed(futures):
            label = futures[f]
            try:
                hits = f.result()
                agency_hits = [r for r in hits if r.get("url") and
                               any(d in r.get("url","") for d in
                                   ["justice.gov","fbi.gov","ftc.gov","sec.gov","cftc.gov",
                                    "fincen.gov","occ.gov","consumerfinance.gov","oig.hhs.gov"])]
                if agency_hits:
                    results[label] = [{"title": r["title"], "url": r["url"],
                                       "snippet": r.get("content","")[:250]} for r in agency_hits[:3]]
            except Exception:
                pass

    total = sum(len(v) for v in results.values())
    return {
        "source": "federal_enforcement",
        "agencies_checked": len(agencies),
        "total_hits": total,
        "findings": results,
        "has_findings": total > 0
    }


# ── 4. Professional License Boards ──────────────────────────────────────────────
def professional_license_check(name: str, state: str = None, industry: str = None) -> dict:
    """
    Check professional license status across key boards.
    Revoked/suspended license = immediate red flag.
    """
    queries = []
    state_q = f" {state}" if state else ""

    # Universal
    queries += [
        ("general",     f'"{name}" professional license{state_q} status active revoked suspended'),
        ("real_estate", f'"{name}" real estate license{state_q} NMLS realtor broker'),
        ("medical",     f'"{name}" medical license{state_q} board disciplinary action revoked'),
        ("legal",       f'"{name}" bar admission attorney lawyer{state_q} disciplinary suspended disbarred'),
        ("financial",   f'"{name}" investment advisor CRD IARD license revoked suspended'),
        ("contractor",  f'"{name}" contractor license{state_q} bond suspended revoked'),
        ("insurance",   f'"{name}" insurance license{state_q} agent broker revoked suspended'),
    ]

    # Industry-specific
    if industry:
        ind = industry.lower()
        if "real estate" in ind or "realestate" in ind:
            queries.append(("state_re", f'site:nrds.realtor "{name}" OR "{name}" NAR membership realtor'))
        elif "finance" in ind or "investment" in ind:
            queries.append(("iard",     f'site:adviserinfo.sec.gov "{name}" investment adviser'))
        elif "medical" in ind or "health" in ind:
            queries.append(("med_board",f'"{name}" medical board{state_q} license lookup NPI'))

    # State-level license portals
    if state:
        state_portals = {
            "FL": "myfloridalicense.com",
            "CA": "search.dca.ca.gov",
            "NY": "dos.ny.gov/licensing",
            "TX": "license.state.tx.us",
        }
        portal = state_portals.get(state.upper())
        if portal:
            queries.append(("state_portal", f'site:{portal} "{name}"'))

    results = {}
    with ThreadPoolExecutor(max_workers=7) as ex:
        futures = {ex.submit(serper_search, q, 4): label for label, q in queries}
        for f in as_completed(futures):
            label = futures[f]
            try:
                hits = f.result()
                if hits:
                    results[label] = [{"title": r["title"], "url": r["url"],
                                       "snippet": r.get("content","")[:200]} for r in hits[:3]]
            except Exception:
                pass

    # Scan for revocation signals
    all_text = " ".join(r.get("content","") + r.get("title","")
                        for hits in results.values() for r in hits
                        for hits in [serper_search("", 0)[:0]]).lower() if False else \
               " ".join(str(results)).lower()
    revocation_signals = [w for w in ["revoked","suspended","disbarred","disciplinary",
                                       "surrendered","expired","inactive","complaint"]
                          if w in all_text]

    return {
        "source": "professional_licenses",
        "revocation_signals": revocation_signals,
        "has_concerns": bool(revocation_signals),
        "results": results
    }


# ── 5. CFPB Consumer Complaints ──────────────────────────────────────────────────
def cfpb_complaints(name: str) -> dict:
    """Search CFPB Consumer Complaint Database — financial companies only, free API."""
    encoded = urllib.parse.quote(name)
    url = f"https://www.consumerfinance.gov/data-research/consumer-complaints/search/api/v1/?search_term={encoded}&field=all&size=10"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        hits = data.get("hits", {}).get("hits", [])
        total = data.get("hits", {}).get("total", {})
        total_count = total.get("value", 0) if isinstance(total, dict) else total
        complaints = []
        for h in hits[:5]:
            src = h.get("_source", {})
            complaints.append({
                "company": src.get("company"),
                "product": src.get("product"),
                "issue": src.get("issue"),
                "date": src.get("date_received"),
                "state": src.get("state"),
                "response": src.get("company_response"),
                "timely": src.get("timely"),
            })
        return {"source": "cfpb", "total_complaints": total_count, "complaints": complaints}
    except Exception as e:
        # Fallback
        hits = serper_search(f'site:consumerfinance.gov "{name}" complaints OR "{name}" CFPB complaint', 4)
        return {"source": "cfpb_serper", "error": str(e),
                "mentions": [{"title": r["title"], "url": r["url"]} for r in hits[:3]]}


# ── 6. Glassdoor + Indeed Employee Reviews ───────────────────────────────────────
def employer_review_intel(name: str) -> dict:
    """Pull Glassdoor + Indeed reviews — employees tell the truth."""
    queries = [
        ("glassdoor", f'site:glassdoor.com "{name}" reviews rating employees'),
        ("indeed",    f'site:indeed.com "{name}" reviews employees rating'),
        ("google_emp",f'"{name}" employee review culture workplace fraud layoffs'),
        ("linkedin_emp", f'"{name}" employees layoffs culture linkedin'),
    ]
    results = {}
    rating_signals = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {ex.submit(serper_search, q, 5): label for label, q in queries}
        for f in as_completed(futures):
            label = futures[f]
            try:
                hits = f.result()
                if hits:
                    results[label] = [{"title": r["title"], "url": r["url"],
                                       "snippet": r.get("content","")[:200]} for r in hits[:3]]
                    # Extract rating signals
                    for r in hits[:3]:
                        snippet = r.get("content","")
                        m = re.search(r'([\d.]+)\s*(?:out of\s*)?(?:stars?|/5)\s*(?:rating)?', snippet, re.IGNORECASE)
                        if m:
                            rating_signals[label] = float(m.group(1))
                        # Employee count
                        m2 = re.search(r'([\d,]+)\s+(?:employees?|reviews?)', snippet, re.IGNORECASE)
                        if m2:
                            rating_signals[f"{label}_count"] = m2.group(1)
            except Exception:
                pass

    # Scan for red flags in employee reviews
    all_text = " ".join(str(results)).lower()
    red_flags = [w for w in ["fraud","misleading","illegal","lawsuit","toxic","hostile",
                              "unpaid","bounced check","no payroll","scam","fake"]
                 if w in all_text]

    return {
        "source": "employer_reviews",
        "platforms_checked": ["glassdoor","indeed"],
        "ratings": rating_signals,
        "red_flags_in_reviews": red_flags,
        "results": results
    }


# ── 7. BreachDirectory — Email Breach Check ──────────────────────────────────────
def breachdirectory_check(email: str = None, domain: str = None) -> dict:
    """
    Check BreachDirectory.org for leaked credentials.
    Free API: checks if email/domain appears in breach databases.
    """
    result = {"source": "breachdirectory", "breaches_found": False, "details": []}
    targets = []
    if email:
        targets.append(("email", email))
    if domain:
        targets.append(("domain", domain))

    for kind, val in targets[:2]:
        encoded = urllib.parse.quote(val)
        try:
            url = f"https://breachdirectory.org/api?func=auto&term={encoded}"
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
            })
            resp = urllib.request.urlopen(req, timeout=15)
            data = json.loads(resp.read())
            if data.get("success") and data.get("found"):
                result["breaches_found"] = True
                for item in (data.get("result") or [])[:5]:
                    result["details"].append({
                        "type": kind,
                        "value": val,
                        "source": item.get("sources",""),
                        "has_password": item.get("has_password", False),
                    })
        except Exception:
            pass

    # Supplement with Serper
    for kind, val in targets[:1]:
        hits = serper_search(f'"{val}" breach leaked database haveibeenpwned exposed', 4)
        breach_hits = [r for r in hits if any(d in r.get("url","")
                       for d in ["haveibeenpwned","breachdirectory","dehashed","intelx",
                                 "raidforums","breach"])]
        if breach_hits:
            result["breaches_found"] = True
            result["serper_breach_mentions"] = [{"title": r["title"], "url": r["url"]} for r in breach_hits[:3]]

    return result


# ── 8. Crunchbase + AngelList Startup Intelligence ───────────────────────────────
def crunchbase_intel(name: str) -> dict:
    """
    Scrape Crunchbase/AngelList via Serper for funding, investors, valuations.
    Validates revenue and size claims.
    """
    queries = [
        ("crunchbase",   f'site:crunchbase.com "{name}" funding investors valuation'),
        ("angellist",    f'site:wellfound.com OR site:angel.co "{name}" startup funding'),
        ("pitchbook",    f'site:pitchbook.com "{name}" funding round investors'),
        ("general_fund", f'"{name}" funding raised investors series seed venture capital'),
        ("employees",    f'"{name}" number of employees headcount team size linkedin'),
    ]
    results = {}
    funding_signals = {}

    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {ex.submit(serper_search, q, 5): label for label, q in queries}
        for f in as_completed(futures):
            label = futures[f]
            try:
                hits = f.result()
                if hits:
                    results[label] = [{"title": r["title"], "url": r["url"],
                                       "snippet": r.get("content","")[:200]} for r in hits[:3]]
                    for r in hits[:3]:
                        snippet = r.get("content","")
                        # Extract funding amounts
                        m = re.search(r'\$?([\d.]+)\s*([MBK])\s*(?:in\s+)?(?:funding|raised|round|valuation)',
                                      snippet, re.IGNORECASE)
                        if m:
                            amt = m.group(1)
                            unit = m.group(2).upper()
                            multiplier = {"K":1000,"M":1000000,"B":1000000000}.get(unit,1)
                            funding_signals["amount_usd"] = float(amt) * multiplier
                            funding_signals["amount_str"] = f"${amt}{unit}"
                        # Employee count
                        m2 = re.search(r'([\d,]+)\s+(?:employees?|people|team)', snippet, re.IGNORECASE)
                        if m2:
                            funding_signals["employee_count"] = m2.group(1)
            except Exception:
                pass

    return {
        "source": "crunchbase_intel",
        "funding_signals": funding_signals,
        "found": bool(funding_signals or results.get("crunchbase")),
        "results": results
    }


# ── 9. USASpending — Government Contracts ────────────────────────────────────────
def usaspending_contracts(name: str) -> dict:
    """
    Query USASpending.gov for federal contracts and grants.
    Validates revenue claims — a '$50M company' with no govt contracts is a signal.
    """
    encoded = urllib.parse.quote(name)
    url = f"https://api.usaspending.gov/api/v2/search/spending_by_award/?filters={{\"recipient_search_text\":[\"{name}\"]}}&fields=Award+ID,Recipient+Name,Start+Date,Amount,Awarding+Agency&page=1&limit=5&sort=Amount&order=desc"
    result = {"source": "usaspending", "contracts_found": 0, "total_value": 0, "contracts": []}

    try:
        payload = json.dumps({
            "filters": {"recipient_search_text": [name], "award_type_codes": ["A","B","C","D","02","03","04","05"]},
            "fields": ["Award ID","Recipient Name","Start Date","End Date","Award Amount",
                       "Awarding Agency","Description"],
            "page": 1, "limit": 5, "sort": "Award Amount", "order": "desc"
        }).encode()
        req = urllib.request.Request(
            "https://api.usaspending.gov/api/v2/search/spending_by_award/",
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
        )
        resp = urllib.request.urlopen(req, timeout=20)
        data = json.loads(resp.read())
        awards = data.get("results", [])
        result["contracts_found"] = len(awards)
        for a in awards[:5]:
            amt = a.get("Award Amount") or a.get("award_amount") or 0
            result["total_value"] += float(amt) if amt else 0
            result["contracts"].append({
                "id": a.get("Award ID") or a.get("award_id"),
                "recipient": a.get("Recipient Name") or a.get("recipient_name"),
                "amount": amt,
                "agency": a.get("Awarding Agency") or a.get("awarding_agency"),
                "start": a.get("Start Date") or a.get("period_of_performance_start_date"),
                "description": str(a.get("Description",""))[:150],
            })
    except Exception as e:
        result["api_error"] = str(e)

    # Always supplement with Serper
    hits = serper_search(f'"{name}" government contract federal award USASpending SAM.gov', 4)
    if hits:
        result["serper_mentions"] = [{"title": r["title"], "url": r["url"]} for r in hits[:3]]

    return result


# ── 10. Interpol Red Notices + International Fugitives ───────────────────────────
def interpol_check(name: str) -> dict:
    """
    Check Interpol Red Notices and international fugitive databases.
    Red Notice = requested arrest pending extradition.
    """
    queries = [
        ("interpol",     f'site:interpol.int "{name}" red notice wanted'),
        ("interpol_gen", f'"{name}" interpol red notice wanted fugitive international'),
        ("us_marshals",  f'site:usmarshals.gov "{name}" fugitive wanted'),
        ("fbi_wanted",   f'site:fbi.gov/wanted "{name}"'),
        ("ice_wanted",   f'"{name}" ICE most wanted fugitive deportation'),
        ("un_sanctions", f'"{name}" un security council sanctions list resolution'),
    ]

    results = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(serper_search, q, 4): label for label, q in queries}
        for f in as_completed(futures):
            label = futures[f]
            try:
                hits = f.result()
                official_hits = [r for r in hits if any(d in r.get("url","")
                                  for d in ["interpol.int","usmarshals.gov","fbi.gov",
                                            "ice.gov","un.org","wanted"])]
                if official_hits:
                    results[label] = [{"title": r["title"], "url": r["url"],
                                       "snippet": r.get("content","")[:200]} for r in official_hits[:2]]
            except Exception:
                pass

    # Try Interpol direct API (public red notices)
    try:
        encoded_parts = urllib.parse.quote(name).replace("%20", "+")
        url = f"https://ws-public.interpol.int/notices/v1/red?name={encoded_parts}&resultPerPage=5"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        notices = data.get("_embedded", {}).get("notices", [])
        if notices:
            results["interpol_api"] = []
            for n in notices[:3]:
                results["interpol_api"].append({
                    "name": f"{n.get('forename','')} {n.get('name','')}".strip(),
                    "nationality": n.get("nationalities"),
                    "dob": n.get("date_of_birth"),
                    "charges": n.get("charges",""),
                    "url": n.get("_links",{}).get("self",{}).get("href",""),
                })
    except Exception:
        pass

    has_hits = bool(results)
    return {
        "source": "interpol_fugitive_check",
        "red_notice_found": "interpol_api" in results,
        "has_any_hits": has_hits,
        "findings": results
    }


# ═══════════════════════════════════════════════════════════════════════════════
# v11: US National Business Registry + Intake Form Infrastructure
# ═══════════════════════════════════════════════════════════════════════════════

# ── US National Business Lookup (replaces Sunbiz-for-everything) ─────────────────
def us_national_business_lookup(name: str, state: str = None) -> dict:
    """
    Proper US-wide business registry lookup using:
    1. OpenCorporates (covers all 50 states via API)
    2. SAM.gov (federal contractor/vendor registry — free API)
    3. IRS Tax Exempt Organizations (nonprofits)
    4. State-specific direct registry (if state known)
    5. Serper fallback for Secretary of State portals
    """
    results = {}

    # 1. OpenCorporates — all 50 US states
    try:
        encoded = urllib.parse.quote(name)
        url = f"https://api.opencorporates.com/v0.4/companies/search?q={encoded}&jurisdiction_code=us&per_page=5&inactive=false"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        companies = data.get("results", {}).get("companies", [])
        oc_results = []
        for c in companies[:5]:
            co = c.get("company", {})
            oc_results.append({
                "name": co.get("name"),
                "number": co.get("company_number"),
                "jurisdiction": co.get("jurisdiction_code"),
                "state": co.get("jurisdiction_code","").replace("us_","").upper(),
                "status": co.get("current_status"),
                "type": co.get("company_type"),
                "incorporated": co.get("incorporation_date"),
                "address": co.get("registered_address_in_full"),
                "url": co.get("opencorporates_url"),
            })
        results["opencorporates_us"] = {
            "source": "OpenCorporates (All 50 States)",
            "total_found": data.get("results",{}).get("total_count", 0),
            "companies": oc_results
        }
    except Exception as e:
        results["opencorporates_us"] = {"error": str(e)}

    # 2. SAM.gov — Federal contractor/vendor registry
    try:
        encoded = urllib.parse.quote(name)
        url = f"https://api.sam.gov/entity-information/v3/entities?api_key=DEMO_KEY&legalBusinessName={encoded}&includeSections=entityRegistration,coreData&pageSize=5"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        entities = data.get("entityData", [])
        sam_results = []
        for e in entities[:3]:
            reg = e.get("entityRegistration", {})
            core = e.get("coreData", {})
            addr = core.get("physicalAddress", {})
            sam_results.append({
                "legal_name": reg.get("legalBusinessName"),
                "uei": reg.get("ueiSAM"),
                "cage_code": reg.get("cageCode"),
                "ein": reg.get("taxpayerIdentificationNumber"),
                "status": reg.get("registrationStatus"),
                "activation_date": reg.get("activationDate"),
                "expiration_date": reg.get("registrationExpirationDate"),
                "entity_type": reg.get("entityTypeCode"),
                "address": f"{addr.get('streetAddress','')} {addr.get('city','')} {addr.get('stateOrProvinceCode','')} {addr.get('zipCode','')}".strip(),
                "purpose": reg.get("purposeOfRegistrationDesc"),
            })
        results["sam_gov"] = {
            "source": "SAM.gov (Federal Contractor Registry)",
            "total_found": data.get("totalRecords", 0),
            "entities": sam_results
        }
    except Exception as e:
        # Fallback — Serper search for SAM.gov
        hits = serper_search(f'site:sam.gov "{name}" entity registration UEI', 3)
        results["sam_gov"] = {"source": "SAM.gov (Serper fallback)", "error": str(e),
                              "hits": [{"title": r["title"], "url": r["url"]} for r in hits[:3]]}

    # 3. IRS Tax Exempt (nonprofits, 501c3)
    try:
        encoded = urllib.parse.quote(name)
        url = f"https://efts.sec.gov/LATEST/search-index?q=%22{encoded}%22&forms=990&hits.hits._source=entity_name,file_date,period_of_report"
        req = urllib.request.Request(url, headers={"User-Agent": "Jarvis/1.0 research@jarvis.local", "Accept": "application/json"})
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        hits_data = data.get("hits", {}).get("hits", [])
        if hits_data:
            results["irs_nonprofit"] = {
                "source": "IRS/SEC 990 Filings",
                "found": True,
                "filings": [{"entity": h.get("_source",{}).get("entity_name"),
                             "date": h.get("_source",{}).get("file_date")} for h in hits_data[:3]]
            }
    except Exception:
        pass

    # 4. State-specific direct lookup if state is known
    if state:
        state_direct_urls = {
            "FL": f"https://search.sunbiz.org/Inquiry/CorporationSearch/SearchResults?inquiryType=EntityName&searchTerm={urllib.parse.quote(name)}",
            "CA": f"https://bizfileonline.sos.ca.gov/search/business",
            "NY": f"https://apps.dos.ny.gov/publicInquiry/",
            "TX": f"https://direct.sos.state.tx.us/corp_inquiry/corp_inquiry-entity.asp",
            "DE": f"https://icis.corp.delaware.gov/ecorp/entitysearch/namesearch.aspx",
            "NV": f"https://esos.nv.gov/EntitySearch/OnlineEntitySearch",
            "WY": f"https://wyobiz.wyo.gov/Business/FilingSearch.aspx",
            "CO": f"https://www.sos.state.co.us/biz/BusinessEntityCriteriaExt.do",
            "WA": f"https://www.sos.wa.gov/corps/corps_search.aspx",
            "GA": f"https://ecorp.sos.ga.gov/BusinessSearch",
            "IL": f"https://www.ilsos.gov/corporatellc/",
            "OH": f"https://businesssearch.ohiosos.gov/",
            "PA": f"https://www.corporations.pa.gov/search/corpsearch",
            "NC": f"https://www.sosnc.gov/online_services/search/by_title/_Business_Registration",
            "AZ": f"https://ecorp.azcc.gov/BusinessSearch/BusinessSearch",
            "MA": f"https://corp.sec.state.ma.us/CorpWeb/CorpSearch/CorpSearch.aspx",
            "NJ": f"https://www.njportal.com/DOR/BusinessRecords",
            "MI": f"https://cofs.lara.state.mi.us/SearchApi/Search/Search",
            "MN": f"https://mblsportal.sos.state.mn.us/Business/Search",
            "TN": f"https://tnbear.tn.gov/ECommerce/FilingSearch.aspx",
        }
        state_url = state_direct_urls.get(state.upper())
        if state_url:
            if state.upper() == "FL":
                # Use existing Sunbiz scraper for FL
                results["state_direct_fl"] = sunbiz_lookup(name)
            else:
                # Serper search against state portal
                domain = urllib.parse.urlparse(state_url).netloc
                hits = serper_search(f'site:{domain} "{name}"', 5)
                if hits:
                    results[f"state_direct_{state.lower()}"] = {
                        "source": f"{state.upper()} Secretary of State",
                        "portal_url": state_url,
                        "results": [{"title": r["title"], "url": r["url"],
                                    "snippet": r.get("content","")[:200]} for r in hits[:3]]
                    }
                else:
                    # Direct search query as fallback
                    hits2 = serper_search(
                        f'"{name}" {state} secretary of state corporation LLC registration status', 5
                    )
                    results[f"state_direct_{state.lower()}"] = {
                        "source": f"{state.upper()} Secretary of State (Serper)",
                        "results": [{"title": r["title"], "url": r["url"],
                                    "snippet": r.get("content","")[:200]} for r in hits2[:3]]
                    }

    # 5. EDGAR company search (public companies)
    try:
        encoded = urllib.parse.quote(name)
        url = f"https://www.sec.gov/cgi-bin/browse-edgar?company={encoded}&CIK=&type=&dateb=&owner=include&count=5&search_text=&action=getcompany&output=atom"
        req = urllib.request.Request(url, headers={"User-Agent": "Jarvis/1.0 research@jarvis.local"})
        resp = urllib.request.urlopen(req, timeout=15)
        xml = resp.read().decode("utf-8", errors="ignore")
        # Extract company names from EDGAR Atom feed
        company_names = re.findall(r'<company-name>([^<]+)</company-name>', xml)
        cik_numbers = re.findall(r'<CIK>(\d+)</CIK>', xml)
        if company_names:
            results["sec_edgar_companies"] = {
                "source": "SEC EDGAR (Public Companies)",
                "found": True,
                "companies": [{"name": n, "cik": c}
                              for n, c in zip(company_names[:5], cik_numbers[:5])]
            }
    except Exception:
        pass

    total_sources = sum(1 for v in results.values()
                       if isinstance(v, dict) and not v.get("error") and
                       (v.get("companies") or v.get("entities") or v.get("results") or v.get("found")))
    return {
        "source": "us_national_registry",
        "state_targeted": state,
        "sources_checked": list(results.keys()),
        "sources_with_data": total_sources,
        "data": results
    }


# ── Intake Form Schema ────────────────────────────────────────────────────────────
INTAKE_FORM_SCHEMA = {
    "version": "1.0",
    "sections": [
        {
            "id": "subject",
            "title": "Who are you searching?",
            "fields": [
                {"id": "target",       "label": "Full Name / Business Name",    "type": "text",     "required": True},
                {"id": "type",         "label": "Subject Type",                 "type": "select",   "required": True,
                 "options": ["company","person","organization","watch"]},
                {"id": "industry",     "label": "Industry",                     "type": "select",   "required": False,
                 "options": ["finance","real-estate","luxury","healthcare","tech",
                             "crypto","legal","retail","manufacturing","hospitality",
                             "watches","jewelry","art","other"]},
                {"id": "aliases",      "label": "Known Aliases / Other Names",  "type": "text",     "required": False,
                 "placeholder": "maiden name, former company name, DBA..."},
            ]
        },
        {
            "id": "location",
            "title": "Where are they based?",
            "description": "More specific = more accurate registry hits",
            "fields": [
                {"id": "country",  "label": "Country",          "type": "country_select", "required": False},
                {"id": "state",    "label": "State / Province",  "type": "text",  "required": False,
                 "placeholder": "FL, CA, NY, ON, BC..."},
                {"id": "city",     "label": "City",              "type": "text",  "required": False},
                {"id": "address",  "label": "Known Address",     "type": "text",  "required": False},
            ]
        },
        {
            "id": "contact",
            "title": "Contact & Digital Presence",
            "description": "Every field you fill in adds another targeted search",
            "fields": [
                {"id": "url",       "label": "Website",          "type": "url",   "required": False},
                {"id": "email",     "label": "Email",            "type": "email", "required": False},
                {"id": "phone",     "label": "Phone",            "type": "tel",   "required": False},
                {"id": "linkedin",  "label": "LinkedIn",         "type": "text",  "required": False},
                {"id": "instagram", "label": "Instagram Handle", "type": "text",  "required": False,
                 "placeholder": "@handle"},
                {"id": "twitter",   "label": "Twitter/X Handle", "type": "text",  "required": False,
                 "placeholder": "@handle"},
                {"id": "facebook",  "label": "Facebook URL",     "type": "url",   "required": False},
                {"id": "ebay",      "label": "eBay Username",    "type": "text",  "required": False},
            ]
        },
        {
            "id": "identity",
            "title": "Identity Details",
            "description": "Reduces false positives — especially for common names",
            "fields": [
                {"id": "dob",            "label": "Date of Birth",               "type": "date",  "required": False,
                 "show_if": {"type": "person"}},
                {"id": "company_number", "label": "Business Reg # / EIN / CRN",  "type": "text",  "required": False},
                {"id": "owner",          "label": "Known Owner Name",            "type": "text",  "required": False,
                 "placeholder": "Triggers deep person profile"},
                {"id": "company",        "label": "Associated Company",          "type": "text",  "required": False,
                 "show_if": {"type": "person"}},
            ]
        },
        {
            "id": "context",
            "title": "Search Context",
            "description": "Helps the AI know exactly what to look for",
            "fields": [
                {"id": "relationship", "label": "Your Relationship",   "type": "select", "required": False,
                 "options": ["counterparty","business-partner","vendor","employee-candidate",
                             "investor","tenant","customer","other"]},
                {"id": "stakes",       "label": "Transaction Stakes",  "type": "select", "required": False,
                 "options": ["small (<$10K)","medium ($10K-$100K)","large ($100K-$1M)","critical (>$1M)"],
                 "description": "Large/Critical auto-escalates to deep search"},
                {"id": "concerns",     "label": "Specific Concerns",   "type": "text",   "required": False,
                 "placeholder": "fraud, fake credentials, sanctions, money laundering..."},
                {"id": "notes",        "label": "What You Already Know","type": "textarea","required": False,
                 "placeholder": "Any background, context, or red flags you've already noticed..."},
            ]
        },
        {
            "id": "depth",
            "title": "Search Depth",
            "fields": [
                {"id": "depth", "label": "Depth", "type": "select", "required": False,
                 "default": "standard",
                 "options": [
                     {"value": "quick",    "label": "⚡ Quick   (~20s · ~$0.03) — Web + corporate only"},
                     {"value": "standard", "label": "🔍 Standard (~45s · ~$0.06) — All modules"},
                     {"value": "deep",     "label": "🔬 Deep    (~90s · ~$0.12) — 2× queries + extended profiles"},
                 ]},
            ]
        }
    ]
}

def get_intake_form_schema() -> dict:
    """Return the intake form schema for the frontend to render."""
    return INTAKE_FORM_SCHEMA
def main():
    global OPENROUTER_KEY

    parser = argparse.ArgumentParser(
        description="Jarvis OSINT Engine — company/person/watch intelligence",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  osint "Acme Watches Miami"
  osint "Andre Mercier" --type person
  osint "Daytona 126500" --type watch
  osint "Acme LLC" --state FL --save
        """
    )
    # ── Core ──────────────────────────────────────────────────────────────────
    parser.add_argument("target", help="Name, business, or person to investigate")
    parser.add_argument("--type", choices=["company","person","organization","watch"],
                        default="company", help="Target type")
    parser.add_argument("--industry", default=None,
                        help="Industry context (finance, real-estate, luxury, healthcare, tech, crypto, etc.)")

    # ── Location ──────────────────────────────────────────────────────────────
    parser.add_argument("--country", default=None,
                        help="Country (US, UK, CA, AU, HK, SG, DE, FR, CH, IT, NL, AE, JP, ...)")
    parser.add_argument("--state", default=None,
                        help="US state or province (FL, CA, NY, TX, ON, BC, ...)")
    parser.add_argument("--city", default=None, help="City")
    parser.add_argument("--address", default=None, help="Known street address")

    # ── Contact & Digital ─────────────────────────────────────────────────────
    parser.add_argument("--url", default=None, help="Website URL")
    parser.add_argument("--email", default=None, help="Email address")
    parser.add_argument("--phone", default=None, help="Phone number")
    parser.add_argument("--linkedin", default=None, help="LinkedIn URL or handle")
    parser.add_argument("--instagram", default=None, help="Instagram handle")
    parser.add_argument("--twitter", default=None, help="Twitter/X handle")
    parser.add_argument("--facebook", default=None, help="Facebook URL")
    parser.add_argument("--ebay", default=None, help="eBay username")
    parser.add_argument("--handle", default=None, help="Generic social handle for maigret username search")

    # ── Identity ──────────────────────────────────────────────────────────────
    parser.add_argument("--dob", default=None, help="Date of birth (persons — improves identity precision)")
    parser.add_argument("--aliases", default=None, help="Comma-separated known aliases / other names / maiden name")
    parser.add_argument("--company-number", default=None, help="Business registration number / EIN / company number")
    parser.add_argument("--owner", default=None, help="Known owner name — triggers deep person profile")
    parser.add_argument("--company", default=None, help="Associated company (when target is a person)")

    # ── Context ───────────────────────────────────────────────────────────────
    parser.add_argument("--relationship", default=None,
                        help="Relationship type (counterparty, partner, vendor, employee, investor)")
    parser.add_argument("--stakes", default=None,
                        help="Transaction stakes (small, medium, large, critical) — affects depth")
    parser.add_argument("--concerns", default=None,
                        help="Specific concerns to investigate (e.g. 'money laundering' 'fake credentials')")
    parser.add_argument("--notes", default=None, help="Additional known context for AI synthesis")

    # ── Run Options ───────────────────────────────────────────────────────────
    parser.add_argument("--depth", choices=["quick","standard","deep"], default="standard",
                        help="Search depth: quick=~20s/$0.03 | standard=~45s/$0.06 | deep=~90s/$0.12")
    parser.add_argument("--deep", action="store_true", help="Alias for --depth deep")
    parser.add_argument("--save", action="store_true", help="Save report to JSON file")
    parser.add_argument("--json", action="store_true", help="Output raw JSON only")
    parser.add_argument("--fresh", action="store_true", help="Force re-run even if cached report exists")
    parser.add_argument("--no-owner-profile", action="store_true", help="Skip automatic owner profiling")
    args = parser.parse_args()

    OPENROUTER_KEY = load_openrouter_key()
    init_cache()

    # Check cache first (skip if --fresh)
    if not getattr(args, "fresh", False):
        cached = get_cached_report(args.target, args.type)
        if cached:
            if not args.json:
                print(f"\n⚡ Cache hit — report from {cached['_meta'].get('cached_at','?')[:10]} (use --fresh to re-run)\n")
                print_report(cached)
            else:
                print(json.dumps(cached, indent=2))
            if args.save:
                path = save_report(cached, args.target)
                print(f"📁 Saved: {path}\n")
            return
    if not OPENROUTER_KEY:
        print("❌ OpenRouter key not found", file=sys.stderr)
        sys.exit(1)

    target      = args.target
    target_type = args.type
    state       = (args.state or "").upper() or None
    url         = args.url
    deep_mode   = getattr(args, "deep", False) or getattr(args, "depth", "standard") == "deep"
    depth       = "deep" if deep_mode else getattr(args, "depth", "standard")
    notes       = getattr(args, "notes", None)

    # ── Build context dict from all intake fields ────────────────────────────
    aliases_raw = getattr(args, "aliases", None)
    ctx = {
        "email":          getattr(args, "email", None),
        "phone":          getattr(args, "phone", None),
        "url":            url,
        "country":        getattr(args, "country", None),
        "state":          state,
        "city":           getattr(args, "city", None),
        "address":        getattr(args, "address", None),
        "linkedin":       getattr(args, "linkedin", None),
        "instagram":      getattr(args, "instagram", None),
        "twitter":        getattr(args, "twitter", None),
        "facebook":       getattr(args, "facebook", None),
        "ebay":           getattr(args, "ebay", None),
        "handle":         getattr(args, "handle", None),
        "dob":            getattr(args, "dob", None),
        "aliases":        [a.strip() for a in aliases_raw.split(",")] if aliases_raw else [],
        "company_number": getattr(args, "company_number", None),
        "company":        getattr(args, "company", None),
        "industry":       getattr(args, "industry", None),
        "relationship":   getattr(args, "relationship", None),
        "stakes":         getattr(args, "stakes", None),
        "concerns":       getattr(args, "concerns", None),
        "notes":          notes,
    }

    # Auto-escalate depth based on stakes
    if ctx.get("stakes") in ("large", "critical") and depth == "standard":
        depth = "deep"
        deep_mode = True

    # Depth multiplier
    results_per_query = {"quick": 3, "standard": 5, "deep": 10}.get(depth, 5)

    if deep_mode:
        _orig_serper = serper_search
        def _deep_serper(query, max_results=5):
            return _orig_serper(query, max(max_results, results_per_query))
        globals()["serper_search"] = _deep_serper

    if not args.json:
        extras = []
        if ctx.get("email"):   extras.append(f"email:{ctx['email']}")
        if ctx.get("phone"):   extras.append(f"phone:{ctx['phone']}")
        if ctx.get("country"): extras.append(f"country:{ctx['country']}")
        if ctx.get("city"):    extras.append(f"city:{ctx['city']}")
        if ctx.get("industry"):extras.append(f"industry:{ctx['industry']}")
        if ctx.get("concerns"):extras.append(f"concerns:{ctx['concerns']}")
        extra_str = " | " + " | ".join(extras) if extras else ""
        print(f"\n🔍 Running OSINT on: {target} [{target_type}] [{depth.upper()}]{extra_str}")
        print("   Running all searches in parallel...", end="", flush=True)

    t0 = time.time()

    # ── Build dynamic queries ────────────────────────────────────────────────
    queries = build_queries(target, target_type, ctx)

    # If URL provided, add domain-specific queries
    if url:
        domain = urllib.parse.urlparse(url).netloc.replace("www.", "")
        queries += [
            f'site:{domain}',
            f'"{domain}" owner company review',
            f'"{target}" "{domain}" review complaints',
            f'whois "{domain}" domain registration',
        ]

    # Build corporate lookup jobs (always run FL Sunbiz + OpenCorporates for companies)
    corporate_jobs = []
    if url:
        corporate_jobs.append(("domain_intel", domain_intel, url))

    # Wire in Kali OSINT tools + extra known context
    if url and target_type in ("company", "person"):
        domain_seed = urllib.parse.urlparse(url).netloc.replace("www.", "")
        corporate_jobs.append(("theharvester", theharvester_lookup, domain_seed))
        corporate_jobs.append(("whatweb_scan", whatweb_scan, url))
        corporate_jobs.append(("nmap_scan", nmap_scan, domain_seed))
        corporate_jobs.append(("wayback_history", wayback_history, url))

    # ── Wire context fields into module jobs ────────────────────────────────────
    phone     = ctx.get("phone")
    email_arg = ctx.get("email")
    handle    = ctx.get("handle") or ctx.get("instagram") or ctx.get("twitter")

    if phone:
        corporate_jobs.append(("phone_deep", phoneinfoga_lookup, phone))
    if email_arg:
        corporate_jobs.append(("holehe_check", holehe_email_check, email_arg))
        corporate_jobs.append(("email_discovery_seed", email_discovery, email_arg))
        corporate_jobs.append(("h8mail_breach", h8mail_lookup, email_arg))
        corporate_jobs.append(("ghunt_google", ghunt_lookup, email_arg))
        corporate_jobs.append(("socialscan_email", socialscan_check, email_arg))
    # All social handles — maigret checks username across 50+ platforms
    for h_key in ("handle", "instagram", "twitter"):
        h = ctx.get(h_key)
        if h:
            corporate_jobs.append((f"username_osint_{h_key}", username_osint, h))
            corporate_jobs.append((f"socialscan_{h_key}", socialscan_check, h))
            corporate_jobs.append((f"instaloader_{h_key}", instaloader_profile, h))
    # eBay username if provided
    if ctx.get("ebay"):
        corporate_jobs.append(("ebay_seller_direct", ebay_seller_lookup, ctx["ebay"]))
    # LinkedIn if provided — add targeted search
    if ctx.get("linkedin"):
        corporate_jobs.append(("linkedin_direct", linkedin_intel, target, ctx["linkedin"]))

    # ── v8: Smart Country Detection ─────────────────────────────────────────────
    country_hint = getattr(args, 'country', None)
    detected_countries = detect_country(target, country_hint)

    if target_type in ("company", "person"):
        # ── Smart registry routing — only fire registries relevant to detected countries ──
        is_us   = "US" in detected_countries
        is_uk   = "UK" in detected_countries
        is_ch   = "CH" in detected_countries
        is_fr   = "FR" in detected_countries
        is_intl = any(c not in ("US",) for c in detected_countries)  # has any non-US country

        # OpenCorporates — global coverage (140+ jurisdictions including all non-US)
        corporate_jobs.append(("opencorporates", opencorporates_lookup, target, state))

        # US-specific: only fire if US detected OR no country detected (default)
        if is_us or not is_intl:
            # us_national_business_lookup covers: OpenCorporates US, SAM.gov,
            # IRS nonprofits, state-specific portal, SEC EDGAR — all in one call
            corporate_jobs.append(("us_national_registry", us_national_business_lookup, target, state))

        # UK
        if is_uk:
            corporate_jobs.append(("companies_house_uk", companies_house_lookup, target))

        # Switzerland
        if is_ch:
            corporate_jobs.append(("zefix_ch", zefix_lookup, target))

        # France
        if is_fr:
            corporate_jobs.append(("pappers_fr", pappers_lookup, target))

        # All other countries — global registry engine
        non_handled = [c for c in detected_countries if c not in ("US","UK","CH","FR")]
        if non_handled:
            corporate_jobs.append(("global_registries", global_registry_search, target, non_handled))

        # State courts — scope to detected country
        if is_us or not is_intl:
            state_list = [state] if state else ["FL","CA","NY","TX"]
            corporate_jobs.append(("state_courts", state_court_search, target, state_list))
        elif "CA" in detected_countries:
            # Canadian court search
            corporate_jobs.append(("state_courts", state_court_search, target, ["CA"]))
        elif "UK" in detected_countries:
            corporate_jobs.append(("state_courts", state_court_search, target, ["UK"]))
        # Marketplace + reputation — always run for companies
        corporate_jobs.append(("ebay_seller", ebay_seller_lookup, target))
        corporate_jobs.append(("chrono24_seller", chrono24_seller_lookup, target))
        corporate_jobs.append(("forum_reputation", forum_reputation_lookup, target))
        corporate_jobs.append(("related_entities", related_entities_lookup, target))
        # OFAC sanctions check
        corporate_jobs.append(("ofac", ofac_check, target))
        # Federal court + bankruptcy (US-focused but still useful globally for US-listed entities)
        corporate_jobs.append(("federal_courts", courtlistener_search, target))
        corporate_jobs.append(("bankruptcy", bankruptcy_search, target))
        # SEC EDGAR — US only
        # (US state registries now handled by smart routing above)
        corporate_jobs.append(("sec_edgar", sec_edgar_search, target))
        # News archive
        corporate_jobs.append(("news_archive", news_archive_search, target))
        # Social + profile intel
        corporate_jobs.append(("linkedin_intel", linkedin_intel, target))
        corporate_jobs.append(("instagram_intel", instagram_intel, target))
        corporate_jobs.append(("google_business", google_business_intel, target))
        # eBay sold history
        corporate_jobs.append(("ebay_sold", ebay_sold_listings, target))
        # Watch platform presence
        corporate_jobs.append(("watch_platforms", watch_platform_presence, target))
        # FEC donations + PPP loans — US only
        if is_us or not is_intl:
            corporate_jobs.append(("fec_donations", fec_lookup, target))
            corporate_jobs.append(("ppp_loans", ppp_loan_lookup, target))
        # Data breach
        corporate_jobs.append(("data_breach", data_breach_check, target))
        # Email discovery
        corporate_jobs.append(("email_discovery", email_discovery, target))
        # Property records
        corporate_jobs.append(("property_records", property_records_lookup, target))
        # NEW v7: FINRA BrokerCheck
        corporate_jobs.append(("finra", finra_brokercheck, target))
        # NEW v7: USPTO Trademark
        corporate_jobs.append(("uspto_trademark", uspto_trademark_search, target))
        # NEW v7: BBB
        corporate_jobs.append(("bbb", bbb_lookup, target, state))
        # NEW v7: Ripoff Report
        corporate_jobs.append(("ripoffreport", ripoffreport_lookup, target))
        # NEW v7: EU/UN Sanctions
        corporate_jobs.append(("eu_un_sanctions", eu_un_sanctions_check, target))
        # NEW v7: Voter registration (persons only)
        if target_type == "person" and (is_us or not is_intl):
            corporate_jobs.append(("voter_registration", voter_registration_lookup, target, state or "FL"))
        # NEW v10: ICIJ Offshore Leaks
        corporate_jobs.append(("icij", icij_offshore_leaks, target))
        # NEW v10: DOJ + federal enforcement
        corporate_jobs.append(("federal_enforcement", doj_federal_enforcement, target))
        # NEW v10: Professional licenses
        corporate_jobs.append(("pro_licenses", professional_license_check, target, state, ctx.get("industry")))
        # NEW v10: CFPB complaints
        corporate_jobs.append(("cfpb", cfpb_complaints, target))
        # NEW v10: Glassdoor/Indeed employer reviews
        corporate_jobs.append(("employer_reviews", employer_review_intel, target))
        # NEW v10: Crunchbase/startup intel
        corporate_jobs.append(("crunchbase", crunchbase_intel, target))
        # NEW v10: USASpending contracts — US only
        if is_us or not is_intl:
            corporate_jobs.append(("usaspending", usaspending_contracts, target))
        # NEW v10: Interpol + fugitive check
        corporate_jobs.append(("interpol", interpol_check, target))
        # NEW v10: BreachDirectory (if email or domain available)
        domain_for_breach = urllib.parse.urlparse(url).netloc.replace("www.","") if url else None
        if email_arg or domain_for_breach:
            corporate_jobs.append(("breach_directory", breachdirectory_check, email_arg, domain_for_breach))
        # Phone reverse — only if phone number detected in target
        import re as _re
        phone_match = _re.search(r'[\d\-\(\)\+\s]{10,15}', target)
        if phone_match:
            corporate_jobs.append(("phone_lookup", phone_reverse_lookup, phone_match.group(0).strip()))

    # Run everything in parallel
    raw_results, corporate_data = run_searches_parallel(queries, corporate_jobs)
    # Inject intake context into corporate_data so synthesis has full picture
    corporate_data["_intake_ctx"] = {k: v for k, v in ctx.items() if v and k != "notes"}
    search_time = time.time() - t0

    if not args.json:
        print(f" done ({search_time:.1f}s)")
        print("   Synthesizing with Haiku...", end="", flush=True)

    # ── v8: Owner Deep Profile (runs in parallel while synthesis fires) ──────────
    owner_profile_future = None
    skip_owner = getattr(args, 'no_owner_profile', False)
    manual_owner = getattr(args, 'owner', None)
    if not skip_owner:
        from concurrent.futures import ThreadPoolExecutor as _TPE
        _pool = _TPE(max_workers=1)
        if manual_owner:
            # Manual owner specified — profile directly
            loc_hint = state or getattr(args, 'country', None)
            owner_profile_future = _pool.submit(
                lambda: {"source": "owner_profiles",
                         "owners_found": [manual_owner],
                         "profiles": {manual_owner: deep_person_profile(manual_owner, company=target, location=loc_hint)}}
            )
        elif target_type in ("company", "watch"):
            owner_profile_future = _pool.submit(extract_and_profile_owners, target, corporate_data, raw_results)
        elif target_type == "person":
            # Person IS the subject — run deep profile directly
            owner_profile_future = _pool.submit(
                lambda: {"source": "owner_profiles",
                         "owners_found": [target],
                         "profiles": {target: deep_person_profile(target, location=state or getattr(args, 'country', None))}}
            )

    # Synthesize with Haiku
    report = synthesize_with_haiku(target, target_type, raw_results, corporate_data, notes=ctx.get("notes") or notes)
    total_time = time.time() - t0

    # Collect owner profiles
    if owner_profile_future:
        try:
            owner_data = owner_profile_future.result(timeout=90)
            report["owner_profiles"] = owner_data
            # Bubble up owner red signals into top-level red_flags
            for owner, profile in owner_data.get("profiles", {}).items():
                sigs = profile.get("signal_summary", {})
                all_sigs = (sigs.get("criminal_signals",[]) + sigs.get("fraud_signals",[]) +
                            sigs.get("financial_distress_signals",[]))
                if all_sigs:
                    flag = f"OWNER {owner}: signals detected — {', '.join(all_sigs[:4])}"
                    if "red_flags" not in report:
                        report["red_flags"] = []
                    if flag not in report["red_flags"]:
                        report["red_flags"].append(flag)
            _pool.shutdown(wait=False)
        except Exception:
            report["owner_profiles"] = {"source": "owner_profiles", "error": "timed out"}

    if not args.json:
        print(f" done ({total_time:.1f}s total)\n")

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_report(report)

    # Post-synthesis: run virtual office check on extracted addresses
    if report and not report.get("error"):
        addrs = report.get("locations", [])
        cr = report.get("corporate_records", {})
        if cr.get("principal_address"):
            addrs = [cr["principal_address"]] + addrs
        if addrs:
            vo_result = virtual_office_check(addrs)
            report["virtual_office"] = vo_result
            if vo_result["virtual_office_detected"] and not args.json:
                print(f"⚠️  VIRTUAL OFFICE FLAG: {vo_result['flags']}")

    # Save to cache
    if report and not report.get("error"):
        try:
            report["_meta"]["total_time_seconds"] = total_time
        except Exception:
            pass
        save_to_cache(target, target_type, report)

    if args.save:
        path = save_report(report, target)
        print(f"📁 Saved: {path}\n")


if __name__ == "__main__":
    main()


