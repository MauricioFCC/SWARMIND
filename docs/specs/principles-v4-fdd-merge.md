# Spec: principios universales v4.0.0 — merge selectivo FDD/DDD/SDD

| Campo | Valor |
|---|---|
| Estado | Implementado (2026-11-12) |
| Principios rectores | `SPE` (spec para lo irreversible), `FIC` (ficha para features), `FRC` (fricción proporcional), `GATE` (evidencia), `IDP` (no reimplementar) |
| Research | `docs/research/frontier-2026-11-12-fdd-principles.md` (H3 elegida) |
| Alcance | `.opencode/core/base_principles{,.min,_full}.md`, taxonomía, artefactos `docs/fdd/`, guard de integridad y sus tests |
| Fuera de alcance | Reescribir el harness, adoptar Penpot, reemplazar `AGENTS.md`, tocar los 41 tags `UPG·NAM·FRS` |

---

## 1. Problema (WHY)

SWARMIND tiene 45 códigos N1, 3 suites de integridad y un `xtask check` de 15
gates. Su metodología cubre investigación (`RSF`/`FRS`/`EDV`), verificación
(`TST`/`GATE`/`ADV`), arquitectura (`ARQ`/`CLA`/`AGR`) y contexto
(`TKN`/`CEN`/`RPA`), pero **no tiene capa de entrega ni de dominio**:

1. No hay unidad de trabajo con nombre de resultado ni corte vertical; una
   sesión nueva no sabe qué feature retomar ni dónde quedó.
2. No hay mapa de dominio; el conocimiento de entidades vive solo en el código.
3. No hay propiedad de archivos ni coordinador único: el fan-out puede editar
   el mismo archivo desde dos frentes.
4. No hay hitos que distingan *diseñado* de *verificado* e *integrado*, y el
   hito *integrado* debe ser humano.
5. `SPE` exige spec para todo, lo que contradice la evidencia de FDD/SDD: la
   especificación exhaustiva previa es cascada y encarece cambios pequeños.
6. La taxonomía de adherencia está desincronizada: `EDV` y `RSV` no aparecen,
   `DOR` es un fantasma y 4 códigos GUIDE ocupan el N1 siempre inyectado.
7. La detección de duplicados N1 es O(n²) (`codes.count(code)` por código).

## 2. Decisión (WHAT)

Adoptar el **merge selectivo** (H3): seis códigos nuevos, cuatro degradados,
una matriz de selección «-DD» en N2, taxonomía biyectiva y guard compartido.

### 2.1 N1 nuevo (47 códigos, ≤60 líneas)

| Código | Regla atómica | Categoría |
|---|---|---|
| `DOM` | mapa de dominio vivo: entidades + lenguaje ubicuo + dónde vive cada una | FDD |
| `FIC` | una ficha por feature: acción + resultado + objeto, corte vertical, criterios demostrables, estado para retomar | FDD |
| `HIT` | hitos diseñado→implementado→verificado→integrado; *integrado* solo lo marca una persona; afirmar sin evidencia = no hecho | GOV |
| `FRC` | fricción proporcional: elegir el «-DD» según el requisito; irreversible = spec + ADR + rollback; puntual = fix + test | FDD |
| `OWN` | propiedad de archivos: un solo coordinador escribe por ola; cada archivo con dueño en la ficha; paralelo sin archivos compartidos | FDD |
| `DEC` | decisiones cerradas: tema/decisión/por qué; invariantes con una sola puerta; el doc manda antes que el código | GOV |

### 2.2 Degradados de N1 a N2 (sin romper citas)

`WFP`, `MCL`, `MKS` y `RPA` son modo GUIDE según la propia taxonomía; dejan de
inyectarse siempre y pasan a la tabla N2. Se mantienen como códigos válidos y
citables: **no se renombran ni se eliminan**.

Política de alias (expand/contract de Parallel Change):

| Código | Estado v4.0.0 | Resolución |
|---|---|---|
| `WFP` | N2 | tabla N2 «Workflow Patterns» |
| `MCL` | N2 | tabla N2 «MetaClaw» |
| `MKS` | N2 | tabla N2 «Memento-Skills» |
| `RPA` | N2 | tabla N2 «Re-Pin After compaction» |
| `DOR` | N2 (nunca fue N1) | tabla N2 «DORA como SLO» |
| `QLT` | N2 deprecado | tabla N2, cubierto por `NAM`/`TYP`/`IMM`/`SOL`/`MAG`/`FSZ` |

Los 5 códigos del ADR-0098 (`CLA`, `VAL`, `FST`, `AAA`, `ATM`) **conservan**
presencia N1 y categoría.

### 2.3 Taxonomía biyectiva (47 ↔ 47)

| Cat | Nombre | Códigos | Modo |
|---|---|---|---|
| PRC | Proceso e investigación | RSF, IDP, FRS, EDV, RSV, FND, SPE, UPG, POC, ATM | CHECK |
| ARC | Arquitectura y código | ARQ, SOL, CMP, DEM, NAM, TYP, IMM, MAG, FSZ, AGR, CLA | CHECK |
| QLT | Calidad y testing | TST, PBT, GATE, CPD, ADV, AAA | CHECK |
| SEC | Seguridad y aislamiento | SEG, SBX, VAL | CHECK |
| DOC | Documentación y commits | DOC, CMT, SVE | CHECK |
| CTX | Contexto y tokens | CEN, TKN | CHECK |
| GOV | Gobernanza y evidencia | ERR, FAIL, BTR, EVO, FDE, FST, HIT, DEC | CHECK |
| FDD | Entrega por feature y dominio | DOM, FIC, FRC, OWN | CHECK |

### 2.4 Matriz de selección «-DD» (N2)

En N2 se añade la tabla de 10 filas del research §8: FDD, DDD, SDD, CDD, TDD,
BDD, ATDD, RDD, maqueta y ola 0. La regla `FRC` remite a esa tabla; el N2 solo
se inyecta con presupuesto >70 %, así que no encarece el caso común.

### 2.5 Artefactos FDD

`docs/fdd/README.md` (constitución + flujo), `docs/fdd/dominio.md` (plantilla
del mapa) y `docs/fdd/ficha-template.md` (plantilla de ficha con los 4 hitos y
las secciones de decisión, dueños, evidencia y próximo paso).

## 3. Diseño y fórmulas

### 3.1 Presupuesto de contexto

Sea `L(N1)` el número de líneas no vacías del bloque N1 y `C` su costo en
caracteres. Restricción dura: `L(N1) ≤ 60`. Antes: 45. Después: 47.

```
C_antes   = 5262 caracteres (45 líneas, 45 códigos)
C_despues = 4139 caracteres (47 líneas, 47 códigos)
ΔC/C_antes = −21.3 %
```

El N2 crece con la matriz y las seis reglas FDD, pero `N2` solo se inyecta
cuando el presupuesto supera el 70 % (`token_budget_router`), por lo que el
costo del caso común baja un 21,3 % frente al N1 anterior.

### 3.2 Complejidad del guard

| Chequeo | Antes | Después |
|---|---|---|
| Duplicados N1 | `codes.count(code)` por código → **O(n²)** | `Counter(codes)` → **O(n)** esperado |
| Taxonomía | 5 códigos comprobados contra 44 → **O(k·m)** con k=5 | biyección de conjuntos → **O(n+m)** |
| Coste con n=47 | 2 209 comparaciones | 47 hashes + 47 búsquedas |

Prueba de equivalencia: para toda lista de códigos, el resultado O(n) debe ser
idéntico al oráculo O(n²); y el número de comparaciones del oráculo crece
~4× por cada duplicación de n, mientras el guard O(n) no crece cuadráticamente
(se verifica por conteo de hashes, no por tiempo de pared, para evitar flakes).

### 3.3 Fricción proporcional (definición operativa)

```
riesgo(r) = w1·irreversible + w2·superficie_contrato + w3·riesgo_datos
friccion(r) = clamp(F0 + riesgo(r), F0, Fmax)
```

- `riesgo = 0` → fix + test de regresión (sin ficha completa).
- `riesgo` medio → ficha `FIC` + criterios demostrables.
- `riesgo` alto → spec `SPE` + ADR + rollback + `DEC`.

La matriz N2 implementa la selección: se elige el artefacto que minimiza el
costo esperado `E = P(error)·C(error) + C(proceso)`, no el que más guste.

## 4. Criterios de aceptación (testeables)

| ID | Criterio | Test |
|---|---|---|
| AC-01 | N1 contiene `DOM`, `FIC`, `HIT`, `FRC`, `OWN`, `DEC` con sus palabras clave | `test_n1_has_fdd_codes` |
| AC-02 | N1 tiene exactamente 47 códigos, sin duplicados y ≤60 líneas | `test_n1_budget_and_count` |
| AC-03 | `base` y `min` tienen el mismo conjunto N1 y la misma versión | `test_principles_integrity` (existente) |
| AC-04 | Taxonomía = biyección sobre N1: sin ausentes y sin fantasmas (`DOR`/`OPS`/`QLT` fuera del N1) | `test_taxonomy_is_exact_bijection` |
| AC-05 | Categoría `FDD` = `{DOM, FIC, FRC, OWN}`; `GOV` incluye `HIT` y `DEC` | `test_fdd_and_gov_taxonomy` |
| AC-06 | N2 contiene la matriz con FDD/DDD/SDD/CDD/TDD/BDD/ATDD/RDD | `test_n2_has_dd_selection_matrix` |
| AC-07 | `WFP`/`MCL`/`MKS`/`RPA` están en N2 y no en N1; alias resuelven a una sección existente | `test_demoted_codes_have_home` |
| AC-08 | Existen `docs/fdd/{README.md,dominio.md,ficha-template.md}` y la ficha declara los 4 hitos | `test_fdd_artifacts_exist` |
| AC-09 | Guard de duplicados O(n) equivale al oráculo O(n²) en property-based | `test_duplicates_equivalent_to_oracle` |
| AC-10 | Guard escala lineal (hashes lineales; oráculo cuadrático en comparaciones) | `test_duplicates_scaling` |
| AC-11 | Las tres copias declaran versión `4.0.0`; `_full.md` no reintroduce N1/N2 | `test_principles_integrity`, `test_principles_full_drift` |
| AC-12 | `pyproject.toml` y `CHANGELOG.md` alineados en 11.97 | `test_version_alignment` |

## 5. Plan de migración (expand/contract)

1. **Expand**: añadir el guard y los tests en RED; los artefactos `docs/fdd/`.
2. **Migrate**: actualizar N1 + taxonomía + N2 en `base` y `min`; añadir N3 FDD;
   subir versión a 4.0.0 en las tres copias.
3. **Contract**: retirar de N1 los 4 GUIDE (quedan en N2); verde en
   `validate_skills`, `generate_skill_specs`, `xtask check`.
4. **Docs**: CHANGELOG 11.97, roadmap, MEJORAS, ADR-0106 local; `publish.py`.

## 6. Riesgos y mitigación

| Riesgo | Mitigación |
|---|---|
| N1 se vuelve una lista de deseos | Solo CHECK; la matriz y los detalles van a N2/N3 |
| Romper citas existentes | `UPG·NAM·FRS` intacto; alias y códigos movidos siguen válidos |
| Tests frágiles por timing | La escala se mide por conteo de hashes/comparaciones |
| Doble fuente de verdad | Ficha = estado de la feature; spec = contrato del cambio irreversible; ADR = decisión cerrada |
| Conflicto `SPE` vs `FRC` | `FRC` acota `SPE`: spec obligatoria solo para riesgo alto |

## 7. Lo que NO se aplica y por qué

- **Penpot / maqueta obligatoria**: no aplica a un harness sin UI de producto.
- **Waves como objeto de primer nivel**: se representa en la ficha (`Olas`),
  no como entidad del harness; evita una segunda fuente de estado.
- **Adopción literal de las 5 fases FDD de 1997**: la fase «modelo general»
  completa antes de la primera feature es cascada; se sustituye por `DOM`
  incremental + `FND` walking skeleton.
- **Benchmark LLM-juez de adherencia**: fuera de alcance de este ciclo; la
  evidencia es estructural y determinista.
