# SEO Maturity Grader - Operations Checklist

This checklist covers everything needed to deploy and operate the SEO Maturity Grader in production.

---

## 1. API Keys & Configuration

### Required for Full Functionality

| Service | Env Variable | Free Tier | Annual Cost (Paid) | Setup URL |
|---------|-------------|-----------|-------------------|-----------|
| Google PageSpeed Insights | `PAGESPEED_API_KEY` | ✅ 25K queries/day | Free | [console.cloud.google.com](https://console.cloud.google.com/apis/credentials) |
| SerpApi | `SERPAPI_KEY` | ✅ 100 searches/month | $50/month | [serpapi.com](https://serpapi.com/manage-api-key) |

### Optional Enhancements

| Service | Env Variable(s) | Purpose | Cost |
|---------|----------------|---------|------|
| Google Custom Search | `GCS_API_KEY`, `GCS_CX` | Alternative SERP (100/day free) | Free tier |
| WHOISXML API | `WHOISXML_API_KEY` | Accurate domain age | $29/month |
| Moz API | `MOZ_ACCESS_ID`, `MOZ_SECRET_KEY` | Domain Authority | $99/month |
| Ahrefs API | `AHREFS_API_KEY` | Domain Rating | Enterprise |
| Majestic API | `MAJESTIC_API_KEY` | Trust Flow | $49/month |

### Minimum Viable Setup

```bash
# Minimum: Only PageSpeed (free, recommended)
PAGESPEED_API_KEY=your_key_here

# Ideal: PageSpeed + SerpApi
PAGESPEED_API_KEY=your_pagespeed_key
SERPAPI_KEY=your_serpapi_key
```

---

## 2. Quotas & Rate Limits

### External API Limits

| Service | Default Quota | Our Rate Limit | Notes |
|---------|--------------|----------------|-------|
| PageSpeed API | 25,000/day (free) | 1 req/sec | Bursting allowed |
| SerpApi | 100/month (free) | 1 req/sec | Consider paid tier |
| Google Custom Search | 100/day (free) | 1 req/sec | Very limited |
| WHOISXML | 500/month (free) | 1 req/sec | Cache heavily |

### Internal Rate Limiting

The backend implements:
- **Per-origin rate limiting**: 1 request/second to each external API
- **Exponential backoff**: On 5xx errors, retry with delays (1s → 2s → 4s)
- **Max retries**: 3 attempts before failing
- **Request timeout**: 10 seconds hard limit

---

## 3. Caching Strategy

### Cache Settings

```python
CACHE_TTL_SECONDS = 21600  # 6 hours
CACHE_MAX_SIZE = 1000      # items
```

### What Gets Cached

| Data Type | Cache Key | TTL | Notes |
|-----------|-----------|-----|-------|
| PageSpeed metrics | URL (normalized) | 6 hours | CWV data is fairly stable |
| SERP rankings | domain + keyword | 6 hours | Rankings change slowly |
| WHOIS data | domain | 6 hours | Domain age doesn't change |
| Authority metrics | domain | 6 hours | DA changes slowly |
| On-page analysis | URL | 6 hours | Content changes rarely |

### Cache Invalidation

Currently in-memory only. For production with multiple instances:
- Consider Redis for shared caching
- Implement cache-aside pattern

---

## 4. Monitoring Endpoints

### Health Check

```bash
# Basic health check
curl http://localhost:8000/seo/grader/health

# Expected response:
{
  "status": "healthy",
  "version": "1.0.0",
  "services": {
    "pagespeed": "configured",
    "serp": "configured",
    "whois": "fallback",
    "authority": "fallback"
  }
}
```

### Recommended Monitoring

1. **Uptime monitoring**: Ping `/seo/grader/health` every 30s
2. **Error rate**: Monitor 4xx and 5xx responses
3. **Latency**: Track P50, P95, P99 for `/seo/grader/submit`
4. **External API health**: Log adapter fallback usage

### Alerting Thresholds

| Metric | Warning | Critical |
|--------|---------|----------|
| Error rate (5xx) | > 1% | > 5% |
| P95 latency | > 10s | > 30s |
| Health check failures | 2 consecutive | 5 consecutive |

---

## 5. Security Checklist

### Input Validation
- [x] URL scheme validation (http/https only)
- [x] SSRF prevention (private IPs rejected)
- [x] Localhost rejection
- [x] Keyword length limits (80 chars)
- [x] Questionnaire value bounds (1-5)

### Network Security
- [ ] HTTPS only in production
- [ ] CORS configured for frontend origins only
- [ ] Rate limiting per client IP (consider adding)

### API Key Security
- [ ] Store keys in secrets manager (not env files in prod)
- [ ] Rotate API keys periodically
- [ ] Audit key usage

---

## 6. Deployment Checklist

### Pre-Deploy

- [ ] Set required environment variables
- [ ] Configure CORS_ORIGINS for production frontend URL
- [ ] Set DEBUG=false
- [ ] Verify API keys work

### Deploy

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the server
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Post-Deploy

- [ ] Verify health endpoint responds
- [ ] Test a sample grading request
- [ ] Check logs for errors
- [ ] Confirm external API connectivity

---

## 7. Scaling Considerations

### Current Limitations (V1)

- **In-memory cache**: Lost on restart, not shared across instances
- **No persistence**: No database, all stateless
- **Single instance**: No horizontal scaling without shared cache

### For Multi-Instance Deployment

1. Add Redis for shared caching:
   ```python
   # Future: Replace TTLCache with Redis
   REDIS_URL=redis://localhost:6379
   ```

2. Add distributed rate limiting:
   ```python
   # Future: Use Redis for rate limit state
   ```

3. Consider queue for heavy workloads:
   ```python
   # Future: Celery/RQ for async processing
   ```

---

## 8. Disaster Recovery

### Graceful Degradation

The system is designed to work with reduced functionality:

| Missing Service | Behavior |
|----------------|----------|
| PageSpeed API | Falls back to timing heuristics (marked "approximate") |
| SERP API | Returns 0 visibility (conservative) |
| WHOIS API | Uses python-whois library (less reliable) |
| Authority API | Uses heuristics (age + brand presence) |

### Recovery Steps

1. Check external API status pages
2. Verify API keys are valid and not rate-limited
3. Clear cache if stale data suspected
4. Roll back to previous version if code issue

---

## 9. Logging & Debugging

### Log Levels

```bash
# Production
DEBUG=false  # INFO level

# Development
DEBUG=true   # DEBUG level
```

### Key Log Points

- Request received with `client_request_id`
- Declared evaluation result
- Observed evaluation result  
- External API fallback usage
- Errors with full stack trace

### Example Log Output

```
2025-12-29 14:00:00 - main - INFO - Grader request received [request_id=abc-123]
2025-12-29 14:00:01 - pagespeed_adapter - DEBUG - PageSpeed API response for example.com
2025-12-29 14:00:02 - main - INFO - Grader complete: score=67, stage=Structured [request_id=abc-123]
```

---

## 10. Support Contacts

### External Service Support

- **Google Cloud Support**: [console.cloud.google.com/support](https://console.cloud.google.com/support)
- **SerpApi Support**: support@serpapi.com
- **WHOISXML Support**: support@whoisxmlapi.com
- **Moz Support**: help@moz.com
