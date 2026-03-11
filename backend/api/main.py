"""
Herkulio API - FastAPI Application
Standalone SaaS OSINT Platform
"""
import os
from contextlib import asynccontextmanager
from typing import Optional

import redis.asyncio as redis
from fastapi import FastAPI, Depends, HTTPException, Security, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Load environment variables
load_dotenv('/app/config/.env')

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://herkulio:herkulio_password@postgres:5432/herkulio")
engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Redis setup
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
redis_client: Optional[redis.Redis] = None

# Security
security = HTTPBearer(auto_error=False)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    global redis_client
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    yield
    # Shutdown
    await redis_client.close()
    await engine.dispose()

app = FastAPI(
    title="Herkulio Intelligence API",
    description="Multi-tenant OSINT platform for investigating individuals, companies, and watch dealers",
    version="1.0.0",
    lifespan=lifespan
)

# Dependency to get DB session
async def get_db():
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()

# Dependency to get current tenant/user from API key
async def get_current_tenant(
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: AsyncSession = Depends(get_db)
):
    """Validate API key and return tenant context"""
    if not credentials:
        raise HTTPException(status_code=401, detail="API key required")
    
    # TODO: Implement API key validation against database
    # For now, return a mock tenant context
    return {
        "tenant_id": "mock-tenant-id",
        "user_id": "mock-user-id",
        "plan": "pro"
    }

@app.get("/")
async def root():
    return {
        "name": "Herkulio Intelligence API",
        "version": "1.0.0",
        "status": "operational"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "services": ["api", "postgres", "redis"]}

# Import and include routers
from api.routes import investigations, tenants, users, billing, webhooks

app.include_router(investigations.router, prefix="/api/v1/investigations", tags=["Investigations"])
app.include_router(tenants.router, prefix="/api/v1/tenants", tags=["Tenants"])
app.include_router(users.router, prefix="/api/v1/users", tags=["Users"])
app.include_router(billing.router, prefix="/api/v1/billing", tags=["Billing"])
app.include_router(webhooks.router, prefix="/api/v1/webhooks", tags=["Webhooks"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
