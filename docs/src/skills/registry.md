# Registro de Skills — AGENTIC Harness

**31 skills** disponibles en `.opencode/skills/`. Cada skill tiene formato dual: `SKILL.md` (completo) y `SKILL.min.md` (minificado).

## Tabla Completa de Skills

### ?? Tecnología y Desarrollo
| Skill | Dominio | Propósito |
|-------|---------|-----------|
| **architecture** | architecture | Patrones GoF, Clean/Hexagonal, DDD, C4, ADRs |
| **rust-lang** | systems | Rust: ownership, async, FFI con Python, crates, optimización |
| **frontend-uiux** | frontend | Generative UI 2026, design tokens, A2UI/OpenUI, WCAG 2.2 |
| **responsive-ui** | frontend | UI responsive, mobile-first, Core Web Vitals, accesibilidad axe-core |
| **data-science** | data | ML pipelines, PyTorch/JAX, GPU acceleration, feature engineering |
| **devops-infra** | devops | CI/CD, Docker, Kubernetes, Terraform, monitoreo, OpenTelemetry |

### ?? Seguridad
| Skill | Dominio | Propósito |
|-------|---------|-----------|
| **security-audit** | security | SAST, DAST, threat modeling (STRIDE), SBOM, compliance OWASP/SOC2 |

### ?? Negocio y Gestión
| Skill | Dominio | Propósito |
|-------|---------|-----------|
| **hedgefund** | finance | Doctrina hedge fund: riesgo/reward, capital allocation, stop-loss |
| **business-strategy** | business | DOFA, Porter, Canvas, OKR, ROI, planificación estratégica |
| **project-management** | management | Scrum, Kanban, WBS, riesgos, estimaciones, stakeholders |
| **communication** | communication | Escritura ejecutiva, presentaciones, storytelling, negociación |

### ?? Finanzas y Trading
| Skill | Dominio | Propósito |
|-------|---------|-----------|
| **quant-trading** | trading | Estrategias cuantitativas CQE Rust, backtesting, execution |
| **risk-execution** | trading | Risk management, position sizing, market making, TCA |
| **behavioral-economics** | economics | Teoría de juegos, sesgos, incentivos, nudges |

### ?? Ciencia e Investigación
| Skill | Dominio | Propósito |
|-------|---------|-----------|
| **alpha-research** | research | Factor research, ML, feature engineering, validación estadística |
| **math-doc** | academic | Documentos matemáticos, LaTeX, proofs, estadística |
| **science-doc** | academic | Documentos científicos, peer review, revisiones sistemáticas |
| **physical-sciences** | science | Física, química, biología, método científico experimental |

### ?? Humanidades y Ciencias Sociales
| Skill | Dominio | Propósito |
|-------|---------|-----------|
| **psychology** | psychology | Psicología cognitiva, organizacional, del aprendizaje, neurociencia |
| **education** | education | Diseño instruccional (ADDIE), Bloom, andragogía, microlearning |
| **ethics** | philosophy | Ética de IA, alineamiento de valores (Floridi, Russell), gobernanza |
| **linguistics** | linguistics | Lingüística cognitiva, semiótica, pragmática, análisis del discurso |
| **sociology** | sociology | Dinámicas de grupo, teoría de redes, cultura digital, antropología |
| **creative-design** | design | Design Thinking, branding, prototipado, ideación creativa |

### ?? Salud y Legal
| Skill | Dominio | Propósito |
|-------|---------|-----------|
| **healthtech** | health | Sistemas clínicos, interoperabilidad, HIPAA, FHIR |
| **legal-doc** | legal | Análisis jurídico colombiano multi-especialidad, RTF+C |

### ?? Retail
| Skill | Dominio | Propósito |
|-------|---------|-----------|
| **pos-retail** | retail | Punto de venta, operaciones retail, inventario, facturación |

### ?? Sostenibilidad
| Skill | Dominio | Propósito |
|-------|---------|-----------|
| **sustainability** | environment | ESG, huella de carbono, reportes GRI/SASB/TCFD, economía circular |

### ?? Meta
| Skill | Dominio | Propósito |
|-------|---------|-----------|
| **meta-ads-optimizer** | marketing | Optimizacion Meta Ads con 12 sub-skills (BOAD, ShapleyFlow, MetaClaw) |
| **evolve** | meta | Auto-mejora continua, ciclo ASI-Evolve (Learn?Design?Experiment?Analyze?Deploy) |

## Carga de Skills por Proyecto

Los skills se despliegan selectivamente según el tipo de proyecto:

| Tipo | Skills |
|------|--------|
| **Trading** (CQE, Onyx) | evolve, hedgefund, quant-trading, alpha-research, risk-execution, math-doc, science-doc |
| **Healthtech** (HC) | evolve, hedgefund, healthtech, legal-doc, science-doc |
| **Retail** (PDV) | evolve, hedgefund, pos-retail, legal-doc |
| **General** (Hermes) | evolve, hedgefund, math-doc, legal-doc, science-doc, healthtech, pos-retail, quant-trading, risk-execution |

## Carga Manual de Skills

```bash
!skill load rust-lang          # Carga skill de Rust
!skill load frontend-uiux      # Carga skill de UI/UX
!skill list                    # Lista todos los skills disponibles
!skill status                  # Muestra skills activos en la sesión
```

## Formato de Skills

Cada skill tiene dos archivos:

- **`SKILL.md`** — Versión completa con frontmatter YAML, descripción, responsabilidades, técnicas, comandos y referencias (~200-400 líneas)
- **`SKILL.min.md`** — Versión minificada con solo frontmatter + responsabilidades esenciales + comandos (~15-20 líneas). Usada para carga rápida cuando el contexto es limitado.

### Estructura de un SKILL.md

```yaml
---
name: rust-lang
domain: systems
description: "Experto en Rust..."
version: 1.0.0
project_agnostic: true
inherit:
  - core/base_principles.md
variables:
  - RUST_TOOLCHAIN: stable, nightly
  - ASYNC_RUNTIME: tokio, smol, async-std
---
```

Luego incluye secciones de: Descripción, Responsabilidades, Técnicas, Comandos y Referencias.

