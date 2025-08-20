# Redis Configuration Fix

## Problem
The WAHA (WhatsApp HTTP API) service was failing with Redis connection errors:
```
Error: connect ECONNREFUSED 127.0.0.1:6379
[Redis] Connection failed: MaxRetriesPerRequestError
```

## Solution
Added Redis service to `docker-compose.yaml` with proper configuration:

### Changes Made:
1. **Added Redis service** with persistent storage
2. **Configured WAHA** to use Redis via `REDIS_URL` environment variable  
3. **Added dependency** so WAHA starts after Redis
4. **Updated .gitignore** to exclude Redis data directory

### Redis Service Configuration:
- **Image**: `redis:7-alpine` (lightweight, stable)
- **Persistence**: Enabled with `--appendonly yes`
- **Storage**: `./redis-data:/data` volume mount
- **Port**: 6379 (standard Redis port)

### WAHA Integration:
- **Environment Variable**: `REDIS_URL=redis://redis:6379`
- **Service Dependency**: `depends_on: redis`

## Usage
```bash
# Start all services (includes Redis)
docker compose up

# Start Redis only
docker compose up redis -d

# Check Redis connection
docker compose exec redis redis-cli ping
```

This fix resolves the Redis connection errors and ensures WAHA has proper session storage.