# Spec — Cableado (wiring) de proyectos Rust/DB en Swarmind

## Outcome medible

Un proyecto Rust de base de datos (workspace Cargo con crates de
storage/query/vector) se detecta como tipo `database` (o `rust` si es
genérico) en `scripts/deploy_all.py`, y su hoja de ruta (gates G0–G3,
T1/T2/T3, FF-01..FF-12, STRIDE, política `unsafe`, bindings
PyO3/napi/C-FFI, `xtask trace`, ADRs locales) queda mapeada a módulos
concretos del harness — sin nombres privados en el código (detección
genérica por layout + keywords).

Criterio de éxito: `pytest harness/tests/test_deploy_all.py -q` en verde,
`ruff check scripts/deploy_all.py` limpio, y
`deploy_all.py --project <db> --dry-run` reportando `type=database`.

## 1. Detección de tipo (implementado)

`_detect_type(name, project_dir)` en `scripts/deploy_all.py`:

- Si existe `Cargo.toml` en la raíz → `database` cuando el nombre
  menciona db/data/store/vector/lance/kv/sql **o** el workspace declara
  miembros/dependencias de storage/query/vector (`_cargo_declares_storage`
  con tomllib + fallback a texto crudo); si no → `rust`.
- Sin `Cargo.toml` → reglas históricas por nombre (trading, healthtech,
  retail, security, general). Cargo tiene precedencia sobre el nombre.
- `discover_projects()` pasa la ruta (`_detect_type(entry.name, entry)`).
- El resto del deploy es agnóstico al tipo: `ptype` solo fluye a logs,
  plantilla README y estadísticas; skills se gobiernan por
  `.opencode/deploy.yaml` (mirror/add-only/skip) y la config propia se
  preserva por backup/restore — ningún `if ptype ==` necesita extensión.

## 2. Mapeo hoja de ruta → módulos Swarmind

| Pieza de la hoja de ruta | Módulo Swarmind (estado) | Acople |
|---|---|---|
| T1 (<90s, bloquea merge): fmt, clippy `-D warnings`, nextest, deny, audit, geiger, insta | `harness/validation/rust_gates.py::run_rust_t1` (existe) | Invocar con `repo=<raíz Rust>` desde CI/guardian; `passed=False` bloquea merge igual que cualquier gate T1 |
| Política `unsafe`: `unsafe_code` forbid/deny, `// SAFETY:`, budget ≤2/kLOC, allowlist de exenciones | `harness/security/rust_policy.py::evaluate_rust_policy` (existe) | Lee `Cargo.toml`, `deny.toml`, `Cargo.lock`, SBOM y `*.rs`; veredicto `passed` + hallazgos `archivo:línea: motivo` |
| Supply chain: 0 HIGH/CRITICAL, licencias, SBOM, secretos | `rust_policy` (checks deny/lockfile/SBOM/secretos) + `harness/validation/supply_chain_gate.py` (lado Python) | `deny`/`audit` corren en ambos: `rust_gates` (comandos cargo) y `rust_policy` (archivos, sin red) |
| STRIDE (threat modeling) | Skill `security-audit` + `routing_rules.yaml` (`security-audit` → guardian, security-engineer) | El modelo de amenazas vive en ADRs locales del proyecto Rust; el harness verifica controles vía `rust_policy` |
| SPE/GATE: spec antes de codear (edges, invariantes, BigO, I/O) | `harness/validation/cp_spec_gate.py` + `specs/task_template.md` (existen) | Todo cambio Rust abre spec con los 4 pilares; sin spec completa = sin start |
| Evidencia de fix: repro que fallaba→pasa, 0 debilitamiento de tests | `harness/validation/fix_evidence.py` (existe) | Aplica a fixes Rust igual que a Python (gate T1 determinista) |
| Anti-overfit: suite oculta | `harness/validation/heldout_suite.py` (existe) | Casos reservados para cambios Rust; `OVERFIT` si pasa lo visible y falla lo oculto |
| FF-01..FF-12 (feature flags) | `project_config.yaml` propia del proyecto + `deploy_all` backup/restore (existe) | Los flags viven en config del proyecto Rust (nunca en código Swarmind); el deploy los preserva |
| `xtask trace` (trazabilidad) | Trazas con `trace_id` estilo `mcp_executor` (existe) | Correlacionar ejecuciones Rust con spans del harness vía IDs |
| Bindings PyO3/napi/C-FFI | Skill `rust-lang` + `routing_rules.yaml` (`rust-lang` → builder, backend-engineer) | Revisión de bindings por builder/backend-engineer; `catch_unwind`/`PyErr` como invariantes de revisión |
| ADRs locales del proyecto | Convención `docs/src/es/adr/` (Swarmind) como referencia | El proyecto Rust mantiene sus ADRs; el harness solo exige ADR-0001-equivalente para decisiones irreversibles |
| Tipo `database`/`rust` en deploy | `scripts/deploy_all.py` + `.opencode/deploy.yaml` (implementado aquí) | Mirror de `.opencode/` + skills según política; config propia (`TECH_STACK=Rust`, `DOMAIN=database`) preservada |
| Enrutamiento de tareas Rust | `.opencode/config/routing_rules.yaml` (existe) | `rust-lang` → builder/backend-engineer; `data` → scientist/data-engineer; presupuestos en `token_budgets.yaml` (roles existentes, sin cambios) |

## 3. Siguientes pasos (diseño, NO implementar)

| Artefacto futuro (proyecto Rust) | Consumidor en el harness | Gate |
|---|---|---|
| Crate MCP server: tools `query`/`insert`/`traverse`/`search` + allowlist de paths + timeouts por tool | `harness/tools_sandbox/mcp_executor.py` (subproceso con timeout, validación contra schema, log con `trace_id`) | T1: cada tool responde en plazo con schema válido; T2: juez rubrica precisión de `traverse`/`search` |
| Bridge PyO3: `catch_unwind` en toda frontera, errores como `PyErr`, sin `panic!` cruzando a Python | `rust_policy.py` (extender: prohibir `panic!`/`unwrap` en crate de bindings salvo tests) + adapter tests | T1: `rust_policy` en verde; tests del bridge en `run_rust_t1` (nextest) |
| A2A agent-card (capacidades, auth, límites) | `discover_projects`/`project_config` (metadatos) + `mcp_executor` (endpoint) | T2: card válida contra schema + smoke `query`/`search` |
| Adapter contract tests: snapshots `insta` + suite YAML (query vectorial, roundtrip FFI) | `rust_gates.py::_run_insta` (ya soporta `--check` con skip si no hay snapshots) + `heldout_suite.py` (casos ocultos del adapter) | T1: `insta --check` verde; held-out: `ACCEPT` solo si todo lo oculto pasa |
| `xtask trace` → spans OTel | `mcp_executor` (propagar `trace_id`) + telemetry del harness | T3: correlación traza Rust↔harness en regresión nocturna |

Orden sugerido: (1) MCP server con 1 tool (`query`) + allowlist, (2) adapter
tests `insta` mínimos, (3) agent-card, (4) bridge PyO3 endurecido, (5) resto
de tools. Cada paso trae su spec SPE y su gate T1 antes del siguiente.
