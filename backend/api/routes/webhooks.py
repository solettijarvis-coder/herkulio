"""
Webhooks API Routes
"""
from fastapi import APIRouter, HTTPException

router = APIRouter()

@router.get("/")
async def list_webhooks():
    """List configured webhooks"""
    raise HTTPException(status_code=501, detail="Not implemented")

@router.post("/")
async def create_webhook():
    """Create new webhook endpoint"""
    raise HTTPException(status_code=501, detail="Not implemented")

@router.delete("/{webhook_id}")
async def delete_webhook(webhook_id: str):
    """Delete webhook endpoint"""
    raise HTTPException(status_code=501, detail="Not implemented")
