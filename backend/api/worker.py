"""
Celery Worker for Async Investigations
"""
import os
from celery import Celery
from celery.signals import task_prerun, task_postrun

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

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

@celery_app.task(bind=True, max_retries=3)
def run_investigation_task(self, investigation_id: str, target: str, target_type: str, depth: str, context: dict, tenant_id: str = None):
    """
    Run an investigation asynchronously.
    
    This calls the herkulio_engine.py with proper tenant isolation.
    Uses Herkulio's own memory system - completely separate from Jarvis.
    """
    try:
        # Update status to running
        # TODO: Update database
        
        # Import Herkulio's memory (not Jarvis's)
        from osint.memory import get_memory
        memory = get_memory(tenant_id)
        
        # Import and run the engine
        import sys
        sys.path.insert(0, '/app/osint')
        from herkulio_engine import run_investigation
        
        result = run_investigation(
            target=target,
            target_type=target_type,
            depth=depth,
            **context
        )
        
        # Store entity in Herkulio's memory
        entity_id = str(uuid.uuid4())
        memory.store_entity(
            entity_id=entity_id,
            name=target,
            entity_type=target_type,
            data=result.get("raw_data", {}),
            risk_score=result.get("risk_score")
        )
        
        # Cache investigation for quick lookup
        memory.cache_investigation(
            investigation_id=investigation_id,
            target=target,
            risk_level=result.get("risk_level", "unknown"),
            findings=result
        )
        
        # Save results to database
        # TODO: Update database with report
        
        return {
            "investigation_id": investigation_id,
            "status": "completed",
            "result": result
        }
        
    except Exception as exc:
        # Retry on failure
        self.retry(countdown=60, exc=exc)

@task_prerun.connect
def task_started(sender=None, task_id=None, task=None, args=None, kwargs=None, **extras):
    """Log task start"""
    print(f"Starting task {task.name}[{task_id}]")

@task_postrun.connect
def task_completed(sender=None, task_id=None, task=None, args=None, kwargs=None, retval=None, state=None, **extras):
    """Log task completion"""
    print(f"Completed task {task.name}[{task_id}] with state {state}")
