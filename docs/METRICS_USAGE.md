# Metrics Usage Guide

## Overview

The SEM Agent uses Prometheus metrics for monitoring system performance and business metrics. All metrics are exposed at the `/metrics` endpoint in Prometheus text format.

## Available Metrics

### Counters

#### `sem_reports_generated_total`
Tracks the total number of reports generated.

**Labels:**
- `tenant_id`: Tenant identifier
- `report_type`: Type of report (e.g., 'weekly', 'monthly', 'daily')

**Usage:**
```python
from app.core.metrics import track_report_generation

track_report_generation(report_type="weekly", tenant_id="tenant-123")
```

#### `sem_keywords_detected_total`
Tracks the total number of inefficient keywords detected.

**Labels:**
- `tenant_id`: Tenant identifier

**Usage:**
```python
from app.core.metrics import track_keyword_detection

# Single keyword
track_keyword_detection(tenant_id="tenant-123")

# Multiple keywords
track_keyword_detection(tenant_id="tenant-123", count=5)
```

#### `sem_approvals_processed_total`
Tracks approval decision outcomes.

**Labels:**
- `tenant_id`: Tenant identifier
- `decision`: Approval decision ('approved', 'rejected', 'expired')

**Usage:**
```python
from app.core.metrics import track_approval_decision

track_approval_decision(tenant_id="tenant-123", decision="approved")
```

### Histograms

#### `sem_report_generation_seconds`
Measures the duration of report generation operations.

**Labels:**
- `report_type`: Type of report being generated

**Buckets:** 0.5s, 1s, 2.5s, 5s, 10s, 30s, 60s, 120s, 300s

**Usage with context manager:**
```python
from app.core.metrics import track_report_generation_time

with track_report_generation_time("weekly"):
    # Generate report
    report = generate_weekly_report(tenant_id="tenant-123")
```

#### `sem_gemini_latency_seconds`
Measures Gemini API response times.

**Labels:**
- `model`: Gemini model name (e.g., 'gemini-2.0-flash-exp')

**Buckets:** 0.1s, 0.25s, 0.5s, 1s, 2.5s, 5s, 10s, 30s

**Usage with context manager:**
```python
from app.core.metrics import track_gemini_latency

with track_gemini_latency("gemini-2.0-flash-exp"):
    response = await gemini_client.generate_content(prompt)
```

**Usage with decorator:**
```python
from app.core.metrics import track_latency, gemini_latency

@track_latency(gemini_latency, "gemini-2.0-flash-exp")
async def call_gemini_api(prompt: str):
    return await gemini_client.generate_content(prompt)
```

#### `sem_google_ads_api_latency_seconds`
Measures Google Ads API response times.

**Labels:**
- `operation`: API operation name (e.g., 'search_keywords', 'update_campaign', 'get_performance')

**Buckets:** 0.1s, 0.25s, 0.5s, 1s, 2.5s, 5s, 10s, 30s

**Usage with context manager:**
```python
from app.core.metrics import track_google_ads_latency

with track_google_ads_latency("search_keywords"):
    keywords = await google_ads_client.search_keywords(customer_id)
```

### Gauges

#### `sem_active_tenants`
Current number of active tenants in the system.

**Usage:**
```python
from app.core.metrics import update_active_tenants_gauge
from app.api.deps import get_db

db = next(get_db())
update_active_tenants_gauge(db)
```

#### `sem_pending_approvals`
Current number of pending approval requests.

**Usage:**
```python
from app.core.metrics import update_pending_approvals_gauge
from app.api.deps import get_db

db = next(get_db())
update_pending_approvals_gauge(db)
```

**Update all gauges at once:**
```python
from app.core.metrics import update_all_gauges
from app.api.deps import get_db

db = next(get_db())
update_all_gauges(db)
```

## Complete Examples

### Example 1: Report Generation Service

```python
from app.core.metrics import (
    track_report_generation,
    track_report_generation_time,
    track_keyword_detection,
)

async def generate_weekly_report(tenant_id: str) -> dict:
    """Generate weekly report with metrics tracking."""

    # Track generation time
    with track_report_generation_time("weekly"):
        # Generate report
        report = await _generate_report_data(tenant_id)

        # Track keywords detected
        keyword_count = len(report["inefficient_keywords"])
        if keyword_count > 0:
            track_keyword_detection(tenant_id, count=keyword_count)

        # Track report generation
        track_report_generation(report_type="weekly", tenant_id=tenant_id)

    return report
```

### Example 2: Gemini API Service

```python
from app.core.metrics import track_gemini_latency

async def analyze_keywords_with_gemini(keywords: list[str]) -> dict:
    """Analyze keywords using Gemini API with latency tracking."""

    model_name = "gemini-2.0-flash-exp"

    with track_gemini_latency(model_name):
        prompt = create_keyword_analysis_prompt(keywords)
        response = await gemini_client.generate_content(prompt)
        result = parse_gemini_response(response)

    return result
```

### Example 3: Approval Processing

```python
from app.core.metrics import track_approval_decision

async def process_approval(approval_id: int, decision: str, db: Session) -> None:
    """Process approval with metrics tracking."""

    approval = db.query(Approval).filter(Approval.id == approval_id).first()

    if not approval:
        raise ValueError(f"Approval {approval_id} not found")

    # Update approval status
    if decision == "approve":
        approval.status = ApprovalStatus.APPROVED
        track_approval_decision(approval.tenant_id, decision="approved")
    elif decision == "reject":
        approval.status = ApprovalStatus.REJECTED
        track_approval_decision(approval.tenant_id, decision="rejected")

    db.commit()
```

### Example 4: Background Job for Gauge Updates

```python
from app.core.metrics import update_all_gauges
from app.api.deps import get_db
import asyncio

async def update_metrics_gauges():
    """Background job to update gauge metrics every 60 seconds."""

    while True:
        try:
            db = next(get_db())
            update_all_gauges(db)
            db.close()
        except Exception as e:
            logger.error(f"Error updating gauges: {e}")

        await asyncio.sleep(60)
```

## Accessing Metrics

### Local Development

```bash
curl http://localhost:8000/metrics
```

### Production

```bash
curl https://your-domain.com/metrics
```

### Sample Output

```
# HELP sem_reports_generated_total Total reports generated
# TYPE sem_reports_generated_total counter
sem_reports_generated_total{report_type="weekly",tenant_id="tenant-123"} 42.0

# HELP sem_keywords_detected_total Total inefficient keywords detected
# TYPE sem_keywords_detected_total counter
sem_keywords_detected_total{tenant_id="tenant-123"} 157.0

# HELP sem_approvals_processed_total Total approval decisions
# TYPE sem_approvals_processed_total counter
sem_approvals_processed_total{decision="approved",tenant_id="tenant-123"} 35.0
sem_approvals_processed_total{decision="rejected",tenant_id="tenant-123"} 7.0

# HELP sem_report_generation_seconds Report generation duration
# TYPE sem_report_generation_seconds histogram
sem_report_generation_seconds_bucket{le="0.5",report_type="weekly"} 0.0
sem_report_generation_seconds_bucket{le="1.0",report_type="weekly"} 2.0
sem_report_generation_seconds_bucket{le="2.5",report_type="weekly"} 15.0
sem_report_generation_seconds_sum{report_type="weekly"} 45.6
sem_report_generation_seconds_count{report_type="weekly"} 42.0

# HELP sem_active_tenants Number of active tenants
# TYPE sem_active_tenants gauge
sem_active_tenants 23.0

# HELP sem_pending_approvals Number of pending approval requests
# TYPE sem_pending_approvals gauge
sem_pending_approvals 8.0
```

## Prometheus Configuration

Add this to your `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'sem-agent'
    scrape_interval: 30s
    static_configs:
      - targets: ['localhost:8000']
```

## Grafana Dashboards

### Key Metrics to Monitor

1. **Report Generation Rate**: `rate(sem_reports_generated_total[5m])`
2. **Keyword Detection Rate**: `rate(sem_keywords_detected_total[5m])`
3. **Approval Rate**: `rate(sem_approvals_processed_total{decision="approved"}[5m])`
4. **API Latency P95**: `histogram_quantile(0.95, rate(sem_gemini_latency_seconds_bucket[5m]))`
5. **Active Tenants**: `sem_active_tenants`
6. **Pending Approvals**: `sem_pending_approvals`

### Alert Rules

```yaml
groups:
  - name: sem_agent_alerts
    rules:
      - alert: HighErrorRate
        expr: rate(sem_reports_generated_total[5m]) == 0
        for: 5m
        annotations:
          summary: "No reports generated in 5 minutes"

      - alert: HighPendingApprovals
        expr: sem_pending_approvals > 100
        for: 10m
        annotations:
          summary: "More than 100 pending approvals"

      - alert: HighAPILatency
        expr: histogram_quantile(0.95, rate(sem_gemini_latency_seconds_bucket[5m])) > 10
        for: 5m
        annotations:
          summary: "Gemini API P95 latency > 10s"
```

## Best Practices

1. **Always use context managers** for timing operations - they ensure metrics are recorded even if exceptions occur
2. **Use appropriate labels** - labels create separate time series, so use them judiciously
3. **Update gauges periodically** - Set up a background job to update gauge metrics every 60 seconds
4. **Don't block on metrics** - Metrics recording is fast, but use async where possible
5. **Label cardinality** - Avoid high-cardinality labels (like user IDs) - use tenant_id instead
6. **Histogram buckets** - Default buckets are tuned for typical operations; adjust if needed

## Testing

```python
import pytest
from app.core.metrics import (
    reports_generated,
    track_report_generation,
    track_report_generation_time,
)

def test_report_metrics():
    """Test report generation metrics."""
    initial = reports_generated.labels(
        tenant_id="test-tenant",
        report_type="weekly"
    )._value.get()

    track_report_generation(report_type="weekly", tenant_id="test-tenant")

    final = reports_generated.labels(
        tenant_id="test-tenant",
        report_type="weekly"
    )._value.get()

    assert final == initial + 1


def test_timing_metrics():
    """Test timing context manager."""
    from app.core.metrics import report_generation_time
    import time

    with track_report_generation_time("weekly"):
        time.sleep(0.1)

    # Check that histogram was updated
    # (In real tests, you'd use prometheus_client test utilities)
```
