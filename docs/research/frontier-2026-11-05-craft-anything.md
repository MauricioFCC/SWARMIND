# Craft Anything — investigación profunda (2026-11-05)

> Repo: [storytold/craft-anything](https://github.com/storytold/craft-anything)
> (Rust, Apache-2.0/MIT, 14.6k stars, creado 2026-10-31, HEAD `main` leído hoy).
> Objetivo: extraer lo aplicable a las operaciones y agentes de ingeniería
> inversa de SWARMIND, no clonar la app.

## 1. Qué es (leído en README y docs)

Motor **clean-room** en Rust para (a) estudiar cómo funciona cualquier web, app,
juego o archivo y (b) pedir a un agente de código que construya una versión
propia, comparando el resultado con el original. Dos modos:

- **Clean room** (default): no lee código, archivos ni fuente de la página; solo
  lo observable desde fuera (capturas, texto visible, layout medido, ventanas).
  Las herramientas de interior se **rechazan** con remediación.
- **Deep**: permite leer código/archivos, JavaScript, memoria, tráfico, etc.
  (uso privado). No es un sandbox del SO (lo dice explícitamente).

**301 herramientas** de motor en 17 toolsets, cada una con tres caras: comando
CLI (`craft-anything-cli <id-con-guiones>`), herramienta MCP y herramienta del
agente. Ejemplos: `core_investigation_show`, `native_function_pseudocode`,
`web_page_capture`, `app_rebuild_claim_check`, `frida_script_run`.

## 2. El hallazgo principal: memoria de investigación + evidencia

Dos piezas de `crates/evidence` y `crates/engine/src/tools/investigation_tools.rs`
son directamente trasladables a cualquier harness:

### 2.1 Evidencia con id derivado del contenido

Cada resultado es un registro con `subject`, `operation`, `params`, `result`,
`confidence` (`observed|derived|inferred`), `authority` (`original-files`,
`our-run`, `earlier-record`, `outside-service`, `reasoning`), `environment`
(`clean_room`, `engine`, `host`), `limitations`, `coverage`, `locations`,
`links` y `carries_target_content` (marca de contenido no confiable del target).

El **id es el SHA-256 del JSON canónico** (RFC 8785: claves ordenadas por UTF-16,
sin espacios, escapes mínimos) excluyendo solo `summary`, `subject.name` y
`carries_target_content` (display-only). Consecuencias:

- la misma observación produce el mismo id → deduplicación idempotente;
- cualquier edición del registro almacenado se detecta al importar (`verify`);
- `links` permiten cadenas de derivación (evidencia derivada de evidencia).

### 2.2 Investigación durable y revisionada

`state.json` estructurado + renders Markdown (`brief.md`, `plan.md`,
`hypotheses.md`, `findings.md`, `handoff.md`) bajo `investigation/`:

- `brief` (pregunta, propósito, targets, restricciones, `done_when`);
- `plan` (pasos `todo|doing|done|blocked` con `why`);
- `hypotheses` (`testing|supported|refuted|abandoned`, predicción, evidencia
  a favor/en contra);
- `findings` (**exige ≥1 id de evidencia existente**);
- `unknowns` (pregunta abierta, severidad, probes, resolución que **exige
  evidencia**: "la ausencia no es prueba");
- `handoff` (dónde estamos, siguiente paso, trampas).

Concurrencia optimista: toda actualización lleva `based_on_revision`; una
revisión obsoleta devuelve `StaleRevision` con remediación. Hay lock de fichero
y escritura atómica (`write_atomic`).

## 3. Otras piezas relevantes

| Pieza | Qué aporta | Aplicable |
|---|---|---|
| `core_target_triage` | identifica el artefacto antes de tocarlo | Sí (implementado) |
| `core_feature_find` / `app_feature_follow` | trazar una feature de UI a código | Diseño futuro |
| `app_rebuild_claim_check` / `app_coverage_evaluate` | verificar afirmaciones de reconstrucción con evidencia | Sí (concepto) |
| `core_unknowns_show` / `core_person_ask` | preguntas abiertas y aprobación humana | Sí (unknowns) |
| `plugins.mcp` + WASM | extender con servidores MCP sin tocar código | Sí (puente MCP futuro) |
| `clean_room.rs` | allowlist de herramientas clean-room | Sí (política) |
| `journal` append-only | auditoría de llamadas/aprobaciones/errores | Futuro |

## 4. Hipótesis evaluadas

| # | Hipótesis | Accuracy | Latencia | Escalabilidad | Robustez | Reproducibilidad | Veredicto |
|---|---|---|---|---|---|---|---|
| H1 | Portar las 301 herramientas a Python en SWARMIND | media | alta | pobre (301 mantenimientos) | baja | media | **Rechazada** (coste O(301), duplica upstream) |
| H2 | Adoptar el protocolo (evidencia+investigación+clean-room) y **puentear** el CLI/MCP para las 301 | alta | baja (subprocess) | alta (el motor escala aparte) | media-alta (falla claro) | alta (id canónico) | **Elegida** |
| H3 | Copiar solo prompts/README al agente | baja | baja | alta | baja | baja | Rechazada (no ejecutable, sin gate) |
| H4 | Construir un sandbox OS completo (Firecracker/Job Objects) | alta | media | media | alta | media | Fuera de alcance (proyecto aparte) |

## 5. Diseño adoptado en SWARMIND

```
harness/reverse_engineering/
  canonical.py      JSON canónico + sha256 + stable_id
  evidence.py       Evidence + EvidenceLedger (JSONL, tamper check)
  investigation.py  brief/plan/hypotheses/findings/unknowns/handoff + renders
  triage.py         fingerprint O(bytes) + inventario ZIP/TAR sin extraer
  policy.py         clean-room vs deep (allow/deny por prefijo)
  bridge.py         craft-anything-cli (301 tools) -> Evidence
  cli.py            python -m harness.reverse_engineering <cmd>
```

Orden de complejidad:

- `canonical_json`: O(k log k) por objeto (k claves), O(n) en bytes; sin
  cambios de clase frente a `serde_json` del original.
- `Evidence.compute_id`: O(n) hash sobre el JSON canónico (n bytes).
- `triage.fingerprint`: O(bytes) hash + O(1) magic; `inventory_archive` O(k)
  entradas, sin descomprimir.
- `bridge`: O(1) overhead + coste del CLI externo.

Antes (estado previo de SWARMIND): la skill `reverse-engineering` era
procedimental, sin ledger verificable, sin estado durable y sin gate
clean-room/deep. Después: 29 tests adversariales, estado revisionado y puente
opcional al motor de 301 herramientas.

## 6. Gap analysis y límites

- **No se portan las 301 herramientas**: el puente exige `craft-anything-cli`
  instalado (`CRAFT_ANYTHING_CLI` o PATH). Sin él, el harness conserva triaje,
  evidencia e investigación.
- **Clean-room es una política de operaciones, no un sandbox del SO**: el motor
  externo/agente sigue actuando con los permisos del usuario.
- **No se implementa el bucle rebuild + checks** (`app_rebuild_claim_check`,
  comparación de screenshots): requiere el motor y agentes de código.
- **No hay Frida/GDB/Ghidra orquestados**: se delegan al CLI externo en Deep.
- **Canonical JSON**: se replica la semántica (orden UTF-16, escapes), no se
  garantiza igualdad byte-a-byte con la implementación Rust para floats
  exóticos; los ids son estables dentro de Python.

## 7. Fuentes leídas

- README del repo (secciones Clean room/Deep, AI, Agents, Under the hood).
- `docs/tools.md` (301 herramientas, 17 toolsets) y `docs/tool-ids.md` (esquema).
- `docs/extending.md` (seams, plugins MCP/WASM, toolsets).
- `crates/evidence/src/{lib,unknown,canonical}.rs` (modelo e id).
- `crates/engine/src/tools/investigation_tools.rs` (estado, revisiones, renders).
- `apps/craft-anything-cli/src/{main,tool_args}.rs` (CLI `<tool> --json '{...}'`,
  `--deep`/`--clean-room`, exit 0/1/2/130).
