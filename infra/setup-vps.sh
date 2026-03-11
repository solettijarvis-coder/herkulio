#!/bin/bash
# Setup a fresh VPS for Herkulio
# Run this on a new DigitalOcean, AWS, or Hetzner VPS

set -e

echo "=========================================="
echo "Herkulio VPS Setup"
echo "=========================================="

# Update system
apt-get update
apt-get upgrade -y

# Install essentials
apt-get install -y \
    curl \
    wget \
    git \
    htop \
    ufw \
    fail2ban \
    certbot \
    python3-certbot-nginx

# Configure firewall
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# Configure fail2ban
cat > /etc/fail2ban/jail.local << EOF
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 3

[sshd]
enabled = true
EOF

systemctl restart fail2ban

# Setup swap (for 2GB RAM VPS)
if [ ! -f /swapfile ]; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# Optimize sysctl for containers
cat >> /etc/sysctl.conf << EOF
vm.swappiness=10
vm.vfs_cache_pressure=50
net.core.somaxconn=65535
EOF

sysctl -p

# Create herkulio user
useradd -m -s /bin/bash herkulio || true
usermod -aG docker herkulio 2>/dev/null || true

echo ""
echo "=========================================="
echo "VPS Setup Complete!"
echo "=========================================="
echo ""
echo "Next: Run the deployment script as root:"
echo "  sudo bash -c '\$(curl -fsSL https://raw.githubusercontent.com/solettijarvis-coder/herkulio/main/infra/deploy.sh)'"
echo ""
echo "Or manually:"
echo "  git clone https://github.com/solettijarvis-coder/herkulio.git /opt/herkulio"
echo "  cd /opt/herkulio"
echo "  cp config/.env.prod.example config/.env.prod"
echo "  # Edit config/.env.prod"
echo "  docker-compose -f infra/docker/docker-compose.prod.yml up -d"
echo ""
