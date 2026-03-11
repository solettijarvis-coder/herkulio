"""
Celery Worker for Async Investigations
Fully wired to Herkulio OSINT Engine
"""
import os
import sys
import uuid
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
    task_time_limit=600,  # 10 minutes max per investigation
    worker_prefetch_multiplier=1,
)

# Database for sync operations in worker
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

@celery_app.task(bind=True, max_retries=3)
def run_investigation_task(self, investigation_id: str, target: str, target_type: str, depth: str, context: dict, tenant_id: str, rerun: bool = False):
    """
    Run an investigation asynchronously using Herkulio's OSINT engine.
    
    This is completely separate from Jarvis - uses Herkulio's own:
    - OSINT engine (29 modules)
    - Memory system (per-tenant SQLite)
    - Database (PostgreSQL)
    """
    from herkulio_engine import run_investigation
    from memory import get_memory
    
    session = Session()
    start_time = datetime.utcnow()
    
    try:
        # Update status to running
        from api.models import Investigation
        investigation = session.query(Investigation).filter_by(id=investigation_id).first()
        if investigation:
            investigation.status = "running"
            investigation.started_at = start_time
            session.commit()
        
        # Import Herkulio's memory (NOT Jarvis's)
        memory = get_memory(tenant_id)
        
        # Run the actual OSINT investigation
        # This calls the full 29-module engine
        result = run_investigation(
            target=target,
            target_type=target_type,
            depth=depth,
            **context
        )
        
        # Calculate duration and cost
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        
        # Estimate cost based on depth
        cost_map = {"quick": 0.02, "standard": 0.05, "deep": 0.10}
        estimated_cost = cost_map.get(depth, 0.05)
        
        # Extract risk info from result
        risk_score = result.get("risk_score", 50)
        risk_level = result.get("risk_level", "medium")
        if not risk_level:
            if risk_score >= 75:
                risk_level = "high"
            elif risk_score >= 50:
                risk_level = "medium"
            else:
                risk_level = "low"
        
        # Store entity in Herkulio's memory (NOT Jarvis's)
        entity_id = str(uuid.uuid4())
        memory.store_entity(
            entity_id=entity_id,
            name=target,
            entity_type=target_type,
            data=result.get("raw_data", {}),
            risk_score=risk_score
        )
        
        # Cache investigation for quick lookup
        memory.cache_investigation(
            investigation_id=investigation_id,
            target=target,
            risk_level=risk_level,
            findings=result
        )
        
        # Update database with results
        if investigation:
            investigation.status = "completed"
            investigation.completed_at = end_time
            investigation.duration_seconds = int(duration)
            investigation.risk_score = risk_score
            investigation.risk_level = risk_level
            investigation.confidence_score = result.get("confidence_score", 70)
            investigation.report_json = result
            investigation.report_markdown = result.get("markdown_report", "")
            investigation.modules_used = result.get("modules_used", [])
            investigation.cost_usd = Decimal(str(estimated_cost))
            session.commit()
        
        return {
            "investigation_id": investigation_id,
            "status": "completed",
            "duration_seconds": duration,
            "risk_score": risk_score,
            "risk_level": risk_level
        }
        
    except Exception as exc:
        # Update status to failed
        try:
            if investigation:
                investigation.status = "failed"
                investigation.completed_at = datetime.utcnow()
                session.commit()
        except:
            pass
        
        session.close()
        
        # Retry on failure
        self.retry(countdown=60, exc=exc)
        
    finally:
        session.close()

@task_prerun.connect
def task_started(sender=None, task_id=None, task=None, args=None, kwargs=None, **extras):
    """Log task start"""
    print(f"[{datetime.utcnow().isoformat()}] Starting task {task.name}[{task_id}]")

@task_postrun.connect
def task_completed(sender=None, task_id=None, task=None, args=None, kwargs=None, retval=None, state=None, **extras):
    """Log task completion"""
    print(f"[{datetime.utcnow().isoformat()}] Completed task {task.name}[{task_id}] with state {state}")
