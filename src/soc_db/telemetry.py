from __future__ import annotations

from fastapi import FastAPI
from opentelemetry import metrics, trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from prometheus_client import Counter, Gauge, Histogram

from soc_db import __version__

_resource = Resource.create({
    "service.name": "soc-db",
    "service.version": __version__,
})

_tracer: trace.Tracer | None = None
_meter: metrics.Meter | None = None

chips_total = Gauge("soc_db_chips_total", "Total number of chips in database")
requests_total = Counter("soc_db_requests_total", "Total HTTP requests", ["method", "path", "status"])
requests_in_flight = Gauge("soc_db_requests_in_flight", "Current requests being processed")
request_duration_seconds = Histogram(
    "soc_db_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path", "status"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0),
)
vendor_distribution = Gauge("soc_db_vendor_chips", "Chip count per vendor", ["vendor"])


def setup_telemetry() -> None:
    tracer_provider = TracerProvider(resource=_resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(tracer_provider)

    meter_provider = MeterProvider(resource=_resource)
    metrics.set_meter_provider(meter_provider)

    global _tracer, _meter
    _tracer = trace.get_tracer("soc-db", __version__)
    _meter = metrics.get_meter("soc-db", __version__)


def instrument_app(app: FastAPI) -> None:
    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=trace.get_tracer_provider(),
        excluded_urls="/health,/metrics",
    )


def get_tracer() -> trace.Tracer:
    if _tracer is None:
        raise RuntimeError("Telemetry not initialized — call setup_telemetry() first")
    return _tracer


def get_meter() -> metrics.Meter:
    if _meter is None:
        raise RuntimeError("Telemetry not initialized — call setup_telemetry() first")
    return _meter


def update_vendor_metrics(chips: list[dict]) -> None:
    vendor_counts: dict[str, int] = {}
    for c in chips:
        v = c.get("vendor", "Unknown")
        vendor_counts[v] = vendor_counts.get(v, 0) + 1
    for vname, count in vendor_counts.items():
        vendor_distribution.labels(vendor=vname).set(count)
    chips_total.set(len(chips))
