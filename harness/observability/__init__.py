"""
Observability module — structured JSON logging, correlation IDs, RED metrics.

Re-exports the public API from logging.py for convenient access.
"""

from harness.observability.logging import (
    setup_structured_logging,
    set_trace_context,
    generate_correlation_id,
    generate_trace_id,
    generate_span_id,
    with_observability,
    log_metrics,
    reset_metrics,
)

__all__ = [
    "setup_structured_logging",
    "set_trace_context",
    "generate_correlation_id",
    "generate_trace_id",
    "generate_span_id",
    "with_observability",
    "log_metrics",
    "reset_metrics",
]
