"""
LanceDB Migration — Lógica de migración de colecciones LanceDB.

Extraída de lance_vector_store.py para reducir el monolito.
Incluye:
  - _infer_schema_recursive(): inferencia recursiva de schema desde metadata
  - _sample_row_for_collection(): generación de filas sample para creación de tablas
  - Helpers de migración entre versiones de schema

Patrón RECURSIVO: _infer_schema_recursive() recorre dicts anidados recursivamente
para inferir tipos de datos, reemplazando ~100 líneas de if/elif anidados.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Recursive schema inference
# ---------------------------------------------------------------------------

def _infer_schema_recursive(metadata: Dict[str, Any], prefix: str = "") -> Dict[str, str]:
    """
    Infiere schema LanceDB recursivamente desde un dict de metadata.
    
    Reemplaza el approach anterior de if/elif anidados para cada colección.
    Recorre el dict recursivamente determinando tipos Python → tipos LanceDB.
    
    Args:
        metadata: Dict con datos de ejemplo para inferir tipos
        prefix: Prefijo para keys anidadas (usado en recursión)
    
    Returns:
        Dict[str, str] con field_name → type_string
    """
    schema: Dict[str, str] = {}
    
    for key, value in metadata.items():
        full_key = f"{prefix}.{key}" if prefix else key
        
        if isinstance(value, dict):
            # RECURSIVO: explorar sub-dicts
            schema.update(_infer_schema_recursive(value, full_key))
        elif isinstance(value, list):
            if value and isinstance(value[0], dict):
                # Lista de dicts → JSON string
                schema[full_key] = "string"
            elif value and isinstance(value[0], (int, float)):
                schema[full_key] = "string"  # JSON-encoded list
            else:
                schema[full_key] = "string"  # JSON-encoded list
        elif isinstance(value, bool):
            schema[full_key] = "boolean"
        elif isinstance(value, int):
            schema[full_key] = "int64"
        elif isinstance(value, float):
            schema[full_key] = "float64"
        else:
            schema[full_key] = "string"
    
    return schema


# ---------------------------------------------------------------------------
# Sample row generation (replaces _sample_row_for_collection)
# ---------------------------------------------------------------------------

# Mapa de campos específicos por colección (para crear schema completo)
_COLLECTION_SPECIFIC_FIELDS: Dict[str, Dict[str, Any]] = {
    "rag_chunks": {
        "source_file": "",
        "start_line": 0,
        "end_line": 0,
        "domain": "",
        "tipo_doc": "",
        "tags": "[]",  # JSON string
    },
    "asi_cognition_store": {
        "title": "",
        "content": "",
        "domain": "",
        "tags": "[]",
        "metrics": "{}",
        "access_count": 0,
        "last_accessed": "",
    },
    "agent_workspace_logs": {
        "channel": "",
        "thread_id": "",
        "from_agent": "",
        "to_agent": "",
        "message": "",
        "message_type": "",
        "status": "sent",
        "task_id": "",
        "iteration": 0,
        "attachments": "[]",
    },
    "tasks_board": {
        "title": "",
        "description": "",
        "agent_assigned": "",
        "status": "pending",
        "priority": 0,
        "updated_at": "",
        "transition_history": "[]",
    },
    "procedural_skills": {
        "name": "",
        "domain": "",
        "agent": "",
        "trigger": "",
        "steps_text": "",
    },
    "prompt_evolution_log": {
        "agent": "",
        "mutation_type": "",
        "test_task": "",
        "tokens_before": 0,
        "tokens_after": 0,
        "success": True,
        "promoted": False,
    },
    "scheduler_log": {
        "job_name": "",
        "trigger": "",
        "status": "",
        "duration_ms": 0,
        "error": "",
    },
    "hitl_approval_log": {
        "agent_role": "",
        "action": "",
        "approved": True,
        "user_feedback": "",
        "mode": "hitl",
    },
    "iteration_reports": {
        "id": "",
        "timestamp": "",
        "bugs_found": 0,
        "bugs_fixed": 0,
        "bugs_needs_review": 0,
        "security_issues": 0,
        "secrets_found": 0,
        "docs_updated": 0,
        "docs_stale": 0,
        "token_input": 0,
        "token_output": 0,
        "costo_estimado": 0.0,
        "eficiencia": "{}",
        "commit_message_suggested": "",
        "files_changed": "[]",
        "elapsed_seconds": 0.0,
    },
}


def generate_sample_row(collection_name: str) -> Dict[str, Any]:
    """
    Genera una fila sample con todas las columnas que una colección puede necesitar.
    
    Args:
        collection_name: Nombre de la colección
    
    Returns:
        Dict con campos base + específicos de la colección
    """
    now = datetime.now(timezone.utc).isoformat()
    dim = 384

    # Campos base comunes a todas las colecciones
    base: Dict[str, Any] = {
        "id": "init",
        "vector": [0.0] * dim,
        "metadata": "{}",
        "created_at": now,
    }

    # Campos específicos de la colección
    specific = _COLLECTION_SPECIFIC_FIELDS.get(collection_name, {})

    return {**base, **specific}


# ---------------------------------------------------------------------------
# Schema diff & migration helpers
# ---------------------------------------------------------------------------

def diff_schemas(old_schema: Dict[str, str], new_schema: Dict[str, str]) -> Dict[str, List[str]]:
    """
    Compara dos schemas y retorna diferencias.
    
    Args:
        old_schema: Schema actual
        new_schema: Schema deseado
    
    Returns:
        Dict con 'added', 'removed', 'changed' lists
    """
    old_keys = set(old_schema.keys())
    new_keys = set(new_schema.keys())
    
    return {
        "added": sorted(new_keys - old_keys),
        "removed": sorted(old_keys - new_keys),
        "changed": sorted(
            k for k in old_keys & new_keys if old_schema[k] != new_schema[k]
        ),
    }


def serialize_for_schema(value: Any) -> Any:
    """
    Convierte valores no-primitivos a strings JSON para compatibilidad con schema LanceDB.
    
    Dicts, lists-of-dicts y estructuras anidadas se serializan a JSON.
    """
    if isinstance(value, (dict, list)) and not isinstance(value, str):
        return json.dumps(value)
    return value


def adapt_vector(vec: Any, target_dim: int) -> Any:
    """
    Trunca o paddea un vector a una dimensión objetivo.
    
    Args:
        vec: Vector numpy o lista
        target_dim: Dimensión deseada
    
    Returns:
        Vector adaptado
    """
    import numpy as np
    v = np.array(vec, dtype=np.float32).flatten()
    current_dim = v.shape[0]
    if current_dim == target_dim:
        return v
    if current_dim > target_dim:
        return v[:target_dim]
    padded = np.zeros(target_dim, dtype=np.float32)
    padded[:current_dim] = v
    return padded
