# Skills de agentes — investigación de frontera (2026-11-01)

> Pregunta: ¿cómo se mejoran 44 skills de un harness multi-agente sin inflar
> contexto y sin que el routing degrade? Fuentes leídas en esta sesión (URL);
> lo no verificado va marcado `[UNVERIFIED]`.

## 1. Especificación vigente (Agent Skills)

De [agentskills.io/specification](https://agentskills.io/specification) y
[Claude skill authoring best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices):

- `name`: ≤64 chars, `[a-z0-9-]`; `description`: ≤1024 chars, debe decir **qué**
  hace y **cuándo** usarlo.
- El **body** idealmente <500 líneas; el resto va a ficheros enlazados
  (*progressive disclosure*): el agente los carga solo si los necesita.
- Checklist oficial: descripción específica, ejemplos concretos, workflows con
  pasos claros, referencias a un nivel de profundidad.

**Implicación**: el `description` es el índice de routing; el cuerpo es la
implementación. Sin contrato, cuerpo y descripción divergen sin señal.

## 2. Routing body-aware (el hallazgo que cambia el diseño)

[SkillRouter (arXiv 2603.22455)](https://arxiv.org/abs/2603.22455) mide, sobre
un benchmark derivado de SkillsBench con ~80K skills candidatas:

- Exponer solo **nombre + descripción** (progressive disclosure puro) cuesta
  **37–44 puntos** de accuracy de routing frente a usar todos los campos.
- Descripciones *destiladas del cuerpo* recuperan parte del gap, pero quedan
  **7–21 puntos** por debajo del routing all-field.
- Su pipeline body-aware (1.2B params, retrieve-and-rerank) logra **74.0 %
  Hit@1** con 13× menos parámetros y 5.8× más rápido que el mejor baseline.

**Decisión**: el contrato SDD guarda `routing.body_keywords` derivados del
cuerpo (tf-idf vs corpus), como señal barata lista para el router, sin cargar
el cuerpo completo en contexto.

## 3. Calidad de descripciones y solape

[skill-distill](https://github.com/lov-alt/skill-distill) (herramienta, no
paper) reporta métricas de su propio banco: descripciones cortas inútiles 44 %,
ruido no accionable 60 %+, routing ~49 % sin optimizar vs ~74 % con
descripciones distintas. `[UNVERIFIED]` como medición independiente (es
material del propio producto); se usa solo como dirección de diseño.

[EMNLP 2026 Findings — Agent Skill Evaluation and Evolution](https://aclanthology.org/2026.findings-emnlp.1427.pdf)
sistematiza evaluación de skills en: calidad, alineación con trayectoria y
resultado de tarea; y documenta que el solape/conflicto crece con la librería.
Nuestro gate `test_skill_overlap` (Jaccard + coseno) ya cubre el eje de solape.

## 4. Contratos verificables (ADR-0048 propio)

El repo ya define `SkillContract` (`harness/context/skill_contract.py`) con
`preconditions`, `postconditions`, `invariants` y `failing_test`. El gap
medido: **1 de 44** skills tenía `SKILL.spec.json`.

## 5. Fórmulas usadas

- **tf-idf** para keywords de body:

  ```
  score(t) = tf(t, body) · log((N + 1) / (df(t) + 1))
  body_keywords = top-8 por score, t ∉ tokens(description) ∪ stopwords
  ```

  Complejidad: `O(Σ tokens)` por corpus (una pasada + ordenación top-k con
  `k=8`, `O(V log V)` acotado por vocabulario).

- **Drift** por digest: `source_sha256 = sha256(SKILL.md)`; el spec solo es
  válido si coincide (coste `O(bytes)` por skill, 44 ficheros < 1 s).

- **Solape** (gate existente): `Jaccard(A,B) = |A∩B| / |A∪B|` sobre tokens de
  trigger; umbral de "pico" accionable en `test_skill_overlap`.

## 6. Tabla de decisión

| Necesidad | Técnica | Antes | Después | Fuente |
|---|---|---|---|---|
| Contrato formal por skill | spec derivado + digest | 1/44 specs | 44/44 | ADR-0048 + agentskills.io |
| Detectar body drift | `source_sha256` | 0 gates | 44 gates | agentskills.io (versionado) |
| Señal de routing | `routing.body_keywords` tf-idf | solo description | body-aware barato | arXiv 2603.22455 |
| No inflar contexto | keywords (no body) en spec | — | +8 términos/skill | progressive disclosure |
| Reproducibilidad | generador determinista + `--check` | manual | `0 cambios` verificable | best practices |

## 7. No aplicado (y por qué)

- **Router body-aware entrenado** (SkillRouter): requiere benchmark de queries
  reales y un modelo; fuera de alcance de un ciclo. Los keywords quedan como
  señal preparada.
- **Bench de routing end-to-end**: no hay corpus de consultas etiquetadas en el
  repo; montarlo sin ground truth sería decorativo.
- **SPLADE/embeddings de descripciones**: el harness ya usa embeddings en
  memoria; añadirlos al gate de skills duplicaría coste sin métrica de verdad.
