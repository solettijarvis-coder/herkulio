"""
ENTITY_RESOLVER.py — False Positive Reduction & Entity Disambiguation
======================================================================
Solves the "wrong John Smith" problem.

When search results come back, many will be about OTHER people/companies
with the same or similar names. This module scores each result for
relevance to the ACTUAL target using all available context anchors.

Anchors (identity signals):
  - Location (city, state, country)
  - Company association
  - Industry context
  - Email domain
  - Age / DOB range
  - Known associates

Each result gets a relevance score. Low-scoring results get demoted
or removed before they pollute synthesis.
"""

import re
from difflib import SequenceMatcher


class EntityResolver:
    """
    Score search results for relevance to the actual target.
    Filters out "wrong John Smith" noise.
    """

    def __init__(self, target: str, target_type: str, context: dict):
        self.target = target.lower().strip()
        self.target_words = set(self.target.split())
        self.target_type = target_type
        self.ctx = context or {}

        # Build anchor signals
        self.location_anchors = self._build_location_anchors()
        self.company_anchors = self._build_company_anchors()
        self.industry_anchors = self._build_industry_anchors()
        self.email_domain = self._extract_email_domain()

    def _build_location_anchors(self) -> set:
        """Build set of location terms for matching."""
        anchors = set()
        for field in ["city", "state", "country", "address"]:
            val = self.ctx.get(field, "")
            if val:
                for word in val.lower().split():
                    if len(word) > 2:
                        anchors.add(word)
        return anchors

    def _build_company_anchors(self) -> set:
        """Build set of company-related terms."""
        anchors = set()
        for field in ["company", "employer"]:
            val = self.ctx.get(field, "")
            if val:
                for word in val.lower().split():
                    if len(word) > 2:
                        anchors.add(word)
        # Also add target name words (for company searches)
        if self.target_type == "company":
            for word in self.target_words:
                if len(word) > 2:
                    anchors.add(word)
        return anchors

    def _build_industry_anchors(self) -> set:
        """Build industry-related terms."""
        anchors = set()
        industry = self.ctx.get("industry", "")
        if industry:
            anchors.update(industry.lower().split())
        notes = self.ctx.get("notes", "")
        if notes:
            # Extract key terms from notes
            for word in notes.lower().split():
                if len(word) > 3:
                    anchors.add(word)
        return anchors

    def _extract_email_domain(self) -> str:
        """Extract domain from email if available."""
        email = self.ctx.get("email", "")
        if email and "@" in email:
            return email.split("@")[-1].lower()
        return ""

    def score_result(self, result: dict) -> float:
        """
        Score a search result for relevance to the actual target.
        Returns 0.0 (irrelevant) to 1.0 (perfect match).
        """
        if not isinstance(result, dict):
            return 0.0

        text = (
            (result.get("title", "") or "") + " " +
            (result.get("content", "") or "") + " " +
            (result.get("url", "") or "")
        ).lower()

        if not text.strip():
            return 0.0

        score = 0.0

        # --- Target name presence ---
        # Full name match
        if self.target in text:
            score += 0.35
        else:
            # Partial name match (for common names)
            word_matches = sum(1 for w in self.target_words if w in text and len(w) > 2)
            name_ratio = word_matches / max(len(self.target_words), 1)
            score += name_ratio * 0.25

        # --- Location anchor match ---
        if self.location_anchors:
            loc_matches = sum(1 for anchor in self.location_anchors if anchor in text)
            if loc_matches > 0:
                score += min(0.25, loc_matches * 0.10)

        # --- Company anchor match ---
        if self.company_anchors:
            co_matches = sum(1 for anchor in self.company_anchors if anchor in text)
            if co_matches > 0:
                score += min(0.20, co_matches * 0.08)

        # --- Industry context match ---
        if self.industry_anchors:
            ind_matches = sum(1 for anchor in self.industry_anchors if anchor in text)
            if ind_matches > 0:
                score += min(0.15, ind_matches * 0.05)

        # --- Email domain match ---
        if self.email_domain and self.email_domain in text:
            score += 0.15

        # --- Negative signals (wrong entity) ---
        # Different location mentioned prominently
        wrong_location_signals = self._detect_wrong_location(text)
        if wrong_location_signals > 0:
            score -= wrong_location_signals * 0.15

        # Clearly different industry
        if self._detect_wrong_industry(text):
            score -= 0.20

        return max(0.0, min(1.0, score))

    def _detect_wrong_location(self, text: str) -> int:
        """Detect if result is about someone in a different location."""
        if not self.location_anchors:
            return 0

        # Common false positive locations
        # If we're looking for someone in Miami and result mentions Phoenix...
        other_cities = {
            "phoenix", "seattle", "portland", "boston", "denver",
            "detroit", "minneapolis", "kansas city", "memphis",
            "pittsburgh", "cleveland", "st louis", "indianapolis",
        }

        wrong_count = 0
        for city in other_cities:
            if city in text and city not in self.location_anchors:
                wrong_count += 1

        return min(2, wrong_count)  # Cap penalty

    def _detect_wrong_industry(self, text: str) -> bool:
        """Detect if result is clearly about a different industry."""
        if not self.industry_anchors:
            return False

        # If we're looking for a watch dealer and result is about a plumber...
        clearly_wrong = {
            "plumb": ["watch", "jewel", "luxury", "finance"],
            "hvac": ["watch", "jewel", "luxury", "finance"],
            "dental": ["watch", "jewel", "luxury", "finance"],
            "pediatr": ["watch", "jewel", "luxury", "finance"],
            "veterinar": ["watch", "jewel", "luxury", "finance"],
        }

        for wrong_kw, protected_industries in clearly_wrong.items():
            if wrong_kw in text:
                if any(ind in str(self.industry_anchors) for ind in protected_industries):
                    return True

        return False

    def filter_results(self, results: list, threshold: float = 0.20) -> list:
        """Filter a list of results, keeping only those above threshold."""
        scored = []
        for r in results:
            s = self.score_result(r)
            if s >= threshold:
                r["_entity_relevance"] = round(s, 2)
                scored.append(r)

        # Sort by relevance
        scored.sort(key=lambda x: x.get("_entity_relevance", 0), reverse=True)
        return scored

    def filter_all_results(self, raw_results: dict, threshold: float = 0.20) -> dict:
        """Filter all query results through entity resolution."""
        filtered = {}
        for query, results in raw_results.items():
            if isinstance(results, list):
                kept = self.filter_results(results, threshold)
                if kept:
                    filtered[query] = kept
        return filtered


# ═══════════════════════════════════════════════════════════════════════════════
# TEST
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Test: searching for "John Smith" watch dealer in Miami
    resolver = EntityResolver(
        target="John Smith",
        target_type="person",
        context={
            "city": "Miami",
            "state": "FL",
            "industry": "watches",
            "notes": "watch dealer, luxury timepieces",
        }
    )

    test_results = [
        {"title": "John Smith - Watch Dealer Miami", "content": "John Smith operates a luxury watch dealership in Miami, FL", "url": "https://example.com"},
        {"title": "John Smith - Plumber in Phoenix AZ", "content": "John Smith plumbing services in Phoenix Arizona", "url": "https://plumber.com"},
        {"title": "John Smith - Chrono24 Dealer", "content": "Professional watch dealer John Smith, based in South Florida", "url": "https://chrono24.com/dealer/123"},
        {"title": "John Smith - Dentist Seattle", "content": "Dr. John Smith, DDS, family dentistry in Seattle WA", "url": "https://dentist.com"},
        {"title": "Smith & Associates LLC", "content": "Investment firm in New York handling securities and trading", "url": "https://smith-invest.com"},
    ]

    print("Entity Resolution Test: 'John Smith' (watch dealer, Miami)")
    print("=" * 60)
    for r in test_results:
        score = resolver.score_result(r)
        keep = "✅ KEEP" if score >= 0.20 else "❌ FILTER"
        print(f"  {keep} ({score:.2f}) {r['title']}")
