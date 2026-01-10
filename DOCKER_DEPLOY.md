# DOCKER DEPLOYMENT GUIDE

## Quick Start (Local Development)

### 1. Using Docker Compose (Recommended)

```bash
# Build and start everything
docker-compose up --build

# Run in background
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

**Access:**
- App: http://localhost:5000
- CockroachDB UI: http://localhost:8080

---

## Production Deployment

### Option 1: Google Cloud Run (Easiest)

```bash
# Install Google Cloud SDK first

# Build and deploy
gcloud run deploy tryspeak \
  --source . \
  --region europe-west1 \
  --allow-unauthenticated \
  --set-env-vars="$(cat .env | grep -v '^#' | xargs)" \
  --memory 512Mi \
  --cpu 1 \
  --max-instances 10 \
  --timeout 120
```

**Benefits:**
- Automatic scaling
- Pay per use
- HTTPS included
- No server management

---

### Option 2: Docker on VPS (DigitalOcean, AWS, etc)

```bash
# On your server

# 1. Clone repo
git clone https://github.com/yourrepo/tryspeak.git
cd tryspeak

# 2. Create .env
cp .env.example .env
# Edit .env with your credentials

# 3. Build image
docker build -t tryspeak .

# 4. Run container
docker run -d \
  --name tryspeak \
  -p 80:5000 \
  --env-file .env \
  --restart unless-stopped \
  tryspeak

# 5. Check logs
docker logs -f tryspeak

# 6. Update app
git pull
docker build -t tryspeak .
docker stop tryspeak
docker rm tryspeak
docker run -d --name tryspeak -p 80:5000 --env-file .env --restart unless-stopped tryspeak
```

---

### Option 3: Docker Hub + Pull

```bash
# Build and push to Docker Hub
docker build -t yourusername/tryspeak:latest .
docker push yourusername/tryspeak:latest

# On production server
docker pull yourusername/tryspeak:latest
docker run -d \
  --name tryspeak \
  -p 80:5000 \
  --env-file .env \
  --restart unless-stopped \
  yourusername/tryspeak:latest
```

---

### Option 4: Kubernetes (Advanced)

```bash
# Create deployment
kubectl create deployment tryspeak --image=yourusername/tryspeak:latest

# Expose service
kubectl expose deployment tryspeak --port=80 --target-port=5000 --type=LoadBalancer

# Set environment variables
kubectl create secret generic tryspeak-env --from-env-file=.env
kubectl set env deployment/tryspeak --from=secret/tryspeak-env

# Scale
kubectl scale deployment tryspeak --replicas=3
```

---

## Database Setup

### Using Cloud CockroachDB (Recommended)
1. Sign up at cockroachlabs.cloud
2. Create free cluster
3. Get connection string
4. Add to .env: `DATABASE_URL=...`

### Using Docker CockroachDB (Development)
Already included in docker-compose.yml

```bash
# Access database
docker exec -it tryspeak-db ./cockroach sql --insecure

# Create database
CREATE DATABASE tryspeak;

# Tables are created automatically by app
```

---

## Environment Variables

**Required in production:**
```bash
# Database
DATABASE_URL=postgresql://...

# Auth0
AUTH0_DOMAIN=...
AUTH0_CLIENT_ID=...
AUTH0_CLIENT_SECRET=...
AUTH0_AUDIENCE=...

# Stripe
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PUBLISHABLE_KEY=pk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_ID=price_...

# VAPI
VAPI_API_KEY=...
VAPI_ONBOARDING_PHONE=...

# Twilio
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_PHONE_NUMBER=...

# App
BACKEND_URL=https://tryspeak.com
SECRET_KEY=random-64-char-string
```

---

## SSL/HTTPS

### Cloud Run / Cloud Platform
HTTPS automatic ✅

### VPS with Nginx + Let's Encrypt

```nginx
# /etc/nginx/sites-available/tryspeak

server {
    listen 80;
    server_name tryspeak.com www.tryspeak.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name tryspeak.com www.tryspeak.com;

    ssl_certificate /etc/letsencrypt/live/tryspeak.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/tryspeak.com/privkey.pem;

    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
# Install certbot
sudo apt-get install certbot python3-certbot-nginx

# Get certificate
sudo certbot --nginx -d tryspeak.com -d www.tryspeak.com

# Auto-renewal (already set up by certbot)
```

---

## Monitoring

### Health Check
```bash
curl http://localhost:5000/health
```

### View Logs
```bash
# Docker Compose
docker-compose logs -f app

# Single Container
docker logs -f tryspeak

# Last 100 lines
docker logs --tail 100 tryspeak
```

### Container Stats
```bash
docker stats tryspeak
```

---

## Backup & Recovery

### Backup Database
```bash
# CockroachDB backup
docker exec tryspeak-db ./cockroach dump tryspeak --insecure > backup.sql

# Restore
docker exec -i tryspeak-db ./cockroach sql --insecure < backup.sql
```

### Backup .env
```bash
# Store securely (NOT in git)
cp .env .env.backup
```

---

## Scaling

### Horizontal Scaling (Multiple Instances)

```bash
# Docker Compose
docker-compose up --scale app=3

# Kubernetes
kubectl scale deployment tryspeak --replicas=5
```

### Vertical Scaling (More Resources)

```bash
# Update docker-compose.yml
services:
  app:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
```

---

## Troubleshooting

### App won't start
```bash
# Check logs
docker logs tryspeak

# Check environment variables
docker exec tryspeak env | grep DATABASE_URL

# Test database connection
docker exec tryspeak python -c "from services.cockroachdb_service import DB; print('OK')"
```

### Port already in use
```bash
# Find process
lsof -i :5000

# Kill it
kill -9 <PID>

# Or use different port
docker run -p 8000:5000 ...
```

### Database connection failed
```bash
# Check database is running
docker ps | grep db

# Check connection string
echo $DATABASE_URL

# Test connection
psql $DATABASE_URL
```

---

## Security Checklist

- [ ] Use HTTPS (SSL certificate)
- [ ] Set strong SECRET_KEY
- [ ] Use environment variables (never commit .env)
- [ ] Run as non-root user (already configured)
- [ ] Keep Docker images updated
- [ ] Enable firewall
- [ ] Use private network for database
- [ ] Regular backups
- [ ] Monitor logs for suspicious activity

---

## Performance Tips

1. **Use production WSGI server** (already using gunicorn)
2. **Enable gzip compression**
3. **Use CDN for static files** (Cloudflare)
4. **Database connection pooling** (configured)
5. **Cache API responses** (Redis optional)
6. **Load balancer** (if > 1000 users)

---

## Cost Estimation

### Google Cloud Run (Recommended)
- **0-100 users:** $0-10/month
- **100-500 users:** $20-50/month
- **500-1000 users:** $50-100/month

### DigitalOcean Droplet
- **Basic:** $6/month (1GB RAM)
- **Standard:** $12/month (2GB RAM)
- **Performance:** $24/month (4GB RAM)

### AWS ECS
- **Similar to Cloud Run**

---

## Questions?

**Docker Docs:** https://docs.docker.com  
**Google Cloud Run:** https://cloud.google.com/run/docs  
**CockroachDB Cloud:** https://cockroachlabs.cloud
