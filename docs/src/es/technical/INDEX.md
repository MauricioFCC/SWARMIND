---
title: Manual Tecnico - Indice
description: Indice por capas de los modulos core del harness; manual completo y fichas tecnicas por modulo (orquestacion, memoria/RAG, QA, guardrails, modelo).
domain: "technical"
updated: 2026-10-12
toc: true
---

# Manual Tecnico - Indice

Mapa de la capa tecnica. Cada fila aisla la ficha de un modulo y responde una
pregunta concreta (progressive disclosure: el agente selecciona bajo demanda).

## Documentos

| Archivo | Que responde | Estado |
|---------|--------------|--------|
| [manual-tecnico.md](manual-tecnico.md) | Vision completa del harness: instalacion, arquitectura de modulos y operacion. | APLICADO |
| [multi_provider.md](multi_provider.md) | Como funciona el multi-API provider con failover entre OpenAI, Anthropic, Google, Mistral y DeepSeek. | APLICADO |
| [prompt_compressor.md](prompt_compressor.md) | Como comprime prompts el motor de 5 estrategias (extractiva, abstractiva, structured, system prompt, conversation). | APLICADO |
| [shared_cache.md](shared_cache.md) | Como funciona el cache semantico compartido entre agentes (LRU + TTL + embedding). | APLICADO |
| [event_bus.md](event_bus.md) | Como se comunican los agentes via Pub/Sub asincrono con canales y wildcards. | APLICADO |
| [speculative_decoder.md](speculative_decoder.md) | Como acelera la generacion LLM 2-5x con decodificacion especulativa drafter+verifier. | APLICADO |
| [kv_cache_sharing.md](kv_cache_sharing.md) | Como se comparte el KV cache entre agentes secuenciales para evitar recomputacion. | APLICADO |
| [a2a_protocol.md](a2a_protocol.md) | Como se comunican los agentes con el protocolo A2A v1.0 estandarizado. | APLICADO |
| [got_planner.md](got_planner.md) | Como razona multi-paso el Graph-of-Thought planner y sus 5 estrategias de expansion. | APLICADO |
| [io_fusion.md](io_fusion.md) | Como reduce round-trips a backends vectoriales con I/O Fusion batch. | APLICADO |
| [adaptive_pool.md](adaptive_pool.md) | Como auto-escala el worker pool segun CPU y memoria. | APLICADO |
| [pipeline_macu.md](pipeline_macu.md) | Como ejecuta el pipeline DAG con replanning continuo (MACU). | APLICADO |
| [guardrail_engine.md](guardrail_engine.md) | Como aplica los guardrails de 5 capas (Input, Output, Content, Tool, Policy). | APLICADO |
| [eval_factory.md](eval_factory.md) | Como evalua LLM, RAG, Agent y MCP con el framework de 7 dimensiones. | APLICADO |
| [factory.md](factory.md) | Como orquesta el AI Factory Stack de 7 capas el pipeline completo. | APLICADO |
| [predictor.md](predictor.md) | Como predice fallos el L1 FailurePredictor con datos historicos. | APLICADO |
| [detector.md](detector.md) | Como detecta anomalias en ejecuciones el L2 VisualAnomalyDetector. | APLICADO |
| [generator.md](generator.md) | Como genera casos de test el L3 TestCaseGenerator con guardrails anti-alucinacion. | APLICADO |
| [agent.md](agent.md) | Como ejecuta tests de forma autonoma el L4 AutonomousTestAgent con MCP. | APLICADO |
| [orchestrator.md](orchestrator.md) | Como orquesta la calidad extremo a extremo el L5 QAOrchestrator. | APLICADO |

## Navegacion

- Padre: [README de docs ES](../README.md)
- Arquitectura de coordinacion: [Swiss Watch](../architecture/swiss-watch.md)
- API autogenerada del paquete `harness`: [Indice API](../api/README.md)
