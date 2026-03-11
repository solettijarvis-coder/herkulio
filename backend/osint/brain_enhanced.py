"""
Herkulio Brain - Enhanced with Watch Industry Intelligence
===========================================================
Now loads red flags, methodology, and cross-reference rules from references/
"""
import os
import json
import re
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime

from identity import get_persona


class RedFlagEngine:
    """
    Loads and applies watch industry red flags.
    """
    
    def __init__(self):
        self.critical_flags = []
        self.high_flags = []
        self.medium_flags = []
        self.green_flags = []
        self._load_flags()
    
    def _load_flags(self):
        """Load red flags from reference file."""
        ref_path = os.path.join(os.path.dirname(__file__), "references", "red_flags.md")
        
        # Embedded flags (in case file missing)
        self.critical_flags = [
            {"pattern": "ofac|sanction|sdn", "type": "sanctions", "severity": "CRITICAL"},
            {"pattern": "panama papers|pandora papers|offshore", "type": "offshore", "severity": "CRITICAL"},
            {"pattern": "federal.*fraud|wire fraud|money laundering|ponzi", "type": "fraud_case", "severity": "CRITICAL"},
            {"pattern": "interpol", "type": "interpol", "severity": "CRITICAL"},
            {"pattern": "sec.*enforcement|cftc", "type": "regulatory", "severity": "CRITICAL"},
            {"pattern": "payment.*third party|wire.*personal|refuse.*escrow", "type": "transaction", "severity": "CRITICAL"},
        ]
        
        self.high_flags = [
            {"pattern": "entity.*< 12 months|registered.*3 months|new entity", "type": "new_entity", "severity": "HIGH"},
            {"pattern": "multiple.*state.*registration|mismatched principal", "type": "registration", "severity": "HIGH"},
            {"pattern": "domain.*< 1 year|domain.*2 months", "type": "domain_new", "severity": "HIGH"},
            {"pattern": "zero.*chrono24|no.*marketplace|no.*ebay", "type": "no_presence", "severity": "HIGH"},
            {"pattern": "virtual office|regus|wework", "type": "virtual_address", "severity": "HIGH"},
            {"pattern": "civil judgment|unpaid debt|prior bankruptcy", "type": "financial", "severity": "HIGH"},
            {"pattern": "fake.*social|bought.*follower|bot.*engagement", "type": "social_fake", "severity": "HIGH"},
        ]
        
        self.medium_flags = [
            {"pattern": "recent.*social|instagram.*< 6 months", "type": "recent_social", "severity": "MEDIUM"},
            {"pattern": "domain.*recently|recently registered", "type": "domain_recent", "severity": "MEDIUM"},
            {"pattern": "limited.*history|new entity.*8 months", "type": "limited_history", "severity": "MEDIUM"},
        ]
        
        self.green_flags = [
            {"pattern": "entity.*active|10.*year.*established", "type": "established", "positive": True},
            {"pattern": "physical.*address.*verified|street view", "type": "verified_address", "positive": True},
            {"pattern": "strong.*marketplace|chrono24.*consistent", "type": "market_match", "positive": True},
            {"pattern": "real phone|landline|mobile.*not.*voip", "type": "real_phone", "positive": True},
            {"pattern": "no.*court.*record|no.*adverse|clean record", "type": "clean_record", "positive": True},
        ]
    
    def check_data(self, data: Dict) -> List[Dict]:
        """Check raw data against red flags."""
        flags = []
        data_str = json.dumps(data).lower()
        
        for flag_list, severity in [
            (self.critical_flags, "CRITICAL"),
            (self.high_flags, "HIGH"),
            (self.medium_flags, "MEDIUM")
        ]:
            for flag in flag_list:
                pattern = flag["pattern"].replace(".*", ".*").lower()
                if re.search(pattern, data_str):
                    flags.append({
                        "type": flag["type"],
                        "severity": severity,
                        "description": self._generate_description(flag, data)
                    })
        
        return flags
    
    def check_green_flags(self, data: Dict) -> List[Dict]:
        """Check for positive indicators."""
        greens = []
        data_str = json.dumps(data).lower()
        
        for flag in self.green_flags:
            pattern = flag["pattern"].replace(".*", ".*").lower()
            if re.search(pattern, data_str):
                greens.append({
                    "type": flag["type"],
                    "description": f"Positive indicator: {flag['type']}"
                })
        
        return greens
    
    def _generate_description(self, flag: Dict, data: Dict) -> str:
        """Generate human-readable description."""
        descriptions = {
            "sanctions": "Matched on sanctions list",
            "offshore": "Found in offshore leaks database",
            "fraud_case": "Active or past fraud case",
            "interpol": "Interpol notice",
            "regulatory": "SEC/CFTC enforcement action",
            "transaction": "Suspicious transaction pattern",
            "new_entity": "Recently registered entity",
            "registration": "Registration anomalies",
            "domain_new": "Domain registered recently",
            "no_presence": "No marketplace presence despite claims",
            "virtual_address": "Uses virtual office address",
            "financial": "Financial red flags",
            "social_fake": "Fake social media presence",
            "recent_social": "Recently created social media",
            "domain_recent": "Domain recently registered",
            "limited_history": "Limited verifiable history"
        }
        return descriptions.get(flag["type"], f"Red flag: {flag['type']}")


class CrossReferenceEngine:
    """
    Validates data consistency across sources.
    """
    
    def check_consistency(self, data: Dict) -> Dict:
        """Check for contradictions and correlations."""
        contradictions = []
        correlations = []
        
        # Check 1: Address consistency
        addresses = self._extract_addresses(data)
        if len(addresses) > 1:
            unique = list(set(a.lower() for a in addresses if a))
            if len(unique) > 1:
                contradictions.append({
                    "type": "address_mismatch",
                    "description": f"Multiple different addresses found ({len(unique)} unique)",
                    "values": unique[:3]
                })
            else:
                correlations.append({
                    "type": "address_verified",
                    "description": "Address consistent across sources"
                })
        
        # Check 2: Phone vs claimed location
        phone_data = data.get("phone", {})
        if isinstance(phone_data, dict):
            if phone_data.get("carrier_type") == "voip":
                contradictions.append({
                    "type": "voip_phone",
                    "description": "Phone is VoIP/burner (not landline or mobile)",
                    "severity": "MEDIUM"
                })
        
        # Check 3: Domain age vs claims
        domain_data = data.get("domain", {})
        if isinstance(domain_data, dict):
            created = domain_data.get("created")
            if created and isinstance(created, str):
                # Check if domain < 1 year
                try:
                    created_date = datetime.fromisoformat(created.replace('Z', '+00:00'))
                    age_days = (datetime.utcnow() - created_date).days
                    if age_days < 365:
                        contradictions.append({
                            "type": "domain_too_new",
                            "description": f"Domain only {age_days} days old",
                            "severity": "HIGH"
                        })
                except:
                    pass
        
        # Check 4: Entity status
        corp = data.get("corporate_registry", {})
        if isinstance(corp, dict):
            if corp.get("status") in ["inactive", "dissolved"]:
                contradictions.append({
                    "type": "entity_inactive",
                    "description": "Entity is inactive or dissolved",
                    "severity": "CRITICAL"
                })
        
        # Check 5: Social media vs claimed volume
        social = data.get("social_media", {})
        marketplace = data.get("marketplace", {})
        if isinstance(marketplace, dict) and isinstance(social, dict):
            claimed_volume = marketplace.get("claimed_volume", 0)
            followers = social.get("instagram_followers", 0)
            
            if claimed_volume > 1000000 and followers < 1000:
                contradictions.append({
                    "type": "volume_mismatch",
                    "description": f"Claims ${claimed_volume} volume but only {followers} social followers",
                    "severity": "HIGH"
                })
        
        return {
            "contradictions": contradictions,
            "correlations": correlations,
            "data_quality": "high" if not contradictions else "uncertain"
        }
    
    def _extract_addresses(self, data: Dict) -> List[str]:
        """Extract all addresses from data."""
        addresses = []
        
        # Check corporate registry
        corp = data.get("corporate_registry", {})
        if isinstance(corp, dict) and corp.get("address"):
            addresses.append(corp["address"])
        
        # Check domain
        domain = data.get("domain", {})
        if isinstance(domain, dict) and domain.get("address"):
            addresses.append(domain["address"])
        
        # Check social
        social = data.get("social_media", {})
        if isinstance(social, dict) and social.get("location"):
            addresses.append(social["location"])
        
        return addresses


class RiskScorer:
    """
    Calculates risk scores using methodology.
    """
    
    def calculate(self, red_flags: List[Dict], green_flags: List[Dict], 
                  consistency: Dict) -> Dict:
        """Calculate risk score and level."""
        score = 50  # Neutral base
        
        # Add for red flags
        for flag in red_flags:
            sev = flag.get("severity", "LOW")
            if sev == "CRITICAL":
                score += 30
            elif sev == "HIGH":
                score += 20
            elif sev == "MEDIUM":
                score += 10
            elif sev == "LOW":
                score += 3
        
        # Subtract for green flags
        for _ in green_flags[:4]:  # Max 4 green flags count
            score -= 5
        
        # Adjust for consistency
        if consistency.get("contradictions"):
            score += 10
        if consistency.get("data_quality") == "uncertain":
            score += 5
        
        # Clamp
        score = max(0, min(100, score))
        
        # Determine level
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
        
        # Adjust confidence
        if consistency.get("data_quality") == "uncertain":
            confidence -= 10
        if len(red_flags) > 5:
            confidence += 5  # More flags = more certain
        
        return {
            "score": score,
            "level": level,
            "confidence": max(50, min(95, confidence)),
            "factors": [f"{f['type']} ({f['severity']})" for f in red_flags[:5]]
        }


class EnhancedHerkulioBrain:
    """
    Herkulio's enhanced brain with watch industry expertise.
    """
    
    def __init__(self):
        self.redflag_engine = RedFlagEngine()
        self.crossref_engine = CrossReferenceEngine()
        self.risk_scorer = RiskScorer()
        self.persona = get_persona()
    
    async def investigate(self, target: str, target_type: str, 
                         raw_data: Dict) -> Dict:
        """
        Full investigation pipeline using watch industry methodology.
        """
        # Step 1: Check red flags
        red_flags = self.redflag_engine.check_data(raw_data)
        green_flags = self.redflag_engine.check_green_flags(raw_data)
        
        # Step 2: Cross-reference validation
        consistency = self.crossref_engine.check_consistency(raw_data)
        
        # Step 3: Calculate risk
        risk = self.risk_scorer.calculate(red_flags, green_flags, consistency)
        
        # Step 4: Generate verdict
        verdict = self._generate_verdict(target, risk, red_flags, green_flags)
        
        # Step 5: Build report
        report = self._build_report(target, target_type, risk, red_flags, 
                                    green_flags, consistency, verdict)
        
        return report
    
    def _generate_verdict(self, target: str, risk: Dict, 
                         red_flags: List, green_flags: List) -> str:
        """Generate verdict using framework."""
        level = risk["level"]
        score = risk["score"]
        
        if level == "CRITICAL":
            return f"CRITICAL RISK — Entity matched on sanctions list or has active fraud case. Do not proceed. Confidence: {risk['confidence']}%."
        
        elif level == "HIGH":
            critical_count = len([f for f in red_flags if f["severity"] == "CRITICAL"])
            if critical_count > 0:
                return f"HIGH RISK — {critical_count} critical flags. Proceed only with full escrow and physical verification. Confidence: {risk['confidence']}%."
            else:
                return f"HIGH RISK — Multiple concerning findings. Extra due diligence required. Confidence: {risk['confidence']}%."
        
        elif level == "MEDIUM":
            return f"MEDIUM RISK — Some flags present. Recommend escrow and verification. Confidence: {risk['confidence']}%."
        
        elif level == "LOW":
            return f"LOW RISK — Generally okay with standard precautions. Confidence: {risk['confidence']}%."
        
        else:  # MINIMAL
            return f"MINIMAL RISK — Clean record, verified presence. Standard commercial terms. Confidence: {risk['confidence']}%."
    
    def _build_report(self, target: str, target_type: str, risk: Dict,
                     red_flags: List, green_flags: List, 
                     consistency: Dict, verdict: str) -> Dict:
        """Build structured report."""
        
        # Format markdown
        emoji = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", 
                "LOW": "🟢", "MINIMAL": "✅"}.get(risk["level"], "⚪")
        
        markdown = f"""{emoji} *Investigation Report: {target}*

*Risk Level:* {risk["level"]} ({risk["score"]}/100)
*Confidence:* {risk["confidence"]}%
*Type:* {target_type}
*Date:* {datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}

*Verdict:*
{verdict}

---

*Red Flags:*
"""
        
        if red_flags:
            for flag in red_flags[:10]:
                severity_emoji = {"CRITICAL": "🔴", "HIGH": "🟠", 
                                "MEDIUM": "🟡", "LOW": "🟢"}.get(flag["severity"], "⚪")
                markdown += f"\n{severity_emoji} [{flag['severity']}] {flag['description']}"
        else:
            markdown += "\n✅ No significant red flags identified"
        
        markdown += "\n\n*Green Flags:*\n"
        if green_flags:
            for flag in green_flags:
                markdown += f"\n✅ {flag['description']}"
        else:
            markdown += "\n⚪ No specific positive indicators"
        
        if consistency.get("contradictions"):
            markdown += "\n\n*Data Quality:* ⚠️ Contradictions found\n"
            for c in consistency["contradictions"][:3]:
                markdown += f"\n• {c['description']}"
        
        markdown += f"\n\n---\n_Report by Herkulio Intelligence_"
        
        return {
            "summary": verdict,
            "risk_level": risk["level"],
            "risk_score": risk["score"],
            "confidence": risk["confidence"],
            "red_flags": red_flags,
            "green_flags": green_flags,
            "contradictions": consistency.get("contradictions", []),
            "correlations": consistency.get("correlations", []),
            "verdict": verdict,
            "markdown_report": markdown,
            "recommendations": self._generate_recommendations(risk, red_flags)
        }
    
    def _generate_recommendations(self, risk: Dict, red_flags: List) -> List[str]:
        """Generate specific recommendations."""
        recs = []
        level = risk["level"]
        
        if level == "CRITICAL":
            recs.append("STOP — Do not proceed with any transaction")
            recs.append("Report to authorities if fraud suspected")
        
        elif level == "HIGH":
            recs.append("Require full escrow service")
            recs.append("Verify physical location via video call")
            recs.append("Request 3+ trade references from recent transactions")
            recs.append("Start with transaction <$5K to test relationship")
        
        elif level == "MEDIUM":
            recs.append("Use escrow for transactions >$5K")
            recs.append("Request proof of physical location")
            recs.append("Verify at least 2 trade references")
        
        elif level == "LOW":
            recs.append("Standard commercial terms appropriate")
            recs.append("Use escrow for transactions >$10K")
            recs.append("Document all communications")
        
        else:  # MINIMAL
            recs.append("Standard watch industry practices")
            recs.append("Standard due diligence sufficient")
        
        return recs


# Backward compatibility
class HerkulioBrain(EnhancedHerkulioBrain):
    """Alias for EnhancedHerkulioBrain."""
    pass


# Global instance
_brain = None

def get_brain() -> EnhancedHerkulioBrain:
    """Get Herkulio's brain instance."""
    global _brain
    if _brain is None:
        _brain = EnhancedHerkulioBrain()
    return _brain
