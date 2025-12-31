# SEO Maturity Grader Backend

A production-quality, deterministic SEO maturity scoring API built with FastAPI.

**🆓 FREE MODE**: This backend uses only FREE APIs. No paid subscriptions required!

## Quick Start

### 1. Install Dependencies

```bash
cd seo-maturity-grader-backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment Variables (Optional)

Create a `.env` file for better accuracy (optional but recommended):

```bash
# PageSpeed Insights API (FREE - 25,000 queries/day)
PAGESPEED_API_KEY=your_pagespeed_key_here
```

**Without the API key**, the grader still works using fallback heuristics.

### 3. Run the Server

```bash
# Development mode with auto-reload
uvicorn main:app --reload

# Production mode
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 4. Test the API

```bash
curl http://localhost:8000/seo/grader/health
```

---

## Environment Variables

| Variable | Required | Cost | Description |
|----------|----------|------|-------------|
| `PAGESPEED_API_KEY` | Optional | **FREE** | Google PageSpeed Insights API key (25K queries/day) |
| `DEBUG` | Optional | - | Enable debug logging |
| `CORS_ORIGINS` | Optional | - | Allowed CORS origins (default: localhost) |

### Getting Your Free PageSpeed API Key

1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Create a new project (or use existing)
3. Search for "PageSpeed Insights API" and enable it
4. Go to **Credentials** → **Create Credentials** → **API Key**
5. Copy the key to your `.env` file

**Note**: All other SEO metrics (SERP visibility, domain age, authority) are calculated using built-in fallback heuristics at **no cost**.

---

## API Reference

### POST /seo/grader/submit

Submit a website for SEO maturity grading.

**Request:**

```json
{
  "website_url": "https://example.com",
  "brand_category": "SaaS",
  "target_keywords": ["seo automation", "rank tracking"],
  "questionnaire_answers": {
    "T1": 4, "T2": 3, "T3": 5, "T4": 3,
    "C1": 4, "C2": 3, "C3": 2, "C4": 3,
    "M1": 2, "M2": 3
  },
  "client_request_id": "optional-uuid-for-tracing"
}
```

**Response:**

```json
{
  "total_score": 67,
  "stage": "Structured",
  "questionnaire_score": 32,
  "observed_score": 35,
  "dimension_scores": {
    "declared": {
      "technical": 15,
      "content_keywords": 12,
      "measurement": 5
    },
    "observed": {
      "core_web_vitals": 14,
      "onpage": 10,
      "authority_proxies": 6,
      "serp_reality": 5
    }
  },
  "declared_vs_observed_gap": "Minimal — declared and observed capabilities are well-aligned",
  "top_risks": [
    "Core Web Vitals inconsistent for key landing pages",
    "Low observed SERP presence for declared keywords",
    "Insufficient visible high-quality referring domains"
  ],
  "raw_signals_summary": {
    "lcp_ms": 3200,
    "cls": 0.12,
    "inp_ms": 240,
    "title_present": true,
    "meta_unique": false,
    "h1_present": true,
    "domain_age_years": 2,
    "referring_domains_estimate": null,
    "serp_hits_top10": 0,
    "serp_hits_top30": 1
  },
  "notes": "Core Web Vitals from PageSpeed Insights API; Authority estimated from domain age and heuristics (approximate); SERP data from SERPAPI.",
  "generated_at": "2025-12-29T14:00:00+05:30"
}
```

### GET /seo/grader/health

Check API health and service configuration.

**Response:**

```json
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

---

## Scoring Model

### Questionnaire Component (50 points)

| Dimension | Questions | Weight |
|-----------|-----------|--------|
| Technical SEO | T1, T2, T3, T4 | 20 points |
| Content & Keywords | C1, C2, C3, C4 | 20 points |
| Measurement & Analytics | M1, M2 | 10 points |

### Observed Component (50 points)

| Bucket | Weight | Data Source |
|--------|--------|-------------|
| Core Web Vitals | 20 points | PageSpeed Insights API |
| On-page SEO | 15 points | HTML parsing |
| Authority Proxies | 10 points | Moz/fallback heuristics |
| SERP Reality | 5 points | SerpApi/GCS |

### Stage Mapping

| Score Range | Stage |
|-------------|-------|
| 0-30 | Chaotic |
| 31-50 | Reactive |
| 51-70 | Structured |
| 71-85 | Optimised |
| 86-100 | Strategic |

---

## Example curl Request

```bash
curl -X POST http://localhost:8000/seo/grader/submit \
  -H "Content-Type: application/json" \
  -d '{
    "website_url": "https://example.com",
    "brand_category": "SaaS",
    "target_keywords": ["seo automation"],
    "questionnaire_answers": {
      "T1": 4, "T2": 3, "T3": 5, "T4": 3,
      "C1": 4, "C2": 3, "C3": 2, "C4": 3,
      "M1": 2, "M2": 3
    }
  }'
```

---

## Running Tests

```bash
# Install test dependencies
pip install -r requirements.txt

# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=. --cov-report=term-missing

# Run specific test file
pytest tests/test_scoring.py -v
```

---

## Limitations & Known Caveats

1. **Deterministic Scoring**: All scoring is deterministic. Same inputs always produce same outputs.

2. **Approximate Metrics**: When API keys are not configured:
   - Core Web Vitals are estimated from response timing
   - Authority is estimated from domain age and heuristics
   - SERP visibility returns 0 (conservative)

3. **Stateless V1**: No database. All data is ephemeral.
   - Cache is in-memory only
   - No history tracking
   - Each request is independent

4. **Rate Limits**: External APIs have quotas:
   - PageSpeed: 25K/day (free)
   - SerpApi: 100/month (free)
   - Monitor usage in production

5. **Security**: 
   - SSRF prevention blocks localhost and private IPs
   - URL validation enforces http/https only
   - HTTP URLs allowed but generate warnings

---

## Project Structure

```
seo-maturity-grader-backend/
├── main.py                 # FastAPI application
├── config.py              # Environment configuration
├── requirements.txt       # Python dependencies
├── README.md              # This file
├── OPS_CHECKLIST.md       # Operations guide
├── models/
│   ├── __init__.py
│   ├── schemas.py         # Pydantic models
│   └── enums.py           # Constants
├── evaluators/
│   ├── __init__.py
│   ├── declared_evaluator.py    # Questionnaire scoring
│   ├── observed_evaluator.py    # Website analysis
│   └── scoring.py               # Final computation
├── adapters/
│   ├── __init__.py
│   ├── pagespeed_adapter.py     # PageSpeed API
│   ├── serp_adapter.py          # SERP APIs
│   ├── whois_adapter.py         # Domain age
│   └── authority_adapter.py     # Moz/Ahrefs
├── utils/
│   ├── __init__.py
│   ├── url_validator.py         # SSRF prevention
│   ├── cache.py                 # LRU cache
│   ├── rate_limiter.py          # Rate limiting
│   └── rounding.py              # Deterministic math
└── tests/
    ├── __init__.py
    ├── test_scoring.py          # Scoring tests
    ├── test_url_validation.py   # Validation tests
    └── test_integration.py      # Integration tests
```

---

## License

Internal use only. See TDSC licensing terms.
