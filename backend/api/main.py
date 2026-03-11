"""
Herkulio API - FastAPI Application
Standalone SaaS OSINT Platform
"""
import os
import hashlib
import secrets
from contextlib import asynccontextmanager
from typing import Optional
from datetime import datetime, timedelta

import redis.asyncio as redis
import jwt
from fastapi import FastAPI, Depends, HTTPException, Security, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from dotenv import load_dotenv

# Load environment variables
load_dotenv('/app/config/.env')

# Import models
from api.models import init_db, create_tables, get_db, Tenant, User, ApiKey, Investigation

# Config
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://herkulio:herkulio_password@postgres:5432/herkulio")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"

# Redis setup
redis_client: Optional[redis.Redis] = None

# Security
security = HTTPBearer(auto_error=False)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global redis_client
    
    # Initialize database
    init_db(DATABASE_URL)
    
    # Initialize Redis
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    
    # Create tables on startup
    await create_tables()
    
    yield
    
    # Cleanup
    await redis_client.close()

app = FastAPI(
    title="Herkulio Intelligence API",
    description="Multi-tenant OSINT platform for investigating individuals, companies, and watch dealers",
    version="1.0.0",
    lifespan=lifespan
)

# Authentication helpers
def hash_api_key(key: str) -> str:
    """Hash API key for storage"""
    return hashlib.sha256(key.encode()).hexdigest()

def generate_api_key() -> str:
    """Generate new API key"""
    return f"hk_{secrets.token_urlsafe(32)}"

def create_jwt_token(user_id: str, tenant_id: str) -> str:
    """Create JWT access token"""
    expires = datetime.utcnow() + timedelta(hours=24)
    payload = {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "exp": expires,
        "type": "access"
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)

async def verify_jwt_token(token: str) -> Optional[dict]:
    """Verify and decode JWT token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

# Dependencies
async def get_current_tenant(
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Validate API key or JWT and return tenant context.
    Supports both API key (Bearer hk_xxx) and JWT auth.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    token = credentials.credentials
    
    # Check if it's an API key (starts with hk_)
    if token.startswith("hk_"):
        # Hash the key for lookup
        key_hash = hash_api_key(token)
        key_prefix = token[:8]
        
        # Look up in database
        result = await db.execute(
            select(ApiKey, User, Tenant)
            .join(User, ApiKey.user_id == User.id)
            .join(Tenant, ApiKey.tenant_id == Tenant.id)
            .where(ApiKey.key_hash == key_hash)
            .where(ApiKey.key_prefix == key_prefix)
            .where(ApiKey.is_active == True)
        )
        row = result.first()
        
        if not row:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key"
            )
        
        api_key, user, tenant = row
        
        # Check expiration
        if api_key.expires_at and api_key.expires_at < datetime.utcnow():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key expired"
            )
        
        # Update usage
        api_key.usage_count += 1
        api_key.last_used_at = datetime.utcnow()
        await db.commit()
        
        return {
            "tenant_id": str(tenant.id),
            "user_id": str(user.id),
            "plan": tenant.plan,
            "api_key_id": str(api_key.id),
            "scopes": api_key.scopes or ["investigations:read", "investigations:write"]
        }
    
    # Otherwise treat as JWT
    payload = await verify_jwt_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )
    
    return {
        "tenant_id": payload["tenant_id"],
        "user_id": payload["user_id"],
        "plan": "pro",  # Could look up from DB
        "scopes": ["investigations:read", "investigations:write", "admin"]
    }

@app.get("/")
async def root():
    return {
        "name": "Herkulio Intelligence API",
        "version": "1.0.0",
        "status": "operational",
        "documentation": "/docs"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    health = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {}
    }
    
    # Check Redis
    try:
        await redis_client.ping()
        health["services"]["redis"] = "ok"
    except:
        health["services"]["redis"] = "error"
    
    # Check Database
    try:
        async for session in get_db():
            await session.execute(select(Tenant).limit(1))
            health["services"]["postgres"] = "ok"
            break
    except Exception as e:
        health["services"]["postgres"] = f"error: {str(e)}"
    
    # Overall status
    if all(s == "ok" for s in health["services"].values()):
        health["status"] = "healthy"
    else:
        health["status"] = "degraded"
    
    return health

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
