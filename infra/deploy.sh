#!/bin/bash
# Deploy Herkulio to Production VPS
# Run this on your production server after setting up the VPS

set -e

HERKULIO_DIR="/opt/herkulio"
GITHUB_USER="solettijarvis-coder"

echo "=========================================="
echo "Herkulio Production Deployment"
echo "=========================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root or with sudo"
    exit 1
fi

# Install Docker if not present
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
fi

# Install Docker Compose
if ! command -v docker-compose &> /dev/null; then
    echo "Installing Docker Compose..."
    curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
fi

# Create herkulio directory
mkdir -p $HERKULIO_DIR
cd $HERKULIO_DIR

# Clone repository (or pull if exists)
if [ -d ".git" ]; then
    echo "Pulling latest code..."
    git pull origin main
else
    echo "Cloning repository..."
    git clone https://github.com/$GITHUB_USER/herkulio.git .
fi

# Setup environment file
if [ ! -f "config/.env.prod" ]; then
    echo "Creating production environment file..."
    cp config/.env.prod.example config/.env.prod
    echo "⚠️  IMPORTANT: Edit config/.env.prod with your real API keys!"
    echo "Run: nano $HERKULIO_DIR/config/.env.prod"
    exit 1
fi

# Create required directories
mkdir -p data/postgres data/redis data/api

# Login to GitHub Container Registry
echo "Logging into GitHub Container Registry..."
echo "You need a GitHub Personal Access Token with 'read:packages' scope"
read -p "Enter GitHub PAT: " GITHUB_TOKEN
echo $GITHUB_TOKEN | docker login ghcr.io -u $GITHUB_USER --password-stdin

# Pull and start services
echo "Starting Herkulio services..."
docker-compose -f infra/docker/docker-compose.prod.yml pull
docker-compose -f infra/docker/docker-compose.prod.yml up -d

# Wait for database
echo "Waiting for database..."
sleep 10

# Run migrations
echo "Running database migrations..."
docker-compose -f infra/docker/docker-compose.prod.yml exec -T api alembic upgrade head || echo "Migrations may need to be run manually"

# Check status
echo ""
echo "=========================================="
echo "Deployment Status"
echo "=========================================="
docker-compose -f infra/docker/docker-compose.prod.yml ps

echo ""
echo "=========================================="
echo "Herkulio is deployed!"
echo "=========================================="
echo ""
echo "Web:    https://herkulio.com (once DNS is configured)"
echo "API:    https://api.herkulio.com"
echo ""
echo "Next steps:"
echo "1. Configure DNS: herkulio.com → $(curl -s ifconfig.me)"
echo "2. Edit config/.env.prod with real API keys"
echo "3. Restart: docker-compose -f infra/docker/docker-compose.prod.yml restart"
echo ""
echo "Logs: docker-compose -f infra/docker/docker-compose.prod.yml logs -f"
echo ""
