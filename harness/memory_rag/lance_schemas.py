"""
Schema definitions for LanceDB collections.
Extracted from lance_vector_store.py for file size compliance.
"""

# Default collections and their schemas
DEFAULT_COLLECTIONS = {
    "tasks_board": {
        "description": "Task assignments, statuses, and agent routing records",
        "schema": {
            "id": "string", "agent": "string", "task": "string",
            "status": "string", "vector": "list<float>",
            "metadata": "dict", "created_at": "string",
        },
    },
    "rag_chunks": {
        "description": "Knowledge chunks retrieved for RAG-enhanced inference",
        "schema": {
            "id": "string", "domain": "string", "chunk": "string",
            "vector": "list<float>", "metadata": "dict", "created_at": "string",
        },
    },
    "asi_cognition_store": {
        "description": "Lessons, insights, and cognition artifacts from evolve loops",
        "schema": {
            "id": "string", "title": "string", "content": "string",
            "domain": "string", "tags": "list<string>", "metrics": "dict",
            "vector": "list<float>", "created_at": "string",
        },
    },
    "agent_workspace_logs": {
        "description": "Message bus / Slack channels for inter-agent communication",
        "schema": {
            "id": "string", "channel": "string", "thread_id": "string",
            "from_agent": "string", "to_agent": "string", "message": "string",
            "message_type": "string", "status": "string", "task_id": "string",
            "iteration": "int", "attachments": "list<string>",
            "vector": "list<float>", "metadata": "dict", "created_at": "string",
        },
    },
    "procedural_skills": {
        "description": "Auto-generated procedural skills from successful multi-step tasks",
        "schema": {
            "id": "string", "name": "string", "domain": "string",
            "agent": "string", "trigger": "string", "steps_text": "string",
            "vector": "list<float>", "metadata": "dict", "created_at": "string",
        },
    },
    "prompt_evolution_log": {
        "description": "History of prompt mutations and promotions from the PromptEvolver",
        "schema": {
            "id": "string", "agent": "string", "mutation_type": "string",
            "test_task": "string", "tokens_before": "int", "tokens_after": "int",
            "success": "bool", "promoted": "bool", "timestamp": "string",
            "vector": "list<float>", "metadata": "dict", "created_at": "string",
        },
    },
    "scheduler_log": {
        "description": "Execution log for scheduled jobs",
        "schema": {
            "id": "string", "job_name": "string", "trigger": "string",
            "status": "string", "duration_ms": "int", "error": "string",
            "timestamp": "string", "vector": "list<float>",
            "metadata": "dict", "created_at": "string",
        },
    },
    "hitl_approval_log": {
        "description": "Human-in-the-Loop approval decisions for destructive actions",
        "schema": {
            "id": "string", "agent_role": "string", "action": "string",
            "approved": "bool", "user_feedback": "string",
            "auto_pilot_override": "bool",
            "vector": "list<float>", "metadata": "dict", "created_at": "string",
        },
    },
    "semantic_cache": {
        "description": "Semantic cache for LLM responses",
        "schema": {
            "prompt_hash": "string",
            "prompt_text_short": "string",
            "response": "string",
            "agent_role": "string",
            "hit_count": "int",
            "created_at": "string",
            "last_accessed": "string",
            "ttl_seconds": "int",
        },
    },
    "iteration_reports": {
        "description": "End-of-iteration pipeline reports",
        "schema": {
            "id": "string", "timestamp": "string", "bugs_found": "int",
            "bugs_fixed": "int", "bugs_needs_review": "int",
            "security_issues": "int", "secrets_found": "int",
            "docs_updated": "int", "docs_stale": "int",
            "token_input": "int", "token_output": "int",
            "costo_estimado": "float",
            "eficiencia": "string", "commit_message_suggested": "string",
            "files_changed": "string", "elapsed_seconds": "float",
            "vector": "list<float>",
        },
    },

    # =====================================================================
    # TELEMETRÍA Y KPIS — nuevas colecciones para tracking de rendimiento
    # =====================================================================

    "agent_performance": {
        "description": "Métricas de rendimiento por agente por sesión",
        "schema": {
            "id": "string",
            "session_id": "string",
            "agent_name": "string",
            "task": "string",
            "subtask_count": "int",
            "success_count": "int",
            "error_count": "int",
            "total_duration_ms": "float",
            "avg_latency_ms": "float",
            "success_rate": "float",
            "tokens_input": "int",
            "tokens_output": "int",
            "pipeline_type": "string",
            "complexity_score": "float",
            "vector": "list<float>",
            "metadata": "dict",
            "created_at": "string",
        },
    },
    "skill_effectiveness": {
        "description": "Efectividad de skills por dominio y agente",
        "schema": {
            "id": "string",
            "skill_name": "string",
            "domain": "string",
            "agent": "string",
            "use_count": "int",
            "success_rate": "float",
            "avg_duration_ms": "float",
            "avg_tokens_saved": "int",
            "promotion_count": "int",
            "last_used": "string",
            "vector": "list<float>",
            "metadata": "dict",
            "created_at": "string",
        },
    },
    "telemetry_events": {
        "description": "Eventos de telemetría estructurada del sistema",
        "schema": {
            "id": "string",
            "event_type": "string",
            "session_id": "string",
            "agent": "string",
            "level": "string",
            "message": "string",
            "duration_ms": "float",
            "status": "string",
            "tags": "list<string>",
            "vector": "list<float>",
            "metadata": "dict",
            "created_at": "string",
        },
    },
    "session_kpis": {
        "description": "KPIs agregados por sesión de ejecución",
        "schema": {
            "id": "string",
            "session_id": "string",
            "task": "string",
            "project": "string",
            "status": "string",
            "total_duration_ms": "float",
            "total_subtasks": "int",
            "total_errors": "int",
            "total_warnings": "int",
            "success_rate": "float",
            "levels_completed": "int",
            "agents_involved": "int",
            "pipeline_type": "string",
            "complexity": "string",
            "vector": "list<float>",
            "metadata": "dict",
            "created_at": "string",
            "updated_at": "string",
        },
    },
    "agent_interactions": {
        "description": "Registro de interacciones entre agentes para grafos de colaboración",
        "schema": {
            "id": "string",
            "session_id": "string",
            "from_agent": "string",
            "to_agent": "string",
            "message_type": "string",
            "subtask_id": "string",
            "duration_ms": "float",
            "success": "bool",
            "vector": "list<float>",
            "metadata": "dict",
            "created_at": "string",
        },
    },
}
