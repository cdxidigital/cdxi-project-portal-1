# Deployment Guide

This document provides comprehensive instructions for deploying the CDXI Project Portal to production.

## Prerequisites

- Docker and Docker Compose installed
- MongoDB instance (cloud-hosted recommended for production)
- Stripe account and API keys
- Domain name and SSL certificate
- Server with at least 2GB RAM, 10GB storage

## Environment Setup

### 1. Configuration Files

Create production environment files:

```bash
# Copy and configure production environment
cp .env.production.example .env.production
nano .env.production  # Edit with production values
```

Update the following critical values:
- `MONGO_URL`: Production MongoDB connection string
- `JWT_SECRET`: Generate a strong 32+ character secret
- `ADMIN_PASSWORD`: Set a strong admin password
- `STRIPE_API_KEY`: Use production Stripe API key
- `CORS_ORIGINS`: Set to your production domain
- `REACT_APP_API_URL`: Set to your API domain

### 2. Backend Configuration

```bash
cd backend
cp .env.example .env
# Update with production values
```

### 3. Frontend Configuration

```bash
cd frontend
cp .env.example .env
# Update REACT_APP_API_URL to production API endpoint
```

## Local Testing

Test the complete stack locally before deployment:

```bash
# Start services
npm run docker:up

# Check logs
npm run docker:logs

# Run tests
npm run test

# Verify endpoints
curl http://localhost:8000/api/
curl http://localhost:3000
```

## Docker Build & Push

### 1. Build Images

```bash
# Development
npm run docker:build

# Production (optimized)
npm run docker:prod:build
```

### 2. Push to Registry (Optional)

```bash
# Set Docker credentials
export DOCKER_USERNAME=your_username
export DOCKER_PASSWORD=your_password
export DOCKER_REGISTRY=docker.io
export DOCKER_NAMESPACE=your_namespace

# Build and push
npm run deploy
```

## Production Deployment

### Option 1: Docker Compose (Simple)

```bash
# On production server
git clone <repo>
cd cdxi-project-portal

# Setup environment
cp .env.production.example .env.production
nano .env.production

# Start services
docker-compose -f docker-compose.prod.yml up -d

# View logs
docker-compose -f docker-compose.prod.yml logs -f
```

### Option 2: Kubernetes (Advanced)

Create `k8s/deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: cdxi-backend
spec:
  replicas: 2
  selector:
    matchLabels:
      app: cdxi-backend
  template:
    metadata:
      labels:
        app: cdxi-backend
    spec:
      containers:
      - name: backend
        image: your-registry/cdxi-backend:latest
        ports:
        - containerPort: 8000
        env:
        - name: MONGO_URL
          valueFrom:
            secretKeyRef:
              name: cdxi-secrets
              key: mongo-url
        - name: JWT_SECRET
          valueFrom:
            secretKeyRef:
              name: cdxi-secrets
              key: jwt-secret
        livenessProbe:
          httpGet:
            path: /api/
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /api/
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
```

Deploy with:
```bash
kubectl apply -f k8s/deployment.yaml
```

## Nginx Reverse Proxy

Create `nginx.conf`:

```nginx
upstream backend {
    server localhost:8000;
}

upstream frontend {
    server localhost:3000;
}

server {
    listen 80;
    server_name yourdomain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com;
    
    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
    
    # Frontend
    location / {
        proxy_pass http://frontend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # API
    location /api {
        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }
}
```

Install SSL certificate with Let's Encrypt:
```bash
sudo apt-get install certbot python3-certbot-nginx
sudo certbot certonly --nginx -d yourdomain.com
```

## Database Migration

### MongoDB Atlas (Recommended)

1. Create cluster at https://www.mongodb.com/cloud/atlas
2. Get connection string
3. Update `MONGO_URL` in `.env.production`

### Local MongoDB

```bash
# Install MongoDB
curl https://www.mongodb.org/static/pgp/server-6.0.asc | apt-key add -
apt-get install -y mongodb-org

# Start service
systemctl start mongod
systemctl enable mongod

# Verify
mongo --version
```

## Health Checks & Monitoring

### API Health

```bash
# Check backend health
curl -s http://localhost:8000/api/ | jq .

# Check frontend health
curl -s http://localhost:3000
```

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f backend
docker-compose logs -f frontend

# System logs
tail -f logs/cdxi-api_*.log
```

### Monitoring Setup

```bash
# Install Prometheus
docker run -d \
  --name prometheus \
  -p 9090:9090 \
  -v $(pwd)/prometheus.yml:/etc/prometheus/prometheus.yml \
  prom/prometheus

# Install Grafana
docker run -d \
  --name grafana \
  -p 3001:3000 \
  grafana/grafana
```

## Backup & Recovery

### MongoDB Backup

```bash
# Create backup
mongodump --uri="mongodb+srv://user:password@cluster.mongodb.net/cdxi_db" --out=./backups

# Restore backup
mongorestore --uri="mongodb+srv://user:password@cluster.mongodb.net/cdxi_db" ./backups
```

### Automated Backup

Create cron job:
```bash
0 2 * * * /usr/local/bin/backup-mongo.sh
```

Content of `backup-mongo.sh`:
```bash
#!/bin/bash
BACKUP_DIR="/backups/mongodb"
DATE=$(date +"%Y%m%d_%H%M%S")
mongodump --uri="$MONGO_URL" --out="$BACKUP_DIR/$DATE"
# Keep last 30 days only
find $BACKUP_DIR -mtime +30 -exec rm -rf {} \;
```

## Troubleshooting

### Backend won't start
```bash
# Check MongoDB connection
nc -zv mongodb_host 27017

# Check logs
docker-compose logs backend

# Verify environment variables
docker-compose exec backend env | grep MONGO
```

### Frontend shows blank page
```bash
# Check API connectivity from browser console
fetch('http://localhost:8000/api/').then(r => r.json()).then(console.log)

# Check REACT_APP_API_URL
docker-compose exec frontend env | grep REACT_APP_API_URL
```

### Payment processing issues
```bash
# Verify Stripe key
echo $STRIPE_API_KEY

# Check webhook logs
docker-compose logs backend | grep -i stripe
```

## Security Checklist

- [ ] Rotate JWT_SECRET
- [ ] Use strong ADMIN_PASSWORD
- [ ] Enable HTTPS/SSL
- [ ] Configure firewall rules
- [ ] Setup rate limiting
- [ ] Enable MongoDB authentication
- [ ] Use environment-specific secrets
- [ ] Rotate Stripe API keys
- [ ] Setup error tracking (Sentry)
- [ ] Enable audit logging
- [ ] Regular security updates
- [ ] Backup strategy in place

## Rollback Procedure

```bash
# If new version has issues, rollback to previous
docker-compose pull  # Get all available versions
docker-compose -f docker-compose.prod.yml down
docker image ls  # Find previous stable version
docker tag old-image-id new-registry/cdxi-backend:latest
docker-compose -f docker-compose.prod.yml up -d
```

## Performance Optimization

### Frontend
```bash
# Run production build
cd frontend
npm run build
# Check bundle size
npm install -g webpack-bundle-analyzer
```

### Backend
```bash
# Enable caching
# Add Redis configuration
# Setup database connection pooling
# Configure uvicorn workers
```

## Maintenance

### Regular Tasks

Daily:
- Monitor error logs
- Check disk space
- Verify backup completion

Weekly:
- Review application metrics
- Update dependencies
- Security patches

Monthly:
- Full backup test
- Database optimization
- Performance review

For support, refer to CONTRIBUTING.md or contact the development team.
