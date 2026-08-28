# ADR 0056: Deduplicación Keep-Last-Per-Prompt en Observabilidad

## Estado
Aplicado | Implementado en `harness/observability/session_replay.py` (`dedupe_keep_last`) | Propietario: @coordinator

## Contexto
Agent Lightning v1.0 (Microsoft Research, arXiv 2608.17528) encontró que en pipelines agénticos
con reintentos, **las llamadas LLM repetidas con prompt idéntico contaminan los datos de
entrenamiento y las métricas**: cada reintento registra el mismo prompt múltiples veces. Su
solución operativa: endpoints idempotentes y, al registrar eventos, **conservar solo la última
llamada por prompt** (keep-last-per-prompt).

En SWARMIND, `SessionReplay.replay()` reconstruye todos los eventos del log incluyendo reintentos:
si un agente reintentó una llamada 3 veces, el replay muestra 3 eventos idénticos, inflando
métricas de tokens/costos y ensuciando el contexto exportado a Markdown/JSON.

## Decisión
Añadir la función pura `dedupe_keep_last(events)` a `session_replay.py`:

- Agrupa eventos por clave `(role, content)` y conserva **solo la última ocurrencia** de cada grupo.
- Preserva el orden cronológico de los eventos restantes (estable).
- Es una función pura sobre la salida de `replay()`: no muta el log ni cambia el contrato
  existente de `replay/export_markdown/export_json`.

## Consecuencias
### Positivas
- Métricas de tokens/costos por sesión sin inflación por reintentos.
- Contexto exportado limpio para re-uso como prompt (Cache-Shape friendly).
- Cero riesgo de regresión: función aditiva, API existente intacta.

### Negativas
- Pierde la traza de reintentos (para auditoría de fallos usar `replay()` sin dedup — ambos
  accesos quedan disponibles).

## Alternatives Considered
1. **Dedup dentro de `replay()` con flag default True**: cambia el contrato existente y rompe
   auditoría de reintentos; se prefiere composición explícita.
2. **Dedup por hash de contenido completo**: innecesario; `(role, content)` captura el caso
   documentado (mismo prompt reintentado) sin ambigüedad.

## Relacionado
- ADR 0048: Optimización Profunda de Tokens (Token Economics)
- Agent Lightning v1.0 §3.2 (01_search_frontier)
