# Herkulio Memory System
# Separate from Jarvis/JLC - this is Herkulio's own knowledge graph

import os
import json
from datetime import datetime
from typing import Optional, List, Dict
import sqlite3

HERKULIO_MEMORY_DIR = os.environ.get("HERKULIO_MEMORY_DIR", "/app/data/memory")
os.makedirs(HERKULIO_MEMORY_DIR, exist_ok=True)

class HerkulioMemory:
    """
    Herkulio's standalone memory system.
    No connection to Jarvis's ~/life/ or OpenClaw memory.
    """
    
    def __init__(self, tenant_id: Optional[str] = None):
        self.tenant_id = tenant_id or "system"
        self.db_path = os.path.join(HERKULIO_MEMORY_DIR, f"{self.tenant_id}.db")
        self._init_db()
    
    def _init_db(self):
        """Initialize SQLite for this tenant's memory"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Entities: People, companies, watches, dealers
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS entities (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL, -- person, company, watch, dealer
                normalized_name TEXT,
                data JSON,
                risk_score INTEGER,
                first_seen TIMESTAMP,
                last_seen TIMESTAMP,
                investigation_count INTEGER DEFAULT 0
            )
        """)
        
        # Relationships between entities
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS relationships (
                id TEXT PRIMARY KEY,
                source_id TEXT,
                target_id TEXT,
                type TEXT, -- owns, works_for, associated_with, sold_to
                confidence INTEGER,
                evidence JSON,
                first_seen TIMESTAMP
            )
        """)
        
        # Watch market data
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS watch_data (
                id TEXT PRIMARY KEY,
                reference TEXT,
                brand TEXT,
                model TEXT,
                price_data JSON,
                market_trend TEXT,
                last_price DECIMAL,
                last_updated TIMESTAMP
            )
        """)
        
        # Investigation history (lightweight, full data in PostgreSQL)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS investigation_cache (
                id TEXT PRIMARY KEY,
                target TEXT,
                target_normalized TEXT,
                risk_level TEXT,
                key_findings JSON,
                created_at TIMESTAMP
            )
        """)
        
        conn.commit()
        conn.close()
    
    def store_entity(self, entity_id: str, name: str, entity_type: str, 
                     data: Dict, risk_score: Optional[int] = None):
        """Store or update an entity"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        now = datetime.utcnow().isoformat()
        normalized = name.lower().strip()
        
        cursor.execute("""
            INSERT INTO entities (id, name, type, normalized_name, data, risk_score, first_seen, last_seen, investigation_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(id) DO UPDATE SET
                data = excluded.data,
                risk_score = excluded.risk_score,
                last_seen = excluded.last_seen,
                investigation_count = investigation_count + 1
        """, (entity_id, name, entity_type, normalized, json.dumps(data), risk_score, now, now))
        
        conn.commit()
        conn.close()
    
    def get_entity(self, entity_id: str) -> Optional[Dict]:
        """Retrieve entity by ID"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM entities WHERE id = ?", (entity_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                "id": row[0],
                "name": row[1],
                "type": row[2],
                "data": json.loads(row[4]) if row[4] else {},
                "risk_score": row[5],
                "investigation_count": row[8]
            }
        return None
    
    def find_by_name(self, name: str) -> List[Dict]:
        """Find entities by name (fuzzy match)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        normalized = name.lower().strip()
        cursor.execute("""
            SELECT * FROM entities 
            WHERE normalized_name LIKE ? 
            ORDER BY investigation_count DESC
        """, (f"%{normalized}%",))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [{"id": r[0], "name": r[1], "type": r[2], "risk_score": r[5]} for r in rows]
    
    def store_relationship(self, source_id: str, target_id: str, 
                          rel_type: str, confidence: int, evidence: Dict):
        """Store relationship between entities"""
        import uuid
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        rel_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        
        cursor.execute("""
            INSERT OR REPLACE INTO relationships 
            (id, source_id, target_id, type, confidence, evidence, first_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (rel_id, source_id, target_id, rel_type, confidence, json.dumps(evidence), now))
        
        conn.commit()
        conn.close()
    
    def get_related(self, entity_id: str) -> List[Dict]:
        """Get all entities related to this one"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT r.*, e.name as target_name 
            FROM relationships r
            JOIN entities e ON r.target_id = e.id
            WHERE r.source_id = ?
        """, (entity_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [{"target": r[7], "type": r[3], "confidence": r[4]} for r in rows]
    
    def cache_investigation(self, investigation_id: str, target: str,
                           risk_level: str, findings: Dict):
        """Cache investigation summary for quick lookup"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        now = datetime.utcnow().isoformat()
        normalized = target.lower().strip()
        
        cursor.execute("""
            INSERT INTO investigation_cache (id, target, target_normalized, risk_level, key_findings, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (investigation_id, target, normalized, risk_level, json.dumps(findings), now))
        
        conn.commit()
        conn.close()
    
    def check_prior_investigation(self, target: str) -> Optional[Dict]:
        """Check if we've investigated this target before"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        normalized = target.lower().strip()
        cursor.execute("""
            SELECT * FROM investigation_cache 
            WHERE target_normalized = ?
            ORDER BY created_at DESC LIMIT 1
        """, (normalized,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                "investigation_id": row[0],
                "target": row[1],
                "risk_level": row[3],
                "findings": json.loads(row[4]) if row[4] else {},
                "created_at": row[5]
            }
        return None

# Global instance for system use
_system_memory = None

def get_memory(tenant_id: Optional[str] = None) -> HerkulioMemory:
    """Get memory instance for tenant"""
    if tenant_id is None:
        global _system_memory
        if _system_memory is None:
            _system_memory = HerkulioMemory()
        return _system_memory
    return HerkulioMemory(tenant_id)
