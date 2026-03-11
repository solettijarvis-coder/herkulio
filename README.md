# Herkulio SaaS

Standalone OSINT intelligence platform. Multi-tenant SaaS for investigating individuals, companies, and watch dealers.

## Quick Start

```bash
# Clone and setup
cd herkulio-saas

cp config/.env.example config/.env
# Edit config/.env with your API keys

docker-compose up -d
```

## Architecture

```
herkulio-saas/
├── backend/         # FastAPI + OSINT engine
├── frontend/        # Next.js dashboard
├── database/        # PostgreSQL migrations
└── infra/           # Docker, K8s, Terraform
```

## Services

- **API** (port 8000): FastAPI REST API
- **Web** (port 3000): Next.js dashboard
- **PostgreSQL** (port 5432): Multi-tenant database
- **Redis** (port 6379): Caching & rate limiting
- **Worker**: Celery for async investigations

## Environment Variables

See `config/.env.example` for required variables.

## API Documentation

Once running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## License

Proprietary - JLC Ventures
