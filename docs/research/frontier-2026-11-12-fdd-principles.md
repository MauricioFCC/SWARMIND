# Frontier research — FDD y metodologías «-DD» aplicadas a los principios de SWARMIND

| Campo | Valor |
|---|---|
| Fecha | 2026-11-12 |
| Tarea explícita | Comparar el harness FDD de `FRONTIER_RESEARCH` con la metodología de SWARMIND y decidir qué cambiar, quitar, mejorar, mergear y refactorizar de los principios universales |
| Estado | Research cerrado; decisión H3 (híbrido selectivo) implementada en la spec `docs/specs/principles-v4-fdd-merge.md` |
| Fuente local | `local://FRONTIER_RESEARCH/FR-0009-11NOV2026-Articulos-varios-linkeding.md` (referencia a FDD y `arielelevy/fdd`) |
| Alcance | Principios universales (`base_principles.md`, `.min.md`, `_full.md`) y su sistema de integridad; no se reimplementa el harness |

## 0. Pregunta de investigación

¿Qué debe adoptar SWARMIND del FDD (Feature-Driven Development) y del resto de
metodologías «-DD» (DDD, SDD, CDD, TDD, BDD, ATDD, RDD) **sin** degradar la
adherencia, el costo de contexto ni la verificabilidad de sus 45 códigos N1?

La respuesta no es «adoptar FDD completo» ni «descartarlo»: es un **merge
selectivo** donde cada capa resuelve un problema distinto y la fricción se
dimensiona por riesgo.

## 1. Método (BUSEV + SIFT)

1. **Estrategia 1 — fuente primaria**: README y `skills/fdd/SKILL.md` del repo
   canónico `arielelevy/fdd` v2.5; `FR-0009` y la metodología local MESA v2.2.
2. **Estrategia 2 — refutación**: literatura que critica la especificación
   exhaustiva previa (Fowler/Böckeler sobre SDD; Preston-Werner sobre el exceso
   de waterfall) y que exige entregas verticales pequeñas.
3. **Escalada 4×** solo donde hubo contradicción real: DDD (Evans), BDD
   (North), ATDD, CDD (OpenAPI), RDD, AGENTS.md, Anthropic «Building effective
   agents», Parallel Change y SemVer.
4. **SIFT** por fuente: ¿quién lo dice?, ¿es primaria?, ¿fecha?, ¿aplica a
   agentes o solo a equipos humanos?
5. **Claim-trace**: cada afirmación de este documento apunta a una URL leída o
   queda marcada `[UNVERIFIED]`.

## 2. Fuentes consultadas

| # | Fuente | URL | Qué se usó | Estado |
|---|---|---|---|---|
| F1 | FDD v2.5 — README | https://github.com/arielelevy/fdd | ficha por feature, mapa de dominio, 4 hitos, propiedad de archivos, coordinador único, fricción proporcional | Leída |
| F2 | FDD v2.5 — `skills/fdd/SKILL.md` | https://raw.githubusercontent.com/arielelevy/fdd/main/skills/fdd/SKILL.md | plantilla de ficha, hitos, olas, estado para retomar, «afirmar sin evidencia = no hecho» | Leída |
| F3 | FDD original (De Luca & Coad, 1997; *Java Modeling in Color*, 1999) | — | cinco fases: modelo general, lista de features, plan, diseño y construcción por feature | `[UNVERIFIED]` (libro, sin copia digital) |
| F4 | DDD — Evans, *Domain-Driven Design* (2003) | — | lenguaje ubicuo, bounded contexts, agregados, modelo de dominio | `[UNVERIFIED]` (libro) |
| F5 | Fowler/Böckeler — SDD y sus 3 herramientas | https://martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html | crítica a la spec exhaustiva previa; spec como contrato, no como cascada | Leída |
| F6 | Dan North — Introducing BDD (2006) | https://dannorth.net/blog/introducing-bdd/ | escenarios de comportamiento, nombres-sentencia, aceptación automatizada | Leída |
| F7 | OpenAPI Specification v3.2.1 | https://spec.openapis.org/oas/latest.html | CDD: contrato de interfaz como fuente previa para consumidores y agentes | Leída |
| F8 | Preston-Werner — Readme Driven Development (2010) | https://tom.preston-werner.com/2010/08/23/readme-driven-development.html | RDD: documentar uso antes del código; «implementación perfecta de la especificación equivocada» | Leída |
| F9 | AGENTS.md | https://agents.md/ | AGENTS.md como README para agentes; mapa corto, no manual | Leída |
| F10 | Anthropic — Building effective agents | https://www.anthropic.com/engineering/building-effective-agents | workflows vs agentes; simplicidad; patrones evaluator-optimizer/voting | Leída |
| F11 | SemVer 2.0.0 | https://semver.org/ | MAJOR/MINOR/PATCH para versionar el cambio de contrato de los principios | Leída |
| F12 | Parallel Change (expand/contract) | https://martinfowler.com/bliki/ParallelChange.html | migración compatible de códigos: expandir, migrar, contratar | Leída |
| F13 | MESA v2.2 + BUSEV (local) | `local://FRONTIER_RESEARCH/mesa adversarial y busqueda metodos/` | ficha única, kill criteria, TTL+dueño, triangulación | Leída |

## 3. Qué aporta FDD (y qué ya existía)

FDD v2.5 no es el FDD de 1997 trasplantado: es una reescritura para agentes que
trabajan en sesiones cortas y que otra sesión debe poder retomar sin el chat.
Sus piezas y su solapamiento real con SWARMIND:

| Pieza FDD | Problema que resuelve | Estado en SWARMIND (v3.6.0) |
|---|---|---|
| Constitución y arquitectura inmutables | ningún cambio, ni el más chico, se sale de las reglas | Cubierto parcialmente por `FND`, `ARQ`, `AGR`, `CLA`; falta la idea de «puerta única» explícita |
| Mapa de dominio (`docs/dominio.md`) | la sesión nueva sabe qué entidades hay sin explorar el repo | **Ausente** (solo DDD implícito en `CLA`: «dominio puro») |
| Feature con nombre de resultado + corte vertical | evita «arreglar rules.py» y capas enteras sin valor | **Ausente** como regla; `FDE` habla de producto, no de unidad de entrega |
| Una ficha por feature | objetivo, alcance, criterios, dominio, dueños, decisiones, evidencia y próximo paso en un lugar | Solo `SPE` (spec por tarea), que FDD critica cuando es exhaustiva |
| Hitos diseñado → implementado → verificado → integrado | distingue propuesto de hecho, verificado e integrado | `GATE` cubre claim→evidence→gate, pero no la distinción de hitos ni el «integrado solo humano» |
| Decisiones cerradas con motivo | no reabrir lo decidido; invariantes con una sola puerta | **Ausente** (los ADR son post-decisión, no la tabla viva de la feature) |
| Archivos y dueños | dos frentes no editan el mismo archivo | **Ausente**; el fan-out puede colisionar |
| Un solo coordinador | una autoridad de escritura por ola | **Ausente** como regla (existe orquestador, no propiedad) |
| Preguntas HITL centralizadas | no bloquear el avance por preguntas dispersas | **Ausente** |
| Fricción proporcional al riesgo | no aplicar el mismo proceso a un typo que a una migración | **Conflicto** con `SPE` («sin spec = sin start») |
| Estado para retomar | la sesión nueva continúa sin el chat | Parcial en `RPA` (re-anclaje) y `BTR` (trazas), no como artefacto |
| «Afirmar sin evidencia = no hecho» | elimina el falso-DONE | Ya cubierto por `GATE` (0 false-DONE) |

## 4. Las «-DD» no compiten: atacan problemas distintos

| Enfoque | Eje | Qué resuelve | Dónde encaja en SWARMIND |
|---|---|---|---|
| FDD | La feature | planificar, dividir y entregar valor en cortes verticales | capa de entrega (nueva) |
| DDD | El dominio | modelar reglas complejas y linguaje ubicuo | `DOM` + `CLA` |
| SDD | La especificación | precisión previa de contratos y criterios | `SPE` acotado por riesgo |
| CDD | El contrato de interfaz | cliente y servidor/agente en paralelo | `SPE` para APIs públicas (OpenAPI/AsyncAPI) |
| TDD | La prueba | calidad a nivel de código | `TST`, `PBT`, `AAA` |
| BDD | El comportamiento | alinear negocio y aceptación | criterios de la ficha (condición→acción→resultado) |
| ATDD | La aceptación | criterios automatizados antes de implementar | `GATE` + criterios demostrables de la ficha |
| RDD | El uso | documentar cómo se usa antes de codificar | README-first en librerías/CLI públicas |

La lectura correcta es **selección por requisito**, no adopción simultánea. FDD
aporta el contenedor (ficha, hitos, dueños); DDD aporta el mapa; SDD/CDD
aportan el contrato cuando el costo de equivocarse es alto; TDD/BDD/ATDD
aportan la verificación; RDD aporta la experiencia de uso.

## 5. Inventario medido de SWARMIND (antes)

| Métrica | Valor | Cómo se midió |
|---|---|---|
| Códigos N1 | 45 (43 de 3 letras + `GATE`/`FAIL`) | regex `^([A-Z][A-Z0-9]{1,4}):` sobre el primer bloque cercado |
| Líneas N1 | 45 | líneas no vacías del bloque |
| Tamaño N1 | 5 262 caracteres (`base`), 5 158 (`min`) | longitud del bloque |
| Códigos en la taxonomía | 44 | tabla `| CAT | ... | códigos |` |
| Códigos N1 ausentes de la taxonomía | `EDV`, `RSV` | diferencia de conjuntos |
| Códigos fantasma en la taxonomía | `DOR` | diferencia de conjuntos |
| Códigos N1 de modo GUIDE | `WFP`, `MCL`, `MKS`, `RPA` | tabla de taxonomía (SYS = GUIDE) |
| Skills que citan `UPG·NAM·FRS` | 41 | grep en `.opencode/skills/*/SKILL.md` |
| Validadores de integridad | 3 suites | `test_principles_integrity.py`, `test_principles_adr0098.py`, `test_principles_full_drift.py` |
| Duplicados N1: complejidad | O(n²) | `codes.count(code)` por cada código |

Hallazgo central: **el N1 no tiene capa de entrega ni de dominio**, y su
taxonomía ya está desincronizada (2 ausentes + 1 fantasma). Añadir FDD sin
arreglar eso habría aumentado el drift.

## 6. Hipótesis comparadas

| Hipótesis | Descripción | Adherencia | Costo de contexto | Escalabilidad | Robustez | Reproducibilidad |
|---|---|---|---|---|---|---|
| **H1 — Adopción completa** | Volcar las 9-10 piezas FDD al N1 | Alta para FDD, diluye las 45 reglas existentes | +~10 líneas siempre inyectadas (~+20 %) | Baja: N1 se acerca al techo de 60 líneas | Media: duplica `GATE`/`SPE` | Media: más reglas que recordar |
| **H2 — Reemplazo minimalista** | Un solo meta-principio + matriz de selección; mover todo lo demás a N3 | Baja: pierde chequeos atómicos que hoy matan mutantes | −~90 % del N1 | Alta | Baja: nada que un gate pueda verificar | Baja: depende del juicio del agente |
| **H3 — Merge selectivo (elegida)** | 6 códigos FDD/DDD nuevos; 4 GUIDE degradados a N2; matriz de selección en N2; taxonomía biyectiva; alias para códigos movidos | Alta: cada regla nueva es CHECK | Mejora: N1 5 262 → 4 139 caracteres (−21,3 %) con +6 capacidades; la matriz va a N2 | Alta: N1 47 ≤ 60; gate O(n²)→O(n) | Alta: elimina fantasmas y dangling | Alta: tests deterministas + property-based |

### Por qué gana H3

- **Accuracy/adherencia**: 6 reglas atómicas y verificables (`DOM`, `FIC`,
  `HIT`, `FRC`, `OWN`, `DEC`) en lugar de un bloque narrativo. Las reglas que
  ya funcionan no se tocan.
- **Latencia/costo**: el N1 pasa de 45 a 47 líneas, pero de 5 262 a 4 139
  caracteres (−21,3 %): las reglas se vuelven índices atómicos y el detalle
  vive en N2/N3 (DRFR: densidad > detalle). La matriz «-DD» entra en N2, que
  solo se inyecta con presupuesto >70 %, así que el costo siempre-inyectado
  baja pese a sumar seis capacidades.
- **Escalabilidad**: el chequeo de duplicados pasa de O(n²) a O(n) con
  `Counter`; la validación de taxonomía pasa de comprobar 5 códigos contra una
  tabla de 44 a una biyección O(n+m) sobre 47.
- **Robustez**: cero códigos fantasma, cero N1 sin categoría, alias explícito
  para lo degradado; los 5 códigos del ADR-0098 conservan su lugar.
- **Reproducibilidad**: todo se prueba con suites deterministas (sin red) y
  property-based para el checker de duplicados.

## 7. Gap analysis (qué cambia cada decisión)

| Gap | Decisión | Código/artefacto |
|---|---|---|
| No hay mapa de dominio | **Añadir** (DDD) | `DOM` + `docs/fdd/dominio.md` |
| No hay unidad de entrega con nombre de resultado | **Añadir** (FDD) | `FIC` + `docs/fdd/ficha-template.md` |
| No hay hitos ni «integrado solo humano» | **Añadir** (FDD + HITL) | `HIT` |
| No hay decisiones cerradas vivas | **Añadir** (FDD) | `DEC` |
| Fan-out sin propiedad de archivos | **Añadir** (FDD) | `OWN` |
| `SPE` aplica la misma fricción a todo | **Mergear/reconciliar** (FDD + SDD/CDD) | `FRC` + matriz N2 |
| 4 códigos GUIDE ocupan N1 | **Quitar de N1** (degradar a N2) | `WFP`, `MCL`, `MKS`, `RPA` |
| Taxonomía con 2 ausentes y 1 fantasma | **Corregir** | tabla biyectiva |
| `CMT`/`ATM` y `ERR`/`FST` se solapan | **Mantener** (ya son atómicos y ADR-0098 los fija); documentar el solapamiento como complemento, no duplicado | sin cambio |
| No hay criterio para elegir «-DD» | **Añadir matriz** en N2 | tabla de selección |
| Detección de duplicados O(n²) | **Refactorizar** | `harness/context/principles_guard.py` |

## 8. Matriz de selección por requisito (la «mezcla» aplicada)

| Requisito | Enfoque dominante | Artefacto mínimo | Gate |
|---|---|---|---|
| Feature de usuario con valor | FDD | ficha con nombre de resultado y corte vertical | criterios demostrables + `HIT` |
| Dominio con reglas complejas | DDD | `docs/fdd/dominio.md` (entidades, agregados, lenguaje ubicuo) | revisión de mapa + `DOM` |
| API pública o contrato entre servicios | CDD/SDD | OpenAPI/AsyncAPI + spec de cambio | contrato versionado + `SPE`/`SVE` |
| Cambio de comportamiento | TDD/ATDD | test rojo con criterio de aceptación | `TST` + `GATE` |
| Comportamiento de negocio acordado | BDD | escenario condición→acción→resultado en la ficha | criterio aceptado por la persona |
| Migración irreversible o de datos | SDD | spec + ADR + rollback | `SPE` + `SBX` + `DEC` |
| Librería, SDK o CLI pública | RDD | README de uso antes del código | ejemplo ejecutable |
| Bug puntual | Fix + regresión | test que reproduce + fix | `TST` (sin ficha completa) |
| Cambio visual | Maqueta + BDD | recorrido con estados + escenario | aprobación humana |
| Infraestructura interna | FDD (ola 0) | ficha/tarea con criterio observable | `GATE` |

Regla de oro: **la fricción crece con el costo de equivocarse**, no con el
gusto del agente. Un typo no necesita constitución; un cambio de contrato sí.

## 9. Evidencia, límites y lo que NO se afirma

- El piloto de FDD reporta −43 % de tokens para retomar, −56 % de tokens
  nuevos y −50 % de comandos con 5/5 respuestas correctas. Es **una corrida por
  condición**: se usa como **indicio**, no como medición estable
  (`[UNVERIFIED]` como efecto generalizable).
- No se ejecutó un benchmark propio de adherencia con LLM-juez para esta
  decisión. El argumento de calidad es estructural (reglas atómicas,
  taxonomía biyectiva, artefactos verificables), no un A/B de calidad.
- No se adopta Penpot ni ninguna herramienta visual: la maqueta queda como
  referencia opcional en la ficha, no como dependencia del harness.
- No se copia el corpus FDD: se citan y adaptan sus invariantes. El texto
  original tiene licencia MIT; aun así se prefiere una formulación propia y
  corta para no arrastrar 500 líneas al contexto.
- Los números de tokens del N1 posterior son mediciones locales del bloque
  (caracteres), no tokens de un tokenizer específico.

## 10. Amenazas a la validez

| Amenaza | Mitigación |
|---|---|
| Sesgo de fuente única (FDD) | Triangulación con DDD/SDD/BDD/CDD/RDD y con la crítica de Fowler |
| Métricas del piloto no replicadas | Marcadas como indicio; no se usan para justificar el merge |
| N1 como «lista de deseos» | Solo entran reglas con CHECK verificable; el resto va a N2/N3 |
| Ruptura de convenciones existentes | `UPG·NAM·FRS` intacto; alias para códigos movidos; ADR-0098 preservado |
| Drift futuro | Taxonomía biyectiva + tests + `xtask check` en CI |

## 11. Referencias

1. FDD v2.5 — https://github.com/arielelevy/fdd
2. FDD skill — https://raw.githubusercontent.com/arielelevy/fdd/main/skills/fdd/SKILL.md
3. Fowler/Böckeler, *SDD with 3 tools* — https://martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html
4. Dan North, *Introducing BDD* — https://dannorth.net/blog/introducing-bdd/
5. OpenAPI 3.2.1 — https://spec.openapis.org/oas/latest.html
6. Preston-Werner, *Readme Driven Development* — https://tom.preston-werner.com/2010/08/23/readme-driven-development.html
7. AGENTS.md — https://agents.md/
8. Anthropic, *Building effective agents* — https://www.anthropic.com/engineering/building-effective-agents
9. SemVer 2.0.0 — https://semver.org/
10. Fowler, *Parallel Change* — https://martinfowler.com/bliki/ParallelChange.html
11. Evans, *Domain-Driven Design* (2003) — `[UNVERIFIED]`
12. De Luca & Coad, *Java Modeling in Color with UML* (1999) — `[UNVERIFIED]`
