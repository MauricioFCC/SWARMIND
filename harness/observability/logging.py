#!/usr/bin/env python3
"""
Structured logging utility for Swarmind with JSON format, correlation IDs,
and RED metrics (Rate, Errors, Duration).

Integrado desde observability_logging.py (raíz) → harness/observability/logging.py
para eliminar código muerto y unificar la configuración de logging.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Callable
from contextvars import ContextVar
from functools import wraps
from typing import Any

# Context variables for tracing
correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)
trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)
span_id_var: ContextVar[str | None] = ContextVar("span_id", default=None)

# Metrics storage (in production, this would go to a metrics backend like Prometheus)
_metrics: dict[str, Any] = {
    "request_count": 0,
    "error_count": 0,
    "total_duration": 0.0,
}


def setup_structured_logging(level: int = logging.INFO) -> None:
    """
    Configure structured JSON logging for the application.

    Args:
        level: Logging level (default: INFO)
    """
    class JSONFormatter(logging.Formatter):
        """Custom formatter that outputs JSON structured logs."""

        def format(self, record: logging.LogRecord) -> str:
            log_entry: dict[str, Any] = {
                "timestamp": self.formatTime(record, self.datefmt),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno,
            }

            # Add trace context if available
            corr_id = correlation_id_var.get()
            if corr_id:
                log_entry["correlation_id"] = corr_id

            trace_id = trace_id_var.get()
            if trace_id:
                log_entry["trace_id"] = trace_id

            span_id = span_id_var.get()
            if span_id:
                log_entry["span_id"] = span_id

            # Add exception info if present
            if record.exc_info:
                log_entry["exception"] = self.formatException(record.exc_info)

            # Add extra fields from record
            if hasattr(record, "extra_fields"):
                log_entry.update(record.extra_fields)  # type: ignore[arg-type]

            return json.dumps(log_entry, ensure_ascii=False)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add console handler with JSON formatter
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    root_logger.addHandler(handler)


def set_trace_context(
    correlation_id: str | None = None,
    trace_id: str | None = None,
    span_id: str | None = None,
) -> None:
    """
    Set trace context variables for the current execution context.

    Args:
        correlation_id: Correlation ID for grouping related operations
        trace_id: Trace ID for distributed tracing
        span_id: Span ID for the current operation
    """
    if correlation_id is not None:
        correlation_id_var.set(correlation_id)
    if trace_id is not None:
        trace_id_var.set(trace_id)
    if span_id is not None:
        span_id_var.set(span_id)


def generate_correlation_id() -> str:
    """Generate a new correlation ID."""
    return str(uuid.uuid4())


def generate_trace_id() -> str:
    """Generate a new trace ID."""
    return str(uuid.uuid4())


def generate_span_id() -> str:
    """Generate a new span ID."""
    return str(uuid.uuid4())


def with_observability(operation_name: str | None = None):
    """
    Decorator that adds observability (logging, metrics, tracing) to a function.

    Args:
        operation_name: Name of the operation (defaults to function name)

    Returns:
        Decorated function with observability
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Generate trace IDs for this operation
            corr_id = correlation_id_var.get() or generate_correlation_id()
            trace_id = trace_id_var.get() or generate_trace_id()
            span_id = generate_span_id()

            # Set trace context
            set_trace_context(correlation_id=corr_id, trace_id=trace_id, span_id=span_id)

            # Prepare operation name
            op_name = operation_name or f"{func.__module__}.{func.__name__}"

            # Start timing
            start_time = time.time()
            success = False

            try:
                # Log function entry
                logging.getLogger(func.__module__).info(
                    f"Starting operation: {op_name}",
                    extra={  # type: ignore[arg-type]
                        "extra_fields": {
                            "operation": op_name,
                            "operation_type": "start",
                            "args_count": len(args),
                            "kwargs_count": len(kwargs),
                        }
                    },
                )

                # Execute function
                result = func(*args, **kwargs)
                success = True
                return result

            except Exception as e:
                # Log exception
                logging.getLogger(func.__module__).exception(
                    f"Operation failed: {op_name}",
                    extra={  # type: ignore[arg-type]
                        "extra_fields": {
                            "operation": op_name,
                            "operation_type": "error",
                            "error_type": type(e).__name__,
                            "error_message": str(e),
                        }
                    },
                )
                raise

            finally:
                # Calculate duration and update metrics
                duration = time.time() - start_time
                _metrics["request_count"] += 1
                if not success:
                    _metrics["error_count"] += 1
                _metrics["total_duration"] += duration

                # Log function exit
                logging.getLogger(func.__module__).info(
                    f"Completed operation: {op_name}",
                    extra={  # type: ignore[arg-type]
                        "extra_fields": {
                            "operation": op_name,
                            "operation_type": "end",
                            "duration_seconds": duration,
                            "success": success,
                        }
                    },
                )

                # Clear trace context for this operation
                span_id_var.set(None)

        return wrapper
    return decorator


def log_metrics() -> dict[str, Any]:
    """
    Get current metrics values.

    Returns:
        Dictionary with current metrics
    """
    total_requests = _metrics["request_count"]
    error_rate = (_metrics["error_count"] / total_requests * 100) if total_requests > 0 else 0
    avg_duration = (_metrics["total_duration"] / total_requests) if total_requests > 0 else 0

    return {
        "request_count": _metrics["request_count"],
        "error_count": _metrics["error_count"],
        "error_rate_percent": round(error_rate, 2),
        "total_duration_seconds": round(_metrics["total_duration"], 2),
        "average_duration_seconds": round(avg_duration, 3),
        "requests_per_second": round(_metrics["request_count"] / max(_metrics["total_duration"], 1), 2),
    }


def reset_metrics() -> None:
    """Reset all metrics to zero."""
    global _metrics
    _metrics = {
        "request_count": 0,
        "error_count": 0,
        "total_duration": 0.0,
    }

