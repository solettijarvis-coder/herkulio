"""
Herkulio Brain - Core Intelligence System
==========================================
The cognitive layer that processes investigations, detects patterns, 
and makes Herkulio more than just a data fetcher.
"""
import os
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import httpx

from identity import get_persona


@dataclass
class InvestigationContext:
    """Context for an investigation."""
    target: str
    target_type: str  # person, company, watch, dealer
    depth: str  # quick, standard, deep
    user_intent: str  # vet_dealer, check_watch, company_dd, etc.
    prior_knowledge: Dict[str, Any]
    industry: Optional[str] = None
    geography: Optional[str] = None


class HerkulioBrain:
    """
    Herkulio's core intelligence.
    
    Responsibilities:
    1. Route to right modules
    2. Synthesize findings
    3. Detect patterns & red flags
    4. Calculate confidence
    5. Generate recommendations
    6. Learn from patterns
    """
    
    def __init__(self):
        self.openrouter_key = os.environ.get("OPENROUTER_API_KEY")
        self.model = os.environ.get("DEFAULT_MODEL", "google/gemini-2.5-flash")
        self.persona = get_persona()
    
    async def think(self, context: InvestigationContext, raw_data: Dict) -> Dict:
        """
        Main thinking loop.
        Takes raw OSINT data and produces intelligence.
        """
        # Step 1: Assess data quality
        data_quality = self._assess_data_quality(raw_data)
        
        # Step 2: Detect patterns and anomalies
        patterns = self._detect_patterns(raw_data, context)
        
        # Step 3: Calculate risk
        risk = self._calculate_risk(raw_data, patterns, context)
        
        # Step 4: Synthesize with AI
        synthesis = await self._synthesize(context, raw_data, patterns, risk)
        
        # Step 5: Generate recommendations
        recommendations = self._generate_recommendations(risk, patterns, context)
        
        return {
            "summary": synthesis.get("summary", ""),
            "risk_level": risk["level"],
            "risk_score": risk["score"],
            "confidence": risk["confidence"],
            "patterns": patterns,
            "red_flags": patterns.get("red_flags", []),
            "recommendations": recommendations,
            "data_quality": data_quality,
            "key_findings": synthesis.get("key_findings", []),
            "markdown_report": self._format_markdown(synthesis, risk, patterns, context)
        }
    
    def _assess_data_quality(self, data: Dict) -> Dict:
        """Assess quality and completeness of raw data."""
        sources = len(data.keys())
        has_direct_hit = any("error" not in str(v).lower() for v in data.values())
        
        # Check for contradictions
        contradictions = self._detect_contradictions(data)
        
        return {
            "sources_count": sources,
            "has_direct_hits": has_direct_hit,
            "contradictions": contradictions,
            "completeness": "high" if sources > 10 else "medium" if sources > 5 else "low",
            "reliability": "high" if not contradictions else "uncertain"
        }
    
    def _detect_patterns(self, data: Dict, context: InvestigationContext) -> Dict:
        """Detect patterns and anomalies in data."""
        patterns = {
            "watch_industry": self._check_watch_industry_patterns(data, context),
            "financial": self._check_financial_patterns(data),
            "reputation": self._check_reputation_patterns(data),
            "structural": self._check_structural_patterns(data),
            "red_flags": []
        }
        
        # Aggregate red flags
        for category in patterns.values():
            if isinstance(category, dict) and "red_flags" in category:
                patterns["red_flags"].extend(category["red_flags"])
        
        return patterns
    
    def _check_watch_industry_patterns(self, data: Dict, context: InvestigationContext) -> Dict:
        """Watch industry specific patterns."""
        flags = []
        findings = []
        
        # Check if mentioned on watch forums
        if data.get("forum_reputation"):
            forums = data["forum_reputation"]
            if isinstance(forums, dict):
                if forums.get("negative_mentions", 0) > 0:
                    flags.append({
                        "type": "forum_complaints",
                        "severity": "MEDIUM",
                        "description": f"Negative mentions on {forums.get('sources', ['forums'])}"
                    })
        
        # Check Chrono24/eBay seller status
        if data.get("chrono24_seller"):
            chrono = data["chrono24_seller"]
            if not chrono.get("verified", False):
                flags.append({
                    "type": "unverified_seller",
                    "severity": "MEDIUM",
                    "description": "Unverified seller on major platform"
                })
        
        # Watch-specific red flags
        if context.target_type == "watch":
            if "daytona" in context.target.lower() and data.get("price_data"):
                price = data["price_data"]
                if price.get("current", 0) < 20000:  # Suspiciously low for Daytona
                    flags.append({
                        "type": "suspicious_pricing",
                        "severity": "HIGH",
                        "description": "Price significantly below market ($" + str(price.get('current')) + ")"
                    })
        
        return {
            "findings": findings,
            "red_flags": flags
        }
    
    def _check_financial_patterns(self, data: Dict) -> Dict:
        """Financial crime and solvency patterns."""
        flags = []
        
        # Check sanctions
        sanctions = data.get("sanctions")
        if sanctions and sanctions.get("matches"):
            flags.append({
                "type": "sanctions_match",
                "severity": "CRITICAL",
                "description": f"Matched on sanctions list: {sanctions.get('lists', [])}"
            })
        
        # Check court records
        courts = data.get("court_records")
        if courts:
            if courts.get("bankruptcy", False):
                flags.append({
                    "type": "bankruptcy",
                    "severity": "HIGH",
                    "description": "Bankruptcy filing found"
                })
            if courts.get("judgments", 0) > 0:
                flags.append({
                    "type": "judgments",
                    "severity": "HIGH",
                    "description": f"{courts['judgments']} legal judgments"
                })
        
        # PPP loan checks
        ppp = data.get("ppp_loans")
        if ppp and ppp.get("amount", 0) > 100000:
            findings.append(f"Large PPP loan: ${ppp['amount']}")
        
        return {
            "findings": findings if 'findings' in dir() else [],
            "red_flags": flags
        }
    
    def _check_reputation_patterns(self, data: Dict) -> Dict:
        """Online reputation patterns."""
        flags = []
        
        # Data breach check
        breaches = data.get("data_breaches")
        if breaches and breaches.get("found", False):
            if breaches.get("count", 0) > 5:
                flags.append({
                    "type": "multiple_breaches",
                    "severity": "MEDIUM",
                    "description": f"Found in {breaches['count']} data breaches"
                })
        
        # Review patterns
        reviews = data.get("reviews")
        if reviews:
            if reviews.get("rating", 5) < 2.5 and reviews.get("count", 0) > 10:
                flags.append({
                    "type": "poor_reviews",
                    "severity": "MEDIUM",
                    "description": f"Low rating: {reviews['rating']}/5 from {reviews['count']} reviews"
                })
        
        return {
            "findings": [],
            "red_flags": flags
        }
    
    def _check_structural_patterns(self, data: Dict) -> Dict:
        """Corporate structure and ownership patterns."""
        flags = []
        
        # Shell company indicators
        corp = data.get("corporate_registry")
        if corp:
            if corp.get("employee_count", 100) < 3:
                flags.append({
                    "type": "minimal_staff",
                    "severity": "LOW",
                    "description": "Very few employees (possible shell)"
                })
            
            # Virtual office check
            if corp.get("virtual_office", False):
                flags.append({
                    "type": "virtual_office",
                    "severity": "LOW",
                    "description": "Uses virtual office address"
                })
        
        return {
            "findings": [],
            "red_flags": flags
        }
    
    def _calculate_risk(self, data: Dict, patterns: Dict, context: InvestigationContext) -> Dict:
        """Calculate overall risk score and level."""
        score = 50  # Neutral starting point
        
        # Adjust based on red flags
        for flag in patterns.get("red_flags", []):
            severity = flag.get("severity", "LOW")
            if severity == "CRITICAL":
                score += 30
            elif severity == "HIGH":
                score += 20
            elif severity == "MEDIUM":
                score += 10
            elif severity == "LOW":
                score += 3
        
        # Data quality
        quality = self._assess_data_quality(data)
        if quality["contradictions"]:
            score += 10
        if quality["completeness"] == "low":
            score -= 5  # Less data = less certainty
        
        # Calibrate
        score = min(100, max(0, score))
        
        # Map to level
        if score >= 90:
            level = "CRITICAL"
            confidence = 85
        elif score >= 75:
            level = "HIGH"
            confidence = 80
        elif score >= 50:
            level = "MEDIUM"
            confidence = 75
        elif score >= 25:
            level = "LOW"
            confidence = 70
        else:
            level = "MINIMAL"
            confidence = 65
        
        # Adjust confidence based on data quality
        if quality["reliability"] == "uncertain":
            confidence -= 15
        
        return {
            "score": score,
            "level": level,
            "confidence": max(50, min(95, confidence)),
            "factors": [f"{rf['type']} (+{rf['severity']})" for rf in patterns.get("red_flags", [])[:5]]
        }
    
    async def _synthesize(self, context: InvestigationContext, data: Dict, 
                          patterns: Dict, risk: Dict) -> Dict:
        """Use AI to synthesize findings into narrative."""
        # Build prompt
        prompt = self._build_synthesis_prompt(context, data, patterns, risk)
        
        # Call OpenRouter
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.openrouter_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": self.persona.get_system_prompt()},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.3,
                        "max_tokens": 2000
                    },
                    timeout=60.0
                )
                
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                
                # Parse structured output
                return self._parse_synthesis(content)
                
        except Exception as e:
            # Fallback if AI fails
            return {
                "summary": f"Investigation of {context.target} shows {risk['level']} risk based on {len(patterns.get('red_flags', []))} red flags.",
                "key_findings": [f["description"] for f in patterns.get("red_flags", [])[:5]],
                "error": str(e)
            }
    
    def _build_synthesis_prompt(self, context: InvestigationContext, data: Dict,
                                patterns: Dict, risk: Dict) -> str:
        """Build prompt for AI synthesis."""
        red_flags = patterns.get("red_flags", [])
        
        prompt = f"""Investigation Report: {context.target}
Type: {context.target_type}
Risk Level: {risk['level']} ({risk['score']}/100)
Confidence: {risk['confidence']}%

RED FLAGS ({len(red_flags)} found):
{chr(10).join([f"- [{f['severity']}] {f['description']}" for f in red_flags[:10]])}

RAW DATA SOURCES:
{json.dumps({k: type(v).__name__ for k, v in data.items() if v}, indent=2)}

SYNTHESIZE:
1. Executive summary (2-3 sentences)
2. Key findings (bullet points)
3. Risk assessment
4. Specific recommendations

Format as JSON with keys: summary, key_findings (list), risk_assessment, recommendations (list)"""
        
        return prompt
    
    def _parse_synthesis(self, content: str) -> Dict:
        """Parse AI response into structured data."""
        try:
            # Try to extract JSON from markdown
            if "```json" in content:
                json_start = content.find("```json") + 7
                json_end = content.find("```", json_start)
                content = content[json_start:json_end].strip()
            
            return json.loads(content)
        except:
            # Fallback parsing
            return {
                "summary": content[:500],
                "key_findings": [line.strip() for line in content.split("\n") if line.strip().startswith("-")][:10],
                "risk_assessment": "See risk score",
                "recommendations": []
            }
    
    def _generate_recommendations(self, risk: Dict, patterns: Dict, 
                                  context: InvestigationContext) -> List[str]:
        """Generate actionable recommendations."""
        recs = []
        
        if risk["level"] in ["CRITICAL", "HIGH"]:
            recs.append("STOP - Do not proceed with transaction. High risk detected.")
            recs.append("Request additional verification from counterparty")
            
        if context.target_type == "dealer":
            if risk["level"] == "MEDIUM":
                recs.append("Request references from recent transactions")
                recs.append("Verify escrow service is legitimate")
            else:
                recs.append("Standard due diligence sufficient")
        
        if context.target_type == "company":
            if patterns.get("structural", {}).get("red_flags", []):
                recs.append("Request proof of physical office")
                recs.append("Verify bank account details independently")
        
        return recs if recs else ["No specific concerns raised"]
    
    def _format_markdown(self, synthesis: Dict, risk: Dict, patterns: Dict,
                        context: InvestigationContext) -> str:
        """Generate markdown report."""
        emoji = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}.get(risk["level"], "⚪")
        
        md = f"""# {emoji} Investigation Report: {context.target}

**Risk Level:** {risk["level"]} ({risk["score"]}/100)  
**Confidence:** {risk["confidence"]}%  
**Investigation Type:** {context.target_type}  
**Date:** {datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}

## Executive Summary

{synthesis.get("summary", "No summary available")}

## Key Findings

"""
        
        for finding in synthesis.get("key_findings", []):
            md += f"- {finding}\n"
        
        md += "\n## Red Flags\n\n"
        
        for flag in patterns.get("red_flags", []):
            md += f"- **[{flag['severity']}]** {flag['description']}\n"
        
        if not patterns.get("red_flags"):
            md += "_No significant red flags identified_\n"
        
        md += "\n## Recommendations\n\n"
        
        for rec in synthesis.get("recommendations", []):
            md += f"- {rec}\n"
        
        md += f"\n---\n*Report generated by Herkulio Intelligence Platform*"
        
        return md
    
    def _detect_contradictions(self, data: Dict) -> List[Dict]:
        """Detect contradictory information across sources."""
        contradictions = []
        
        # Compare addresses
        addresses = []
        for source, info in data.items():
            if isinstance(info, dict) and "address" in info:
                addresses.append((source, info["address"]))
        
        if len(addresses) > 1:
            # Simple check - different non-empty addresses
            unique = set(a for _, a in addresses if a)
            if len(unique) > 1:
                contradictions.append({
                    "type": "address_mismatch",
                    "sources": [s for s, _ in addresses],
                    "values": list(unique)
                })
        
        return contradictions


# Global instance
brain = HerkulioBrain()

def get_brain() -> HerkulioBrain:
    """Get Herkulio's brain instance."""
    return brain
