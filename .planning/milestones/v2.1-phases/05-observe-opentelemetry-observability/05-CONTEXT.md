# Phase 5: OBSERVE — OpenTelemetry Observability - Context

**Gathered:** 2026-07-19
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — smart discuss skipped)

<domain>
## Phase Boundary

FastAPI and core library emit OpenTelemetry traces with Prometheus-exposed business metrics.

Requirements: OBSERVE-01, OBSERVE-02

Success criteria:
1. FastAPI endpoints emit OpenTelemetry traces with request-scoped span context
2. Business metrics (chip count, queries/sec, vendor distribution) exposed at /metrics Prometheus endpoint
3. Health endpoint (/health) is excluded from tracing to avoid noise
4. OTel overhead under 5% (verified by before/after benchmark)
</domain>

<decisions>
## Implementation Decisions

### the agent's Discretion
All implementation choices are at the agent's discretion — pure infrastructure phase.

### Key constraints
- OpenTelemetry SDK + API for tracing
- Prometheus client for business metrics (separate from OTel metrics)
- Auto-instrumentation for FastAPI via opentelemetry-instrumentation-fastapi
- Health endpoint excluded from tracing
- OTel overhead benchmark-verified under 5%
</decisions>

<code_context>
## Existing Code Insights

### Key Files
- `api/main.py` — FastAPI app, middleware, all endpoints
- `src/soc_db/config.py` — settings
- `tests/integration/test_api.py` — API tests

### Current Observability
- Structured JSON logging (log_config.py)
- Request ID middleware
- Duration logging per request
- Simple /metrics endpoint (uptime, requests, rps, chips_cached)
</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase.

Key constraints:
- OTel auto-instrumentation for FastAPI + uvicorn
- Prometheus /metrics for business metrics only
- No OTLP exporter until a collector is deployed (research recommendation)
- All existing tests must pass
- GitHub Pages must NOT be touched</specifics>

<deferred>
## Deferred Ideas

- OTLP exporter + collector deployment — v2.2+
- Jaeger/Tempo backend — v2.2+
</deferred>
