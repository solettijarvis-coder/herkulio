"""
Investigations API Routes - Fully Implemented
"""
import uuid
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from api.models import get_db, Investigation, Tenant, UsageLog
from api.main import get_current_tenant, redis_client
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
    
    class Config:
        from_attributes = True

class InvestigationDetail(InvestigationResponse):
    report_json: Optional[dict] = None
    cost_usd: Optional[float] = None
    duration_seconds: Optional[int] = None

@router.post("/", response_model=InvestigationResponse, status_code=status.HTTP_202_ACCEPTED)
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
    tenant_id = tenant["tenant_id"]
    user_id = tenant["user_id"]
    
    # Check tenant quota
    quota_result = await db.execute(
        select(func.count(Investigation.id))
        .where(Investigation.tenant_id == tenant_id)
        .where(Investigation.created_at >= datetime.utcnow() - timedelta(days=30))
    )
    current_usage = quota_result.scalar()
    
    tenant_result = await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )
    tenant_obj = tenant_result.scalar_one()
    
    if current_usage >= tenant_obj.quota_searches_monthly:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Monthly quota exceeded. Limit: {tenant_obj.quota_searches_monthly}"
        )
    
    # Check Herkulio's memory for prior investigations
    memory = get_memory(tenant_id)
    prior = memory.check_prior_investigation(data.target)
    
    if prior:
        # Return cached result if recent (< 7 days)
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
    
    # Create investigation record
    investigation_id = uuid.uuid4()
    normalized_target = data.target.lower().strip()
    
    investigation = Investigation(
        id=investigation_id,
        tenant_id=tenant_id,
        user_id=user_id,
        target=data.target,
        target_type=data.target_type,
        target_normalized=normalized_target,
        context={
            "email": data.email,
            "phone": data.phone,
            "url": data.url,
            "state": data.state,
            "country": data.country,
            "city": data.city,
            "notes": data.notes
        },
        depth=data.depth,
        status="pending"
    )
    
    db.add(investigation)
    await db.commit()
    
    # Queue Celery task
    context = {
        "email": data.email,
        "phone": data.phone,
        "url": data.url,
        "state": data.state,
        "country": data.country,
        "city": data.city,
        "notes": data.notes
    }
    
    # Run async task
    run_investigation_task.delay(
        investigation_id=str(investigation_id),
        target=data.target,
        target_type=data.target_type,
        depth=data.depth,
        context=context,
        tenant_id=tenant_id
    )
    
    # Log usage
    usage_log = UsageLog(
        tenant_id=tenant_id,
        user_id=user_id,
        resource_type="investigation",
        quantity=1,
        metadata={"target": data.target, "depth": data.depth}
    )
    db.add(usage_log)
    await db.commit()
    
    return InvestigationResponse(
        id=str(investigation_id),
        target=data.target,
        target_type=data.target_type,
        status="pending",
        created_at=datetime.utcnow()
    )

@router.get("/{investigation_id}", response_model=InvestigationDetail)
async def get_investigation(
    investigation_id: str,
    db: AsyncSession = Depends(get_db),
    tenant: dict = Depends(get_current_tenant)
):
    """Get investigation details and results"""
    tenant_id = tenant["tenant_id"]
    
    result = await db.execute(
        select(Investigation)
        .where(Investigation.id == investigation_id)
        .where(Investigation.tenant_id == tenant_id)
    )
    investigation = result.scalar_one_or_none()
    
    if not investigation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Investigation not found"
        )
    
    return InvestigationDetail(
        id=str(investigation.id),
        target=investigation.target,
        target_type=investigation.target_type,
        status=investigation.status,
        risk_score=investigation.risk_score,
        risk_level=investigation.risk_level,
        created_at=investigation.created_at,
        report_json=investigation.report_json,
        cost_usd=float(investigation.cost_usd) if investigation.cost_usd else None,
        duration_seconds=investigation.duration_seconds
    )

@router.get("/", response_model=dict)
async def list_investigations(
    limit: int = 20,
    offset: int = 0,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    tenant: dict = Depends(get_current_tenant)
):
    """List investigations for the tenant"""
    tenant_id = tenant["tenant_id"]
    
    query = select(Investigation).where(Investigation.tenant_id == tenant_id)
    
    if status:
        query = query.where(Investigation.status == status)
    
    # Get total count
    count_result = await db.execute(
        select(func.count(Investigation.id)).where(Investigation.tenant_id == tenant_id)
    )
    total = count_result.scalar()
    
    # Get paginated results
    query = query.order_by(Investigation.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    investigations = result.scalars().all()
    
    return {
        "items": [
            InvestigationResponse(
                id=str(inv.id),
                target=inv.target,
                target_type=inv.target_type,
                status=inv.status,
                risk_score=inv.risk_score,
                risk_level=inv.risk_level,
                created_at=inv.created_at
            )
            for inv in investigations
        ],
        "total": total,
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
    tenant_id = tenant["tenant_id"]
    
    result = await db.execute(
        select(Investigation)
        .where(Investigation.id == investigation_id)
        .where(Investigation.tenant_id == tenant_id)
    )
    investigation = result.scalar_one_or_none()
    
    if not investigation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Investigation not found"
        )
    
    # Reset status and queue again
    investigation.status = "pending"
    await db.commit()
    
    # Queue new task
    run_investigation_task.delay(
        investigation_id=str(investigation_id),
        target=investigation.target,
        target_type=investigation.target_type,
        depth=investigation.depth,
        context=investigation.context,
        tenant_id=tenant_id,
        rerun=True
    )
    
    return {"status": "rerun_queued", "investigation_id": investigation_id}

@router.get("/{investigation_id}/report")
async def get_report(
    investigation_id: str,
    format: str = "json",  # json, markdown
    db: AsyncSession = Depends(get_db),
    tenant: dict = Depends(get_current_tenant)
):
    """Download investigation report"""
    tenant_id = tenant["tenant_id"]
    
    result = await db.execute(
        select(Investigation)
        .where(Investigation.id == investigation_id)
        .where(Investigation.tenant_id == tenant_id)
    )
    investigation = result.scalar_one_or_none()
    
    if not investigation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Investigation not found"
        )
    
    if investigation.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Investigation not completed. Status: {investigation.status}"
        )
    
    if format == "markdown":
        return {
            "format": "markdown",
            "content": investigation.report_markdown or "No markdown report available"
        }
    
    # Default JSON
    return {
        "format": "json",
        "investigation_id": investigation_id,
        "target": investigation.target,
        "target_type": investigation.target_type,
        "risk_score": investigation.risk_score,
        "risk_level": investigation.risk_level,
        "confidence_score": investigation.confidence_score,
        "report": investigation.report_json,
        "modules_used": investigation.modules_used,
        "cost_usd": float(investigation.cost_usd) if investigation.cost_usd else 0,
        "duration_seconds": investigation.duration_seconds,
        "created_at": investigation.created_at.isoformat() if investigation.created_at else None,
        "completed_at": investigation.completed_at.isoformat() if investigation.completed_at else None
    }
