# Registro de Skills — AGENTIC Harness

16 skills disponibles en `.opencode/skills/`. Cada skill tiene formato dual (SKILL.md + SKILL.min.md).

| Skill | Dominio | Propósito | SKILL.md | .min.md |
|-------|---------|-----------|----------|---------|
| **evolve** | self-improvement | Meta-skill de auto-mejora continua (ASI-Evolve loop) | ✅ | ✅ |
| **hedgefund** | finance | Doctrina fundacional: todo proyecto como Hedge Fund | ✅ | ✅ |
| **quant-trading** | trading | Estrategias cuantitativas con CQE Rust | ✅ | ✅ |
| **alpha-research** | research | Investigación de alpha, factores, ML avanzado | ✅ | ✅ |
| **risk-execution** | trading | Risk management y ejecución algorítmica | ✅ | ✅ |
| **frontend-uiux** | frontend | UI/UX profesional con Generative UI 2026 (fusionado con responsive-ui) | ✅ | ✅ |
| **responsive-ui** | frontend | UI responsive, WCAG 2.2, Core Web Vitals | ✅ | ✅ |
| **rust-lang** | systems | Desarrollo Rust: ownership, async, FFI, crates | ✅ | ✅ |
| **architecture** | architecture | Arquitectura de software: GoF, hexagonal, DDD, C4 | ✅ | ✅ |
| **data-science** | data | Data Science/ML: pandas, PyTorch, GPU, feature engineering | ✅ | ✅ |
| **security-audit** | security | AppSec/DevSecOps: SAST, DAST, threat modeling, SBOM | ✅ | ✅ |
| **math-doc** | science | Documentación matemática y científica | ✅ | ✅ |
| **science-doc** | science | Documentación científica general | ✅ | ✅ |
| **legal-doc** | legal | Análisis jurídico colombiano multi-especialidad | ✅ | ✅ |
| **healthtech** | health | Salud e interoperabilidad de sistemas clínicos | ✅ | ✅ |
| **pos-retail** | retail | Punto de venta y retail | ✅ | ✅ |

## Carga de Skills
Los skills se cargan automáticamente según el dominio del proyecto:
- **Trading**: evolve, hedgefund, quant-trading, alpha-research, risk-execution, math-doc, science-doc
- **Healthtech**: evolve, hedgefund, healthtech, legal-doc, science-doc
- **Retail**: evolve, hedgefund, pos-retail, legal-doc
- **General**: evolve, hedgefund, math-doc, legal-doc, science-doc, healthtech, pos-retail, quant-trading, risk-execution

## Comandos
- `!skill load <skill>` — Carga un skill específico
- `!skill list` — Lista skills disponibles
- `!skill status` — Muestra skills activos
