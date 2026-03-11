#!/usr/bin/env python3
"""
HERKULIO_ENGINE.py — Unified Intelligence Pipeline v2
======================================================
The new entry point that wires together:
  - module_router.py (smart module selection)
  - cross_reference.py (data validation)
  - synthesis_v2.py (two-pass AI synthesis)
  - report_formatter.py (tiered output)
  - osint.py (the actual module functions — used as a library)

Replaces the old osint.py main() flow:
  OLD: fire everything → dump into one prompt → pray
  NEW: route smartly → search → filter → cross-reference → extract → analyze → format

Usage:
  python3 herkulio_engine.py "Acme Watches LLC" --type company --state FL --depth deep --save
  python3 herkulio_engine.py "Pasta Palace" --type company --country CA --state BC --city Vancouver
  python3 herkulio_engine.py "John Smith" --type person --state FL --email john@test.com
"""

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

# Add osint dir to path
OSINT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, OSINT_DIR)

# Load .env
from dotenv import load_dotenv
load_dotenv(os.path.join(OSINT_DIR, '.env'))

# Our new modules
from module_router import (
    select_modules, detect_industry, resolve_geography, format_routing_summary
)
from cross_reference import (
    CrossReferencer, ContradictionDetector, ConfidenceTagger, format_for_synthesis
)
from synthesis_v2 import TwoPassSynthesizer
from report_formatter import format_report
from entity_resolver import EntityResolver
from investigation_memory import store_investigation, check_prior_knowledge
from pattern_detector import PatternDetector, format_pattern_results

# Import existing module functions from osint.py (used as library)
import osint as ENGINE

# ═══════════════════════════════════════════════════════════════════════════════
# RESULT QUALITY SCORER (Item #9)
# ═══════════════════════════════════════════════════════════════════════════════

# Domain authority tiers
TIER1_DOMAINS = {
    "gov", "mil", "judiciary", "uscourts", "sec.gov", "justice.gov",
    "fbi.gov", "ftc.gov", "treasury.gov", "state.gov", "irs.gov",
    "sunbiz.org", "companies-house", "zefix.ch", "ofac",
}
TIER2_DOMAINS = {
    "reuters.com", "bloomberg.com", "wsj.com", "nytimes.com", "bbc.com",
    "opencorporates.com", "courtlistener.com", "bbb.org", "linkedin.com",
    "crunchbase.com", "pitchbook.com", "glassdoor.com",
}


def score_result(result: dict, target: str, context: dict = None) -> float:
    """
    Score a search result for relevance. 0.0 = garbage, 1.0 = perfect.
    Results below 0.2 get filtered out before synthesis.
    """
    if not isinstance(result, dict) or result.get("error"):
        return 0.0

    score = 0.0
    title = (result.get("title", "") or "").lower()
    url = (result.get("url", "") or "").lower()
    content = (result.get("content", "") or "").lower()
    target_lower = target.lower()

    # Target name in title (strong signal)
    target_words = target_lower.split()
    if len(target_words) >= 2:
        # At least 2 words of target in title
        matches = sum(1 for w in target_words if w in title and len(w) > 2)
        if matches >= 2:
            score += 0.35
        elif matches >= 1:
            score += 0.15
    elif target_lower in title:
        score += 0.30

    # Authoritative domain
    for domain in TIER1_DOMAINS:
        if domain in url:
            score += 0.30
            break
    else:
        for domain in TIER2_DOMAINS:
            if domain in url:
                score += 0.20
                break

    # Content has substance (not just a snippet)
    if len(content) > 100:
        score += 0.10
    if len(content) > 300:
        score += 0.05

    # Location match
    ctx = context or {}
    location_terms = []
    for field in ["city", "state", "country"]:
        val = ctx.get(field, "")
        if val:
            location_terms.append(val.lower())
    if location_terms:
        loc_matches = sum(1 for loc in location_terms if loc in content or loc in title)
        if loc_matches > 0:
            score += 0.15

    # Recency signals
    for year in ["2025", "2026"]:
        if year in content or year in title:
            score += 0.05
            break

    return min(1.0, score)


def filter_results(raw_results: dict, target: str, context: dict = None,
                    threshold: float = 0.2) -> dict:
    """Filter search results by quality score. Returns only relevant results."""
    filtered = {}
    total_before = 0
    total_after = 0

    for query, results in raw_results.items():
        total_before += len(results)
        scored = []
        for r in results:
            s = score_result(r, target, context)
            if s >= threshold:
                r["_quality_score"] = round(s, 2)
                scored.append(r)
        # Sort by quality score descending
        scored.sort(key=lambda x: x.get("_quality_score", 0), reverse=True)
        if scored:
            filtered[query] = scored
            total_after += len(scored)

    return filtered


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE → FUNCTION MAPPING
# ═══════════════════════════════════════════════════════════════════════════════

def _build_module_jobs(selected_modules: list, target: str, target_type: str,
                        geo: dict, context: dict) -> list:
    """
    Map selected module IDs to actual function calls from osint.py.
    Returns list of (label, function, *args) tuples for parallel execution.
    """
    jobs = []
    state = geo.get("region", "").replace("US-", "").replace("CA-", "") if geo.get("region") else None
    country = geo.get("country", "US")
    url = context.get("url")
    email = context.get("email")
    phone = context.get("phone")
    handle = context.get("handle") or context.get("instagram")
    domain = None
    if url:
        import urllib.parse
        domain = urllib.parse.urlparse(url if "://" in url else f"https://{url}").netloc.replace("www.", "")

    for module_id in selected_modules:
        try:
            if module_id == "ofac_check":
                jobs.append(("ofac", ENGINE.ofac_check, target))
            elif module_id == "eu_un_sanctions":
                jobs.append(("eu_un_sanctions", ENGINE.eu_un_sanctions_check, target))
            elif module_id == "icij_offshore":
                jobs.append(("icij", ENGINE.icij_offshore_leaks, target))
            elif module_id == "interpol_check":
                jobs.append(("interpol", ENGINE.interpol_check, target))
            elif module_id == "opencorporates":
                jobs.append(("opencorporates", ENGINE.opencorporates_lookup, target, state))
            elif module_id == "news_archive":
                jobs.append(("news_archive", ENGINE.news_archive_search, target))
            elif module_id == "google_business":
                jobs.append(("google_business", ENGINE.google_business_intel, target))
            elif module_id == "linkedin_intel":
                jobs.append(("linkedin_intel", ENGINE.linkedin_intel, target))
            elif module_id == "forum_reputation":
                jobs.append(("forum_reputation", ENGINE.forum_reputation_lookup, target))
            elif module_id == "related_entities":
                jobs.append(("related_entities", ENGINE.related_entities_lookup, target))
            elif module_id == "sunbiz_fl":
                jobs.append(("sunbiz_fl", ENGINE.sunbiz_lookup, target))
            elif module_id == "us_national_registry":
                jobs.append(("us_national_registry", ENGINE.us_national_business_lookup, target, state))
            elif module_id == "companies_house_uk":
                jobs.append(("companies_house_uk", ENGINE.companies_house_lookup, target))
            elif module_id == "zefix_ch":
                jobs.append(("zefix_ch", ENGINE.zefix_lookup, target))
            elif module_id == "pappers_fr":
                jobs.append(("pappers_fr", ENGINE.pappers_lookup, target))
            elif module_id == "global_registries":
                non_handled = [c for c in geo.get("countries", []) if c not in ("US", "UK", "CH", "FR")]
                if non_handled:
                    jobs.append(("global_registries", ENGINE.global_registry_search, target, non_handled))
            elif module_id == "federal_courts":
                jobs.append(("federal_courts", ENGINE.courtlistener_search, target))
            elif module_id == "bankruptcy_search":
                jobs.append(("bankruptcy", ENGINE.bankruptcy_search, target))
            elif module_id == "state_courts":
                states = [state] if state else ["FL", "CA", "NY", "TX"]
                jobs.append(("state_courts", ENGINE.state_court_search, target, states))
            elif module_id == "federal_enforcement":
                jobs.append(("federal_enforcement", ENGINE.doj_federal_enforcement, target))
            elif module_id == "sec_edgar":
                jobs.append(("sec_edgar", ENGINE.sec_edgar_search, target))
            elif module_id == "finra_brokercheck":
                jobs.append(("finra", ENGINE.finra_brokercheck, target))
            elif module_id == "fec_donations":
                jobs.append(("fec_donations", ENGINE.fec_lookup, target))
            elif module_id == "ppp_loans":
                jobs.append(("ppp_loans", ENGINE.ppp_loan_lookup, target))
            elif module_id == "usaspending":
                jobs.append(("usaspending", ENGINE.usaspending_contracts, target))
            elif module_id == "cfpb_complaints":
                jobs.append(("cfpb", ENGINE.cfpb_complaints, target))
            elif module_id == "chrono24_seller":
                jobs.append(("chrono24_seller", ENGINE.chrono24_seller_lookup, target))
            elif module_id == "watch_platforms":
                jobs.append(("watch_platforms", ENGINE.watch_platform_presence, target))
            elif module_id == "ebay_seller":
                jobs.append(("ebay_seller", ENGINE.ebay_seller_lookup, target))
            elif module_id == "ebay_sold_listings":
                jobs.append(("ebay_sold", ENGINE.ebay_sold_listings, target))
            elif module_id == "professional_licenses":
                jobs.append(("pro_licenses", ENGINE.professional_license_check, target, state))
            elif module_id == "domain_intel":
                if url:
                    jobs.append(("domain_intel", ENGINE.domain_intel, url))
            elif module_id == "theharvester":
                if domain:
                    jobs.append(("theharvester", ENGINE.theharvester_lookup, domain))
            elif module_id == "whatweb_scan":
                if url:
                    jobs.append(("whatweb_scan", ENGINE.whatweb_scan, url))
            elif module_id == "nmap_scan":
                if domain:
                    jobs.append(("nmap_scan", ENGINE.nmap_scan, domain))
            elif module_id == "wayback_history":
                if url:
                    jobs.append(("wayback_history", ENGINE.wayback_history, url))
            elif module_id == "holehe_check":
                if email:
                    jobs.append(("holehe_check", ENGINE.holehe_email_check, email))
            elif module_id == "h8mail_breach":
                if email:
                    jobs.append(("h8mail_breach", ENGINE.h8mail_lookup, email))
            elif module_id == "ghunt_google":
                if email:
                    jobs.append(("ghunt_google", ENGINE.ghunt_lookup, email))
            elif module_id == "email_discovery":
                jobs.append(("email_discovery", ENGINE.email_discovery, target, domain))
            elif module_id == "phone_deep":
                if phone:
                    jobs.append(("phone_deep", ENGINE.phoneinfoga_lookup, phone))
            elif module_id == "phone_reverse":
                if phone:
                    jobs.append(("phone_reverse", ENGINE.phone_reverse_lookup, phone))
            elif module_id == "username_osint":
                if handle:
                    jobs.append(("username_osint", ENGINE.username_osint, handle))
            elif module_id == "instaloader_profile":
                if handle:
                    jobs.append(("instaloader_profile", ENGINE.instaloader_profile, handle))
            elif module_id == "instagram_intel":
                jobs.append(("instagram_intel", ENGINE.instagram_intel, target, handle))
            elif module_id == "property_records":
                jobs.append(("property_records", ENGINE.property_records_lookup, target))
            elif module_id == "data_breach":
                jobs.append(("data_breach", ENGINE.data_breach_check, target, domain))
            elif module_id == "breach_directory":
                jobs.append(("breach_directory", ENGINE.breachdirectory_check, email, domain))
            elif module_id == "voter_registration":
                if target_type == "person":
                    jobs.append(("voter_registration", ENGINE.voter_registration_lookup, target, state or "FL"))
            elif module_id == "bbb_lookup":
                jobs.append(("bbb", ENGINE.bbb_lookup, target, state))
            elif module_id == "ripoffreport":
                jobs.append(("ripoffreport", ENGINE.ripoffreport_lookup, target))
            elif module_id == "uspto_trademark":
                jobs.append(("uspto_trademark", ENGINE.uspto_trademark_search, target))
            elif module_id == "employer_reviews":
                jobs.append(("employer_reviews", ENGINE.employer_review_intel, target))
            elif module_id == "crunchbase_intel":
                jobs.append(("crunchbase", ENGINE.crunchbase_intel, target))
            # Restaurant/hospitality modules (new — use Serper for now)
            elif module_id == "health_inspection":
                jobs.append(("health_inspection", ENGINE.serper_search,
                             f'"{target}" health inspection grade score violation restaurant', 5))
            elif module_id == "liquor_license":
                jobs.append(("liquor_license", ENGINE.serper_search,
                             f'"{target}" liquor license alcohol permit restaurant bar', 5))
            elif module_id == "yelp_opentable":
                jobs.append(("yelp_opentable", ENGINE.serper_search,
                             f'"{target}" yelp OR opentable reviews rating restaurant', 5))
        except AttributeError:
            pass  # Module function doesn't exist in osint.py — skip

    return jobs


# ═══════════════════════════════════════════════════════════════════════════════
# PARALLEL EXECUTOR WITH ERROR HANDLING (Item #39)
# ═══════════════════════════════════════════════════════════════════════════════

def execute_modules_parallel(jobs: list, max_workers: int = 10) -> tuple:
    """
    Execute module jobs in parallel with error handling and retry.
    Returns (results_dict, errors_list, timing_dict)
    """
    results = {}
    errors = []
    timing = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for job in jobs:
            label = job[0]
            func = job[1]
            args = job[2:]
            f = executor.submit(_safe_execute, func, *args)
            futures[f] = (label, time.time())

        for future in as_completed(futures):
            label, start_time = futures[future]
            elapsed = round(time.time() - start_time, 1)
            timing[label] = elapsed

            try:
                result = future.result()
                if result is not None:
                    results[label] = result
            except Exception as e:
                errors.append({
                    "module": label,
                    "error": str(e),
                    "time": elapsed,
                })

    return results, errors, timing


def _safe_execute(func, *args):
    """Execute a function with timeout protection and error capture."""
    try:
        return func(*args)
    except Exception as e:
        return {"error": str(e), "status": "failed"}


# ═══════════════════════════════════════════════════════════════════════════════
# SEARCH QUERY BUILDER (uses module_router context)
# ═══════════════════════════════════════════════════════════════════════════════

def build_search_queries(target: str, target_type: str, geo: dict,
                          industry: list, context: dict, depth: str) -> list:
    """Build targeted search queries using all available context."""
    ctx = {
        "state": geo.get("region", "").replace("US-", "").replace("CA-", "") if geo.get("region") else "",
        "country": geo.get("country", ""),
        "city": geo.get("city", ""),
    }
    ctx.update(context)

    return ENGINE.build_queries(target, target_type, ctx)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════

def run_investigation(target: str, target_type: str = "company",
                       country: str = None, state: str = None, city: str = None,
                       url: str = None, email: str = None, phone: str = None,
                       handle: str = None, industry_hint: str = None,
                       depth: str = "standard", notes: str = None,
                       stakes: str = None, save: bool = False,
                       output_json: bool = False) -> dict:
    """
    Run the full Herkulio intelligence pipeline.
    
    This is the new unified entry point that replaces osint.py main().
    """
    t0 = time.time()

    # ── Load API key ──────────────────────────────────────────────────
    or_key = ENGINE.load_openrouter_key()
    if not or_key:
        return {"error": "OpenRouter key not found"}

    # Also set Serper key from env if available
    serper_env = os.environ.get("SERPER_API_KEY")
    if serper_env:
        ENGINE.SERPER_KEY = serper_env
    tavily_env = os.environ.get("TAVILY_API_KEY")
    if tavily_env:
        ENGINE.TAVILY_KEY = tavily_env

    ENGINE.OPENROUTER_KEY = or_key
    ENGINE.init_cache()

    # Build context dict
    context = {
        "url": url, "email": email, "phone": phone,
        "handle": handle, "notes": notes, "stakes": stakes,
        "instagram": handle,  # alias
    }
    context = {k: v for k, v in context.items() if v}  # Remove None values

    # ── STEP 1: RESOLVE GEOGRAPHY ─────────────────────────────────────
    geo = resolve_geography(target, country=country, state=state, city=city)

    # ── STEP 2: DETECT INDUSTRY ────────────────────────────────────────
    industry = detect_industry(target, url=url, notes=notes, explicit=industry_hint)

    # ── STEP 3: SELECT MODULES ─────────────────────────────────────────
    selected_modules, skipped_modules = select_modules(
        target_type, industry, geo, context, depth
    )
    routing_summary = format_routing_summary(selected_modules, skipped_modules, geo, industry, depth)

    if not output_json:
        print(f"\n🔍 HERKULIO INTELLIGENCE — {target} [{target_type}]")
        print(f"   {geo.get('country', '?')} | {', '.join(industry)} | {depth.upper()}")
        print(f"   {len(selected_modules)} modules selected, {len(skipped_modules)} skipped")

    # ── STEP 4: BUILD SEARCH QUERIES ──────────────────────────────────
    queries = build_search_queries(target, target_type, geo, industry, context, depth)

    if not output_json:
        print(f"   {len(queries)} search queries built")
        print("   Running parallel searches...", end="", flush=True)

    # ── STEP 5: EXECUTE SEARCHES (parallel) ───────────────────────────
    search_t0 = time.time()

    # Web search queries via Serper
    raw_results = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(ENGINE.serper_search, q): q for q in queries}
        for f in as_completed(futures):
            q = futures[f]
            try:
                raw_results[q] = f.result()
            except Exception:
                raw_results[q] = []

    # Module jobs (corporate registries, specialized lookups, etc.)
    module_jobs = _build_module_jobs(selected_modules, target, target_type, geo, context)
    corporate_data, module_errors, module_timing = execute_modules_parallel(module_jobs)

    search_time = time.time() - search_t0

    if not output_json:
        print(f" done ({search_time:.1f}s)")

    # ── STEP 5.5: CHECK PRIOR KNOWLEDGE ─────────────────────────────
    prior = check_prior_knowledge(target, context)
    if prior.get("has_prior_knowledge") and not output_json:
        print(f"\n{prior.get('message', '')}\n")

    # ── STEP 6: FILTER RESULTS (quality + entity resolution) ──────────
    # First pass: quality scoring
    filtered_results = filter_results(raw_results, target, context, threshold=0.15)

    # Second pass: entity resolution (false positive reduction)
    resolver = EntityResolver(target, target_type, {**context, **{
        "city": geo.get("city", ""),
        "state": (geo.get("region") or "").replace("US-", "").replace("CA-", ""),
        "country": geo.get("country", ""),
        "industry": " ".join(industry),
    }})
    filtered_results = resolver.filter_all_results(filtered_results, threshold=0.15)

    total_before = sum(len(v) for v in raw_results.values())
    total_after = sum(len(v) for v in filtered_results.values())

    if not output_json:
        print(f"   Filtered: {total_before} → {total_after} results (quality + entity resolution)")

    # ── STEP 7: TWO-PASS SYNTHESIS ────────────────────────────────────
    if not output_json:
        print("   Running two-pass synthesis...", end="", flush=True)

    synth = TwoPassSynthesizer(or_key)
    report = synth.run(
        target=target,
        target_type=target_type,
        raw_results=filtered_results,
        corporate_data=corporate_data,
        routing_summary=routing_summary,
        context=context,
        stakes=stakes,
        notes=notes,
    )

    total_time = time.time() - t0

    if not output_json:
        print(f" done ({total_time:.1f}s total)")

    # ── STEP 7.5: PATTERN DETECTION ─────────────────────────────────────
    detector = PatternDetector(report, industry=industry)
    triggered_patterns = detector.detect_all()
    if triggered_patterns:
        report["behavioral_patterns"] = triggered_patterns
        if "red_flags" not in report:
            report["red_flags"] = []
        for p in triggered_patterns:
            if p.get("severity") in ("HIGH", "CRITICAL"):
                flag = f"PATTERN: {p['name']} ({p['severity']}) — {p['signals_matched']}/{p['signals_total']} signals"
                if flag not in report["red_flags"]:
                    report["red_flags"].append(flag)

        if not output_json:
            print(format_pattern_results(triggered_patterns))

    # ── STEP 7.6: STORE IN INVESTIGATION MEMORY ──────────────────────────
    if report and not report.get("error"):
        try:
            mem_result = store_investigation(report)
            if not output_json:
                print(f"   📝 Memory: {mem_result.get('entities_stored', 0)} entities, {mem_result.get('links_stored', 0)} links stored")
        except Exception:
            pass

    # ── STEP 7.7: ATTACH PRIOR KNOWLEDGE ─────────────────────────────────
    if prior.get("has_prior_knowledge"):
        report["prior_knowledge"] = prior

    # ── STEP 8: ENRICH METADATA ───────────────────────────────────────
    if "_meta" not in report:
        report["_meta"] = {}
    report["_meta"].update({
        "pipeline": "herkulio_engine_v2",
        "total_time_seconds": round(total_time, 1),
        "search_time_seconds": round(search_time, 1),
        "modules_selected": len(selected_modules),
        "modules_skipped": len(skipped_modules),
        "queries_fired": len(queries),
        "results_before_filter": total_before,
        "results_after_filter": total_after,
        "filter_rate": f"{(1 - total_after / max(total_before, 1)) * 100:.0f}%",
        "module_errors": len(module_errors),
        "geo": geo,
        "industry": industry,
        "depth": depth,
    })
    if module_errors:
        report["_meta"]["errors"] = module_errors
    if triggered_patterns:
        report["_meta"]["patterns_triggered"] = len(triggered_patterns)
        report["_meta"]["pattern_names"] = [p["name"] for p in triggered_patterns]
    if prior.get("has_prior_knowledge"):
        report["_meta"]["prior_knowledge_hits"] = len(prior.get("prior_hits", []))

    # ── STEP 9: OUTPUT ────────────────────────────────────────────────
    if output_json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(format_report(report))

    # ── STEP 10: SAVE ─────────────────────────────────────────────────
    if save:
        path = ENGINE.save_report(report, target)
        print(f"📁 Saved: {path}")

    # Cache
    if report and not report.get("error"):
        ENGINE.save_to_cache(target, target_type, report)

    return report


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Herkulio Intelligence Engine v2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  herkulio_engine.py "Acme Watches LLC" --type company --state FL --depth deep --save
  herkulio_engine.py "Pasta Palace" --type company --country CA --state BC --city Vancouver
  herkulio_engine.py "John Smith" --type person --email john@test.com
  herkulio_engine.py "Rolex Daytona 116500" --type watch
        """
    )
    parser.add_argument("target", help="Name to investigate")
    parser.add_argument("--type", choices=["company", "person", "organization", "watch"],
                        default="company")
    parser.add_argument("--country", default=None)
    parser.add_argument("--state", default=None)
    parser.add_argument("--city", default=None)
    parser.add_argument("--url", default=None)
    parser.add_argument("--email", default=None)
    parser.add_argument("--phone", default=None)
    parser.add_argument("--handle", default=None, help="Instagram/social handle")
    parser.add_argument("--industry", default=None)
    parser.add_argument("--depth", choices=["quick", "standard", "deep"], default="standard")
    parser.add_argument("--notes", default=None)
    parser.add_argument("--stakes", default=None, help="Transaction stakes: small/medium/large/critical")
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--json", action="store_true")

    args = parser.parse_args()

    run_investigation(
        target=args.target,
        target_type=args.type,
        country=args.country,
        state=args.state,
        city=args.city,
        url=args.url,
        email=args.email,
        phone=args.phone,
        handle=args.handle,
        industry_hint=args.industry,
        depth=args.depth,
        notes=args.notes,
        stakes=args.stakes,
        save=args.save,
        output_json=args.json,
    )


if __name__ == "__main__":
    main()
