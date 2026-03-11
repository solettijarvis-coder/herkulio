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
def run_investigation_task(self, investigation_id: str, target: str, target_type: str, depth: str, context: dict):
    """
    Run an investigation asynchronously.
    
    This calls the herkulio_engine.py with proper tenant isolation.
    """
    try:
        # Update status to running
        # TODO: Update database
        
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
