"""
SQLAlchemy Models for Herkulio
Multi-tenant database models
"""
import uuid
from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, 
    Text, ForeignKey, JSON, DECIMAL, create_engine
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.sql import func

Base = declarative_base()

class Tenant(Base):
    """Organizations/teams using Herkulio"""
    __tablename__ = "tenants"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    plan = Column(String(50), default="free")  # free, pro, enterprise
    status = Column(String(50), default="active")
    
    # Quotas
    quota_searches_monthly = Column(Integer, default=5)
    quota_deep_reports = Column(Integer, default=0)
    quota_api_calls = Column(Integer, default=100)
    
    # Billing
    stripe_customer_id = Column(String(255))
    stripe_subscription_id = Column(String(255))
    billing_email = Column(String(255))
    
    # Settings
    settings = Column(JSON, default=dict)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    users = relationship("User", back_populates="tenant")
    investigations = relationship("Investigation", back_populates="tenant")
    api_keys = relationship("ApiKey", back_populates="tenant")

class User(Base):
    """Users belonging to a tenant"""
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    
    # Auth
    email = Column(String(255), nullable=False)
    password_hash = Column(String(255))
    
    # Profile
    first_name = Column(String(100))
    last_name = Column(String(100))
    role = Column(String(50), default="analyst")  # admin, analyst, viewer
    
    # API Access
    api_key_hash = Column(String(255))
    api_key_last_used = Column(DateTime(timezone=True))
    
    # BYOK (Bring Your Own Key)
    openrouter_key_encrypted = Column(Text)
    
    # Preferences
    preferences = Column(JSON, default=dict)
    
    # Status
    last_login_at = Column(DateTime(timezone=True))
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    tenant = relationship("Tenant", back_populates="users")
    investigations = relationship("Investigation", back_populates="user")
    api_keys = relationship("ApiKey", back_populates="user")
    
    __table_args__ = (
        # Unique email per tenant
        {'schema': 'public'}
    )

class ApiKey(Base):
    """API keys for programmatic access"""
    __tablename__ = "api_keys"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    name = Column(String(255), nullable=False)
    key_hash = Column(String(255), nullable=False)
    key_prefix = Column(String(8), nullable=False)
    
    scopes = Column(JSON, default=list)
    
    usage_count = Column(Integer, default=0)
    last_used_at = Column(DateTime(timezone=True))
    expires_at = Column(DateTime(timezone=True))
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    tenant = relationship("Tenant", back_populates="api_keys")
    user = relationship("User", back_populates="api_keys")

class Investigation(Base):
    """OSINT investigations"""
    __tablename__ = "investigations"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    api_key_id = Column(UUID(as_uuid=True), ForeignKey("api_keys.id", ondelete="SET NULL"))
    
    # Target info
    target = Column(String(500), nullable=False)
    target_type = Column(String(50), nullable=False)
    target_normalized = Column(String(500))
    
    # Context
    context = Column(JSON, default=dict)
    
    # Configuration
    depth = Column(String(50), default="standard")
    modules_used = Column(JSON, default=list)
    
    # Results
    status = Column(String(50), default="pending")  # pending, running, completed, failed
    report_json = Column(JSON)
    report_markdown = Column(Text)
    
    # Risk & Confidence
    risk_score = Column(Integer)
    risk_level = Column(String(20))
    confidence_score = Column(Integer)
    
    # Cost tracking
    cost_usd = Column(DECIMAL(10, 4), default=0)
    tokens_used = Column(Integer, default=0)
    
    # Timings
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    duration_seconds = Column(Integer)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    tenant = relationship("Tenant", back_populates="investigations")
    user = relationship("User", back_populates="investigations")

class UsageLog(Base):
    """Usage tracking for billing"""
    __tablename__ = "usage_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    
    resource_type = Column(String(50), nullable=False)
    quantity = Column(Integer, default=1)
    cost_usd = Column(DECIMAL(10, 4), default=0)
    metadata = Column(JSON, default=dict)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Webhook(Base):
    """Webhook endpoints"""
    __tablename__ = "webhooks"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    
    url = Column(String(500), nullable=False)
    secret = Column(String(255))
    events = Column(JSON, default=list)
    
    is_active = Column(Boolean, default=True)
    last_error = Column(Text)
    last_sent_at = Column(DateTime(timezone=True))
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class AuditLog(Base):
    """Security audit log"""
    __tablename__ = "audit_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    
    action = Column(String(100), nullable=False)
    resource_type = Column(String(50))
    resource_id = Column(UUID(as_uuid=True))
    
    ip_address = Column(String(45))
    user_agent = Column(Text)
    changes = Column(JSON)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

# Database connection helper
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

engine = None
async_session = None

def init_db(database_url: str):
    """Initialize database engine"""
    global engine, async_session
    engine = create_async_engine(database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def create_tables():
    """Create all tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_db():
    """Get database session"""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
