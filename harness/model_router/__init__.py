"""
Model Router — Hybrid local/cloud model routing for agent tasks.
Routes simple tasks to local Ollama models, complex tasks to cloud APIs.
"""

from .router import ModelRouter, RoutingDecision

__all__ = ["ModelRouter", "RoutingDecision"]
