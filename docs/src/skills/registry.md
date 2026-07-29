# Registro de Skills — AGENTIC Harness

**30 skills** disponibles en `.opencode/skills/`. Cada skill tiene formato dual: `SKILL.md` (completo) y `SKILL.min.md` (minificado). Cobertura: 100% con ambos formatos.

## Tabla Completa de Skills

### Tecnología y Desarrollo
| Skill | Dominio | Propósito |
|-------|---------|-----------|
| **architecture** | software | Patrones GoF, Clean/Hexagonal, DDD, C4, ADRs, decisión arquitectónica |
| **rust-lang** | systems | Rust: ownership, async, FFI con Python, crates, optimización systems-level |
| **frontend-uiux** | frontend | Generative UI 2026, design tokens, A2UI/OpenUI, WCAG 2.2, StyleSeed |
| **responsive-ui** | frontend | UI responsive, mobile-first, Core Web Vitals, accesibilidad axe-core |
| **data-science** | data | ML pipelines, PyTorch/JAX, GPU acceleration, feature engineering, validación estadística |
| **devops-infra** | devops | CI/CD, Docker, Kubernetes, Terraform, monitoreo, OpenTelemetry, observabilidad |

### Seguridad
| Skill | Dominio | Propósito |
|-------|---------|-----------|
| **risk-intelligence** | risk | Identificacion de riesgos emergentes (CRO Forum 2026) |
| **security-audit** | security | SAST, DAST, threat modeling (STRIDE), SBOM, compliance OWASP/SOC2/ISO27001 |

### Negocio y Gestión
| Skill | Dominio | Propósito |
|-------|---------|-----------|
| **hedgefund** | finance | Doctrina hedge fund: riesgo/reward, capital allocation, stop-loss, institutional risk |
| **business-strategy** | business | DOFA, Porter, Canvas, OKR, ROI, planificación estratégica, KPIs de negocio |
| **project-management** | management | Scrum, Kanban, WBS, riesgos, estimaciones, comunicación con stakeholders |
| **communication** | communication | Escritura ejecutiva, presentaciones, storytelling, negociación, liderazgo |

### Finanzas y Trading
| Skill | Dominio | Propósito |
|-------|---------|-----------|
| **quant-trading** | trading | Estrategias cuantitativas CQE Rust, backtesting, execution, generación de alpha |
| **risk-execution** | trading | Risk management, position sizing, market making, TCA, execution algorítmica |
| **behavioral-economics** | economics | Teoría de juegos, sesgos cognitivos, incentivos, nudges, toma de decisiones |

### Ciencia e Investigación
| Skill | Dominio | Propósito |
|-------|---------|-----------|
| **alpha-research** | research | Factor research, ML avanzado, feature engineering, validación estadística con CQE Rust |
| **math-doc** | academic | Documentos matemáticos, LaTeX, proofs, estadística, notación formal |
| **science-doc** | academic | Documentos científicos, peer review, revisiones sistemáticas, paper drafting |
| **physical-sciences** | science | Física, química, biología, método científico experimental, análisis de datos |

### Humanidades y Ciencias Sociales
| Skill | Dominio | Propósito |
|-------|---------|-----------|
| **psychology** | psychology | Psicología cognitiva, organizacional, del aprendizaje, neurociencia aplicada |
| **education** | education | Diseño instruccional (ADDIE), Bloom, andragogía, microlearning, evaluación educativa |
| **ethics** | philosophy | Ética de IA, alineamiento de valores, marcos éticos para agentes autónomos |
| **linguistics** | linguistics | Lingüística cognitiva, semiótica, pragmática, análisis del discurso, PLN teórico |
| **sociology** | sociology | Dinámicas de grupo, teoría de redes, cultura digital, antropología, sociología del conocimiento |
| **creative-design** | design | Design Thinking, branding, prototipado, ideación, identidad visual, experiencia de usuario |

### Salud y Legal
| Skill | Dominio | Propósito |
|-------|---------|-----------|
| **healthtech** | health | Sistemas clínicos, interoperabilidad, HIPAA, FHIR, historia clínica electrónica |
| **legal-doc** | legal | Análisis jurídico colombiano multi-especialidad, RTF+C, argumentación legal |

### Retail
| Skill | Dominio | Propósito |
|-------|---------|-----------|
| **pos-retail** | retail | Punto de venta, operaciones retail, inventario, facturación, comercio unificado |

### Sostenibilidad
| Skill | Dominio | Propósito |
|-------|---------|-----------|
| **sustainability** | environment | ESG, huella de carbono, reportes GRI/SASB/TCFD, economía circular, cambio climático |

### Meta
| Skill | Dominio | Propósito |
|-------|---------|-----------|
| **meta-ads-optimizer** | marketing | Optimización Meta Ads con 12 sub-skills (BOAD, ShapleyFlow, MetaClaw, MuTON) |
| **evolve** | meta | Auto-mejora continua, ciclo ASI-Evolve (Learn → Design → Experiment → Analyze → Deploy) |

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

