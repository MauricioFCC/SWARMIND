# Repo image y documentación — investigación de frontera (2026-11-06)

> Pregunta: ¿cómo presentar SWARMIND para que un visitante entienda qué es, cómo
> se usa y qué evidencia lo respalda en <2 minutos, sin que la documentación
> derive de la realidad? Fuentes leídas en esta sesión; lo no verificado va
> marcado `[UNVERIFIED]`.

## 1. Qué valora un README de harness agéntico (2026)

De [README best practices (2026)](https://github.com/daverage/readme.md-best-practice)
y [GitHub README template 2026](https://gingiris.github.io/growth-tools/blog/2026/04/02/github-readme-template-guide):

- **Primer párrafo = qué + por qué es distinto + para quién** (no historia).
- Badges bajo el título; **quickstart ejecutable**; demo/GIF o diagrama.
- **Diagramas como código** (Mermaid) mejor que imágenes: versionables y
  buscables por humanos y agentes.
- Estructura para lectores con prisa: features escaneables, árbol del repo,
  documentación, roadmap, changelog, licencia.
- Errores frecuentes: README demasiado largo, changelog embebido, claims sin
  evidencia.

## 2. Documentación mantenible: Diátaxis

De [diataxis.fr](https://diataxis.fr/) y
[Read the Docs — documentation structure](https://docs.readthedocs.com/platform/stable/explanation/documentation-structure.html):

- Cuatro necesidades y formas: **tutoriales** (aprender), **how-to** (resolver),
  **reference** (consultar) y **explanation** (entender).
- La estructura reduce preguntas al autor y hace predecible dónde va cada cosa.
- El índice debe exponer las cuatro categorías; los catálogos (agentes/skills)
  son *reference* y no deben duplicarse a mano: se **generan desde la SSOT**.

## 3. Qué se espera de un harness agéntico (2026)

De [Harness-Bench (arXiv 2605.27922)](https://arxiv.org/html/2605.27922v1):

- Un harness se evalúa como **tarea + modelo + configuración de harness +
  sandbox + evaluador + traza**; el diseño del harness explica diferencias de
  rendimiento entre sistemas con el mismo modelo.
- Importan: herramientas expuestas, política de contexto, estado, permisos y
  recuperación; no solo el modelo.

De [Red Hat — blueprint cloud-native agents (2026-07)](https://developers.redhat.com/articles/2026/07/20/architect-open-blueprint-cloud-native-ai-agents):

- Modelo + harness + sandbox como componentes intercambiables tras interfaces
  abiertas: **MCP** para herramientas, **A2A** para coordinación, sandbox API
  para aislamiento, **SPIFFE** para identidad, **OpenTelemetry/MLflow** para
  trazas, prompts, latencias y costos.
- Advertencias: convenciones GenAI de OTel aún en evolución; memoria envenenada
  es problema abierto; autoría de políticas de sandbox es compleja.

De [Claude agent containment / sandboxing](https://support.claude.com/en/articles/17316105-agent-containment-best-practices-sandboxing-private-beta):

- No montar credenciales (`~/.ssh`, `.env`) dentro del sandbox; separar fase de
  setup (red) de fase de ataque (sin red); aprobar acciones de escritura;
  supervisar runs con red y poder detenerlos.

**Implicación para SWARMIND**: el README debe declarar el modelo (harness),
separar lo que está probado de lo que es roadmap, y exponer límites de sandbox
y supervisión humana — no vender autonomía total.

## 4. Diagnóstico del repo actual (leído)

| Problema | Evidencia | Impacto |
|---|---|---|
| Conteos obsoletos | README dice 42 skills/25 agentes/~7000 tests; realidad 49/26/7745 | Desconfianza y ruido |
| Documentación duplicada a mano | `docs/src/es/SUMMARY.md` lista 20 agentes/34 skills; hay 26/49 | Deriva garantizada |
| Intro de docs desactualizada | `docs/src/es/README.md` dice 35 skills/22 agentes/5383 tests | Mala primera impresión |
| Claims de deuda inexactos | “0 files over 500”; el gate reporta >900 advisory | Claim falso |
| Sin índice de docs en `docs/` | `docs/README.md` no existe | GitHub muestra carpeta sin guía |
| Sin chequeo de enlaces | no hay gate de links internos | Links rotos silenciosos |
| README 441 líneas con changelog embebido | compite con CHANGELOG | Difícil de escanear |

## 5. Hipótesis evaluadas

| # | Hipótesis | Precisión | Mantenimiento | Robustez | Reproducibilidad | Veredicto |
|---|---|---|---|---|---|---|
| H1 | Reescribir README corto + diagrama Mermaid + mapa de docs | alta | alto | alta | alta | **Elegida** |
| H2 | Solo corregir números | baja | bajo | baja | media | Rechazada (parche cosmético) |
| H3 | Generar catálogos de agentes/skills desde la SSOT | alta | muy alto | alta | alta | **Elegida** |
| H4 | Migrar mdbook a docs/src/es y reescribir todo | media | medio | media | media | Parcial (solo índice/hubs; no reescribir 263 páginas) |
| H5 | Añadir un gate de enlaces internos | alta | alto | alta | alta | **Elegida** |

## 6. Diseño aplicado

```
.opencode/agents/*.md ─┐
.opencode/skills/* ────┼─► gen_docs_index.py ─► docs/src/es/{agents,skills}/INDEX.md
registry.yaml ─────────┘                          (tablas + conteos, --check)

README.md / docs/** ─────► check_docs_links.py ─► exit 1 si un link relativo roto
                                                   (mdbook `/assets/...` resuelto)
```

Complejidad: generación `O(A + S)` (A agentes, S skills); chequeo de enlaces
`O(L)` (L enlaces) — ambos lineales, sin O(n²).

**Antes**: catálogos manuales y claims sin verificación; **después**: índice
generado desde la SSOT y gate ejecutable que impide la deriva.

## 7. Fuentes leídas

- https://github.com/daverage/readme.md-best-practice
- https://gingiris.github.io/growth-tools/blog/2026/04/02/github-readme-template-guide
- https://diataxis.fr/
- https://docs.readthedocs.com/platform/stable/explanation/documentation-structure.html
- https://arxiv.org/html/2605.27922v1
- https://developers.redhat.com/articles/2026/07/20/architect-open-blueprint-cloud-native-ai-agents
- https://support.claude.com/en/articles/17316105-agent-containment-best-practices-sandboxing-private-beta

## 8. No aplicado (y por qué)

- **Migrar todo mdbook a español**: 263 páginas; reescritura masiva fuera de un
  ciclo y sin ganancia de precisión inmediata.
- **Social preview PNG**: el repo ya tiene SVG (`docs/src/en/assets/social-preview.svg`);
  GitHub no acepta SVG en “About” y requiere subir PNG a mano (no versionable).
- **Benchmark Harness-Bench propio**: requiere tareas sandbox y evaluadores;
  se documenta como roadmap, no se finge medido.
- **OpenTelemetry GenAI semconv estable**: sigue en evolución; se referencia,
  no se fija versión.
