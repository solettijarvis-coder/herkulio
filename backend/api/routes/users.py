"""
Users API Routes
"""
from fastapi import APIRouter, HTTPException

router = APIRouter()

@router.get("/")
async def list_users():
    """List users in tenant (admin only)"""
    raise HTTPException(status_code=501, detail="Not implemented")

@router.post("/")
async def create_user():
    """Create new user (admin only)"""
    raise HTTPException(status_code=501, detail="Not implemented")

@router.post("/api-keys")
async def create_api_key():
    """Create API key for programmatic access"""
    raise HTTPException(status_code=501, detail="Not implemented")

@router.get("/api-keys")
async def list_api_keys():
    """List API keys"""
    raise HTTPException(status_code=501, detail="Not implemented")
