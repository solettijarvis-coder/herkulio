-- Herkulio SaaS Database Schema
-- Multi-tenant PostgreSQL schema

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Tenants = Organizations/Teams
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL, -- subdomain: tenant.herkulio.com
    plan VARCHAR(50) NOT NULL DEFAULT 'free', -- free, pro, enterprise
    status VARCHAR(50) NOT NULL DEFAULT 'active', -- active, suspended, cancelled
    
    -- Quotas
    quota_searches_monthly INTEGER NOT NULL DEFAULT 5,
    quota_deep_reports INTEGER NOT NULL DEFAULT 0,
    quota_api_calls INTEGER NOT NULL DEFAULT 100,
    
    -- Billing
    stripe_customer_id VARCHAR(255),
    stripe_subscription_id VARCHAR(255),
    billing_email VARCHAR(255),
    
    -- Settings
    settings JSONB DEFAULT '{}',
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Users belong to tenants
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    
    -- Auth
    email VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255), -- null for SSO/API key only users
    
    -- Profile
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    role VARCHAR(50) NOT NULL DEFAULT 'analyst', -- admin, analyst, viewer
    
    -- API Access
    api_key_hash VARCHAR(255),
    api_key_last_used TIMESTAMP WITH TIME ZONE,
    
    -- OpenRouter BYOK (Bring Your Own Key)
    openrouter_key_encrypted TEXT,
    
    -- Preferences
    preferences JSONB DEFAULT '{}',
    
    -- Status
    last_login_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT TRUE,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE(tenant_id, email)
);

-- API Keys for programmatic access
CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    name VARCHAR(255) NOT NULL, -- "Production", "Staging", etc.
    key_hash VARCHAR(255) NOT NULL,
    key_prefix VARCHAR(8) NOT NULL, -- hk_live_... first 8 chars
    
    -- Scopes
    scopes JSONB DEFAULT '["investigations:read", "investigations:write"]',
    
    -- Usage tracking
    usage_count INTEGER DEFAULT 0,
    last_used_at TIMESTAMP WITH TIME ZONE,
    
    -- Expiration
    expires_at TIMESTAMP WITH TIME ZONE,
    
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Investigations are tenant-scoped
CREATE TABLE investigations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE SET NULL,
    api_key_id UUID REFERENCES api_keys(id) ON DELETE SET NULL,
    
    -- Target info
    target VARCHAR(500) NOT NULL,
    target_type VARCHAR(50) NOT NULL, -- person, company, organization
    target_normalized VARCHAR(500), -- normalized for deduplication
    
    -- Context
    context JSONB DEFAULT '{}', -- email, phone, url, state, notes, etc.
    
    -- Configuration
    depth VARCHAR(50) NOT NULL DEFAULT 'standard', -- quick, standard, deep
    modules_used JSONB DEFAULT '[]',
    
    -- Results
    status VARCHAR(50) NOT NULL DEFAULT 'pending', -- pending, running, completed, failed
    report_json JSONB,
    report_markdown TEXT,
    
    -- Risk & Confidence
    risk_score INTEGER, -- 0-100
    risk_level VARCHAR(20), -- low, medium, high, critical
    confidence_score INTEGER, -- 0-100
    
    -- Cost tracking
    cost_usd DECIMAL(10,4) DEFAULT 0,
    tokens_used INTEGER DEFAULT 0,
    
    -- Timings
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    duration_seconds INTEGER,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Usage tracking for billing
CREATE TABLE usage_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    
    resource_type VARCHAR(50) NOT NULL, -- search, report, api_call
    quantity INTEGER NOT NULL DEFAULT 1,
    cost_usd DECIMAL(10,4) DEFAULT 0,
    
    metadata JSONB DEFAULT '{}',
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Webhook endpoints for integrations
CREATE TABLE webhooks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    
    url VARCHAR(500) NOT NULL,
    secret VARCHAR(255), -- for HMAC signature
    
    events JSONB DEFAULT '["investigation.completed"]', -- which events to send
    
    is_active BOOLEAN DEFAULT TRUE,
    last_error TEXT,
    last_sent_at TIMESTAMP WITH TIME ZONE,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Audit log for security
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    
    action VARCHAR(100) NOT NULL, -- investigation.created, user.login, etc.
    resource_type VARCHAR(50),
    resource_id UUID,
    
    ip_address INET,
    user_agent TEXT,
    
    changes JSONB, -- before/after for updates
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_investigations_tenant ON investigations(tenant_id);
CREATE INDEX idx_investigations_user ON investigations(user_id);
CREATE INDEX idx_investigations_target ON investigations(target_normalized);
CREATE INDEX idx_investigations_status ON investigations(status);
CREATE INDEX idx_investigations_created ON investigations(created_at DESC);
CREATE INDEX idx_usage_logs_tenant ON usage_logs(tenant_id, created_at);
CREATE INDEX idx_api_keys_hash ON api_keys(key_hash);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_audit_logs_tenant ON audit_logs(tenant_id, created_at DESC);

-- Row Level Security (RLS) policies
ALTER TABLE investigations ENABLE ROW LEVEL SECURITY;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE webhooks ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;

-- RLS: Users can only see their tenant's data
CREATE POLICY tenant_isolation_investigations ON investigations
    USING (tenant_id = current_setting('app.current_tenant')::UUID);

CREATE POLICY tenant_isolation_users ON users
    USING (tenant_id = current_setting('app.current_tenant')::UUID);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers for updated_at
CREATE TRIGGER update_tenants_updated_at BEFORE UPDATE ON tenants
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_investigations_updated_at BEFORE UPDATE ON investigations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
