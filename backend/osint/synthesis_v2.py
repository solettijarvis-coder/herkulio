"""
SYNTHESIS_V2.py — Two-Pass Intelligence Synthesis Engine
==========================================================
Replaces the single-prompt synthesis in osint.py with a structured pipeline:

  PASS 1 (EXTRACT): Cheap model (Gemini Flash) — maps raw data to structured fields.
                     No analysis, no opinions. Just accurate data extraction.

  CROSS-REFERENCE:  Code, not AI — runs CrossReferencer + ContradictionDetector.

  PASS 2 (ANALYZE): Strong model (Sonnet/Opus for high-risk, Flash for low-risk) —
                     Given structured facts + cross-reference report, produces
                     risk assessment, competing scenarios, and recommendations.

Usage:
    from synthesis_v2 import TwoPassSynthesizer
    
    synth = TwoPassSynthesizer(openrouter_key="sk-or-...")
    report = synth.run(
        target="Acme Watches LLC",
        target_type="company",
        raw_results=search_results,
        corporate_data=corporate_data,
        routing_summary=routing_summary,
        context=intake_context,
    )
"""

import json
import os
import time
import urllib.request
from datetime import datetime, timezone

from cross_reference import (
    CrossReferencer, ContradictionDetector, ConfidenceTagger, format_for_synthesis
)

# ═══════════════════════════════════════════════════════════════════════════════
# MODEL CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

MODELS = {
    "extract":       "google/gemini-2.5-flash",       # Cheap, fast — data mapping only
    "analyze_low":   "google/gemini-2.5-flash",       # Low risk — flash is fine
    "analyze_medium":"qwen/qwen3-235b-a22b",    # Medium risk — solid reasoning
    "analyze_high":  "qwen/qwen3-235b-a22b",    # High risk — best reasoning
    "analyze_critical":"qwen/qwen3-235b-a22b",    # Critical (>$100K) — maximum
}

# Cost per 1M tokens (input) for tracking
MODEL_COSTS = {
    "google/gemini-2.5-flash": 0.15,
    "qwen/qwen3-235b-a22b": 0.14,
    "anthropic/claude-sonnet-4-6": 3.00,
    "anthropic/claude-opus-4-6": 15.00,
}

OR_API = "https://openrouter.ai/api/v1/chat/completions"


def _determine_risk_tier(contradictions: list, xref_report: dict,
                          stakes: str = None) -> str:
    """Determine risk tier from cross-reference results and stakes."""
    # Explicit stakes override
    if stakes:
        stakes_lower = stakes.lower()
        if "critical" in stakes_lower or ">1m" in stakes_lower:
            return "critical"
        if "large" in stakes_lower or "100k" in stakes_lower:
            return "high"

    # Auto-determine from findings
    high_contradictions = sum(
        1 for c in contradictions
        if isinstance(c, dict) and c.get("severity") == "HIGH"
    )
    consistency = xref_report.get("consistency_score", 50)

    if high_contradictions >= 3 or consistency < 20:
        return "high"
    elif high_contradictions >= 1 or consistency < 50:
        return "medium"
    else:
        return "low"


# ═══════════════════════════════════════════════════════════════════════════════
# PASS 1: STRUCTURED EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════════

EXTRACT_SYSTEM = """You are a data extraction specialist. Your ONLY job is to map raw search results into structured JSON fields.

RULES:
- Extract ONLY what is explicitly stated in the data
- Use null for any field where data is not found
- Do NOT analyze, interpret, or assess risk
- Do NOT add opinions or recommendations
- Do NOT infer data that isn't explicitly present
- Be precise with names, numbers, dates

Output valid JSON with these fields:
{
  "target": "entity name",
  "type": "company|person",
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
    "parent_entities": []
  },
  "people": [{"name": "", "role": "", "source": ""}],
  "locations": [],
  "online_presence": {
    "website": null,
    "instagram": null,
    "linkedin": null,
    "facebook": null,
    "other": []
  },
  "financial_signals": {
    "claimed_revenue": null,
    "revenue_verified": false,
    "bankruptcies": null,
    "liens_judgments": null
  },
  "legal_history": [],
  "marketplace_presence": {
    "ebay": {"found": false, "feedback_score": null, "url": null},
    "chrono24": {"found": false, "listings": null, "url": null}
  },
  "social_media": {
    "instagram": {"url": null, "followers": null, "posts": null, "full_name": null},
    "linkedin": {"url": null, "connections": null, "employer": null, "name": null}
  },
  "domain_intel": {
    "domain": null, "registered": null, "age_years": null,
    "registrar": null, "privacy_protected": null
  },
  "ofac_status": {"status": "CLEAR|HIT|UNKNOWN"},
  "federal_cases": {"total_found": 0, "cases": []},
  "bankruptcy": {"total_found": 0},
  "forum_reputation": {"overall_sentiment": null, "mentions": []},
  "watch_platform_presence": {},
  "news_archive": [],
  "red_flags_raw": [],
  "green_flags_raw": [],
  "data_gaps": [],
  "sources_consulted": []
}"""


def _build_extraction_prompt(target: str, target_type: str,
                               raw_results: dict, corporate_data: dict,
                               context: dict = None) -> str:
    """Build the extraction prompt with compacted raw data."""
    # Compact search results — keep only useful content
    search_parts = []
    for query, results in raw_results.items():
        if not results:
            continue
        search_parts.append(f"QUERY: {query}")
        for r in results[:4]:  # Cap at 4 results per query
            if isinstance(r, dict) and not r.get("error"):
                title = r.get("title", "")
                url = r.get("url", "")
                content = r.get("content", "")[:250]
                if title or content:
                    search_parts.append(f"  [{title}] {url}")
                    if content:
                        search_parts.append(f"  {content}")

    search_text = "\n".join(search_parts)
    # Cap total search text
    if len(search_text) > 12000:
        search_text = search_text[:12000] + "\n... (truncated)"

    # Compact corporate data
    corp_parts = []
    for source, data in corporate_data.items():
        if source.startswith("_"):
            continue
        corp_parts.append(f"\nSOURCE: {source}")
        data_str = json.dumps(data, default=str)
        if len(data_str) > 2000:
            data_str = data_str[:2000] + "..."
        corp_parts.append(data_str)

    corp_text = "\n".join(corp_parts)
    if len(corp_text) > 15000:
        corp_text = corp_text[:15000] + "\n... (truncated)"

    # Context
    ctx_text = ""
    if context:
        ctx_lines = [f"  {k}: {v}" for k, v in context.items() if v]
        if ctx_lines:
            ctx_text = "\n\nINTAKE CONTEXT:\n" + "\n".join(ctx_lines)

    return f"""Extract structured data for: {target} (type: {target_type})

=== WEB SEARCH RESULTS ===
{search_text}

=== CORPORATE / MODULE DATA ===
{corp_text}
{ctx_text}

Extract ALL factual data into the JSON structure. Use null for missing fields. Do NOT analyze or assess risk."""


# ═══════════════════════════════════════════════════════════════════════════════
# PASS 2: ANALYTICAL SYNTHESIS
# ═══════════════════════════════════════════════════════════════════════════════

ANALYZE_SYSTEM = """You are an elite intelligence analyst producing a risk assessment report.

You are given:
1. STRUCTURED FACTS — extracted and verified data points
2. CROSS-REFERENCE RESULTS — automated comparison of data across sources
3. CONTRADICTION FLAGS — patterns that indicate potential risk
4. DATA CONFIDENCE — per-section confidence levels

Your job:
- Assess the overall risk of transacting with or trusting this entity
- Produce COMPETING SCENARIOS (not a single verdict)
- Explain your reasoning transparently
- Never ignore contradiction flags
- Never say "CLEAR" without qualifying what was actually checked
- Always note data gaps — absence of evidence is NOT evidence of absence

Output valid JSON:
{
  "executive_summary": "2-3 sentences. Lead with the verdict.",
  "risk_rating": "LOW|MEDIUM|HIGH|CRITICAL",
  "risk_confidence": "HIGH|MEDIUM|LOW",
  "risk_reasoning": "Why this rating, in 2-3 sentences",
  
  "competing_scenarios": [
    {
      "scenario": "A: Legitimate entity",
      "probability": "65%",
      "evidence_for": ["list of supporting evidence"],
      "evidence_against": ["list of contradicting evidence"]
    },
    {
      "scenario": "B: Unproven / thin track record",
      "probability": "25%",
      "evidence_for": [],
      "evidence_against": []
    },
    {
      "scenario": "C: Potential front / fraud risk",
      "probability": "10%",
      "evidence_for": [],
      "evidence_against": []
    }
  ],
  
  "top_findings": [
    "Most important finding (positive or negative)",
    "Second most important",
    "Third most important"
  ],
  
  "red_flags": ["Each with specific evidence"],
  "green_flags": ["Each with specific evidence"],
  "unresolved_questions": ["Things we couldn't verify"],
  
  "recommended_action": "Concrete recommendation: proceed, verify X first, or do not transact",
  "recommended_next_steps": ["Specific actions to take"],
  
  "key_facts": ["Important verified facts"],
  "people": [{"name": "", "role": "", "assessment": ""}],
  "data_gaps": ["What we searched but couldn't find"]
}"""


def _build_analysis_prompt(target: str, target_type: str,
                            extracted_data: dict, xref_text: str,
                            routing_summary: str = None) -> str:
    """Build the analysis prompt with structured data + cross-reference."""

    # Clean extracted data for the prompt (remove nulls to save tokens)
    clean_data = {}
    for k, v in extracted_data.items():
        if v is not None and v != [] and v != {} and v != "":
            if isinstance(v, dict):
                clean_v = {ik: iv for ik, iv in v.items()
                           if iv is not None and iv != [] and iv != "" and iv != {}}
                if clean_v:
                    clean_data[k] = clean_v
            else:
                clean_data[k] = v

    data_json = json.dumps(clean_data, indent=2, default=str)
    if len(data_json) > 10000:
        data_json = data_json[:10000] + "\n... (truncated)"

    routing_text = ""
    if routing_summary:
        routing_text = f"\n\n=== SEARCH METHODOLOGY ===\n{routing_summary}"

    return f"""Analyze this entity: {target} (type: {target_type})

=== VERIFIED STRUCTURED DATA (from extraction pass) ===
{data_json}

{xref_text}
{routing_text}

Produce the complete analytical JSON report now. Remember:
- Lead with the verdict in executive_summary
- Generate 2-3 competing scenarios with probability weights
- Never ignore the contradiction flags above
- Be specific about evidence for each finding"""


# ═══════════════════════════════════════════════════════════════════════════════
# LLM CALLER
# ═══════════════════════════════════════════════════════════════════════════════

def _call_llm(api_key: str, model: str, system: str, user: str,
              max_tokens: int = 4000, temperature: float = 0.1) -> tuple:
    """Call OpenRouter. Returns (content_str, usage_dict)."""
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }).encode()

    req = urllib.request.Request(
        OR_API,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://herkulio.ai",
            "X-Title": "Herkulio Intelligence",
        },
    )

    resp = urllib.request.urlopen(req, timeout=60)
    data = json.loads(resp.read())
    content = data["choices"][0]["message"]["content"].strip()
    usage = data.get("usage", {})
    return content, usage


def _parse_json_response(content: str) -> dict:
    """Parse JSON from LLM response, handling markdown fences."""
    # Strip markdown code fences
    if "```" in content:
        parts = content.split("```")
        for part in parts[1:]:
            if part.strip().startswith("json"):
                part = part.strip()[4:]
            part = part.strip()
            if part.startswith("{"):
                try:
                    return json.loads(part)
                except json.JSONDecodeError:
                    pass

    # Try direct parse
    content = content.strip()
    if content.startswith("{"):
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # Try to repair truncated JSON
            last_brace = content.rfind("}")
            if last_brace > 0:
                try:
                    return json.loads(content[:last_brace + 1])
                except json.JSONDecodeError:
                    pass

    return {"error": "Failed to parse JSON response", "raw": content[-500:]}


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN SYNTHESIZER
# ═══════════════════════════════════════════════════════════════════════════════

class TwoPassSynthesizer:
    """
    Two-pass synthesis engine.
    Pass 1: Extract (cheap model) → structured facts
    Pass 2: Analyze (smart model) → risk assessment with competing scenarios
    """

    def __init__(self, openrouter_key: str):
        self.api_key = openrouter_key
        self.costs = {"extract": 0, "analyze": 0, "total": 0}

    def run(self, target: str, target_type: str, raw_results: dict,
            corporate_data: dict, routing_summary: str = None,
            context: dict = None, stakes: str = None,
            notes: str = None) -> dict:
        """
        Run full two-pass synthesis pipeline.
        Returns the complete report dict.
        """
        t0 = time.time()

        # ── PASS 1: EXTRACT ──────────────────────────────────────────────
        extract_model = MODELS["extract"]
        extract_prompt = _build_extraction_prompt(
            target, target_type, raw_results, corporate_data, context
        )

        try:
            extract_content, extract_usage = _call_llm(
                self.api_key, extract_model, EXTRACT_SYSTEM, extract_prompt,
                max_tokens=5000, temperature=0.05
            )
            extracted_data = _parse_json_response(extract_content)
        except Exception as e:
            extracted_data = {"error": f"Extraction failed: {e}"}

        extract_cost = (
            extract_usage.get("prompt_tokens", 0) * MODEL_COSTS.get(extract_model, 0.15) / 1_000_000 +
            extract_usage.get("completion_tokens", 0) * MODEL_COSTS.get(extract_model, 0.15) * 4 / 1_000_000
        ) if 'extract_usage' in dir() else 0

        # ── CROSS-REFERENCE (code, not AI) ────────────────────────────────
        xref = CrossReferencer(extracted_data)
        xref_report = xref.run_all_checks()

        detector = ContradictionDetector(extracted_data, xref_report)
        contradictions = detector.detect()

        tagger = ConfidenceTagger(extracted_data)
        confidence_tags = tagger.tag_all()

        xref_text = format_for_synthesis(xref_report, contradictions, confidence_tags)

        # ── DETERMINE RISK TIER → MODEL SELECTION ─────────────────────────
        risk_tier = _determine_risk_tier(contradictions, xref_report, stakes)
        analyze_model = MODELS.get(f"analyze_{risk_tier}", MODELS["analyze_medium"])

        # ── PASS 2: ANALYZE ──────────────────────────────────────────────
        analyze_prompt = _build_analysis_prompt(
            target, target_type, extracted_data, xref_text, routing_summary
        )

        try:
            analyze_content, analyze_usage = _call_llm(
                self.api_key, analyze_model, ANALYZE_SYSTEM, analyze_prompt,
                max_tokens=4000, temperature=0.15
            )
            analysis = _parse_json_response(analyze_content)
        except Exception as e:
            analysis = {"error": f"Analysis failed: {e}"}

        analyze_cost = (
            analyze_usage.get("prompt_tokens", 0) * MODEL_COSTS.get(analyze_model, 3.0) / 1_000_000 +
            analyze_usage.get("completion_tokens", 0) * MODEL_COSTS.get(analyze_model, 3.0) * 5 / 1_000_000
        ) if 'analyze_usage' in dir() else 0

        total_time = time.time() - t0

        # ── MERGE INTO FINAL REPORT ──────────────────────────────────────
        report = {**extracted_data}  # Start with extracted facts
        report.update(analysis)       # Overlay analysis results

        # Ensure critical fields exist
        report.setdefault("target", target)
        report.setdefault("type", target_type)
        report.setdefault("risk_rating", analysis.get("risk_rating", "UNKNOWN"))
        report.setdefault("executive_summary", analysis.get("executive_summary", "Analysis incomplete"))
        report.setdefault("competing_scenarios", analysis.get("competing_scenarios", []))
        report.setdefault("top_findings", analysis.get("top_findings", []))

        # Attach cross-reference results
        report["cross_reference"] = {
            "consistency_score": xref_report.get("consistency_score"),
            "summary": xref_report.get("summary"),
            "matches": xref_report.get("matches", []),
            "mismatches": xref_report.get("mismatches", []),
            "gaps": xref_report.get("gaps", []),
        }
        report["contradictions"] = contradictions
        report["confidence_tags"] = confidence_tags

        # Metadata
        report["_meta"] = {
            "synthesis_version": "v2_two_pass",
            "extract_model": extract_model,
            "analyze_model": analyze_model,
            "risk_tier_used": risk_tier,
            "extract_tokens_in": extract_usage.get("prompt_tokens", 0) if 'extract_usage' in dir() else 0,
            "extract_tokens_out": extract_usage.get("completion_tokens", 0) if 'extract_usage' in dir() else 0,
            "analyze_tokens_in": analyze_usage.get("prompt_tokens", 0) if 'analyze_usage' in dir() else 0,
            "analyze_tokens_out": analyze_usage.get("completion_tokens", 0) if 'analyze_usage' in dir() else 0,
            "extract_cost_usd": round(extract_cost, 6),
            "analyze_cost_usd": round(analyze_cost, 6),
            "total_cost_usd": round(extract_cost + analyze_cost, 4),
            "total_time_seconds": round(total_time, 1),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cross_ref_consistency": xref_report.get("consistency_score"),
            "contradictions_found": len(contradictions),
            "high_severity_flags": sum(
                1 for c in contradictions
                if isinstance(c, dict) and c.get("severity") == "HIGH"
            ),
        }

        return report
