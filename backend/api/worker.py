#!/usr/bin/env python3
"""
Celery Worker for Async Investigations
Fully wired to Herkulio Enhanced Brain
"""
import os
import sys
import uuid
import asyncio
from datetime import datetime
from decimal import Decimal

from celery import Celery
from celery.signals import task_prerun, task_postrun
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add osint to path
sys.path.insert(0, '/app/osint')

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://herkulio:herkulio_password@postgres:5432/herkulio")

celery_app = Celery(
    "herkulio",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["api.worker"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,
    worker_prefetch_multiplier=1,
)

# Database for sync operations in worker
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

@celery_app.task(bind=True, max_retries=3)
def run_investigation_task(self, investigation_id: str, target: str, target_type: str, depth: str, context: dict, tenant_id: str = None, rerun: bool = False):
    """
    Run an investigation using Herkulio's ENHANCED brain.
    
    Now includes:
    - Watch industry red flag detection
    - Cross-reference validation
    - Enhanced risk scoring
    - Professional verdict generation
    """
    from herkulio_engine import run_investigation
    from memory import get_memory
    from brain_enhanced import get_brain
    
    session = Session()
    start_time = datetime.utcnow()
    
    try:
        # Update status
        from api.models import Investigation
        investigation = session.query(Investigation).filter_by(id=investigation_id).first()
        if investigation:
            investigation.status = "running"
            investigation.started_at = start_time
            session.commit()
        
        # Get Herkulio's components
        memory = get_memory(tenant_id)
        brain = get_brain()
        
        # Step 1: Run OSINT engine (29 modules)
        raw_result = run_investigation(
            target=target,
            target_type=target_type,
            depth=depth,
            **context
        )
        
        # Step 2: Process through ENHANCED brain
        # This applies watch industry expertise, red flags, cross-references
        result = asyncio.run(brain.investigate(target, target_type, raw_result))
        
        # Calculate timing
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        
        # Cost tracking
        cost_map = {"quick": 0.02, "standard": 0.05, "deep": 0.10}
        estimated_cost = cost_map.get(depth, 0.05)
        
        # Extract results
        risk_score = result.get("risk_score", 50)
        risk_level = result.get("risk_level", "medium")
        confidence = result.get("confidence", 70)
        
        # Step 3: Store in Herkulio's memory
        entity_id = str(uuid.uuid4())
        memory.store_entity(
            entity_id=entity_id,
            name=target,
            entity_type=target_type,
            data=raw_result.get("raw_data", {}),
            risk_score=risk_score
        )
        
        memory.cache_investigation(
            investigation_id=investigation_id,
            target=target,
            risk_level=risk_level,
            findings=result
        )
        
        # Step 4: Save to database
        if investigation:
            investigation.status = "completed"
            investigation.completed_at = end_time
            investigation.duration_seconds = int(duration)
            investigation.risk_score = risk_score
            investigation.risk_level = risk_level
            investigation.confidence_score = confidence
            investigation.report_json = result
            investigation.report_markdown = result.get("markdown_report", "")
            investigation.modules_used = raw_result.get("modules_used", [])
            investigation.cost_usd = Decimal(str(estimated_cost))
            session.commit()
        
        return {
            "investigation_id": investigation_id,
            "status": "completed",
            "duration_seconds": duration,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "confidence": confidence
        }
        
    except Exception as exc:
        # Mark as failed
        try:
            if investigation:
                investigation.status = "failed"
                investigation.completed_at = datetime.utcnow()
                session.commit()
        except:
            pass
        
        session.close()
        self.retry(countdown=60, exc=exc)
        
    finally:
        session.close()

@task_prerun.connect
def task_started(sender=None, task_id=None, task=None, args=None, kwargs=None, **extras):
    print(f"[{datetime.utcnow().isoformat()}] Starting task {task.name}[{task_id}]")

@task_postrun.connect
def task_completed(sender=None, task_id=None, task=None, args=None, kwargs=None, retval=None, state=None, **extras):
    print(f"[{datetime.utcnow().isoformat()}] Completed task {task.name}[{task_id}] with state {state}")
