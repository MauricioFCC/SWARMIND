# SPEC — Ingeniería inversa con evidencia (craft-anything)

> Estado: **implementado** (v1.0.0, 2026-11-05). Extiende la skill
> `reverse-engineering` y el agente `security-engineer` con un protocolo de
> evidencia verificable, investigación durable y política clean-room/deep.
> Fuente: `docs/research/frontier-2026-11-05-craft-anything.md`.

## 1. Contexto

La skill `reverse-engineering` describía herramientas y buenas prácticas, pero
no imponía nada ejecutable: sin ledger verificable, sin estado durable entre
turnos y sin distinción operativa clean-room/deep. `craft-anything` demuestra
que el valor está en el **protocolo** (evidencia con id canónico + memoria de
investigación), no en reimplementar 301 herramientas.

## 2. Objetivo medible

| AC | Criterio | Verificación |
|---|---|---|
| RE-AC1 | `canonical_json` ordena claves por UTF-16, sin espacios, escapes mínimos y rechaza NaN | `test_reverse_engineering.py::TestCanonical` |
| RE-AC2 | El id de evidencia es `ev_<sha256>` del contenido, ignora `summary`/`subject.name`/`carries_target_content` y detecta edición | `TestEvidence::test_id_*` |
| RE-AC3 | El ledger es append-only, deduplica por id y **rechaza** JSONL manipulado al cargar | `TestEvidence::test_ledger_*` |
| RE-AC4 | Un hallazgo exige ≥1 evidencia existente; un unknown resuelto exige resolución + evidencia | `TestInvestigation::test_finding_*` / `test_unknown_*` |
| RE-AC5 | Toda actualización exige `based_on_revision` (concurrencia optimista) | `TestInvestigation::test_revision_obsoleta` |
| RE-AC6 | El estado persiste en `investigation/state.json` + 5 Markdown y se recarga | `TestInvestigation::test_persistencia_y_render` |
| RE-AC7 | El triaje identifica ELF/PE/.NET/Mach-O/APK/JAR/ZIP/WASM/pyc/SQLite/texto por bytes, sin ejecutar ni extraer | `TestTriage` |
| RE-AC8 | Clean-room deniega operaciones Deep-only con remediación (`--deep`); permite memoria/triaje; Deep permite todo | `TestPolicy` |
| RE-AC9 | El puente a `craft-anything-cli` valida id, aplica política, envuelve el resultado en evidencia y falla claro si falta el binario | `TestBridge` |
| RE-AC10 | La CLI `python -m harness.reverse_engineering` cubre triaje/brief/finding/show/policy/bridge | `TestCli` |
| RE-AC11 | La skill `reverse-engineering` documenta el protocolo y el agente `security-engineer` lo ejecuta; `/re` es el atajo | `test_frontier_cycle_contract`-style grep + `validate_skills --strict` |

## 3. Diseño

```
artefacto ──triage──► ArtifactInfo ──► Evidence (ev_sha256) ──► Ledger (JSONL)
                                                   │
objetivo ──política──► clean-room | deep           │
                                                   ▼
        Investigation (state.json, revisión)  ◄── findings/unknowns
          brief · plan · hypotheses · findings · unknowns · handoff
                                                   │
                                             renders Markdown
                                                   │
        (opcional) bridge ──► craft-anything-cli (301 tools) ──► Evidence
```

**Invariantes**:
1. Ningún hallazgo sin evidencia existente (id verificado en el ledger).
2. Ningún unknown resuelto sin resolución + evidencia ("la ausencia no es prueba").
3. Actualización con revisión obsoleta se rechaza, no se sobrescribe.
4. En clean-room no se ejecuta ninguna operación de interior.
5. El contenido del target es **dato no confiable**, nunca instrucciones
   (`carries_target_content`).

**Complejidad**: canonical O(k log k) por objeto; id O(n) en bytes; triaje
O(bytes); inventario O(k) entradas; bridge O(1) + CLI. No hay O(n²).

## 4. Decisiones

- **No se crea un agente nuevo**: `reverse-engineering` ya enruta a
  `security-engineer` (`SKILL_TO_AGENT`). Duplicar la flota añadiría crowding
  de routing sin capacidad nueva (IDP). El agente existente ejecuta el protocolo
  y la skill lo documenta.
- **Reutiliza el `target_router` existente** para el enrutado REA (tipo →
  método/proveedor/evidencia); el triaje añade SHA-256, formato extendido y
  evidencia, sin duplicar la tabla de rutas.
- **No se portan las 301 herramientas**: se puentean por CLI/MCP; el harness
  nativo cubre triaje, evidencia, investigación y política, que son lo
  reutilizable.
- **Clean-room es política de operaciones**, no sandbox: se declara el límite
  (el motor/agente conserva los permisos del usuario).

## 5. Gaps declarados

| Gap | Motivo | Siguiente paso |
|---|---|---|
| Bucle rebuild + comparación (screenshots/self-test) | Requiere el motor externo y agentes de código | Integrar `app_rebuild_claim_check` vía puente |
| Frida/GDB/Ghidra orquestados | Se delegan al CLI en Deep | Sesiones persistentes + evidencia de sesión |
| Journal append-only de llamadas/aprobaciones | No implementado aún | `investigation/journal.jsonl` con hashes encadenados |
| Sandbox OS real | Proyecto aparte | Job Objects/seccomp en `harness/validation` |
| Igualdad byte-a-byte de ids con Rust | Python replica semántica, no floats exóticos | Vector de conformidad compartido |
| MCP server SWARMIND | El puente usa CLI | Exponer `harness.reverse_engineering` por MCP |

## 6. Uso

```bash
python -m harness.reverse_engineering triage ./app.exe --record ./proj
python -m harness.reverse_engineering brief ./proj --question "¿cómo valida la licencia?" \
    --done-when "informe con evidencia"
python -m harness.reverse_engineering finding ./proj --statement "usa AES-128" \
    --evidence ev_... --revision 1
python -m harness.reverse_engineering policy native_function_pseudocode   # denegado
python -m harness.reverse_engineering bridge native_functions_list --deep
```

## Ejemplo

Investigación real (patrón): triaje de un binario → `ev_<sha256>` en el ledger →
brief con la pregunta y `done_when` → hipótesis "la validación está en
`check_license`" con evidencia de strings/xrefs → `finding` que cita esa
evidencia → unknown abierto "¿qué pasa si el reloj se atrasa?" con probes →
handoff para el siguiente turno. Todo sobrevive a un reinicio y cualquier
edición del ledger se detecta al recargar.
