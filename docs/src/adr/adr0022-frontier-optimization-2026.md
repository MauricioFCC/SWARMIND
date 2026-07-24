# ADR-0022: Frontier Optimization 2026 — Arquitectura, Testing y Estado del Arte

## Estado
**ACEPTADO** — Investigacion completada con 3 especialistas paralelos. Implementacion progresiva.

## Contexto
AGENTIC alcanzo 2213 tests, 29 skills (100% minificados), 8 agentes, 22 ADRs. Se realizo una auditoria integral con 3 especialistas (scientist+guardian+architect) investigando 40+ papers julio 2026.

## Investigacion Realizada

### 1. Arquitectura (Scientist)
| Aspecto | Hallazgo | Decision |
|---------|----------|----------|
| Modular Monolith vs Microservices | Sistemas <100K lines NO se benefician de microservicios | **MANTENER monolitho modular** |
| Event-Driven Architecture | WAL existente puede extenderse a event sourcing ligero | **EVOLUCIONAR WAL**, no Kafka |
| Plugin Architecture | ToolRegistry funciona, falta lazy loading granular | **OPTIMIZAR carga diferida** |
| Database Architecture | LanceDB + Redis L2 + SQLite time-series | **MULTI-MODELO** |
| API Design | MCP + A2A correctos, no añadir REST/gRPC interno | **MCP como unico protocolo externo** |

### 2. Testing y Calidad (Guardian)
| Aspecto | Hallazgo | Decision |
|---------|----------|----------|
| Coverage 60→80% | 9 archivos con 0% coverage (~1271 lines) | **+245 tests creados** |
| Mutation Testing | No implementado. mutmut recomendado | **PENDIENTE** |
| Property-Based Testing | PBT templates existen, Hypothesis no usado | **PENDIENTE** |
| Fuzzing | No implementado. Atheris recomendado | **PENDIENTE** |
| Performance Testing | Benchmarks existen pero no en CI | **PENDIENTE** |
| CI/CD Testing | Pre-commit existe, faltan gates de cobertura | **PENDIENTE** |

### 3. Frontier Tecnologias (Scientist)
| Tecnologia | Prioridad | Decision |
|-----------|-----------|----------|
| **A2A SDK oficial** v1.0.1 | 🔴 ALTA | Migrar router_a2a.py a SDK Linux Foundation |
| **Knowledge Graph** (FundaPod) | 🟡 MEDIA | Unificar trazabilidad 29 skills + 22 ADRs |
| **QueenBee** topologias evolutivas | ⚪ MONITOREAR | Solo si cuellos de botella en coordinacion |
| **Phionyx** ejecucion determinista | ⚪ MONITOREAR | Solo si bugs de reproducibilidad |
| **Multi-Modal** input | ⚪ DIFERIDO | Sin demanda concreta de usuarios |
| **PalmClaw** on-device | ❌ RECHAZADO | Arquitectura mobile incompatible |

## Decisiones e Implementacion

### 1. Tests para archivos 0% coverage
**Implementado:** +245 tests nuevos
| Archivo | Tests | Cobertura previa | Estado |
|---------|-------|------------------|--------|
| delegate.py | 38 | 0% | ✅ Creado |
| adaptive_planner.py | 58 | 0% | ✅ Creado |
| fts_search.py | 43 | 0% | ✅ Creado |
| embedding_service.py | 53 | 0% | ✅ Creado |
| hermes_bridge.py | 53 | 0% | ✅ Creado |

### 2. Skills minificados
**Implementado:** 13 nuevos SKILL.min.md
| Skill | Archivo | Estado |
|-------|---------|--------|
| behavioral-economics, business-strategy, communication, creative-design, devops-infra, education, ethics, linguistics, physical-sciences, project-management, psychology, sociology, sustainability | SKILL.min.md | ✅ Cobertura 100% (29/29) |

### 3. Legal NLP Analyzer
**Implementado:** `harness/memory_rag/legal_analyzer.py` (297 lines, 13 tests)
- NER juridico con patrones para normas, cortes, cargos, fechas
- Argument mining: ratio decidendi, obiter dicta
- Clasificacion en 6 tipos documentales
- Skill legal-doc actualizado con tecnicas 2026 (SaulLM, Arg-LLaDA)

### 4. Propagation Fix
**Implementado:** routing_rules.yaml limpiado (612→58 lines)
- Eliminados ~20 agentes fantasma del routing
- deploy_all.py actualizado para no restaurar routing obsoleto
- 36 propagation tests creados

## Pendiente para Proxima Iteracion

| Tarea | Impacto | Dependencias |
|-------|---------|-------------|
| Mutation testing (mutmut) | +45% bugs detection | Instalar mutmut |
| PBT con Hypothesis | +15% bugs frontera | Hypothesis |
| Fuzzing con Atheris | +2% coverage | Instalar atheris |
| A2A SDK oficial | Interoperabilidad Linux Foundation | pip install a2a-sdk |
| CI/CD gates coverage | Calidad preventiva | GitHub Actions |
| Knowledge Graph (FundaPod) | Trazabilidad semantica | NetworkX/Neo4j |

## Consecuencias
- **Tests totales:** 2213 (+256 en la sesion)
- **Skills:** 29 (100% con formato dual SKILL.md + SKILL.min.md)
- **Coverage:** ~65% (+5% en la sesion)
- **Complejidad:** Sin aumento — todas las mejoras son evolutivas
