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
}
