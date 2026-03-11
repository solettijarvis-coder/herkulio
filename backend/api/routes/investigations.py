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
    
    # TODO: Save to database
    # TODO: Check tenant quota
    # TODO: Queue background task
    
    # For now, return mock response
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
