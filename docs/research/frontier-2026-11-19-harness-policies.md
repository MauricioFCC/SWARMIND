# Frontier Research — Políticas de harness y revisión ciega (FR-0010)

- **Fecha:** 2026-11-19
- **Entrada:** `FR-0010-17NOV2026-Articulos-varios-linkeding.md` (Google Drive,
  4 058 líneas de enlaces y posts).
- **Dueño del ciclo:** `harness/validation` + doctrina (`AGENTS.md`).
- **Skill:** `frontier-engineering` (load → research → design → spec → TDD →
  docs).

## 1. Contexto

FR-0010 es un agregado heterogéneo: cursos, repos, papers y posts. El filtro
aplicado es **¿qué cambia una decisión de ingeniería en SWARMIND?** Se
descartaron herramientas de terceros sin relación con el harness (editores de
vídeo, dashboards 3D, juegos, cursos de SQL) y se conservaron los conceptos que
afectan al diseño del arnés, a sus políticas o a sus gates.

## 2. Conceptos seleccionados (con fuente)

| # | Concepto | Fuente | Qué aporta |
|---|---|---|---|
| C1 | **Agent = LLM + harness** | Post "Agent == LLM + Harness" (FR-0010 L1651-1688) | Taxonomía de 5 piezas: contexto, formato de tool call, guardrails, runtime y checks. Sirve de checklist de auditoría. |
| C2 | **EGM (Elephant Goldfish Model)** | https://github.com/google/elephant-goldfish-model (verificado) | El "elefante" conserva el contexto y escribe la especificación; los "peces" revisan **sin haber visto la conversación**, porque quien revisa con todo el contexto hereda los mismos puntos ciegos. |
| C3 | **Binnacle (maker-checker determinista)** | FR-0010 L1087-1105 (repo) | Checks deterministas antes de que ningún modelo juzgue; dataset dorado bloqueado; "quien construye no corrige". |
| C4 | **Harness engineering: planner/generator/evaluator** | https://github.com/walkinglabs/learn-harness-engineering (verificado) | Presupuesto y alcance: el mismo modelo con planner+generator+evaluator pasa de 9 $/20 min/fallo a 200 $/6 h/éxito. El coste del arnés se justifica por resultado, no por número de agentes. |
| C5 | **Harness²: auto-ajuste del arnés, no del modelo** | https://github.com/google-research/harness2 (verificado) | Ajusta instrucciones, herramientas, memoria y skills con resultados observados, sin reentrenar. SWARMIND ya tiene `harness/harness2/`. |
| C6 | **Dream-RSI: "soñar" estrategias offline** | https://dream-rsi.com/ (verificado) | Releer intentos ok/fail y ensayar variantes sin ejecutar el modelo; no mejora la inteligencia, mejora la búsqueda. SWARMIND ya tiene `dream_replay.py`. |
| C7 | **Coste real de los equipos de agentes** | Reporte Claude Code citado en FR-0010 L3019-3039 `[UNVERIFIED: solo el post, no el PDF]` | Los equipos de agentes en plan mode consumen ~7× los tokens de una sesión; el fan-out debe justificar su overhead. |
| C8 | **Fuga de secretos vía configuración del agente** | https://apiiro.com/blog/coding-agents-leaking-secrets-github-dont-ask-again (verificado) | 104 185 copias públicas de `settings.local.json`, 1 122 con secretos reales y 215 indetectables por gitleaks/TruffleHog: aprobar comandos con secretos los persiste. |
| C9 | **Revisión de código a escala de IA** | https://claude.dev/blog/solving-code-review-at-anthropic/ (verificado) | Con cobertura alta, la revisión se optimiza para el mínimo tiempo humano que no aumente revertidos/incidentes: el criterio es riesgo, no volumen leído. |
| C10 | **JevEval: evaluación descompuesta** | FR-0010 L1767-1799 (post) `[UNVERIFIED: repo no consultado]` | Sustituye la nota única del juez por preguntas con pesos (sí/no, escala, elección) y aritmética fija: si baja la nota, se sabe qué pregunta bajó. |

## 3. Hipótesis evaluadas

Criterios: precisión de la mejora, latencia/coste, escalabilidad, robustez ante
fallos y reproducibilidad.

| H | Hipótesis | Precisión | Coste | Escala | Robustez | Reproducible | Veredicto |
|---|---|---|---|---|---|---|---|
| H1 | **Revisión ciega (EGM) + gates deterministas (Binnacle)** reduce puntos ciegos heredados y fugas de secretos en el prompt de revisión | Alta: ataca la causa (contexto compartido) con checks binarios | O(n) local, 0 tokens | O(1) por diff | Alta: falla cerrado (bloquea) | Sí: salida determinista | **Aceptada** |
| H2 | Sustituir el juez LLM por evaluación descompuesta (JevEval) | Media-alta | Igual o menor (varias preguntas binarias vs. una generativa) | Alta | Media (depende de las preguntas) | Alta | Aplazada: exige set etiquetado para calibrar pesos (EDV) |
| H3 | Auto-ajuste estilo Harness² de prompts/tools/skills | Alta en paper | Alto (re-rollouts) | Media | Media (riesgo de drift) | Media | No aplicable ahora: `harness/harness2/` ya existe y el AC de mejora no está medido |
| H4 | "Dreaming" offline de estrategias | Media | ~0 | Alta | Alta | Alta | No aplicable ahora: `dream_replay.py` ya cubre el replay; falta corpus de trazas |
| H5 | Fan-out de subagentes como política por defecto | Baja: 7× tokens | Alto | Media | Baja (más superficie de fallo) | Media | **Rechazada** como default; se exige justificación por tarea |

## 4. Gap analysis (IDP)

Auditoría del repositorio antes de escribir código:

| Capacidad existente | Evidencia | Gap real |
|---|---|---|
| Revisión cruzada por familia de modelo | `harness/validation/cross_review.py` | Asigna otra familia, pero **no aísla el contexto** del autor. |
| Gate anti-vibe (deep scan + 2.º agente) | `harness/validation/vibe_review_gate.py` | Recibe solo el diff, pero **no la spec** ni un checklist de ACs. |
| Gate de evidencia de fix | `harness/validation/fix_evidence.py` | Verifica repro/test, no el paquete de revisión. |
| Escaneo de secretos del repo | `harness/qa/security_policy.py` + `scripts/security_scan.py` | Escanea el repo versionado, **no el prompt que se envía a un revisor**. |
| Harness², Dream-RSI, Co-Harness | `harness/harness2/`, `dream_replay.py`, `harness_critic.py` | Implementados; no se reimplementan. |

**Conclusión:** falta una pieza determinista y pequeña que convierta
`spec + diff` en un **paquete de revisión ciega** con gates previos. No existe
hoy: es un hueco, no un duplicado.

## 5. Diseño (resumen)

`harness/validation/blind_review.py`:

- `extract_acceptance_criteria(spec_md) -> tuple[str, ...]`: ids `AC-*` de
  líneas estructurales (viñeta, fila o id al inicio), una clave por línea,
  tope 50; fallback a la sección "Criterios de aceptación". La prosa que
  menciona ids no infla la lista.
- `redact(text)`: secretos (PEM, GitHub, OpenAI, AWS, Slack, asignaciones
  entrecomilladas) → `<redacted:tipo>`; rutas personales (`C:\Users\<x>`,
  `/home/<x>`, `/Users/<x>`) → `<user>`; idempotente. Los nombres de ejemplo
  (`alice`, `example`, `<x>`) se redactan pero no bloquean. Vive en
  `harness/validation/prompt_sanitizer.py` para reutilizarlo en cualquier
  prompt.
- `build_blind_packet(spec, diff, max_diff_chars, max_files) -> BlindPacket`:
  gates deterministas **antes** de cualquier modelo; si un gate falla, el
  paquete no está aprobado para revisión. El truncado deja marca explícita.
- `render_markdown(packet)`: prompt reproducible con intención, tabla de gates,
  ACs y diff redactado. Sin timestamps ni ruta de la conversación.

Complejidad: `O(|spec| + |diff|)` en tiempo y memoria por 6 pasadas regex de
coste lineal; sin red y sin modelo. Antes: la revisión dependía de un prompt
manual con contexto completo (no medible, no reproducible).

## 6. Fuentes

Verificadas con fetch el 2026-11-19:

- https://github.com/google/elephant-goldfish-model
- https://github.com/google-research/harness2
- https://github.com/walkinglabs/learn-harness-engineering
- https://dream-rsi.com/
- https://apiiro.com/blog/coding-agents-leaking-secrets-github-dont-ask-again
- https://claude.dev/blog/solving-code-review-at-anthropic/

`[UNVERIFIED]` (solo mención en el agregado, sin abrir el original):

- Reporte Claude Code (7× tokens en plan mode) — citado en FR-0010 L3019-3039.
- JevEval — citado en FR-0010 L1767-1799.
