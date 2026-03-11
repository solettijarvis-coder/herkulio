"""
Herkulio OSINT Engine — Standalone Version
Removed all Jarvis-specific dependencies
"""

import os
import sys

# Add osint directory to path
OSINT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, OSINT_DIR)

# Load environment
from dotenv import load_dotenv
load_dotenv('/app/config/.env')

# Configuration from environment (no hardcoded paths)
TAVILY_KEY = os.environ.get("TAVILY_API_KEY")
SERPER_KEY = os.environ.get("SERPER_API_KEY")
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY")
SYNTH_MODEL = os.environ.get("DEFAULT_MODEL", "google/gemini-2.5-flash")

# Data directories (container paths, not Jarvis home)
OUTPUT_DIR = os.environ.get("REPORTS_DIR", "/app/data/reports")
CACHE_DB = os.environ.get("CACHE_DB", "/app/data/cache/reports_cache.db")
CACHE_TTL_DAYS = int(os.environ.get("CACHE_TTL_DAYS", "7"))

# Ensure directories exist
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(os.path.dirname(CACHE_DB), exist_ok=True)

# Import the rest of the original osint.py functionality
# The original file will be imported and used as-is, but with these new config values

# Override the original module's constants
import osint
osint.TAVILY_KEY = TAVILY_KEY
osint.SERPER_KEY = SERPER_KEY
osint.OPENROUTER_KEY = OPENROUTER_KEY
osint.SYNTH_MODEL = SYNTH_MODEL
osint.OUTPUT_DIR = OUTPUT_DIR
osint.CACHE_DB = CACHE_DB
osint.CACHE_TTL_DAYS = CACHE_TTL_DAYS

# Re-export all functions
from osint import (
    build_queries,
    sunbiz_lookup,
    opencorporates_lookup,
    serper_search,
    tavily_search_fallback,
    run_searches_parallel,
    companies_house_lookup,
    zefix_lookup,
    pappers_lookup,
    ebay_seller_lookup,
    chrono24_seller_lookup,
    forum_reputation_lookup,
    phone_reverse_lookup,
    related_entities_lookup,
    ofac_check,
    courtlistener_search,
    bankruptcy_search,
    domain_intel,
    virtual_office_check,
    us_state_registry_search,
    sec_edgar_search,
    news_archive_search,
    linkedin_intel,
    instagram_intel,
    google_business_intel,
    ebay_sold_listings,
    watch_platform_presence,
    fec_lookup,
    ppp_loan_lookup,
    data_breach_check,
    email_discovery,
    property_records_lookup,
    theharvester_lookup,
    username_osint,
    holehe_email_check,
    phoneinfoga_lookup,
    h8mail_lookup,
    whatweb_scan,
    nmap_scan,
    socialscan_check,
    ghunt_lookup,
    instaloader_profile,
    wayback_history,
    finra_brokercheck,
    uspto_trademark_search,
    bbb_lookup,
    ripoffreport_lookup,
    eu_un_sanctions_check,
    voter_registration_lookup,
    score_report_confidence,
    synthesize_with_haiku,
    print_report,
)

__all__ = [
    # Add all exported functions here
]
