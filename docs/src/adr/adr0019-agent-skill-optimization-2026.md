# ADR-0019: Agent & Skill Optimization 2026 — Revisión Crítica y Especialización

## Estado
**ACEPTADO** — Implementado en 2026-07-22. Commits: 3b23d43, a6bc4d9.

## Contexto
El sistema AGENTIC cuenta con 8 agentes y 11 skills desplegados en 5 proyectos. Auditoría profunda con 3 especialistas reveló:

**Problemas sistémicos críticos:**
1. **Frontmatter inconsistente** entre agentes (falta `quality` en scientist, evolve, sub-agentes)
2. **DRY/SSOT violado**: PaCoRe, LTS, Token Economics duplicados en 3+ agentes
3. **Triggers demasiado amplios**: coordinator captura palabras genéricas (`what`, `how`, `why`)
4. **Research First fuera de lugar** en guardian (debería ser "Verify First")
5. **Sub-agentes evolve sin estándares** de calidad

**Oportunidades:**
- 4 nuevos skills especializados necesarios (Rust, Architecture, UI/UX, Data Science)
- Estructura de skill efectiva según investigación Anthropic + OpenAI Agents SDK 2026

## Decisión e Implementación

### 1. Nuevos Skills Especializados (4 creados)
| Skill | Archivo | Líneas | Dominio | Especialidad |
|-------|---------|--------|---------|-------------|
| **rust-lang** | `.opencode/skills/rust-lang/SKILL.md` | 305 | systems | Ownership, async, FFI, crates |
| **architecture** | `.opencode/skills/architecture/SKILL.md` | 293 | architecture | GoF, clean/hexagonal, C4, DDD |
| **responsive-ui** | `.opencode/skills/responsive-ui/SKILL.md` | 354 | frontend | WCAG 2.2 AA/AAA, Core Web Vitals |
| **data-science** | `.opencode/skills/data-science/SKILL.md` | 390 | data | ML pipelines, GPU acceleration |

Cada skill sigue estructura óptima 2026: frontmatter completo, descripción, responsabilidades, técnicas, comandos, referencias.

### 2. Optimización de Agentes (8 revisados)
| Agente | Problema | Mejora |
|--------|----------|--------|
| **coordinator** | Triggers genéricos (`what/how/why`) | Podados a términos de orquestación |
| **builder** | Frontend duplicado (50ln) | Extraído a frontend-uiux skill |
| **scientist** | Falta `quality`, técnicas humanas (SQ3R) | Añadido quality, reemplazadas por LLM-native |
| **guardian** | Research First inadecuado, risk mgmt cuantitativo | Cambiado a "Verify First", risk a risk-execution |
| **evolve** | Falta `quality`, triggers insuficientes | Estandarizado frontmatter |
| **evolve-* (3)** | Frontmatter minimalista sin estándares | Unificado con agentes principales |

### 3. Research Web Frontera 2026
| Hallazgo | Fuente | Aplicación |
|----------|--------|------------|
| Estructura óptima de skill: 150-400 palabras | Anthropic Dec 2024 | Skills existentes ajustados |
| Think tool pattern: +54% en τ-Bench | Anthropic | Propuesto para skills complejos |
| Augmented LLM + tool definitions ACI | OpenAI Agents SDK | Tool definitions type-safe |
| Generative UI 2026 (Geeklego, 7onic, useVyre) | Múltiples fuentes | Frontend-uiux skill actualizado |
| Rust actor model con tokio + channels | Community best practices | Rust skill incluye patrones |

## Consecuencias
- **+4 skills especializados**: rust-lang, architecture, responsive-ui, data-science
- **Skills totales**: 15 (11 existentes + 4 nuevos)
- **DRY mejorado**: Teoría compartida extraíble a `paradigms/` en futura iteración
- **Triggers optimizados**: Menos falsos positivos en routing
