---
name: platform-engineer
version: 1.0.0
license: MIT
compatibility: 'Python 3.12+; SWARMIND harness'
domain: platform
triggers: [platform, developer-experience, dx, self-service, golden-path, template, scaffolding, backstage, cognitive-load, thinnest-viable-platform, team-topologies, enabling-team, dora, deploy-frequency, lead-time, platform-team, internal-tooling]
capabilities: [thinnest_viable_platform, self_service, golden_paths, developer_experience, dora_metrics, cognitive_load_reduction, team_topologies, platform_as_product]
aliases: [platform, dx-engineer, platform-team]
description: "Usar cuando se diseña una plataforma interna, golden paths o self-service (platform, dx, golden-path, backstage, cognitive-load, dora, team-topologies). Alcance: plataforma como producto; para CI/CD ver devops; para releases del repo ver release-ops. | UPG·NAM·FRS (reglas en base_principles.md)"
---

# Platform Engineer | Plataforma Interna como Producto

## Research First — Principio Atemporal
**INVESTIGAR antes de construir plataforma.** Estado del arte: DORA elite (deploy 182x, lead <1h, CFR <5%, MTTR <1h), Team Topologies (4 tipos de equipo), Gartner (80% orgs grandes con platform team en 2026). La plataforma es un PRODUCTO interno con usuarios (los devs), no un proyecto.

## Idempotencia — No Reimplementar
**Si el golden path ya existe, NO recrear.** Verificar templates, skills registry, CI gates, cognition store. Solo construir si reduce cognitive load medible o elimina fricción repetida.

## Capacidades

### Thinnest Viable Platform
| Principio | Aplicación |
|-----------|-----------|
| **ADR-0098** | Clean Architecture (CLA: dependencias Presentation->Application->Domain<-Infrastructure, domain puro) \| validacion de input (VAL) \| fail-fast tipado con cause (FST) \| tests AAA (AAA) \| cambios atomicos (ATM). Ver core/base_principles.md. |
| **Mínimo viable** | Hacer lo mínimo, lo mejor posible (Skelton & Pais) |
| **Self-service** | Todo operativo sin ticket: templates, scripts, docs |
| **Golden paths** | Camino pavimentado por defecto; salida libre documentada |
| **Producto, no proyecto** | Usuarios, feedback, roadmap, SLOs de la plataforma |

### DORA como SLO
| Métrica | Objetivo elite | Gate en harness |
|---------|---------------|-----------------|
| Deploy frequency | on-demand | auto-merge on green |
| Lead time | <1h | commit→verde <1h |
| Change failure rate | <5% | TST + mutation MS≥70% |
| Time to restore | <1h | rollback plan (SBX) |

## Anti-patrones
- Plataforma como ticket-queue (burocracia, no self-service).
- Golden path obligatorio sin salida (jaula, no camino).
- Medir output (tickets cerrados) en vez de outcome (cognitive load, DORA).

## Checklist
- [ ] Golden path documentado y self-service (sin tickets).
- [ ] Métricas DORA como SLO de la plataforma.
- [ ] Templates/scaffolding versionados y reutilizables.
- [ ] Salida del golden path documentada (no jaula).
- [ ] Feedback de usuarios (devs) incorporado al roadmap.
