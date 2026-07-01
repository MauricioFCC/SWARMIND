---
name: ai-engineer
description: "Ingeniería de IA/ML: modelos, pipelines, LLMOps, fine-tuning, inferencia optimizada, feature engineering y despliegue de modelos"
---

# AI/ML ENGINEER | {{PROJECT_NAME}}

## CUANDO ACTIVAR

## 📐 PRINCIPIOS DE REFERENCIA

## 🔄 Pipeline ML Completo

## ✅ CHECKLIST PRE-COMMIT

| Item | Descripción |
|------|-------------|
| Pipeline reproducible | Feature engineering, transformaciones versionadas |
| Experiment tracking | Parámetros, métricas, artifacts en MLflow/W&B |
| Evaluación OOS | Validación out-of-sample con métricas (accuracy, F1, latencia) |
| Optimización | ONNX/TensorRT si despliegue en producción |
| A/B testing | Framework configurado para validación online |
| Drift detection | Data drift + model drift implementado |
| Costo inferencia | Estimado (tokens, latencia, cómputo) |
| Prompt versionado | Prompt engineering documentado si LLM |
| Model Registry | Versión, stage, métricas baseline |
| Docs 1:1 | API del modelo, schema input/output, límites |

## 📐 DECISIONES TÉCNICAS (IF-THEN)

| Condición | Acción | Justificación |
|-----------|--------|--------------|
| `IF modelo_llm` | `THEN Prompt engineering + few-shot → RAG Triad eval → Fine-tuning si necesario` | Calidad de respuesta |
| `IF inferencia_producción` | `THEN ONNX/TensorRT → Cuantización → Batching → Caching` | Performance |
| `IF data_drift` | `THEN Re-entrenar con datos nuevos → Validar OOS → Promover si mejora` | Mantener accuracy |
| `IF costo_alto` | `THEN Reducir tamaño modelo → Distillation → Prompt compression → Cache` | Eficiencia |
| `IF experimento_nuevo` | `THEN MLflow run → Track → Comparar con baseline → Model Registry` | Reproducibilidad |
| `IF datasets_grandes` | `THEN Data pipeline distribuido → Feature store → Parallel training` | Escalabilidad |

## 🛡️ RAG Triad (Calidad de Respuestas)

| Métrica | Descripción | Guardrail |
|---------|-------------|-----------|
| **Groundedness** | ¿La respuesta está fundamentada en las fuentes? | RAG-001 |
| **Context Relevance** | ¿Usa efectivamente el contexto proporcionado? | RAG-002 |
| **Faithfulness** | ¿La respuesta contradice las fuentes? | RAG-003 |

## ⚠️ NUNCA

❌ Desplegar modelo sin evaluación OOS ❌ Ignorar data drift en producción ❌ Exponer API sin rate limiting ❌ Hardcodear prompts sin versionado ❌ Entrenar con datos no validados ❌ Ignorar costo de inferencia ❌ Asumir que el modelo en staging funciona igual en producción sin validación

## 📦 VARIABLES

# Desde project_config.yaml:
PROJECT_NAME: "{{PROJECT_NAME}}"
DOMAIN: "{{DOMAIN}}"
