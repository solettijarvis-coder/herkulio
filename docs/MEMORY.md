# Herkulio Memory System

**Completely separate from Jarvis/JLC memory. Herkulio's own knowledge graph.**

## Overview

Herkulio uses its own SQLite-based memory system per tenant. No connection to:
- Jarvis's `~/life/` PARA system
- OpenClaw's memory
- JLC internal databases

## Structure

```
/app/data/memory/
├── system.db           # System-wide knowledge
├── tenant_abc123.db    # Tenant A's private memory
├── tenant_def456.db    # Tenant B's private memory
└── ...
```

## Tables

### entities
People, companies, watches, dealers that Herkulio has investigated.

```sql
id, name, type, normalized_name, data, risk_score, 
first_seen, last_seen, investigation_count
```

### relationships
Connections between entities (ownership, employment, associations).

```sql
id, source_id, target_id, type, confidence, evidence, first_seen
```

### watch_data
Watch market intelligence.

```sql
id, reference, brand, model, price_data, market_trend, last_price
```

### investigation_cache
Quick lookup for repeat investigations.

```sql
id, target, target_normalized, risk_level, key_findings, created_at
```

## Usage

```python
from osint.memory import get_memory

# Get tenant's memory
memory = get_memory(tenant_id="abc123")

# Store entity
memory.store_entity(
    entity_id="uuid",
    name="John Smith",
    entity_type="person",
    data={"email": "john@example.com"},
    risk_score=75
)

# Check prior investigations
prior = memory.check_prior_investigation("John Smith")
if prior:
    print(f"Investigated {prior['created_at']}: {prior['risk_level']}")

# Find related entities
related = memory.get_related(entity_id)
```

## Data Isolation

- Each tenant gets their own `.db` file
- No cross-tenant data leakage
- SQLite is tenant-scoped, PostgreSQL is shared with RLS
