"""
INVESTIGATION_MEMORY.py — Cross-Case Entity Graph
====================================================
Persistent memory across investigations. When Herkulio investigates a new target,
he checks if ANY entity from the new search matches a previously investigated entity.

"I've seen this person before — he was the owner of ABC Watches. In my previous
investigation, I flagged [X]. Connecting the dots..."

Storage: SQLite (reports_cache.db — same DB as existing cache)
Entities tracked: names, addresses, phones, emails, domains, companies
"""

import json
import os
import sqlite3
import time
from datetime import datetime


DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports_cache.db")


def init_memory():
    """Initialize the investigation memory tables."""
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
    -- Entity graph: all entities encountered across investigations
    CREATE TABLE IF NOT EXISTS entities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_type TEXT NOT NULL,  -- person, company, address, phone, email, domain
        value TEXT NOT NULL,        -- normalized value
        raw_value TEXT,             -- original value
        first_seen TEXT,            -- ISO timestamp
        last_seen TEXT,             -- ISO timestamp
        times_seen INTEGER DEFAULT 1,
        risk_flags TEXT DEFAULT '[]',  -- JSON array of flags from investigations
        UNIQUE(entity_type, value)
    );

    -- Links between entities (relationship graph)
    CREATE TABLE IF NOT EXISTS entity_links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_id_1 INTEGER NOT NULL,
        entity_id_2 INTEGER NOT NULL,
        relationship TEXT,  -- owner_of, registered_at, uses_phone, etc.
        investigation_id TEXT,  -- which investigation found this link
        confidence REAL DEFAULT 0.5,
        created_at TEXT,
        FOREIGN KEY (entity_id_1) REFERENCES entities(id),
        FOREIGN KEY (entity_id_2) REFERENCES entities(id),
        UNIQUE(entity_id_1, entity_id_2, relationship)
    );

    -- Investigation log
    CREATE TABLE IF NOT EXISTS investigations (
        id TEXT PRIMARY KEY,  -- hash ID
        target TEXT NOT NULL,
        target_type TEXT,
        risk_rating TEXT,
        summary TEXT,
        timestamp TEXT,
        entities_found INTEGER DEFAULT 0,
        links_found INTEGER DEFAULT 0
    );

    CREATE INDEX IF NOT EXISTS idx_entity_value ON entities(entity_type, value);
    CREATE INDEX IF NOT EXISTS idx_entity_links ON entity_links(entity_id_1);
    """)
    conn.commit()
    conn.close()


def _normalize(entity_type: str, value: str) -> str:
    """Normalize an entity value for comparison."""
    if not value:
        return ""
    value = value.strip().lower()

    if entity_type == "phone":
        import re
        value = re.sub(r'[^\d+]', '', value)
    elif entity_type == "email":
        value = value.lower().strip()
    elif entity_type == "domain":
        value = value.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]
    elif entity_type == "address":
        import re
        value = re.sub(r'[,\.\#]', ' ', value)
        value = re.sub(r'\s+', ' ', value).strip()
    elif entity_type in ("person", "company"):
        import re
        # Remove common suffixes
        for suffix in [" llc", " inc", " corp", " ltd", " co"]:
            if value.endswith(suffix):
                value = value[:-len(suffix)].strip()
        value = re.sub(r'[,\.\-\'\"&]', ' ', value)
        value = re.sub(r'\s+', ' ', value).strip()

    return value


def _get_or_create_entity(conn, entity_type: str, value: str, raw_value: str = None) -> int:
    """Get existing entity ID or create new one. Returns entity ID."""
    norm = _normalize(entity_type, value)
    if not norm:
        return -1

    now = datetime.utcnow().isoformat()

    # Try to find existing
    row = conn.execute(
        "SELECT id, times_seen FROM entities WHERE entity_type = ? AND value = ?",
        (entity_type, norm)
    ).fetchone()

    if row:
        entity_id = row[0]
        conn.execute(
            "UPDATE entities SET last_seen = ?, times_seen = times_seen + 1 WHERE id = ?",
            (now, entity_id)
        )
        return entity_id
    else:
        cursor = conn.execute(
            "INSERT INTO entities (entity_type, value, raw_value, first_seen, last_seen) VALUES (?,?,?,?,?)",
            (entity_type, norm, raw_value or value, now, now)
        )
        return cursor.lastrowid


def _add_link(conn, id1: int, id2: int, relationship: str, investigation_id: str = None):
    """Add a link between two entities."""
    if id1 < 0 or id2 < 0 or id1 == id2:
        return
    now = datetime.utcnow().isoformat()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO entity_links (entity_id_1, entity_id_2, relationship, investigation_id, created_at) VALUES (?,?,?,?,?)",
            (id1, id2, relationship, investigation_id, now)
        )
    except sqlite3.IntegrityError:
        pass


def store_investigation(report: dict) -> dict:
    """
    Extract entities from a report and store them in the graph.
    Returns summary of what was stored.
    """
    init_memory()
    conn = sqlite3.connect(DB_PATH)

    target = report.get("target", "Unknown")
    target_type = report.get("type", "unknown")
    risk = report.get("risk_rating", "UNKNOWN")
    summary = report.get("executive_summary", "")[:500]

    import hashlib
    inv_id = hashlib.md5(f"{target}{time.time()}".encode()).hexdigest()[:16]

    entities_stored = 0
    links_stored = 0

    # Store target entity
    target_entity_type = "company" if target_type in ("company", "organization") else "person"
    target_eid = _get_or_create_entity(conn, target_entity_type, target)
    entities_stored += 1

    # Add risk flags to target
    if risk in ("HIGH", "CRITICAL"):
        red_flags = report.get("red_flags", [])
        if red_flags:
            conn.execute(
                "UPDATE entities SET risk_flags = ? WHERE id = ?",
                (json.dumps(red_flags[:5]), target_eid)
            )

    # Extract and store people
    people = report.get("people", [])
    cr = report.get("corporate_records", {})
    officers = cr.get("officers_managers", []) if isinstance(cr, dict) else []

    all_people = set()
    for p in people:
        if isinstance(p, dict) and p.get("name"):
            all_people.add(p["name"])
    for o in officers:
        if isinstance(o, dict) and o.get("name"):
            all_people.add(o["name"])
        elif isinstance(o, str):
            all_people.add(o)

    for person_name in all_people:
        pid = _get_or_create_entity(conn, "person", person_name)
        if pid > 0:
            _add_link(conn, pid, target_eid, "officer_of" if target_entity_type == "company" else "associated_with", inv_id)
            entities_stored += 1
            links_stored += 1

    # Store address
    if isinstance(cr, dict) and cr.get("principal_address"):
        aid = _get_or_create_entity(conn, "address", cr["principal_address"])
        if aid > 0:
            _add_link(conn, target_eid, aid, "registered_at", inv_id)
            entities_stored += 1
            links_stored += 1

    # Store domain
    di = report.get("domain_intel", {}) or report.get("domain_info", {})
    if isinstance(di, dict) and di.get("domain"):
        did = _get_or_create_entity(conn, "domain", di["domain"])
        if did > 0:
            _add_link(conn, target_eid, did, "owns_domain", inv_id)
            entities_stored += 1
            links_stored += 1

    # Store phone
    if report.get("phone_lookup"):
        phone_data = report["phone_lookup"]
        if isinstance(phone_data, dict) and phone_data.get("phone"):
            phid = _get_or_create_entity(conn, "phone", phone_data["phone"])
            if phid > 0:
                _add_link(conn, target_eid, phid, "uses_phone", inv_id)
                entities_stored += 1
                links_stored += 1

    # Store emails
    ed = report.get("email_discovery", {})
    if isinstance(ed, dict):
        for email in (ed.get("emails_found", []) or [])[:5]:
            eid = _get_or_create_entity(conn, "email", email)
            if eid > 0:
                _add_link(conn, target_eid, eid, "uses_email", inv_id)
                entities_stored += 1
                links_stored += 1

    # Store related entities
    for re_ent in (report.get("related_entities", []) or [])[:10]:
        if isinstance(re_ent, dict) and re_ent.get("name"):
            reid = _get_or_create_entity(conn, "company", re_ent["name"])
            if reid > 0:
                _add_link(conn, target_eid, reid, "related_to", inv_id)
                entities_stored += 1
                links_stored += 1

    # Log the investigation
    conn.execute(
        "INSERT OR REPLACE INTO investigations (id, target, target_type, risk_rating, summary, timestamp, entities_found, links_found) VALUES (?,?,?,?,?,?,?,?)",
        (inv_id, target, target_type, risk, summary, datetime.utcnow().isoformat(), entities_stored, links_stored)
    )

    conn.commit()
    conn.close()

    return {
        "investigation_id": inv_id,
        "entities_stored": entities_stored,
        "links_stored": links_stored,
    }


def check_prior_knowledge(target: str, context: dict = None) -> dict:
    """
    Before a new investigation, check if we've seen any related entities before.
    Returns prior knowledge context.
    """
    init_memory()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    ctx = context or {}
    prior_hits = []

    # Check target name
    norm_target = _normalize("company", target) or _normalize("person", target)
    if norm_target:
        rows = conn.execute(
            "SELECT * FROM entities WHERE value LIKE ? AND times_seen > 0",
            (f"%{norm_target}%",)
        ).fetchall()
        for row in rows:
            prior_hits.append({
                "match_type": "target_name",
                "entity_type": row["entity_type"],
                "value": row["raw_value"] or row["value"],
                "times_seen": row["times_seen"],
                "first_seen": row["first_seen"],
                "risk_flags": json.loads(row["risk_flags"]) if row["risk_flags"] else [],
            })

    # Check email
    if ctx.get("email"):
        norm_email = _normalize("email", ctx["email"])
        rows = conn.execute(
            "SELECT * FROM entities WHERE entity_type = 'email' AND value = ?",
            (norm_email,)
        ).fetchall()
        for row in rows:
            prior_hits.append({
                "match_type": "email",
                "value": row["raw_value"] or row["value"],
                "times_seen": row["times_seen"],
                "first_seen": row["first_seen"],
            })

    # Check phone
    if ctx.get("phone"):
        norm_phone = _normalize("phone", ctx["phone"])
        rows = conn.execute(
            "SELECT * FROM entities WHERE entity_type = 'phone' AND value = ?",
            (norm_phone,)
        ).fetchall()
        for row in rows:
            prior_hits.append({
                "match_type": "phone",
                "value": row["raw_value"] or row["value"],
                "times_seen": row["times_seen"],
            })

    # Check domain
    if ctx.get("url"):
        norm_domain = _normalize("domain", ctx["url"])
        rows = conn.execute(
            "SELECT * FROM entities WHERE entity_type = 'domain' AND value = ?",
            (norm_domain,)
        ).fetchall()
        for row in rows:
            prior_hits.append({
                "match_type": "domain",
                "value": row["raw_value"] or row["value"],
                "times_seen": row["times_seen"],
            })

    # Get linked investigations for any hits
    linked_investigations = []
    entity_ids = set()
    for hit in prior_hits:
        norm = _normalize(hit.get("entity_type", "company"), hit.get("value", ""))
        rows = conn.execute(
            "SELECT id FROM entities WHERE value = ?", (norm,)
        ).fetchall()
        entity_ids.update(row["id"] for row in rows)

    if entity_ids:
        placeholders = ",".join(["?"] * len(entity_ids))
        link_rows = conn.execute(
            f"SELECT DISTINCT investigation_id FROM entity_links WHERE entity_id_1 IN ({placeholders}) OR entity_id_2 IN ({placeholders})",
            list(entity_ids) + list(entity_ids)
        ).fetchall()
        inv_ids = [r["investigation_id"] for r in link_rows if r["investigation_id"]]

        if inv_ids:
            placeholders2 = ",".join(["?"] * len(inv_ids))
            inv_rows = conn.execute(
                f"SELECT * FROM investigations WHERE id IN ({placeholders2})",
                inv_ids
            ).fetchall()
            for inv in inv_rows:
                linked_investigations.append({
                    "id": inv["id"],
                    "target": inv["target"],
                    "risk_rating": inv["risk_rating"],
                    "summary": inv["summary"],
                    "timestamp": inv["timestamp"],
                })

    conn.close()

    has_prior = len(prior_hits) > 0

    return {
        "has_prior_knowledge": has_prior,
        "prior_hits": prior_hits,
        "linked_investigations": linked_investigations,
        "message": _build_prior_message(prior_hits, linked_investigations) if has_prior else None,
    }


def _build_prior_message(hits: list, investigations: list) -> str:
    """Build a human-readable message about prior knowledge."""
    parts = ["⚡ PRIOR KNOWLEDGE DETECTED:"]

    for hit in hits[:5]:
        match = hit.get("match_type", "?")
        value = hit.get("value", "?")
        times = hit.get("times_seen", 0)
        flags = hit.get("risk_flags", [])

        parts.append(f"  • {match}: '{value}' seen {times}x before")
        if flags:
            parts.append(f"    ⚠️ Prior flags: {', '.join(flags[:3])}")

    if investigations:
        parts.append("")
        parts.append("  Linked previous investigations:")
        for inv in investigations[:3]:
            risk_emoji = {"HIGH": "🔴", "CRITICAL": "🚨", "MEDIUM": "🟡", "LOW": "🟢"}.get(inv.get("risk_rating", ""), "⚪")
            parts.append(f"  {risk_emoji} {inv['target']} — {inv.get('risk_rating', '?')} ({inv.get('timestamp', '?')[:10]})")
            if inv.get("summary"):
                parts.append(f"    {inv['summary'][:150]}")

    return "\n".join(parts)


def get_memory_stats() -> dict:
    """Get statistics about the investigation memory."""
    init_memory()
    conn = sqlite3.connect(DB_PATH)

    entities = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
    links = conn.execute("SELECT COUNT(*) FROM entity_links").fetchone()[0]
    investigations = conn.execute("SELECT COUNT(*) FROM investigations").fetchone()[0]
    flagged = conn.execute("SELECT COUNT(*) FROM entities WHERE risk_flags != '[]' AND risk_flags IS NOT NULL").fetchone()[0]

    conn.close()

    return {
        "total_entities": entities,
        "total_links": links,
        "total_investigations": investigations,
        "flagged_entities": flagged,
    }


if __name__ == "__main__":
    init_memory()
    stats = get_memory_stats()
    print(f"Investigation Memory Stats:")
    print(f"  Entities: {stats['total_entities']}")
    print(f"  Links: {stats['total_links']}")
    print(f"  Investigations: {stats['total_investigations']}")
    print(f"  Flagged: {stats['flagged_entities']}")
