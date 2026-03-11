# Herkulio

**OSINT Intelligence Platform** — Investigate individuals, companies, and watch dealers.

[https://herkulio.com](https://herkulio.com)

## Quick Start

### Local Development

```bash
git clone https://github.com/solettijarvis-coder/herkulio.git
cd herkulio

cp config/.env.example config/.env
# Edit config/.env with your API keys

cd infra/docker
docker-compose up -d
```

Services:
- Web: http://localhost:3000
- API: http://localhost:8000  
- API Docs: http://localhost:8000/docs

### Production Deployment

See [Production Deployment Guide](#production-deployment)

## Architecture

```
Herkulio SaaS Platform
├── Frontend (Next.js)
│   ├── Dashboard (10 tabs: Overview, Users, Costs, Features, Sources, Discovery, Investigate, Cases, Engine, Logs)
│   └── White/Indigo design (Wealthsimple/Linear aesthetic)
├── Backend (FastAPI)
│   ├── REST API with multi-tenant auth
│   ├── 29 OSINT modules
│   ├── Herkulio Memory System (per-tenant SQLite)
│   └── Celery workers for async investigations
├── Database (PostgreSQL)
│   └── Multi-tenant schema with RLS
└── Infrastructure
    ├── Docker Compose (local/dev)
    └── Docker Compose + nginx-proxy (production)
```

## Features

### Investigation Engine
- **29 OSINT modules** — Corporate registries, sanctions, court records, social media, domain intel
- **Risk scoring** — Automated risk assessment with confidence intervals
- **Multi-tenancy** — Each customer isolated, no data leakage
- **Async processing** — Celery workers handle investigations in background
- **Memory system** — Caches prior investigations, tracks entity relationships

### Dashboard
- Real-time investigation status
- Risk breakdown by category
- Case management
- Usage analytics
- API key management

### API
- RESTful endpoints
- JWT authentication
- API key support for programmatic access
- Webhook notifications
- Rate limiting

## Tech Stack

| Component | Technology |
|-----------|------------|
| Frontend | Next.js 15, React 18 |
| Backend | FastAPI, Python 3.11 |
| Database | PostgreSQL 16 |
| Cache/Queue | Redis 7 |
| Workers | Celery |
| Auth | JWT + API Keys |
| Billing | Stripe |
| Container | Docker |
| Reverse Proxy | nginx-proxy |
| SSL | Let's Encrypt (acme-companion) |

## Production Deployment

### Prerequisites

- VPS with 2GB+ RAM (DigitalOcean, AWS, Hetzner)
- Domain name (herkulio.com)
- Docker & Docker Compose

### Step 1: Server Setup

```bash
# On your VPS
curl -fsSL https://raw.githubusercontent.com/solettijarvis-coder/herkulio/main/infra/setup-vps.sh | sudo bash
```

### Step 2: Configure Environment

```bash
cd /opt/herkulio
cp config/.env.prod.example config/.env.prod
nano config/.env.prod  # Add your API keys
```

Required:
- `OPENROUTER_API_KEY` — AI synthesis
- `TAVILY_API_KEY` — Search
- `SERPER_API_KEY` — OSINT search
- `STRIPE_SECRET_KEY` — Billing
- `TELEGRAM_BOT_TOKEN` — Bot (optional)

### Step 3: Deploy

```bash
cd /opt/herkulio
./infra/deploy.sh
```

### Step 4: Configure DNS

Point your domain to the VPS IP:
- `herkulio.com` → VPS IP
- `api.herkulio.com` → VPS IP

SSL certificates auto-provision via Let's Encrypt.

### Step 5: Verify

```bash
docker-compose -f infra/docker/docker-compose.prod.yml ps
docker-compose -f infra/docker/docker-compose.prod.yml logs -f
```

## CI/CD

GitHub Actions workflow:
- Test backend & frontend
- Build Docker images
- Push to GitHub Container Registry
- Deploy to production (manual trigger)

## Development

```bash
# Backend
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn api.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

## API Documentation

Once running, visit:
- Swagger UI: `/docs`
- ReDoc: `/redoc`

## Security

- JWT authentication
- API key scoped access
- Row-level security in PostgreSQL
- Per-tenant SQLite memory (isolated)
- Rate limiting
- Input validation
- No shared state between tenants

## Monitoring

Optional integrations:
- Sentry for error tracking
- CloudWatch/Datadog for metrics
- PagerDuty for alerts

## License

Proprietary — JLC Ventures

## Support

- Email: support@herkulio.com
- Telegram: @herkulio_support
