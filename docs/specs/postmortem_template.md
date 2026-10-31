---
# Postmortem Blameless — Plantilla (ADR-0083)
# Un postmortem por cada fallo SEV>=2. Sin culpa: el sistema fallo, no la persona.
# Fuente: SRE (Google) + failure registry Socratic-SWE.
sev: "{{SEV-1 | SEV-2 | SEV-3}}"
date: "{{DATE}}"
task_id: "{{TASK_ID}}"
status: "draft"  # draft | action-items | done
---

# Postmortem: {{TITULO}}

## 1. Resumen (5 lineas maximo)
<!-- Que paso, impacto, duracion, deteccion. Hechos, no teorias. -->

## 2. Linea de tiempo
| Hora | Evento |
|------|--------|
| {{hh:mm}} | {{deteccion}} |
| {{hh:mm}} | {{mitigacion}} |
| {{hh:mm}} | {{resolucion}} |

## 3. Causa raiz (5 whys)
1. ¿Por que? {{respuesta 1}}
2. ¿Por que? {{respuesta 2}}
3. ¿Por que? {{respuesta 3}}
4. ¿Por que? {{respuesta 4}}
5. ¿Por que? {{causa raiz sistemica}}
<!-- Si el why #5 culpa a una persona, seguir preguntando: el sistema lo permitio. -->

## 4. Que funciono / que no
- **Detecto rapido**: {{que}}
- **Fallo**: {{que}}

## 5. Action items (dueno + fecha, sin excepcion)
| # | Accion | Dueno | Fecha | Estado |
|---|--------|-------|-------|--------|
| 1 | {{accion}} | {{dueno}} | {{fecha}} | pendiente |

## 6. Registro
- [ ] Failure en `harness/db/failures.jsonl` (WHAT+WHY+WHERE)
- [ ] Skill derivado identificado (si aplica)
- [ ] ADR actualizado (si cambio una decision)

## 7. WIP-2 + TTL + tripwire (MESA: lo sistemico se escala, nada sin dueno)
- **WIP-2**: maximo 2 improvements adoptados por mesa/sesion (resto a backlog priorizado).
- **TTL por improvement**: {{TTL_dias}} dias; vencido sin evidencia → se revierte o revalida.
- **Tripwire**: {{condicion medible que dispara revision}} (si se dispara, reabrir postmortem).
- **Dueno + fecha**: toda mejora adoptada sale con dueno y TTL (0 sin dueno a 30d).
