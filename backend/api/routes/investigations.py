"""
Investigations API Routes
"""
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.main import get_db, get_current_tenant
from api.worker import run_investigation_task
from osint.memory import get_memory

router = APIRouter()

# Request/Response Models
class InvestigationCreate(BaseModel):
    target: str = Field(..., min_length=1, max_length=500)
    target_type: str = Field(default="auto", pattern="^(auto|person|company|organization)$")
    depth: str = Field(default="standard", pattern="^(quick|standard|deep)$")
    
    # Optional context
    email: Optional[str] = None
    phone: Optional[str] = None
    url: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    notes: Optional[str] = None

class InvestigationResponse(BaseModel):
    id: str
    target: str
    target_type: str
    status: str
    risk_score: Optional[int] = None
    risk_level: Optional[str] = None
    created_at: datetime

@router.post("/", response_model=InvestigationResponse)
async def create_investigation(
    data: InvestigationCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    tenant: dict = Depends(get_current_tenant)
):
    """
    Create a new investigation.
    
    The investigation runs asynchronously. Check status via GET /{id}.
    """
    investigation_id = str(uuid.uuid4())
    
    # Check Herkulio's own memory for prior investigations
    memory = get_memory(tenant.get("tenant_id"))
    prior = memory.check_prior_investigation(data.target)
    
    if prior:
        # Return cached result if recent (< 7 days)
        from datetime import timedelta
        prior_date = datetime.fromisoformat(prior["created_at"])
        if datetime.utcnow() - prior_date < timedelta(days=7):
            return InvestigationResponse(
                id=prior["investigation_id"],
                target=data.target,
                target_type=data.target_type,
                status="completed",
                risk_score=prior["findings"].get("risk_score"),
                risk_level=prior["risk_level"],
                created_at=prior_date
            )
    
    # TODO: Save to database
    # TODO: Check tenant quota
    # TODO: Queue background task with Herkulio's memory
    
    context = {
        "email": data.email,
        "phone": data.phone,
        "url": data.url,
        "state": data.state,
        "country": data.country,
        "city": data.city,
        "notes": data.notes
    }
    
    # Queue Celery task
    run_investigation_task.delay(
        investigation_id=investigation_id,
        target=data.target,
        target_type=data.target_type,
        depth=data.depth,
        context=context,
        tenant_id=tenant.get("tenant_id")
    )
    
    return InvestigationResponse(
        id=investigation_id,
        target=data.target,
        target_type=data.target_type,
        status="pending",
        created_at=datetime.utcnow()
    )

@router.get("/{investigation_id}")
async def get_investigation(
    investigation_id: str,
    db: AsyncSession = Depends(get_db),
    tenant: dict = Depends(get_current_tenant)
):
    """Get investigation details and results"""
    # TODO: Fetch from database with tenant isolation
    raise HTTPException(status_code=404, detail="Investigation not found")

@router.get("/")
async def list_investigations(
    limit: int = 20,
    offset: int = 0,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    tenant: dict = Depends(get_current_tenant)
):
    """List investigations for the tenant"""
    # TODO: Fetch from database with pagination
    return {
        "items": [],
        "total": 0,
        "limit": limit,
        "offset": offset
    }

@router.post("/{investigation_id}/rerun")
async def rerun_investigation(
    investigation_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    tenant: dict = Depends(get_current_tenant)
):
    """Rerun an existing investigation with fresh data"""
    raise HTTPException(status_code=501, detail="Not implemented")

@router.get("/{investigation_id}/report")
async def get_report(
    investigation_id: str,
    format: str = "json",  # json, markdown, pdf
    db: AsyncSession = Depends(get_db),
    tenant: dict = Depends(get_current_tenant)
):
    """Download investigation report"""
    raise HTTPException(status_code=501, detail="Not implemented")
