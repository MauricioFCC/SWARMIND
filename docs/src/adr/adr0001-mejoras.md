# ADR-0001: AGENTIC Harness — Sistema Multi-Agente Evolutivo

## Estado
**ACEPTADO** — Implementado y en producción desde Julio 2026.

## Contexto

Se necesita un sistema de orquestación multi-agente que permita a LLMs (Large Language Models) colaborar de forma estructurada, eficiente y con calidad institucional. El sistema debe:

1. **Orquestar múltiples agentes** trabajando en paralelo sobre un mismo código base
2. **Mantener calidad constante** sin depender de prompts externos
3. **Optimizar tokens** al máximo sin perder precisión
4. **Ser portable** entre máquinas y usuarios
5. **Auto-mejorarse** mediante retroalimentación continua

## Decisión

Construir **AGENTIC Harness**, un sistema multi-agente con las siguientes características fundamentales:

### 1. Arquitectura Swiss Watch

| Componente | Rol |
|------------|-----|
| **Coordinator** | Orquestador principal. Recibe la tarea, la divide, delega y consolida |
| **Builder** | Implementa código en `src/` siguiendo estándares automáticos |
| **Scientist** | Investiga, analiza y produce documentación (solo texto) |
| **Guardian** | Tests, seguridad, calidad y bugfix en `tests/` |
| **Evolve** | Auto-mejora del sistema, cognition store |

### 2. Patrón de Ejecución: Swiss Watch

```
Nivel 0 (PARALELO TOTAL):
  [coordinator] PLAN: divide el trabajo
  [scientist]   INVESTIGA: texto (0 archivos)

Nivel 1 (PARALELO CONSCIENTE):
  [builder] CORE: src/core/     ← directorio único
  [builder] API:  src/api/      ← directorio único  
  [builder] DB:   src/db/       ← directorio único
  [guardian] TESTS: tests/      ← separado de src/
  [guardian] DOCUMENTA         ← 0 archivos código
  → NADIE COMPARTE DIRECTORIO → CERO COLISIONES

Nivel 2:
  [guardian] BUGFIX: corrige solo errores específicos

Nivel 3:
  [coordinator] CONSOLIDA: integra todo
```

### 3. Escalado Dinámico (Dynamic Scaling)

El sistema analiza el mensaje del usuario y determina cuántos agentes lanzar:

| Alcance | Builders | Guardians | Scientist | Bugfix | Agentes pico |
|---------|:--------:|:---------:|:---------:|:------:|:------------:|
| **Small** (1-2 archivos) | 1 | 1 | - | - | 4 |
| **Medium** (3-5 archivos) | 2 | 1 | ✅ | - | 6 |
| **Large** (6-10 archivos) | 3 | 2 | ✅ | ✅ | 8 |
| **XLarge** (10+ archivos) | 5 | 3 | ✅ | ✅ | 11 |

### 4. Memoria de Estándares (ContextInjector)

Para evitar que el LLM olvide los estándares durante sesiones largas, cada subtarea
lleva un recordatorio ultra-compacto (~23 tokens):

```
[F]CleanCode+DRY+KISS+SSOT+<900LC+Patrones+CompRoot+Resiliencia+DoD+DocStringsES+tests>80+Seg
```

### 5. Framework de Skills

10 skills especializados: `alpha-research`, `evolve`, `healthtech`, `hedgefund`,
`legal-doc`, `math-doc`, `pos-retail`, `quant-trading`, `risk-execution`, `science-doc`

### 6. Memoria Persistente (LanceDB)

- **Cognition Store**: Lecciones aprendidas entre sesiones
- **Semantic Cache**: Evita LLM calls repetidas (hit rate 25-40%)
- **Session Log**: Decisiones de sesión con búsqueda semántica

## Consecuencias

### Positivas
- **Velocidad**: Hasta 11 agentes simultáneos sin colisiones
- **Calidad**: Estándares automáticos en cada subtarea
- **Tokens**: ContextInjector ~23 tokens vs ~400 tokens de preámbulo manual
- **Portabilidad**: Paths relativos, función `_resolve_hermes_root()` con 3 fallbacks
- **Escalabilidad**: Dynamic scaling se adapta al tamaño de la tarea

### Negativas
- **Complejidad**: 20 agent profiles, 31 skills, 48+ módulos de harness
- **Dependencia LanceDB**: Requiere LanceDB para caché y memoria persistente
- **Curva de aprendizaje**: Nuevos usuarios deben entender el patrón Swiss Watch

## ADRs Deprecados Integrados Aqui

Los siguientes ADRs han sido deprecados y su contenido esta resumido aqui:

| ADR | Titulo | Resumen |
|-----|--------|---------|
| 0002 | Dynamic Scaling | ScopeAnalyzer analiza el mensaje y escala de 1-11 agentes segun complejidad (small→xlarge). 4 niveles, integrado en TaskPlanner.decompose(). |
| 0003 | Context Injector | Inyecta recordatorio ultra-compacto (~23 tokens) en CADA subtarea: `[F]CleanCode+DRY+KISS+SSOT+<900LC+Patrones+CompRoot+Resiliencia+DoD+DocStringsES+tests>80+Seg`. Ahorra ~400 tokens por sesion. |
| 0004 | Skill Router | Selecciona solo 1-2 skills relevantes por tarea usando keyword matching + embedding. Reduce 60-80% tokens en skills. |
| 0005 | Memoria Portable | Sistema de paths con 3 niveles de fallback: HERMES_ROOT env var → ~/Documents/Hermes_Memory_Proyects/ → ~/Documents/AGENTIC_MEMORY/. Elimina paths absolutos. |
| 0006 | Legal Doc Colombia | Skill legal-doc reescrito con metodologia RTF+C, 8 roles, fuentes colombianas (SUIN, Relatoria CC), 8 especialidades, 7 fases. |

## Estado Actual (Julio 2026)

| Metrica | Valor |
|---------|-------|
| Agentes | 20 especializados |
| Skills | 31 contextuales |
| ADRs | 28 nucleos + 8 fusionados (38 archivos) |
| Tests | 3400+ pasando |
| Modulos | 48 orchestrator + 30 memory_rag + 12 multi-harness |
| Lineas Python | ~35,000 |

## Referencias

- [GUIA_AGENTIC.md](../../GUIA_AGENTIC.md) — Guía completa de uso
- [AgentVerse (arXiv 2308.10848)](https://arxiv.org/abs/2308.10848) — Multi-agent collaboration
- [AutoGen (Microsoft)](https://www.microsoft.com/en-us/research/blog/autogen-enabling-next-generation-large-language-model-applications/) — Multi-agent conversation framework
- [CrewAI](https://docs.crewai.com/) — Multi-agent orchestration patterns

## Commits Relacionados
- `d102c2f` — Swiss Watch multi-agente (foundation)
- `908935a` — Dynamic scaling (1-11 agents)
- `2f8e46b` — CompositionRoot + Resilience + DoD
- `00ae958` — legal-doc Colombia + JURIDICO project
- `4168061` — Auditoria integral + compactacion ADRs
