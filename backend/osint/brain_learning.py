"""
Herkulio Brain Learning System
================================
Learns from investigations to improve future results.
Pattern recognition, entity relationships, and risk prediction.
"""
import json
import os
from typing import Dict, List, Optional, Set
from datetime import datetime, timedelta
from collections import defaultdict

from memory import get_memory


class PatternLearner:
    """
    Learns patterns from investigations to improve detection.
    """
    
    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.memory = get_memory(tenant_id)
        self.patterns_db_path = f"/app/data/memory/{tenant_id}_patterns.json"
        self._load_patterns()
    
    def _load_patterns(self):
        """Load learned patterns."""
        if os.path.exists(self.patterns_db_path):
            with open(self.patterns_db_path, 'r') as f:
                self.patterns = json.load(f)
        else:
            self.patterns = {
                "fraud_signatures": [],
                "legitimate_profiles": [],
                "risk_correlations": defaultdict(list),
                "false_positives": [],
                "high_confidence_indicators": []
            }
    
    def _save_patterns(self):
        """Save learned patterns."""
        os.makedirs(os.path.dirname(self.patterns_db_path), exist_ok=True)
        with open(self.patterns_db_path, 'w') as f:
            json.dump(self.patterns, f, indent=2)
    
    def learn_from_investigation(self, investigation: Dict, feedback: Optional[str] = None):
        """
        Learn from completed investigation.
        
        feedback can be: 'fraud_confirmed', 'legitimate', 'false_positive'
        """
        target = investigation.get("target", "")
        risk_level = investigation.get("risk_level", "")
        red_flags = investigation.get("red_flags", [])
        
        # Learn fraud signatures
        if feedback == "fraud_confirmed" or risk_level == "CRITICAL":
            signature = self._extract_signature(red_flags, investigation)
            if signature not in self.patterns["fraud_signatures"]:
                self.patterns["fraud_signatures"].append(signature)
        
        # Learn legitimate profiles
        if feedback == "legitimate" or risk_level == "MINIMAL":
            profile = self._extract_profile(investigation)
            if profile not in self.patterns["legitimate_profiles"]:
                self.patterns["legitimate_profiles"].append(profile)
        
        # Learn false positives
        if feedback == "false_positive":
            self.patterns["false_positives"].append({
                "target": target,
                "red_flags_that_missed": [f["type"] for f in red_flags],
                "timestamp": datetime.utcnow().isoformat()
            })
        
        # Learn risk correlations
        self._update_risk_correlations(investigation)
        
        self._save_patterns()
    
    def _extract_signature(self, red_flags: List, investigation: Dict) -> Dict:
        """Extract fraud signature from red flags."""
        return {
            "flag_types": sorted([f["type"] for f in red_flags]),
            "entity_type": investigation.get("target_type", ""),
            "pattern_hash": hash(tuple(sorted([f["type"] for f in red_flags])))
        }
    
    def _extract_profile(self, investigation: Dict) -> Dict:
        """Extract legitimate profile."""
        green_flags = investigation.get("green_flags", [])
        return {
            "indicators": [g["type"] for g in green_flags],
            "entity_type": investigation.get("target_type", "")
        }
    
    def _update_risk_correlations(self, investigation: Dict):
        """Learn which indicators correlate with actual risk."""
        red_flags = investigation.get("red_flags", [])
        risk_level = investigation.get("risk_level", "")
        
        for flag in red_flags:
            flag_type = flag.get("type", "")
            self.patterns["risk_correlations"][flag_type].append({
                "risk_level": risk_level,
                "timestamp": datetime.utcnow().isoformat()
            })
    
    def check_known_patterns(self, red_flags: List, target_type: str) -> Dict:
        """Check if current flags match known fraud patterns."""
        current_signature = sorted([f["type"] for f in red_flags])
        
        matches = []
        for signature in self.patterns["fraud_signatures"]:
            if self._signature_similarity(current_signature, signature["flag_types"]) > 0.7:
                matches.append(signature)
        
        # Check false positive patterns
        false_positive_risk = self._check_false_positive_risk(red_flags)
        
        return {
            "known_fraud_pattern": len(matches) > 0,
            "pattern_matches": matches,
            "false_positive_risk": false_positive_risk,
            "confidence_boost": 15 if len(matches) > 0 else 0
        }
    
    def _signature_similarity(self, sig1: List, sig2: List) -> float:
        """Calculate similarity between two signatures."""
        set1, set2 = set(sig1), set(sig2)
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        return intersection / union if union > 0 else 0
    
    def _check_false_positive_risk(self, red_flags: List) -> float:
        """Check if this matches known false positive patterns."""
        fp_patterns = self.patterns.get("false_positives", [])
        
        current_types = set(f["type"] for f in red_flags)
        
        matches = 0
        for fp in fp_patterns:
            fp_types = set(fp.get("red_flags_that_missed", []))
            if len(current_types & fp_types) / len(current_types | fp_types) > 0.5:
                matches += 1
        
        # Return probability this is false positive
        return min(0.3, matches / 10)  # Cap at 30%
    
    def get_flag_reliability(self, flag_type: str) -> Dict:
        """Get reliability statistics for a flag type."""
        correlations = self.patterns.get("risk_correlations", {}).get(flag_type, [])
        
        if not correlations:
            return {"reliability": "unknown", "sample_size": 0}
        
        # Count how often this flag actually led to high risk
        high_risk_count = sum(1 for c in correlations if c["risk_level"] in ["CRITICAL", "HIGH"])
        total = len(correlations)
        
        reliability = high_risk_count / total if total > 0 else 0
        
        return {
            "reliability": reliability,
            "sample_size": total,
            "high_risk_rate": f"{reliability:.0%}"
        }


class RelationshipMapper:
    """
    Maps relationships between entities for network analysis.
    """
    
    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.memory = get_memory(tenant_id)
    
    def find_connected_entities(self, entity_id: str, depth: int = 2) -> Dict:
        """
        Find all entities connected to this one within N degrees.
        """
        connected = {
            "direct": [],
            "indirect": [],
            "shared_attributes": []
        }
        
        # Get entity
        entity = self.memory.get_entity(entity_id)
        if not entity:
            return connected
        
        # Find direct relationships
        direct = self.memory.get_related(entity_id)
        connected["direct"] = direct
        
        # Find indirect (2nd degree)
        if depth > 1:
            for rel in direct[:5]:  # Limit to avoid explosion
                indirect = self.memory.get_related(rel.get("target_id"))
                connected["indirect"].extend(indirect)
        
        # Find shared attributes
        connected["shared_attributes"] = self._find_shared_attributes(entity)
        
        return connected
    
    def _find_shared_attributes(self, entity: Dict) -> List[Dict]:
        """Find other entities with shared phone, email, address, etc."""
        shared = []
        data = entity.get("data", {})
        
        # Check phone
        phone = data.get("phone")
        if phone:
            # Would query memory for other entities with same phone
            pass
        
        # Check email
        email = data.get("email")
        if email:
            # Would query memory for other entities with same email
            pass
        
        return shared
    
    def detect_shell_network(self, entity_ids: List[str]) -> Dict:
        """
        Detect if entities form a shell company network.
        """
        flags = []
        
        if len(entity_ids) < 2:
            return {"is_shell_network": False, "flags": []}
        
        # Check for shared addresses
        addresses = []
        for eid in entity_ids:
            entity = self.memory.get_entity(eid)
            if entity:
                addr = entity.get("data", {}).get("address")
                if addr:
                    addresses.append(addr.lower())
        
        unique_addresses = set(addresses)
        if len(unique_addresses) < len(addresses):
            flags.append("Multiple entities share same address")
        
        # Check for virtual office addresses
        vo_indicators = ["regus", "wework", "ups store", "suite", "box"]
        for addr in addresses:
            if any(ind in addr for ind in vo_indicators):
                flags.append(f"Virtual office detected: {addr}")
        
        # Check registration dates
        reg_dates = []
        for eid in entity_ids:
            entity = self.memory.get_entity(eid)
            if entity:
                date = entity.get("data", {}).get("registration_date")
                if date:
                    reg_dates.append(datetime.fromisoformat(date))
        
        if reg_dates:
            date_range = max(reg_dates) - min(reg_dates)
            if date_range.days < 30:
                flags.append(f"Entities registered within {date_range.days} days of each other")
        
        return {
            "is_shell_network": len(flags) > 2,
            "flags": flags,
            "entity_count": len(entity_ids)
        }


class RiskPredictor:
    """
    Predicts risk based on patterns and similarities.
    """
    
    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.learner = PatternLearner(tenant_id)
    
    def predict_risk(self, target: str, entity_type: str, 
                     preliminary_data: Dict) -> Dict:
        """
        Predict risk before full investigation based on preliminary checks.
        """
        # Check if we've investigated similar entities
        similar = self._find_similar_entities(target, entity_type)
        
        if similar:
            avg_risk = sum(s.get("risk_score", 50) for s in similar) / len(similar)
            return {
                "predicted_risk": round(avg_risk),
                "confidence": 60,
                "basis": f"Based on {len(similar)} similar entities",
                "similar_entities": [s.get("name") for s in similar[:3]]
            }
        
        # No similar entities found
        return {
            "predicted_risk": None,
            "confidence": 0,
            "basis": "No prior similar investigations",
            "similar_entities": []
        }
    
    def _find_similar_entities(self, target: str, entity_type: str) -> List[Dict]:
        """Find previously investigated similar entities."""
        # This would query memory for entities with similar names/types
        # Simplified version
        return []
    
    def recommend_depth(self, target: str, entity_type: str,
                       preliminary_risk: int) -> str:
        """
        Recommend investigation depth based on initial assessment.
        """
        if preliminary_risk > 75:
            return "deep"  # High risk - go deep
        elif preliminary_risk > 50:
            return "standard"  # Medium risk - standard
        elif entity_type == "company" and "LLC" in target:
            return "standard"  # LLCs need standard check
        else:
            return "quick"  # Low risk - quick check sufficient


class EnhancedRiskScorer:
    """
    Risk scoring with learning and prediction.
    """
    
    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.learner = PatternLearner(tenant_id)
        self.predictor = RiskPredictor(tenant_id)
    
    def calculate(self, red_flags: List, green_flags: List,
                  consistency: Dict, target: str, entity_type: str) -> Dict:
        """
        Calculate enhanced risk score.
        """
        # Base calculation
        score = 50
        
        # Check known patterns
        pattern_analysis = self.learner.check_known_patterns(red_flags, entity_type)
        
        # Add for red flags (weighted by reliability)
        for flag in red_flags:
            sev = flag.get("severity", "LOW")
            flag_type = flag.get("type", "")
            
            # Get reliability for this flag type
            reliability = self.learner.get_flag_reliability(flag_type)
            reliability_mult = reliability.get("reliability", 0.5) + 0.5  # 0.5-1.5x
            
            base = {"CRITICAL": 30, "HIGH": 20, "MEDIUM": 10, "LOW": 3}.get(sev, 3)
            score += base * reliability_mult
        
        # Boost for known fraud patterns
        if pattern_analysis["known_fraud_pattern"]:
            score += 20
            score *= 1.2  # Multiplier
        
        # Reduce for false positive risk
        if pattern_analysis["false_positive_risk"] > 0.2:
            score *= 0.9
        
        # Green flags
        score -= len(green_flags) * 5
        
        # Consistency adjustments
        if consistency.get("contradictions"):
            score += 10
        
        # Clamp
        score = max(0, min(100, int(score)))
        
        # Determine level
        if score >= 90: level = "CRITICAL"
        elif score >= 75: level = "HIGH"
        elif score >= 50: level = "MEDIUM"
        elif score >= 25: level = "LOW"
        else: level = "MINIMAL"
        
        # Enhanced confidence
        base_confidence = 70
        base_confidence += pattern_analysis["confidence_boost"]
        base_confidence += min(10, len(red_flags))  # More flags = more certain
        
        if pattern_analysis["false_positive_risk"] > 0:
            base_confidence -= int(pattern_analysis["false_positive_risk"] * 20)
        
        return {
            "score": score,
            "level": level,
            "confidence": max(50, min(95, base_confidence)),
            "pattern_analysis": pattern_analysis,
            "factors": [f"{f['type']} ({f['severity']})" for f in red_flags[:5]]
        }


# Export for integration
__all__ = ['PatternLearner', 'RelationshipMapper', 'RiskPredictor', 'EnhancedRiskScorer']
