# Spec — Paquete de Revisión Ciega (EGM) con gates deterministas

> Estado: **nueva** (2026-11-19, ciclo frontera FR-0010) — Dueño:
> `harness/validation` — Frontera: 2026-11.
> Research: `docs/research/frontier-2026-11-19-harness-policies.md`.

## 1. Objetivo

Producir un paquete autocontenido para que un revisor (humano o agente) juzgue
un cambio **sin ver la conversación del autor**, con los criterios de aceptación
delante y con gates deterministas ejecutados antes de cualquier juicio de
modelo.

## 2. Problema

- `cross_review` cambia de familia de modelo, pero el revisor sigue recibiendo
  el contexto del autor: hereda sus puntos ciegos (EGM).
- `vibe_review_gate` recibe solo el diff, pero no la intención (spec) ni un
  checklist derivado de los ACs.
- Un prompt de revisión puede filtrar secretos o rutas personales del diff a
  un tercero; el escaneo actual cubre el repo, no el prompt.
- Sin gates previos, un juez de modelo puede "aprobar" un diff con secretos.

## 3. Diseño

Módulo `harness/validation/blind_review.py` (sin red, sin modelo, sin I/O):

| Elemento | Contrato |
|---|---|
| `extract_acceptance_criteria(spec_md)` | Ids `AC-*` con texto, deduplicados por id, orden de aparición, tope 50; fallback a la sección "Criterios de aceptación". |
| `redact(text)` | Secretos → `<redacted:tipo>`; rutas personales → `<user>`; devuelve `(texto, redacciones)`. |
| `build_blind_packet(spec_md, diff, *, max_diff_chars, max_files)` | `BlindPacket` frozen con gates; `ValueError` con `WHAT+WHY+WHERE` si spec/diff vacíos o límites inválidos. |
| `render_markdown(packet)` | Markdown determinista: sin timestamps, sin historial, con tabla de gates, ACs y diff redactado. |

Gates (en orden):

1. `spec_has_acceptance_criteria` — al menos un AC extraído.
2. `no_secrets` — ningún patrón de secreto en el diff original.
3. `no_personal_paths` — ninguna ruta con nombre de usuario en el diff original.
4. `diff_within_budget` — el diff no se truncó (si se trunca, se marca
   explícitamente y el paquete queda bloqueado).
5. `scope_files` — archivos tocados `<= max_files` (anti scope-creep).

`approved_for_review = all(gate.passed)`. El truncado nunca es silencioso.

## 4. Criterios de aceptación

- **AC-BR1** — Dada una spec con `AC-1`/`AC-2`, `extract_acceptance_criteria`
  devuelve ambos textos en orden y sin duplicados (aunque el id se repita).
- **AC-BR2** — Un diff con `AKIA`/`sk-`/`ghp_`/PEM falla `no_secrets`, se
  redacta a `<redacted:tipo>` en el render y no se aprueba.
- **AC-BR3** — Un diff con `C:\Users\<nombre>\...` o `/home/<nombre>/...`
  falla `no_personal_paths` y el render sustituye el nombre por `<user>`; los
  nombres de ejemplo (`alice`, `example`, `test`, `runner`) se redactan pero no
  bloquean, porque no identifican a una persona real.
- **AC-BR4** — Un diff mayor que `max_diff_chars` se trunca en un salto de
  línea, incluye `[TRUNCADO: N caracteres omitidos]` y no se aprueba.
- **AC-BR5** — Un diff con más de `max_files` cabeceras `diff --git` falla
  `scope_files`.
- **AC-BR6** — Spec o diff vacíos lanzan `ValueError` cuyo mensaje contiene
  `WHAT:`, `WHY:` y `WHERE:`.
- **AC-BR7** — `render_markdown` de la misma entrada es idéntico byte a byte
  (determinismo) y no contiene marcas de tiempo ni historial de conversación.
- **AC-BR8** — CLI `scripts/blind_review.py --spec <spec> --diff <archivo>`
  imprime el paquete y devuelve exit 0 si está aprobado, 1 si no.

## 5. Propiedades (PBT)

- **P1 (idempotencia de redacción)**: `redact(redact(x)) == redact(x)` para
  cualquier texto generado.
- **P2 (monotonía de gates)**: añadir un secreto o una ruta personal a un diff
  aprobado lo vuelve no aprobado (nunca al revés).
- **P3 (truncado acotado)**: `len(packet.diff) <= max_diff_chars + len(marca)`.

## 6. Complejidad

- Tiempo: `O(|spec| + |diff|)` (6 regex lineales + 1 `splitlines`).
- Memoria: `O(|spec| + |diff|)` (el paquete guarda el diff redactado).
- Sin llamadas a red, modelo o disco (la CLI es el único borde de I/O).

## 7. Integración y política

- Antes de pedir revisión a otro agente: ejecutar la CLI y adjuntar el
  markdown generado. El revisor **no** recibe la conversación.
- El autor no aprueba su propio diff (maker-checker; Binnacle/EGM).
- Los gates deterministas bloquean antes de cualquier veredicto de modelo.
- Coste: la política de fan-out exige justificar el overhead (~7× tokens en
  equipos de agentes según el reporte citado) con una mejora esperada.

## 8. Riesgos

- Falsos positivos de secretos en ejemplos/documentación: el gate bloquea el
  paquete; se resuelve marcando el ejemplo como `AKIA...` ficticio o excluyendo
  el fichero del diff de revisión. Se prefiere fallar cerrado.
- Un diff que **introduzca** rutas personales reales o credenciales (aunque
  sean de ejemplo) se bloquea: es el coste deliberado de fallar cerrado. Los
  fixtures del propio gate se construyen por partes para no dispararse a sí
  mismos.
- El paquete no sustituye la revisión humana de diseño; la acota.
- Los patrones de secretos son heurísticos: no detectan todos los formatos
  (misma limitación reportada por Apiiro: 215/1 122 indetectables).
