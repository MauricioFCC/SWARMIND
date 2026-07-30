"""
Observability module — structured JSON logging, correlation IDs, RED metrics.

Re-exports the public API from logging.py for convenient access.
"""

from harness.observability.logging import (
    generate_correlation_id,
    generate_span_id,
    generate_trace_id,
    log_metrics,
    reset_metrics,
    set_trace_context,
    setup_structured_logging,
    with_observability,
)

__all__ = [
    "generate_correlation_id",
    "generate_span_id",
    "generate_trace_id",
    "log_metrics",
    "reset_metrics",
    "set_trace_context",
    "setup_structured_logging",
    "with_observability",
]
