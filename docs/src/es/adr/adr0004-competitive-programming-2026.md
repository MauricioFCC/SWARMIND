# ADR-0004: Competitive Programming Techniques 2026

## Estado
**ACEPTADO** — Implementado en commits 2d681c5, fb618ad.

## Contexto
El agente builder necesita generar codigo optimizado para problemas algoritmicos,
no solo codigo funcional. Las tecnicas clasicas (Two Pointers, Sliding Window, DP)
eran insuficientes para problemas de alto rendimiento donde la constante importa
tanto como la complejidad asintotica.

Se requiere un repertorio completo de tecnicas de programacion competitiva
actualizado a 2026, incluyendo optimizaciones de memoria, representacion,
y algoritmos de frontera.

## Decision
Ampliar el repertorio del builder con 3 niveles de tecnicas:

### Nivel 1 — Algoritmos Clasicos Esenciales
Mantenidos del repertorio anterior pero con precision aumentada:

| Tecnica | Precision 2026 |
|---------|---------------|
| Big O Analysis | Analisis amortizado + worst-case + expected case |
| Two Pointers | Con variante 3-way partition (Dutch Flag) |
| Sliding Window | Con deque para min/max en ventana O(n) |
| Divide and Conquer | Con Master Theorem para recurrencias |
| DP | Bitmask DP + DP con convex hull trick |
| Binary Search | Sobre respuesta (parametric search) + parallel binary search |
| Prefix Sum / Difference Array | 2D prefix sum, 3D diff array |
| Greedy | Con exchange argument para demostrar optimalidad |

### Nivel 2 — Estructuras de Datos Avanzadas

| Estructura | Aplicacion | Complejidad |
|-----------|------------|-------------|
| **Segment Tree** | RMQ, sum, gcd, lazy propagation | O(log n) query/update |
| **Fenwick Tree (BIT)** | Prefix sums dinamicas | O(log n), 4x menos codigo que segtree |
| **Binary Indexed Tree 2D** | Sumas rectangulares dinamicas | O(log² n) |
| **Trie (Prefix Tree)** | Autocompletado, XOR maximo | O(k) por operacion |
| **Union-Find (DSU)** | Componentes conexas, Kruskal | O(α(n)) amortizado |
| **Sparse Table** | RMQ inmutable | O(1) query, O(n log n) build |
| **Heavy-Light Decomposition** | Query/update en caminos de arbol | O(log² n) |
| **Centroid Decomposition** | Conteo de caminos, divide & conquer en arbol | O(log n) profundidad |
| **Link-Cut Tree** | Arboles dinamicos (cortar/conectar) | O(log n) amortizado |

### Nivel 3 — Algoritmos de Frontera (2026)

| Algoritmo | Problema | Complejidad |
|-----------|----------|-------------|
| **Static Top Tree** | Query/update en arbol con operaciones de semigrupo | O(log n) |
| **Generating Functions** | Conteo de secuencias, particiones, recurrencias | — |
| **Matrix Exponentiation** | Recurrencias lineales (Fibonacci N=1e18) | O(k³ log n) |
| **SMAWK** | Matrices de Monge (DP optimizacion) | O(n + m) |
| **Stoer-Wagner** | Min cut global en grafo no dirigido | O(nm + n² log n) |
| **Dinitz (Dinamic)** | Max flow O(E√V) en grafos bipartitos | O(E √V) |
| **Min Cost Max Flow** | Flujo con costo minimo (potenciales) | O(F · E log V) |
| **Manacher** | Palindromos en O(n) | O(n) |
| **Z-Algorithm / KMP** | Pattern matching | O(n + m) |
| **Convex Hull Trick (Li Chao)** | DP optimization con rectas | O(log n) por query |

### Nivel 4 — Optimizacion de Constantes y Memoria

| Tecnica | Descripcion |
|---------|-------------|
| **Constraint-Based Pruning** | Usar cotas del problema para podar busqueda |
| **SIMD / Bit-Parallel** | Operaciones con bitsets para acelerar 64x |
| **Memory Hierarchy** | Optimizar patrones de acceso a cache (prefetch, aligned alloc) |
| **Loop Unrolling** | Desenrollar loops manual cuando el compilador no lo hace |
| **Branch Prediction** | Reordenar condiciones para predecibilidad |
| **Representation Selection** | Elegir representacion (adj list/matrix/edge list) segun densidad |

## Codificacion en Agent Prompts

El builder.md incorpora tabla completa de 30+ tecnicas con:
- Tabla de tecnicas clasicas (12 items)
- Tabla de vanguardia Swarmind (TDAD, TDFlow, PaCoRe, REPOREASON, ABC-Bench)
- Testing avanzado (PROBE, AdverTest, PBT, FuzzAgent, SMART)
- Optimizacion de tokens (Cache-Shape, Failure-Spend, Structured Compaction, Harness Effect)

## Archivos Modificados
- `.opencode/agents/builder.md`: 107 lineas con tabla completa de tecnicas
- `.opencode/agents/builder.agent.min.md`: triggers y capabilities ampliados
- `harness/memory_rag/context_injector.py`: UNIVERSAL_FIRMA con tecnicas CP

## Consecuencias
- **Positivas**: Builder puede resolver problemas de concurso (Codeforces, ICPC) con O(n log n) y estructuras avanzadas
- **Negativas**: Mas tecnicas = mas tokens en system prompt (~200 tokens extra)
- **Investigacion First**: Cada tarea comienza con web search del estado del arte, asegurando que las tecnicas sean siempre las mas recientes

## Referencias
- cp-algorithms.com: Static Top Tree, Generating Functions, SMAWK
- Codeforces Blog: "Heavy-Light Decomposition — Explicacion y Aplicaciones"
- Codeforces Blog: "Centroid Decomposition — Divide and Conquer on Trees"
- Algorithmica: "Memory Hierarchy Optimization for Competitive Programming"
- Stoer & Wagner, "A Simple Min-Cut Algorithm", JACM 1997
- Agarwal et al., "SMAWK: A Fast Algorithm for Monge Matrices", 1987
