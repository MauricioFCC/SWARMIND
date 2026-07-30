# ADR-0007: Memoria Completa de Estandares + Tecnicas CP y Comprension

## Estado
**ACEPTADO** — Implementado en commit 35065ed.

## Contexto
El sistema necesita mantener memoria permanente de todos los estandares de calidad,
tecnicas de programacion competitiva y metodos de comprension de textos, sin requerir
que el usuario los mencione en cada interaccion.

## Decision
Ampliar el ContextInjector con 22+ estandares codificados en forma ultra-compacta
(~38 tokens por subtarea) y actualizar los prompts de builder, scientist y coordinator.

## Estandares Fijos (siempre activos, 18 reglas base)

| # | Estandar | Descripcion |
|---|----------|-------------|
| 1 | CleanCode | Funciones <30 lineas, nombres descriptivos |
| 2 | DRY | Cero duplicacion, helpers reutilizables |
| 3 | KISS | Minima complejidad necesaria |
| 4 | SSOT | Una fuente de verdad por dato |
| 5 | <900LC | Ningun archivo supera 900 lineas |
| 6 | Patrones | Strategy, Factory, Repository, CompRoot |
| 7 | CompRoot | Composition Root: un punto de composicion |
| 8 | Copyright | Cabeceras de licencia en cada archivo |
| 9 | Resilience | Erlang/OTP: supervision, let-it-crash |
| 10 | Hardening | Minimo privilegio, defensa en profundidad |
| 11 | YAGNI | No implementar no necesario |
| 12 | ToastGlobal | Manejo global de errores/notificaciones |
| 13 | Helpers | Librerias helpers modulares |
| 14 | PathLib | Toda ruta con pathlib.Path |
| 15 | **DocStringsES** | **Toda funcion documentada en espanol UTF-8** |
| 16 | tests>80 | Cobertura de tests >80% |
| 17 | Seg | Validacion entradas, sin secrets |
| 18 | DoD | Definition of Done checklist |

## Tecnicas de Competencias de Codificacion (Builder)

| Tecnica | Aplicacion |
|---------|-----------|
| Big O Analysis | Analizar complejidad antes de implementar |
| Algoritmos Eficientes | O(n log n) sobre O(n²) por defecto |
| Two Pointers | Busqueda en arrays ordenados |
| Sliding Window | Subarrays con ventana variable |
| Divide and Conquer | Dividir problemas complejos |
| Dynamic Programming | Optimizacion con subestructura optima |
| Binary Search | Busqueda en espacios monotonos |
| Prefix Sum / Diff Array | Consultas de rango frecuentes |
| Early Exit | Terminar loop al determinar resultado |

## Tecnicas de Comprension de Textos (Scientist)

| Tecnica | Aplicacion |
|---------|-----------|
| SQ3R | Survey, Question, Read, Recite, Review |
| Lectura Critica | Identificar sesgos, argumentos debiles |
| Mapa Mental | Estructurar conceptos jerarquicamente |
| Estructura Argumental | Premisa > Razonamiento > Conclusion |
| Lectura en Capas | 3 pasadas: general, detalle, critica |
| Inferencia | Leer entre lineas, implicaciones no explicitas |

## Codificacion en ContextInjector

`
builder: "CleanCode+DRY+KISS+SSOT+<900LC+Patrones+CompRoot+Copyright+Resiliencia
         +Hardening+YAGNI+ToastGlobal+Helpers+PathLib+DoD+DocStringsES+tests>80
         +Seg+Rust+CP_Opt+AlgoEficiente+MemoriaO1+Complejidad+BigO"

scientist: "MetodoCientifico+Fuentes+Analisis+Conclusiones+DocumentarES+DoD
           +PathLib+LecturaCritica+SQ3R+ComprensionProfunda+MapaMental+Resumir
           +Sintetizar"
`

## Archivos Modificados
- harness/memory_rag/context_injector.py: 22+ estandares en firma universal
- .opencode/agents/builder.md: Tabla de tecnicas CP agregada
- .opencode/agents/scientist.md: Tabla de comprension de textos agregada
- .opencode/agents/coordinator.md: CP_Strategies en firma
- .opencode/agents/builder.agent.min.md: quality_overrides ampliado
- .opencode/agents/coordinator.agent.min.md: quality_overrides ampliado

## Consecuencias
- 38 tokens por subtarea (antes ~400 tokens de preambulo manual)
- 18 reglas fijas + tecnicas especializadas por rol
- 3400+ tests pasando (Julio 2026)
