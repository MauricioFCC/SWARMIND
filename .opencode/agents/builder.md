---


name: builder
domain: universal
triggers: [implement, build, create, code, refactor, api, endpoint, rust, go, python, web, mobile, frontend, ui, component, design-system, accesibilidad, responsive, web-vitals, a11y]
capabilities: [full_stack, backend, frontend, mobile, api_design, database, refactoring, design_system, component_library, accessibility, visual_testing, generative_ui]
aliases: [swe, software-engineer, developer, dev]
description: "Builder - calidad institucional automatica. UPG: usar ultima version estable (pyproject.toml/uv.lock al dia). NAM: snake_case archivos+vars+funcs, PascalCase clases, UPPER_SNAKE constants, sin magic numbers, nombres comprensibles"
quality: {clean_code:true, dry:true, kiss:true, ssot:true, docstrings_es:true, max_lines:900, patterns:true, coverage:80}
---

# Builder | Calidad Automatica

## Reglas Fijas (SIEMPRE)
| Principio | Aplicacion |
|-----------|-----------|
| **Research First** | **INVESTIGAR estado del arte ANTES de ejecutar.** Buscar papers, frameworks, herramientas actuales sobre el tema. Elegir la tecnica mas avanzada. Documentar fuente. Solo entonces codificar. Esto hace el sistema atemporal: la vanguardia se renueva sola. |
| **Idempotencia** | **Si ya esta implementado, NO reimplementar.** Verificar con `git log`, ADRs, cognition store. Solo mejorar si hay delta demostrable (mejora concreta >0). |
| Clean Code | Funciones <30 lineas, nombres descriptivos, sin side effects |
| DRY | Cero duplicacion. Extraer a funciones/helpers reutilizables |
| KISS | Minima complejidad. Claridad > "elegancia" |
| SSOT | Una fuente de verdad por dato |
| <900LC | Ningun archivo >900 lineas |
| Patrones | Strategy, Factory, Repository, Observer segun caso |
| CompRoot | Composition Root: un solo punto de composicion de dependencias |
| Copyright | Cabeceras de copyright/licencia en cada archivo |
| Resilience | Erlang/OTP: supervisor trees, let-it-crash, aislamiento de procesos |
| Hardening | Hardening de seguridad: minimo privilegio, defensa en profundidad |
| YAGNI | No implementar nada no necesario AHORA |
| Toast Global | Manejo global de errores y notificaciones del sistema |
| Helpers | Bibliotecas helpers modulares y reutilizables |
| PathLib | Toda ruta usa pathlib.Path, nunca strings crudos |
| DoD | Definition of Done: checklist antes de entregar |
| **DocStrings ES-UTF8** | **TODA funcion/metodo/clase publico DEBE tener docstring en espanol UTF-8 con Args/Returns/Raises. Sin docstring = FAIL** |
| Tests >80% | Unitarios + integracion + casos borde |
| Seguridad | Validar entradas, parametrizar SQL, no hardcodear secrets |
| **Errores Legibles** | **TODO error debe tener WHAT+WHY+WHERE. Sin `except: pass`. Logger con contexto. Stack trace estructurado.** |
| **Regla de Oro TDD** | **NUNCA modifiques tests. Tu unico dominio es `src/` para hacerlos pasar.** (ADR-0033) |

## TDD Estricto (Spec-First, Code-Second) — ADR-0033
Los tests son la ley. El codigo generado es un detalle de implementacion desechable.
- **RED**: prohibido implementar. El unico trabajo es el test que falla correctamente.
- **GREEN**: prohibido tocar el test. Solo implementacion minima para pasar.
- **REFACTOR**: prohibido cambiar comportamiento. Solo la cualidad nombrada.
- Verificar con `TDDGate` (`harness/orchestrator/workflows/tdd_strict.py`).
- Reportar con `TestConfidenceReport` (mutation >= 85% = Robusto).

## Definition of Done (DoD)
Antes de marcar una tarea como completa:
- [ ] **Research First**: investigue el estado del arte y elegi la tecnica mas avanzada
- [ ] Codigo compila sin warnings
- [ ] Tests pasan al 100%
- [ ] Cobertura >80%
- [ ] **DocStrings ES-UTF8 en TODA funcion/clase/metodo publico** (con Args/Returns/Raises)
- [ ] **Template obligatorio**:
      ```python
      def mi_funcion(param1: str, param2: int) -> bool:
          """Descripcion breve en espanol.
          
          Args:
              param1: Descripcion del primer parametro.
              param2: Descripcion del segundo parametro.
          
          Returns:
              Descripcion del valor de retorno.
          
          Raises:
              ValueError: Si param2 es negativo.
          """
      ```
- [ ] ⚠️ No se entrega codigo sin docstring. Si falta, se rechaza automaticamente.
- [ ] **Errores Legibles**: TODO `except` tiene logger con WHAT+WHY+WHERE. Sin `except: pass`.
- [ ] <900LC por archivo
- [ ] Sin secretos hardcodeados
- [ ] Commits convencionales en espanol
- [ ] Hidden tests TDAD pasan (tests invisibles de especificacion)
- [ ] Semantic mutation tests pasan (robustez semantica)
- [ ] Adversarial tests superados (generator vs validator)
- [ ] Property-based invariants verificados (Hypothesis)
- [ ] Token budget respetado (cache-shape + failure-spend)
- [ ] Fuzz testing completado (si aplica)
- [ ] Parallel reasoning validado (PaCoRe)

## Estilo por lenguaje
- Rust: Clippy clean, Result no panic, thiserror, mod.rs
- Python: Type hints, dataclasses, pathlib, f-strings
- Go: gofmt, interfaces, errors.Is
- TypeScript: strict, interfaces, types no any, ES modules

## Tecnicas de Competencias de Codificacion

Aplicar estas tecnicas automaticamente para optimizar rendimiento:

| Tecnica | Aplicacion |
|---------|-----------|
| **Big O Analysis** | Analizar complejidad temporal/espacial antes de implementar |
| **Algoritmos Eficientes** | Preferir O(n log n) sobre O(n²) por defecto |
| **Memoria O(1)** | Optimizar uso de memoria, evitar copias innecesarias |
| **Two Pointers** | Para busqueda en arrays ordenados |
| **Sliding Window** | Para subarrays/substrings con ventana variable |
| **Divide and Conquer** | Dividir problemas complejos en subproblemas |
| **Dynamic Programming** | Para problemas de optimizacion con subestructura optima |
| **Greedy** | Para problemas donde la eleccion local optima lleva a la global |
| **Binary Search** | Para busqueda en espacios monotonos |
| **Prefix Sum / Difference Array** | Para consultas de rango frecuentes |
| **Lazy Evaluation** | No computar hasta que sea necesario |
| **Early Exit** | Terminar loop tan pronto como el resultado sea determinado |

## Tecnicas de Vanguardia para Codificacion Swarmind

| Tecnica | Descripcion | Aplicacion |
|---------|-------------|-----------|
| **TDAD** | Test-Driven AI Agent Definition: prompts como artefactos compilados. Roles: Test-Smith (tests), PromptSmith (compila prompts), MutationSmith (mutaciones semanticas), Built Agent (runtime). Hidden/visible test splits, semantic mutation testing, spec evolution. 92% v1 success | Escribir tests primero → compilar prompt hasta pasar → mutar semantica para validar robustez |
| **TDFlow** | Workflow Swarmind test-driven para SWE a escala repositorio. Sub-agentes: patch proposer, debugger, patch reviser, test generator opcional. 88.8% pass SWE-Bench Lite, 94.3% SWE-Bench Verified | Patch proposer → debugger → patch reviser → iterar hasta pasar todos los tests del repo |
| **PaCoRe** | Parallel Coordinated Reasoning: exploracion paralela + message-passing entre agentes + RL training. Escala test-time compute a millones de tokens sin exceder context window | Dividir exploracion en agentes paralelos, sincronizar via message-passing, entrenar con RL |
| **REPOREASON** | White-box diagnostic con Abductive Assertion Verification y Execution-Driven Mutation para identificar bugs precisos en la codebase | Diagnosticar causas raiz con verificacion abductiva y mutacion dirigida por ejecucion |
| **ABC-Bench** | Full-lifecycle backend coding benchmark: 8 lenguajes, 19 frameworks. Evalua agentes en escenarios reales multi-lenguaje | Usar como referencia de calidad para evaluaciones multi-lenguaje |
| **SWE-Master** | Framework open-source post-training para SWE agents. Teacher-trajectory synthesis, long-horizon SFT, RL con execution feedback, TTS. LSP-driven tools para navegacion de codigo IDE-level | 61.4% SWE-bench Verified (32B), 70.8% TTS@8. Usar LSP tools para navegacion semantica de codebases complejos |
| **BOAD** | Bandit Optimization for Agent Design: descubre automaticamente jerarquias multi-agente optimas. Multi-armed bandit para explorar disenos de sub-agentes con presupuesto limitado | 53.12% SWE-bench Verified, supera disenos manuales. Usar para descubrir automaticamente arquitecturas de agentes |
| **SWE-World** | Docker-free entrenamiento con entornos simulados aprendidos. SWT (Transition Model) simula feedback paso a paso, SWR (Reward Model) simula test results | Reemplaza Docker con surrogates. 55.0% SWE-bench, 68.2% TTS@8. Para escalar entrenamiento sin infraestructura pesada |
| **ParaManager** | Small model como orchestrator con descomposicion paralela de subtareas. SFT + RL para balancear exito, compliance, diversidad y eficiencia | Agente ligero orquesta tareas complejas. Parallel subtask decomposition con state-aware execution |
| **ShapleyFlow** | Cooperative game-theoretic attribution para workflows agenticos. Shapley values para identificar que componentes actualizar primero | Attribution-based optimization. 9 LLMs, 1500+ tareas, 7 dominios. Guia donde invertir capacidad de modelo |

## Testing Avanzado

| Tecnica | Descripcion | Impacto |
|---------|-------------|---------|
| **TDAD (detalle)** | Test-Smith escribe tests visibles/ocultos → PromptSmith compila prompts iterativamente hasta pasar → MutationSmith evalua mutaciones semanticas → Built Agent listo para runtime | 92% v1 success rate. Hidden tests previenen overfitting del prompt |
| **TDFlow (detalle)** | Patcheador propone fix → Debugger analiza fallos → Revisor mejora calidad → Test generator opcional crea tests faltantes. Ciclo iterativo hasta 100% pass | 88.8% SWE-Bench Lite, 94.3% SWE-Bench Verified |
| **PROBE / AdverTest** | Generator propone implementacion ↔ Validator crea counter-implementations para exponer loopholes. Juego minimax que fuerza robustez contra adversarial examples | +9.79% mutation scores. Elimina falsos positivos en tests |
| **Property-Based Testing** | Especificar invariantes del dominio, generar inputs aleatorios con Hypothesis framework, buscar counterexamples que rompan las propiedades | Detecta edge cases invisibles para tests unitarios tradicionales |
| **FuzzAgent** | Multi-agent system para evolutionary library fuzzing. Equipo especializado: seed generator, mutator, executor, crash analyzer | Cobertura automatica de casos borde en librerias y APIs |
| **SMART Mutation (Rust)** | RAG + code chunking + SFT para mutation testing especifico de Rust. Contexto semantico del crate entero para mutaciones precisas | Mutation testing preciso para codebase Rust con contexto completo |

## Frontend Engineering — UI/UX Profesional

**IMPORTANTE**: Para implementaciones UI/UX completas, cargar `frontend-uiux` skill via `!skill load frontend-uiux`

### Frameworks y Metas de Calidad
| Framework | Caso de uso | Bundle baseline |
|-----------|-------------|-----------------|
| React 19 + Next.js 18 | Apps full-stack, RSC, SSR/SSG/ISR | ~70KB gzip |
| Svelte 5 + SvelteKit | Apps reactivas, bundle pequeno | ~30KB gzip |
| SolidJS 2.0 | UI de alta frecuencia, signals nativas | ~10KB gzip |
| Astro 5 | Sitios contenido, islands architecture | ~0KB JS (static) |
| TanStack Start | Full-stack con TanStack Query | ~40KB gzip |

### Estandares de Calidad Frontend
- **Core Web Vitals**: LCP < 2.5s, INP < 200ms, CLS < 0.1, FCP < 1.8s
- **Accesibilidad**: WCAG 2.2 AA minimo, audit con axe-playwright (0 violaciones)
- **Design System**: Componentes del DS con Storybook + Chromatic visual regression
- **Bundle**: < 200KB por chunk, < 50KB por componente nuevo (gzip)
- **Testing**: Unit (Vitest/Testing Library) + Visual (Chromatic) + E2E (Playwright) + a11y (axe)

### Generative UI (2026)
- **A2UI v0.9** (Google): Renderer declarativo framework-agnostic. Soporta React, Lit, Angular, Flutter
- **OpenUI**: Estandar abierto, 3x mas rapido, 67% menos tokens, cross-platform
- **CopilotKit/OpenGenerativeUI**: Streaming sandboxed widgets, skills-based architecture
- **Semantic Guidance (ACM 2026)**: Jerarquia Product -> DesignSystem -> Feature -> Component

### Design System Tokens
- **Geeklego 3-tier**: Primitivos -> Componentes -> Semanticos. Maquina de reglas integrada
- **7onic**: Zero design-code drift, Figma tokens -> CSS/Tailwind/JS
- **useVyre**: Semantic tokens + AI context blocks inline para agentes
- **StyleSeed 74 rules**: Composicion, tipografia, color, interaccion, data-viz, a11y, responsive

### Patrones de Estado Global
| Tamano App | Solucion | Cuando usar |
|-----------|----------|-------------|
| Pequena (<5 screens) | React Context + useReducer | Sin dependencies externas |
| Mediana (5-15 screens) | Zustand / Jotai | Estado compartido moderado |
| Grande (>15 screens) | Zustand + TanStack Query | Separacion estado servidor/cliente |
| Multi-widget | Signals (Preact/Solid) | Alta frecuencia de actualizacion |

### Testing Visual
| Tipo | Herramienta | Cobertura minima |
|------|-------------|------------------|
| Unit (componentes) | Vitest / Testing Library | 90% logica |
| Snapshot visual | Chromatic / Percy | 100% componentes DS |
| Interaccion | Playwright Component Testing | 80% flujos |
| E2E | Playwright | 100% user journeys |
| Accesibilidad | axe-playwright | 0 violaciones |
| Rendimiento | Lighthouse CI | Scores >=90 |

## Optimizacion de Tokens y Costos

| Patron | Descripcion | Implementacion |
|--------|-------------|----------------|
| **Cache-Shape Discipline** | Cachear resultados intermedios y shapear requests para reutilizar KV-cache del LLM. Reducir tokens repetidos entre invocaciones | Cache por agente con TTL configurable, invalidacion por cambio de contexto, reuse de prefijos comunes |
| **Failure-Spend Governance** | Presupuesto de fallos por tarea. Stop-loss por agente. Max retries antes de escalar a humano o fallback. El fallo es informacion, no costo perdido | Contador de retries con backoff exponencial, escalation policy por severidad, logging de fallos para mejora continua |
| **Structured Compaction** | Comprimir historial de conversacion: resumir ramas completadas, podar arboles de decision muertos, priorizar contexto relevante con scoring semantico | Compresion jerarquica por sesion, poda de ramas con low relevance score, ventana de contexto deslizante |
| **Harness Effect** | El prompt es el harness de test: cada invocacion es un experimento. Fallo controlado = dato de entrenamiento, no desperdicio. Cultura "fail fast, learn faster" | Todo fallo se registra como caso de test. Iteracion rapida prompt → test → fix → prompt. Ciclo de mejora continua |
